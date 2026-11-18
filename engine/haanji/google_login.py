"""Sign in with Google, beside email + password and the WhatsApp code.

The same OAuth client as Google Calendar (HAANJI_GOOGLE_CLIENT_ID / _SECRET),
asking only for ``openid email``. Google proves the email; HaanJi decides who
may enter: only an email already given to an owner or a staff member
(``credentials``, or HAANJI_OWNER_EMAIL). Nobody is created by signing in.

The ``state`` sent to Google is signed and expires in ten minutes, so a
callback cannot be forged or replayed from elsewhere. The ID token is read
from Google's token endpoint over TLS, which Google documents as enough to
trust it; its audience, issuer, expiry and email_verified are still checked.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
from typing import Any

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
STATE_TTL_S = 600


def client() -> tuple[str, str]:
    return os.environ.get("HAANJI_GOOGLE_CLIENT_ID", ""), os.environ.get("HAANJI_GOOGLE_CLIENT_SECRET", "")


def configured() -> bool:
    cid, secret = client()
    return bool(cid and secret)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def make_state(secret: bytes, now: float | None = None) -> str:
    body = f"{int(now or time.time())}.{secrets.token_urlsafe(12)}"
    sig = _b64(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def check_state(secret: bytes, state: str, now: float | None = None) -> bool:
    try:
        issued, nonce, sig = state.split(".")
        want = _b64(hmac.new(secret, f"{issued}.{nonce}".encode(), hashlib.sha256).digest())
        return hmac.compare_digest(want, sig) and 0 <= (now or time.time()) - int(issued) <= STATE_TTL_S
    except ValueError:
        return False


def authorize_url(redirect_uri: str, state: str) -> str:
    cid, _ = client()
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect_uri, "response_type": "code",
        "scope": "openid email", "state": state, "prompt": "select_account"})


async def exchange(code: str, redirect_uri: str, transport: httpx.AsyncBaseTransport | None = None) -> dict[str, Any]:
    """The verified identity in Google's ID token: {"email", "email_verified", ...}."""
    cid, secret = client()
    async with httpx.AsyncClient(timeout=15, transport=transport) as c:
        r = await c.post(TOKEN_URL, data={"code": code, "client_id": cid, "client_secret": secret,
                                          "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
        r.raise_for_status()
        id_token = r.json()["id_token"]
    payload = id_token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    if claims.get("aud") != cid or claims.get("iss") not in ISSUERS or int(claims.get("exp", 0)) < time.time():
        raise ValueError("the ID token is not for this client, not from Google, or expired")
    if not claims.get("email_verified"):
        raise ValueError("Google has not verified this email")
    return claims
