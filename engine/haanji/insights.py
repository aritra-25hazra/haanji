"""The owner's Monday-morning answers, computed from real rows.

Everything here is an honest aggregate or an explicitly-stated assumption —
the cost constants are written out, not hidden — because a dashboard a
business owner cannot interrogate is a dashboard they will not trust.
"""
from __future__ import annotations
import datetime as dt
import json
from typing import Any

from .backend.local import LocalBackend
from .store import IST, DemoStore, to_ist

# Cost model, stated in the open. Rupees.
COST_TELEPHONY_PER_MIN = 0.50      # Indian PSTN termination, typical retail
COST_STT_PER_MIN = 0.90            # hosted streaming recognition
COST_TTS_PER_MIN = 0.45            # hosted synthesis
COST_INFRA_PER_CALL = 0.20         # amortised compute
AVG_CALL_MINUTES = 1.6
RECEPTIONIST_MONTHLY = 12000       # a part-time front desk in a tier-2 city
RECEPTIONIST_CALLS_PER_MONTH = 26 * 50


def _calls(n: int) -> str:
    return f"{n} call" if n == 1 else f"{n} calls"


def cost_per_call(receptionist_monthly: int = RECEPTIONIST_MONTHLY,
                  receptionist_calls: int = RECEPTIONIST_CALLS_PER_MONTH) -> dict[str, float]:
    """The agent's cost per call from the vendors' rates, against the shop's
    own front desk (Settings: receptionist_monthly_inr, ..._calls_per_month)."""
    ai = round(AVG_CALL_MINUTES * (COST_TELEPHONY_PER_MIN + COST_STT_PER_MIN
                                   + COST_TTS_PER_MIN) + COST_INFRA_PER_CALL, 2)
    human = round(receptionist_monthly / max(receptionist_calls, 1), 2)
    return {"ai_per_call_inr": ai, "receptionist_per_call_inr": human,
            "assumptions": {
                "avg_call_minutes": AVG_CALL_MINUTES,
                "telephony_per_min": COST_TELEPHONY_PER_MIN,
                "stt_per_min": COST_STT_PER_MIN,
                "tts_per_min": COST_TTS_PER_MIN,
                "infra_per_call": COST_INFRA_PER_CALL,
                "receptionist_monthly": receptionist_monthly,
                "receptionist_calls_per_month": receptionist_calls,
            }}


# The engine's notes on the day, in the console's two languages.
LINES = {
    "hi": {"calls": "Aaj {calls} aayi; {booked} booking bani ({pct}%).",
           "revenue": "Aaj bani bookings catalogue ke daam se lagbhag ₹{revenue} ki hain.",
           "missed": "{total} missed calls mein se {recovered} WhatsApp se wapas aaye.",
           "busy": "Sabse busy ghanta ab tak: {hour}:00, {calls}.",
           "fixed": "Bhasha Bridge ne {n} galat sune shabd theek kiye; sab is dukaan ki apni shabd-list ke the.",
           "spec": "Speculation ne {started} mein se {hits} tool calls poochhe jaane se pehle hi taiyaar rakhe.",
           "cost": "Ek jawab di gayi call ka kharcha ≈ ₹{ai}; part-time receptionist pe ≈ ₹{rec} per call."},
    "en": {"calls": "{calls} came in today; {booked} became bookings ({pct}%).",
           "revenue": "Today's bookings are worth about ₹{revenue} at catalogue prices.",
           "missed": "{recovered} of {total} missed calls came back on WhatsApp.",
           "busy": "Busiest hour so far: {hour}:00, {calls}.",
           "fixed": "Bhasha fixed {n} misheard words, all from this shop's own word list.",
           "spec": "Speculation had {hits} of {started} tool calls ready before they were asked.",
           "cost": "An answered call costs about ₹{ai}; a part-time receptionist about ₹{rec} per call."},
}


def compute(tenant_id: str, store: DemoStore, backend: LocalBackend,
            settings: dict[str, Any] | None = None, now: dt.datetime | None = None,
            lang: str = "hi") -> dict[str, Any]:
    """The owner's day. Everything on the "Today" screen and in the evening
    digest is today's (India's day): the outcomes, the hourly chart, the
    bookings made and what they are worth, the repairs. Only ``calls_total``
    and the callback list reach further back, because a callback stays owed
    until it is made."""
    calls = store.calls(tenant_id, limit=500)
    # "Today" and the hour of a call are India's, whatever clock the host keeps.
    today = (now or dt.datetime.now(IST)).astimezone(IST).date()
    calls_today = [c for c in calls if to_ist(c["started_at"]).date() == today]
    yesterday = today - dt.timedelta(days=1)
    calls_yesterday = sum(1 for c in calls if to_ist(c["started_at"]).date() == yesterday)

    outcomes: dict[str, int] = {}
    by_hour: dict[str, dict[str, int]] = {}
    corrections = spec_started = spec_hits = 0
    for c in calls_today:
        outcomes[c["outcome"] or "IN_PROGRESS"] = outcomes.get(c["outcome"] or "IN_PROGRESS", 0) + 1
        corrections += c["corrections"]
        spec_started += c["spec_started"]
        spec_hits += c["spec_hits"]
        hour = f"{to_ist(c['started_at']).hour:02d}"
        slot = by_hour.setdefault(hour, {"calls": 0, "booked": 0})
        slot["calls"] += 1
        slot["booked"] += 1 if c["outcome"] == "BOOKED" else 0

    # The bookings today's calls made (by their receipt codes), still on the calendar.
    price_of = {s["name"]: (s["price_inr"] or 0) for s in backend.services(tenant_id)}
    codes = {code for c in calls_today if c["outcome"] in ("BOOKED", "RESCHEDULED")
             for code in json.loads(c.get("receipts_json") or "[]")}
    bookings = [b for b in backend.bookings(tenant_id)
                if b.receipt_code in codes and b.status != "CANCELLED" and b.customer_name != "walk-in"]
    revenue = sum(price_of.get(b.service, 0) for b in bookings)

    # The console's callback list: recent calls that ended needing a person.
    leads_open = sum(1 for c in calls if c["outcome"] in ("LEAD_CAPTURED", "HANDED_OFF"))
    missed = store.missed_summary(tenant_id)
    s = settings or {}
    costs = cost_per_call(int(s.get("receptionist_monthly_inr", RECEPTIONIST_MONTHLY)),
                          int(s.get("receptionist_calls_per_month", RECEPTIONIST_CALLS_PER_MONTH)))

    w = LINES.get(lang, LINES["hi"])
    lines: list[str] = []
    if calls_today:
        booked = outcomes.get("BOOKED", 0)
        lines.append(w["calls"].format(calls=_calls(len(calls_today)), booked=booked,
                                       pct=booked * 100 // max(len(calls_today), 1)))
    if revenue:
        lines.append(w["revenue"].format(revenue=f"{revenue:,}"))
    if missed["total"]:
        lines.append(w["missed"].format(total=missed["total"], recovered=missed["recovered"]))
    if by_hour:
        busiest = max(by_hour.items(), key=lambda kv: kv[1]["calls"])
        lines.append(w["busy"].format(hour=busiest[0], calls=_calls(busiest[1]["calls"])))
    if corrections:
        lines.append(w["fixed"].format(n=corrections))
    if spec_started:
        lines.append(w["spec"].format(started=spec_started, hits=spec_hits))
    if calls_today:
        lines.append(w["cost"].format(ai=f"{costs['ai_per_call_inr']:.2f}", rec=f"{costs['receptionist_per_call_inr']:.2f}"))

    return {
        "tenant_id": tenant_id,
        "day": today.isoformat(),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "calls_total": len(calls),
        "calls_today": len(calls_today),
        "calls_yesterday": calls_yesterday,
        "outcomes": outcomes,
        "by_hour": [{"hour": h, **v} for h, v in sorted(by_hour.items())],
        "bookings_confirmed": len(bookings),
        "revenue_booked_inr": revenue,
        "leads_open": leads_open,
        "missed_calls": missed,
        "corrections_total": corrections,
        "speculation": {"started": spec_started, "hits": spec_hits,
                        "hit_rate": round(spec_hits / spec_started, 3) if spec_started else 0.0},
        "cost": costs,
        "insights": lines,
    }
