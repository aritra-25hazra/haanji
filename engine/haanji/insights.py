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
from .store import DemoStore

# Cost model, stated in the open. Rupees.
COST_TELEPHONY_PER_MIN = 0.50      # Indian PSTN termination, typical retail
COST_STT_PER_MIN = 0.90            # hosted streaming recognition
COST_TTS_PER_MIN = 0.45            # hosted synthesis
COST_INFRA_PER_CALL = 0.20         # amortised compute
AVG_CALL_MINUTES = 1.6
RECEPTIONIST_MONTHLY = 12000       # a part-time front desk in a tier-2 city
RECEPTIONIST_CALLS_PER_MONTH = 26 * 50


def cost_per_call() -> dict[str, float]:
    ai = round(AVG_CALL_MINUTES * (COST_TELEPHONY_PER_MIN + COST_STT_PER_MIN
                                   + COST_TTS_PER_MIN) + COST_INFRA_PER_CALL, 2)
    human = round(RECEPTIONIST_MONTHLY / RECEPTIONIST_CALLS_PER_MONTH, 2)
    return {"ai_per_call_inr": ai, "receptionist_per_call_inr": human,
            "assumptions": {
                "avg_call_minutes": AVG_CALL_MINUTES,
                "telephony_per_min": COST_TELEPHONY_PER_MIN,
                "stt_per_min": COST_STT_PER_MIN,
                "tts_per_min": COST_TTS_PER_MIN,
                "infra_per_call": COST_INFRA_PER_CALL,
                "receptionist_monthly": RECEPTIONIST_MONTHLY,
                "receptionist_calls_per_month": RECEPTIONIST_CALLS_PER_MONTH,
            }}


def compute(tenant_id: str, store: DemoStore, backend: LocalBackend) -> dict[str, Any]:
    calls = store.calls(tenant_id, limit=500)
    today = dt.date.today().isoformat()
    calls_today = [c for c in calls if c["started_at"][:10] == today]

    outcomes: dict[str, int] = {}
    by_hour: dict[str, dict[str, int]] = {}
    corrections = spec_started = spec_hits = 0
    for c in calls:
        outcomes[c["outcome"] or "IN_PROGRESS"] = outcomes.get(c["outcome"] or "IN_PROGRESS", 0) + 1
        corrections += c["corrections"]
        spec_started += c["spec_started"]
        spec_hits += c["spec_hits"]
        hour = c["started_at"][11:13]
        slot = by_hour.setdefault(hour, {"calls": 0, "booked": 0})
        slot["calls"] += 1
        slot["booked"] += 1 if c["outcome"] == "BOOKED" else 0

    price_of = {s["name"]: (s["price_inr"] or 0) for s in backend.services(tenant_id)}
    bookings = [b for b in backend.bookings(tenant_id)
                if b.status == "CONFIRMED" and b.customer_name != "walk-in"]
    revenue = sum(price_of.get(b.service, 0) for b in bookings)

    leads_open = backend.conn.execute(
        "SELECT COUNT(*) FROM leads WHERE tenant_id=?", (tenant_id,)).fetchone()[0]
    missed = store.missed_summary(tenant_id)
    costs = cost_per_call()

    lines: list[str] = []
    if calls:
        booked = outcomes.get("BOOKED", 0)
        lines.append(f"{len(calls)} calls handled; {booked} became bookings "
                     f"({booked * 100 // max(len(calls), 1)}%).")
    if revenue:
        lines.append(f"Bookings on the calendar are worth about ₹{revenue:,} at catalogue prices.")
    if missed["total"]:
        lines.append(f"{missed['recovered']} of {missed['total']} missed calls were recovered "
                     f"over WhatsApp — each one is a customer who would have called a competitor.")
    if by_hour:
        busiest = max(by_hour.items(), key=lambda kv: kv[1]["calls"])
        lines.append(f"Busiest hour so far: {busiest[0]}:00, with {busiest[1]['calls']} calls.")
    if corrections:
        lines.append(f"Bhasha Bridge repaired {corrections} misheard words; "
                     f"every one of them was a service, a name or a locality.")
    if spec_started:
        lines.append(f"Speculation answered {spec_hits} of {spec_started} tool calls before "
                     f"they were asked for.")
    lines.append(f"Cost per answered call ≈ ₹{costs['ai_per_call_inr']:.2f}, against "
                 f"≈ ₹{costs['receptionist_per_call_inr']:.2f} per call for a part-time "
                 f"receptionist — and this desk never misses lunch.")

    return {
        "tenant_id": tenant_id,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "calls_total": len(calls),
        "calls_today": len(calls_today),
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
