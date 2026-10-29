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
"""
from __future__ import annotations
import hashlib
import hmac
import logging
import os
from typing import Iterator

GRAPH = "https://graph.facebook.com/v20.0"
log = logging.getLogger(__name__)


def configured() -> bool:
    return bool(os.environ.get("HAANJI_WA_TOKEN") and os.environ.get("HAANJI_WA_PHONE_ID"))


def status() -> dict:
    """What the UI shows: whether a real number is connected, and which."""
    if not configured():
        return {"configured": False, "number": None}
    shown = os.environ.get("HAANJI_WA_DISPLAY_NUMBER")
    if not shown:
        shown = "…" + os.environ.get("HAANJI_WA_PHONE_ID", "")[-4:]
    return {"configured": True, "number": shown}


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


async def _post(body: dict) -> bool:
    import httpx
    to = str(body.get("to", ""))
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{GRAPH}/{os.environ['HAANJI_WA_PHONE_ID']}/messages",
                headers={"Authorization": f"Bearer {os.environ['HAANJI_WA_TOKEN']}"},
                json={"messaging_product": "whatsapp", **body})
            if r.status_code >= 400:
                log.warning("whatsapp send to …%s failed: %s %s", to[-4:], r.status_code, r.text[:200])
                return False
            return True
    except Exception as e:                       # noqa: BLE001 — see send_text
        log.warning("whatsapp send to …%s failed: %s", to[-4:], e)
        return False


async def send_text(to: str, text: str) -> bool:
    """Send one free-form text message. Failures are logged and reported as
    False, never raised: the webhook must still answer Meta with a 200 or
    the delivery is retried.

    Meta accepts free text only inside the 24-hour window after the
    customer's last message. Outside it (a login code, a reminder, the
    evening digest) use :func:`send_template`."""
    if not configured():
        return False
    return await _post({"to": to, "type": "text", "text": {"body": text}})


def template_name(kind: str) -> str | None:
    """The approved template for a kind of message, from the environment:
    HAANJI_WA_TEMPLATE_OTP, _REMINDER, _RECEIPT, _DIGEST, _OUTREACH."""
    return os.environ.get(f"HAANJI_WA_TEMPLATE_{kind.upper()}") or None


async def send_template(to: str, kind: str, params: list[str], *, fallback_text: str | None = None,
                        language: str | None = None) -> bool:
    """Send an approved template message (works outside the 24-hour window).
    Without a template configured for ``kind``, falls back to free text,
    which Meta will accept only if the customer wrote recently."""
    if not configured():
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
