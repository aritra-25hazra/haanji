"""Email out: sign-in codes and password resets, over SMTP (a Gmail account
with an App Password works on the free plan).

    HAANJI_SMTP_HOST      smtp.gmail.com
    HAANJI_SMTP_PORT      465 (implicit TLS) or 587 (STARTTLS)
    HAANJI_SMTP_USER      the account
    HAANJI_SMTP_PASSWORD  its App Password (never the account password)
    HAANJI_MAIL_FROM      the sender shown, e.g. "HaanJi <you@gmail.com>"; defaults to the user

Nothing here logs or reports a secret: status() says whether mail is set up
and how the last send went, with the recipient masked.
"""
from __future__ import annotations
import asyncio
import datetime as dt
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

LAST_SEND: dict[str, Any] = {}


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def configured() -> bool:
    return bool(_env("HAANJI_SMTP_HOST") and _env("HAANJI_SMTP_USER") and _env("HAANJI_SMTP_PASSWORD"))


def _mask(addr: str) -> str:
    name, _, domain = addr.partition("@")
    return f"{name[:1]}…@{domain}" if domain else "…"


def status() -> dict[str, Any]:
    return {"configured": configured(), "last_send": dict(LAST_SEND) or None}


def _send_sync(to: str, subject: str, text: str) -> None:
    host, user, password = _env("HAANJI_SMTP_HOST"), _env("HAANJI_SMTP_USER"), _env("HAANJI_SMTP_PASSWORD")
    port = int(_env("HAANJI_SMTP_PORT") or 465)
    msg = EmailMessage()
    msg["From"] = _env("HAANJI_MAIL_FROM") or user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls(context=context)
            smtp.login(user, password)
            smtp.send_message(msg)


async def send(to: str, subject: str, text: str) -> bool:
    """True when the server accepted the message. A failure is remembered for
    /api/status (type and a short message, never a credential) and returns
    False; it never raises into a request."""
    when = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if not configured():
        LAST_SEND.clear()
        LAST_SEND.update({"at": when, "to": _mask(to), "ok": False, "error": "mail is not set up (HAANJI_SMTP_*)"})
        return False
    try:
        await asyncio.to_thread(_send_sync, to, subject, text)
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        message = str(exc).replace(_env("HAANJI_SMTP_PASSWORD") or "\0", "…")[:200]
        LAST_SEND.clear()
        LAST_SEND.update({"at": when, "to": _mask(to), "ok": False, "error": f"{type(exc).__name__}: {message}"})
        return False
    LAST_SEND.clear()
    LAST_SEND.update({"at": when, "to": _mask(to), "ok": True})
    return True


def code_mail(code: str, purpose: str) -> tuple[str, str]:
    """The subject and body of a sign-in or reset code, in English and Hinglish."""
    what = "password reset" if purpose == "reset" else "sign-in"
    kya = "password reset" if purpose == "reset" else "login"
    subject = f"HaanJi {what} code: {code}"
    body = (f"Your HaanJi {what} code is {code}. It works for 5 minutes. Do not share it with anyone.\n\n"
            f"Aapka HaanJi {kya} code {code} hai. Yeh 5 minute tak chalega. Kisi ko mat batayein.\n\n"
            "If you did not ask for this code, you can ignore this email; your account is unchanged.\n")
    return subject, body
