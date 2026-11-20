"""Time-based one-time passwords (RFC 6238), the codes an authenticator app
(Google Authenticator, Microsoft Authenticator, Authy) shows: HMAC-SHA1 over
the 30-second step, six digits. No dependency beyond the standard library.

A code is accepted for the current step and one step either side (clocks
drift), and never twice: the caller keeps the last step it accepted and
passes it back, so a code seen over someone's shoulder cannot be replayed.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP_S = 30
DIGITS = 6


def new_secret() -> str:
    """160 random bits, base32, as authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret_b32: str) -> bytes:
    s = secret_b32.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def code_at(secret_b32: str, counter: int, digits: int = DIGITS, digest=hashlib.sha1) -> str:
    """The code for one step counter (RFC 4226 dynamic truncation)."""
    mac = hmac.new(_key(secret_b32), struct.pack(">Q", counter), digest).digest()
    offset = mac[-1] & 0x0F
    value = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return f"{value:0{digits}d}"


def verify(secret_b32: str, code: str, now: float | None = None, *, last_step: int = -1, window: int = 1) -> int | None:
    """The step the code belongs to, or None. Steps at or before ``last_step``
    are refused (no replay)."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != DIGITS:
        return None
    step = int((time.time() if now is None else now) // STEP_S)
    for delta in (0, -1, 1, *range(-window, window + 1)):
        s = step + delta
        if abs(delta) > window or s <= last_step:
            continue
        if hmac.compare_digest(code_at(secret_b32, s), code):
            return s
    return None


def uri(secret_b32: str, account: str, issuer: str = "HaanJi") -> str:
    """The otpauth:// link a QR code carries."""
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP_S}")
