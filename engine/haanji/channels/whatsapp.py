"""Meta WhatsApp Cloud API adapter (real mode).

The simulator at /whatsapp needs none of this. To go live, the owner follows
docs/whatsapp-setup.md: a Meta app with the WhatsApp product, then

    HAANJI_WA_TOKEN           access token
    HAANJI_WA_PHONE_ID        the phone number id
    HAANJI_WA_VERIFY_TOKEN    whatever was typed into Meta's webhook form
    HAANJI_WA_APP_SECRET      so deliveries can be checked for Meta's signature
    HAANJI_WA_PACK            which pack answers (default: the engine's default)

in the environment, and https://<engine>/wa/webhook registered as the webhook.
The handler in server.py then feeds real messages through the exact code path
the simulator uses.

Until Meta verifies the business, the Twilio Sandbox (twilio_whatsapp.py)
carries the same messages: with Meta not set up and Twilio set up, every
send below goes through Twilio, and a template becomes its fallback text
(the Sandbox has no custom templates).
"""
from __future__ import annotations
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Iterator

from . import twilio_whatsapp as twilio

GRAPH = "https://graph.facebook.com/v20.0"
log = logging.getLogger(__name__)


def meta_configured() -> bool:
    return bool(os.environ.get("HAANJI_WA_TOKEN") and os.environ.get("HAANJI_WA_PHONE_ID"))


def provider() -> str:
    """meta, twilio, or none: Meta's own API when it is set up, else Twilio."""
    return "meta" if meta_configured() else "twilio" if twilio.configured() else "none"


def configured() -> bool:
    """A real WhatsApp number is connected, through either provider."""
    return provider() != "none"


# The last time Meta refused a send, for the operator: when, to whom (last
# four digits), the HTTP status and Meta's own error code and message. The
# access token never appears in Meta's error, and is never stored here.
LAST_SEND: dict[str, Any] = {}


def _remember(to: str, ok: bool, status_code: int | None = None, body: str = "") -> None:
    if ok:
        LAST_SEND.update({"ok_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        return
    code = message = None
    try:
        err = (json.loads(body) or {}).get("error") or {}
        code, message = err.get("code"), err.get("message")
    except (ValueError, AttributeError):
        message = body[:160] or None
    LAST_SEND["error"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "to": "…" + to[-4:],
                          "status": status_code, "code": code, "message": (message or "")[:200]}


def status() -> dict:
    """What the UI shows: whether a real number is connected, and which, and
    (for the operator) the last send that Meta refused."""
    if provider() == "twilio":
        return twilio.status()
    if not meta_configured():
        return {"configured": False, "number": None, "provider": "none"}
    shown = os.environ.get("HAANJI_WA_DISPLAY_NUMBER")
    if not shown:
        shown = "…" + os.environ.get("HAANJI_WA_PHONE_ID", "")[-4:]
    out: dict[str, Any] = {"configured": True, "provider": "meta", "number": shown}
    if LAST_SEND:
        out["last_send"] = dict(LAST_SEND)
    return out


def extract_incoming(payload: dict) -> Iterator[tuple[str, str, str]]:
    """Yield (message id, sender phone, text) for every text message in a
    webhook delivery. Status updates and media are ignored."""
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            for msg in (change.get("value", {}) or {}).get("messages", []) or []:
                if msg.get("type") == "text":
                    yield msg.get("id", ""), msg["from"], msg["text"]["body"]


def verify_signature(secret: str, raw: bytes, header: str | None) -> bool:
    """Meta signs every delivery: X-Hub-Signature-256 = sha256=HMAC(app secret, body)."""
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


def receiving_phone_id(payload: dict) -> str | None:
    """The phone number id the customer wrote to (``metadata.phone_number_id``
    in the delivery). Replying from that number, not from whatever
    HAANJI_WA_PHONE_ID says, is what keeps a reply in the same chat: a test
    number's allowed-recipient list belongs to that number."""
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            pid = ((change.get("value", {}) or {}).get("metadata", {}) or {}).get("phone_number_id")
            if pid:
                return str(pid)
    return None


def note_statuses(payload: dict) -> int:
    """Meta reports what became of a sent message later, in a delivery of its
    own: sent, delivered, read, or failed with an error code. A 200 from the
    send only means "accepted". Keep the latest, for the operator."""
    seen = 0
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            for st in (change.get("value", {}) or {}).get("statuses", []) or []:
                seen += 1
                err = (st.get("errors") or [{}])[0]
                LAST_SEND["delivery"] = {
                    "status": st.get("status"), "to": "…" + str(st.get("recipient_id", ""))[-4:],
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(st.get("timestamp") or time.time()))),
                    **({"code": err.get("code"), "title": err.get("title"),
                        "detail": ((err.get("error_data") or {}).get("details") or err.get("message") or "")[:200]}
                       if st.get("status") == "failed" else {})}
    return seen


def note_incoming(phone_id: str | None) -> None:
    """For the operator: whether deliveries arrive on the configured number."""
    if phone_id:
        LAST_SEND["incoming_on"] = "…" + phone_id[-4:]
        LAST_SEND["incoming_matches_config"] = phone_id == os.environ.get("HAANJI_WA_PHONE_ID", "")


async def _post(body: dict, phone_id: str | None = None) -> bool:
    import httpx
    to = str(body.get("to", ""))
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{GRAPH}/{phone_id or os.environ['HAANJI_WA_PHONE_ID']}/messages",
                headers={"Authorization": f"Bearer {os.environ['HAANJI_WA_TOKEN']}"},
                json={"messaging_product": "whatsapp", **body})
            if r.status_code >= 400:
                log.warning("whatsapp send to …%s failed: %s %s", to[-4:], r.status_code, r.text[:200])
                _remember(to, False, r.status_code, r.text)
                return False
            _remember(to, True)
            return True
    except Exception as e:                       # noqa: BLE001 — see send_text
        log.warning("whatsapp send to …%s failed: %s", to[-4:], e)
        _remember(to, False, None, type(e).__name__)
        return False


async def send_text(to: str, text: str, phone_id: str | None = None) -> bool:
    """Send one free-form text message. Failures are logged and reported as
    False, never raised: the webhook must still answer Meta with a 200 or
    the delivery is retried.

    Meta accepts free text only inside the 24-hour window after the
    customer's last message. Outside it (a login code, a reminder, the
    evening digest) use :func:`send_template`."""
    if provider() == "twilio":
        return await twilio.send_text(to, text, status_callback=_twilio_status_url())
    if not meta_configured():
        return False
    return await _post({"to": to, "type": "text", "text": {"body": text}}, phone_id)


def template_name(kind: str) -> str | None:
    """The approved template for a kind of message, from the environment:
    HAANJI_WA_TEMPLATE_OTP, _REMINDER, _RECEIPT, _DIGEST, _OUTREACH."""
    return os.environ.get(f"HAANJI_WA_TEMPLATE_{kind.upper()}") or None


async def send_template(to: str, kind: str, params: list[str], *, fallback_text: str | None = None,
                        language: str | None = None) -> bool:
    """Send an approved template message (works outside the 24-hour window).
    Without a template configured for ``kind``, falls back to free text,
    which Meta will accept only if the customer wrote recently. Through
    Twilio it is always the fallback text."""
    if provider() == "twilio":
        return await send_text(to, fallback_text) if fallback_text else False
    if not meta_configured():
        return False
    name = template_name(kind)
    if not name:
        return await send_text(to, fallback_text) if fallback_text else False
    components = []
    if params:
        components.append({"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in params]})
    return await _post({"to": to, "type": "template",
                        "template": {"name": name, "language": {"code": language or os.environ.get("HAANJI_WA_TEMPLATE_LANG", "en")},
                                     "components": components}})


def _twilio_status_url() -> str | None:
    """Where Twilio reports what became of a message, on a public server."""
    base = (os.environ.get("HAANJI_PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
    return f"{base}/wa/twilio/status" if base.startswith("https://") else None
