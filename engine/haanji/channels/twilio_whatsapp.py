"""WhatsApp through Twilio (the free Sandbox, or a Twilio-approved sender).

Meta's own Cloud API (channels/whatsapp.py) needs a verified business. Until
then the Twilio Sandbox carries real WhatsApp messages: each tester sends
"join <two words>" to Twilio's number once, and the Sandbox forwards their
messages to HaanJi and HaanJi's replies to them.

    HAANJI_TWILIO_ACCOUNT_SID   the account (AC…)
    HAANJI_TWILIO_AUTH_TOKEN    its auth token (also checks Twilio's signature)
    HAANJI_TWILIO_WA_FROM       the sender, e.g. whatsapp:+14155238886 (the Sandbox)
    HAANJI_TWILIO_WA_JOIN       the Sandbox's join phrase, e.g. "join able-tiger"

In the Twilio console, Messaging → Try it out → WhatsApp → Sandbox settings,
"When a message comes in" is https://<engine>/wa/twilio (POST).

The Sandbox's limits, from Twilio's documentation (twilio.com/docs/whatsapp/
sandbox): only numbers that have joined can be reached (error 63015); a
number's Sandbox session ends three days after it joined, and it must send
the join phrase again; free-form messages are delivered only within 24 hours
of the person's last message; the Sandbox sends at most one message every
three seconds. Nothing here stores or reports the auth token.
"""
from __future__ import annotations
import logging
import os
import re
import time
from typing import Any
from xml.sax.saxutils import escape

API = "https://api.twilio.com/2010-04-01"
MAX_BODY = 1600                     # Twilio's limit for one WhatsApp message body
log = logging.getLogger(__name__)
LAST_SEND: dict[str, Any] = {}


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def configured() -> bool:
    return bool(_env("HAANJI_TWILIO_ACCOUNT_SID") and _env("HAANJI_TWILIO_AUTH_TOKEN") and _env("HAANJI_TWILIO_WA_FROM"))


def sender() -> str:
    f = _env("HAANJI_TWILIO_WA_FROM")
    return f if f.startswith("whatsapp:") else f"whatsapp:{f}"


def to_address(phone: str) -> str:
    """whatsapp:+91… for a ten-digit Indian number, or the number as given
    when it already carries a country code."""
    p = phone.strip()
    if p.startswith("whatsapp:"):
        return p
    digits = re.sub(r"\D", "", p)
    if p.startswith("+"):
        return f"whatsapp:+{digits}"
    if len(digits) == 10:
        return f"whatsapp:+91{digits}"
    return f"whatsapp:+{digits}"


def phone_of(address: str) -> str:
    """The sender's last ten digits, the way the rest of HaanJi keys a customer."""
    return re.sub(r"\D", "", address or "")[-10:]


def join_code() -> str | None:
    return _env("HAANJI_TWILIO_WA_JOIN") or None


def join_link() -> str | None:
    """wa.me link that opens WhatsApp with the join phrase typed in."""
    code = join_code()
    if not configured() or not code:
        return None
    from urllib.parse import quote
    return f"https://wa.me/{sender().removeprefix('whatsapp:').lstrip('+')}?text={quote(code)}"


def status() -> dict[str, Any]:
    if not configured():
        return {"configured": False, "number": None}
    number = sender().removeprefix("whatsapp:")
    out: dict[str, Any] = {"configured": True, "provider": "twilio", "number": number, "join_code": join_code(),
                           "join_link": join_link(), "sandbox": number == "+14155238886"}
    if LAST_SEND:
        out["last_send"] = dict(LAST_SEND)
    return out


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def note_status(form: dict[str, str]) -> None:
    """Twilio's status callback: what became of a sent message (queued, sent,
    delivered, read, failed, undelivered), kept in the same shape as Meta's
    so the console can tell when WhatsApp cannot deliver."""
    st = form.get("MessageStatus") or form.get("SmsStatus") or ""
    bad = st in ("failed", "undelivered")
    LAST_SEND["delivery"] = {"status": "failed" if bad else st, "to": "…" + phone_of(form.get("To", ""))[-4:], "at": _now(),
                             **({"code": form.get("ErrorCode"), "detail": (form.get("ErrorMessage") or "")[:200]} if bad else {})}


def _chunks(text: str) -> list[str]:
    text = text or ""
    return [text[i:i + MAX_BODY] for i in range(0, len(text), MAX_BODY)] or [""]


def twiml(texts: list[str]) -> str:
    """The webhook's answer: Twilio sends each <Message> back to the sender."""
    body = "".join(f"<Message>{escape(part)}</Message>" for t in texts if t for part in _chunks(t))
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>'


async def send_text(to: str, text: str, status_callback: str | None = None, *, transport=None) -> bool:
    """One message through Twilio's REST API. Failures are logged, remembered
    for /api/status (Twilio's error code and message, never the token) and
    reported as False, never raised."""
    if not configured():
        return False
    import httpx
    sid, token = _env("HAANJI_TWILIO_ACCOUNT_SID"), _env("HAANJI_TWILIO_AUTH_TOKEN")
    dest = to_address(to)
    ok = True
    try:
        async with httpx.AsyncClient(timeout=15, transport=transport) as client:
            for part in _chunks(text):
                data = {"From": sender(), "To": dest, "Body": part}
                if status_callback:
                    data["StatusCallback"] = status_callback
                r = await client.post(f"{API}/Accounts/{sid}/Messages.json", data=data, auth=(sid, token))
                if r.status_code >= 400:
                    try:
                        err = r.json()
                    except ValueError:
                        err = {"message": r.text[:160]}
                    LAST_SEND["error"] = {"at": _now(), "to": "…" + phone_of(dest)[-4:], "status": r.status_code,
                                          "code": err.get("code"), "message": str(err.get("message") or "")[:200]}
                    log.warning("twilio whatsapp to …%s failed: %s %s", phone_of(dest)[-4:], r.status_code, err.get("code"))
                    ok = False
                    break
    except Exception as exc:                      # noqa: BLE001 - see the docstring
        LAST_SEND["error"] = {"at": _now(), "to": "…" + phone_of(dest)[-4:], "status": None, "code": None,
                              "message": type(exc).__name__}
        log.warning("twilio whatsapp to …%s failed: %s", phone_of(dest)[-4:], type(exc).__name__)
        return False
    if ok:
        LAST_SEND["ok_at"] = _now()
    return ok
