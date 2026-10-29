"""The day-before reminder, and what the customer replies to it.

The single cheapest thing a receptionist does for a clinic is the reminder
call: fewer no-shows, freed slots filled. Here it is a WhatsApp message the
evening before (``reminder_hour_ist`` in the pack's settings), and the reply
is handled by the same engine: "1"/"haan" confirms, "2"/"cancel" cancels —
through the ledger, with the reminder's own text as the question and the
customer's reply as the proof, exactly like a confirmation on a call."""
from __future__ import annotations
import datetime as dt
import logging
import re
from typing import Any

from .backend.local import LocalBackend
from .pramaan.receipt import ConfirmationProof
from .speak import spoken_date, spoken_time

log = logging.getLogger("haanji.reminders")
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

_YES = re.compile(r"^\s*(1|haan|haanji|ha|yes|ok|okay|theek|confirm|hyan|ho|aa rahe|aa raha|aaunga|aaungi)\b", re.I)
_NO = re.compile(r"^\s*(2|cancel|nahi|na|no|radd|mat|nako|cancle)\b", re.I)


def reminder_text(booking, business: str, today: dt.date, resolve, lang: str = "hinglish",
                  verify_url: str | None = None) -> str:
    when = f"{spoken_date(booking.date, today, resolve, lang)} {spoken_time(booking.time, lang)}"
    who = f" {booking.staff} ke saath" if booking.staff else ""
    lines = [f"Namaste{(' ' + booking.customer_name.split()[0] + ' ji') if booking.customer_name else ''}! "
             f"{business} se yaad dilana tha: aapki {booking.service} ki booking {when}{who} hai."]
    if booking.receipt_code:
        lines.append(f"Confirmation code {booking.receipt_code}.")
    lines.append("Aa rahe hain? 1 = haan, aa raha hoon · 2 = cancel kar do")
    if verify_url and booking.receipt_code:
        lines.append(f"Receipt: {verify_url}/verify?code={booking.receipt_code}")
    return "\n".join(lines)


def due_today(backend: LocalBackend, tenant_id: str, settings: dict[str, Any],
              now: dt.datetime | None = None) -> list:
    """Bookings whose reminder should go out now: tomorrow's (day-before mode)
    once the reminder hour has passed, or today's within two hours (same-day)."""
    if not settings.get("reminders_on", True):
        return []
    now = now or dt.datetime.now(IST)
    if settings.get("reminder_day_before", True):
        if now.hour < int(settings.get("reminder_hour_ist", 18)):
            return []
        return backend.due_reminders(tenant_id, (now.date() + dt.timedelta(days=1)).isoformat())
    soon = []
    for b in backend.due_reminders(tenant_id, now.date().isoformat()):
        start = dt.datetime.fromisoformat(f"{b.date}T{b.time}:00").replace(tzinfo=IST)
        if dt.timedelta(0) <= start - now <= dt.timedelta(hours=2):
            soon.append(b)
    return soon


def interpret_reply(text: str) -> str | None:
    """'1' / 'haan' -> 'confirm'; '2' / 'cancel' -> 'cancel'; else None."""
    if _YES.match(text or ""):
        return "confirm"
    if _NO.match(text or ""):
        return "cancel"
    return None


def proof_for(reminder: str, reply: str, asked_ms: int, replied_ms: int) -> ConfirmationProof:
    """The reminder was the question; the reply is the caller's own words."""
    return ConfirmationProof(prompt_text=reminder, prompt_start_ms=asked_ms, reply_text=reply,
                             reply_start_ms=replied_ms, asr_confidence=1.0,
                             audio_offset_ms=max(0, replied_ms - asked_ms))
