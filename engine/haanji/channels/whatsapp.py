"""Meta WhatsApp Cloud API adapter (real mode).

The simulator at /whatsapp needs none of this. To go live:

1. Create a Meta app with the WhatsApp product; note the phone number ID and
   a permanent access token.
2. Set  HAANJI_WA_TOKEN, HAANJI_WA_PHONE_ID, HAANJI_WA_VERIFY_TOKEN.
3. Expose the server (e.g. `ngrok http 8090`) and register
   https://<host>/wa/webhook as the webhook with the same verify token.

The webhook handler in server.py then feeds real messages through the exact
code path the simulator uses.
"""
from __future__ import annotations
import os
from typing import Iterator

GRAPH = "https://graph.facebook.com/v20.0"


def configured() -> bool:
    return bool(os.environ.get("HAANJI_WA_TOKEN") and os.environ.get("HAANJI_WA_PHONE_ID"))


def extract_incoming(payload: dict) -> Iterator[tuple[str, str]]:
    """Yield (sender phone, text) for every text message in a webhook delivery."""
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []) or []:
                if msg.get("type") == "text":
                    yield msg["from"], msg["text"]["body"]


async def send_text(to: str, text: str) -> None:
    if not configured():
        return
    import httpx
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(
            f"{GRAPH}/{os.environ['HAANJI_WA_PHONE_ID']}/messages",
            headers={"Authorization": f"Bearer {os.environ['HAANJI_WA_TOKEN']}"},
            json={"messaging_product": "whatsapp", "to": to,
                  "type": "text", "text": {"body": text}})
