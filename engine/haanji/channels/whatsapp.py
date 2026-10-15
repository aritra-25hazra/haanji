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


async def send_text(to: str, text: str) -> None:
    """Send one text message. Failures are logged, never raised: the webhook
    must still answer Meta with a 200 or the delivery is retried."""
    if not configured():
        return
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{GRAPH}/{os.environ['HAANJI_WA_PHONE_ID']}/messages",
                headers={"Authorization": f"Bearer {os.environ['HAANJI_WA_TOKEN']}"},
                json={"messaging_product": "whatsapp", "to": to,
                      "type": "text", "text": {"body": text}})
            if r.status_code >= 400:
                log.warning("whatsapp send to …%s failed: %s %s", to[-4:], r.status_code, r.text[:200])
    except Exception as e:                       # noqa: BLE001 — see docstring
        log.warning("whatsapp send to …%s failed: %s", to[-4:], e)
