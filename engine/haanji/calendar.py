"""The bookings as a calendar.

Two ways out, both standard: an iCalendar feed per tenant that any calendar
app (Google, Apple, Outlook) subscribes to with one URL, and a Google
Calendar push for owners who connect their account. The feed needs no
account at all and is the honest default; the push is the integration
owners ask for by name.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import hmac
from typing import Any, Iterable

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _ics_escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545 folds lines at 75 octets."""
    out, s = [], line.encode("utf-8")
    while len(s) > 75:
        cut = 75
        while cut > 0 and (s[cut] & 0xC0) == 0x80:      # never split a UTF-8 sequence
            cut -= 1
        out.append(s[:cut].decode("utf-8"))
        s = b" " + s[cut:]
    out.append(s.decode("utf-8"))
    return "\r\n".join(out)


def _stamp(date: str, time: str) -> dt.datetime:
    return dt.datetime.fromisoformat(f"{date}T{time}:00").replace(tzinfo=IST)


def event(booking: Any, business: str, verify_base: str | None = None) -> list[str]:
    start = _stamp(booking.date, booking.time)
    end = start + dt.timedelta(minutes=int(booking.duration_min or 30))
    who = booking.customer_name or "walk-in"
    summary = f"{booking.service} — {who}"
    desc = [f"{business}", f"Service: {booking.service}", f"With: {booking.staff}",
            f"Customer: {who}" + (f" ({booking.phone})" if booking.phone else "")]
    if booking.receipt_code:
        desc.append(f"Receipt: {booking.receipt_code}")
        if verify_base:
            desc.append(f"Verify: {verify_base}/verify?code={booking.receipt_code}")
    status = "CONFIRMED" if booking.status == "CONFIRMED" else "CANCELLED"
    return [
        "BEGIN:VEVENT",
        f"UID:{booking.booking_id}@haanji",
        f"DTSTAMP:{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;TZID=Asia/Kolkata:{start.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND;TZID=Asia/Kolkata:{end.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{_ics_escape(summary)}",
        f"DESCRIPTION:{_ics_escape(chr(10).join(desc))}",
        f"STATUS:{status}",
        "END:VEVENT",
    ]


def feed(bookings: Iterable[Any], business: str, pack_id: str, verify_base: str | None = None) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//HaanJi//Bookings//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{_ics_escape(business)} (HaanJi)", "X-WR-TIMEZONE:Asia/Kolkata",
             "BEGIN:VTIMEZONE", "TZID:Asia/Kolkata", "BEGIN:STANDARD", "DTSTART:19700101T000000",
             "TZOFFSETFROM:+0530", "TZOFFSETTO:+0530", "TZNAME:IST", "END:STANDARD", "END:VTIMEZONE"]
    for b in bookings:
        if b.customer_name == "walk-in":
            continue
        lines += event(b, business, verify_base)
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def feed_token(secret: bytes, pack_id: str) -> str:
    """A calendar app cannot send a bearer token, so the feed URL carries a
    per-tenant secret derived from the auth secret."""
    return hmac.new(secret, f"ics:{pack_id}".encode(), hashlib.sha256).hexdigest()[:32]


def google_event(booking: Any, business: str, verify_base: str | None = None) -> dict[str, Any]:
    start = _stamp(booking.date, booking.time)
    end = start + dt.timedelta(minutes=int(booking.duration_min or 30))
    who = booking.customer_name or "walk-in"
    desc = f"{business}\nService: {booking.service}\nWith: {booking.staff}\nCustomer: {who}"
    if booking.phone:
        desc += f" ({booking.phone})"
    if booking.receipt_code:
        desc += f"\nReceipt: {booking.receipt_code}"
        if verify_base:
            desc += f"\nVerify: {verify_base}/verify?code={booking.receipt_code}"
    return {"summary": f"{booking.service} — {who}", "description": desc,
            "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Kolkata"},
            "extendedProperties": {"private": {"haanji_booking": booking.booking_id,
                                               "haanji_receipt": booking.receipt_code or ""}}}
