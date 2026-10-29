"""What a hosted model is told about the business.

Vendor-neutral: the system prompt and the tool schemas are built here from the
vertical pack and the tool registry, so every adapter describes the business
the same way and the deterministic policy's knowledge is exactly the model's.
"""
from __future__ import annotations
import datetime as dt
from typing import Any

from ..vertical import Pack

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

LANGUAGE_NOTES = {
    "hinglish": "Reply in Hinglish (Hindi written in Latin script, mixed with English), "
                "the way a receptionist in an Indian city speaks on the phone.",
    "benglish": "Reply in Benglish (Bengali written in Latin script, mixed with English), "
                "the way a receptionist in Kolkata speaks on the phone.",
    "marathinglish": "Reply in Marathinglish (Marathi written in Latin script, mixed with English), "
                     "the way a receptionist in Pune speaks on the phone.",
    "tanglish": "Reply in Tanglish (Tamil written in Latin script, mixed with English), "
                "the way a receptionist in Chennai speaks on the phone. Say times as "
                "'kaalai 10 mani', 'pathu arai' for half past.",
    "tenglish": "Reply in Tenglish (Telugu written in Latin script, mixed with English), "
                "the way a receptionist in Hyderabad speaks on the phone. Say times as "
                "'udayam 10 gantalaku', 'padinnara' for half past ten.",
    "gujlish": "Reply in Gujlish (Gujarati written in Latin script, mixed with English), "
               "the way a receptionist in Ahmedabad speaks on the phone. Say times as "
               "'savare 10 vage', 'sada das' for half past ten.",
    "punglish": "Reply in Punglish (Punjabi written in Latin script, mixed with English), "
                "the way a receptionist in Ludhiana speaks on the phone. Say times as "
                "'savere 10 vaje', 'saadhe das' for half past ten.",
}


def _hours(pack: Pack) -> str:
    if not pack.hours:
        return "Hours: not specified."
    lines = []
    for day in range(7):
        slots = pack.hours.get(day)
        label = DAYS[day]
        lines.append(f"  {label}: {' and '.join(slots) if slots else 'closed'}")
    return "Hours:\n" + "\n".join(lines)


def _services(pack: Pack) -> str:
    rows = []
    for s in pack.services:
        bits = [f"{s.duration_min} min"]
        if s.price_inr is not None:
            bits.append(f"Rs {s.price_inr}")
        if s.staff:
            bits.append("with " + ", ".join(s.staff))
        row = f"  - {s.name} ({'; '.join(bits)})"
        if s.prep_note:
            row += f". Note: {s.prep_note}"
        rows.append(row)
    return "Services (the only ones you may offer or price):\n" + "\n".join(rows)


def _knowledge(pack: Pack) -> str:
    if not pack.knowledge:
        return ""
    rows = [f"  Q: {q}\n  A: {a}" for q, a, _tags in pack.knowledge]
    return "Things callers often ask:\n" + "\n".join(rows)


def build_system_prompt(pack: Pack, today: dt.date | None = None) -> str:
    """The stable description of one business, in the order a new receptionist
    would be briefed: who you are, what you sell, when you are open, what you
    never do, and how the engine around you works."""
    p, g = pack.persona, pack.guardrails
    staff = ", ".join(pack.staff) if pack.staff else "the team"
    refuse = "; ".join(g.refuse_topics) if g.refuse_topics else "nothing in particular"
    escalate = "; ".join(g.escalate_on) if g.escalate_on else "nothing in particular"
    parts = [
        f"You are {p.agent_name}, the phone receptionist for {p.business_name}.",
        f"Language: {pack.language}. {LANGUAGE_NOTES.get(pack.language, '')}".strip(),
        f"Style: {p.style}. One or two short sentences per turn; this is a phone call, "
        f"not a chat. Never use emoji or bullet points.",
        f"Your greeting was: \"{p.greeting}\" Your closing line is: \"{p.closing}\"",
        f"{pack.staff_role.capitalize()}: {staff}.",
        _services(pack),
        _hours(pack),
        _knowledge(pack),
        "Rules:",
        f"  - Refuse and offer a human for: {refuse}. Your refusal line: \"{g.refusal_line}\"",
        f"  - Escalate (call the handoff tool) for: {escalate}. Say: \"{g.escalation_line}\"",
        "  - Never quote a price or a service that is not in the list above."
        if g.never_quote_outside_catalogue else "",
        f"  - Discounts: at most {g.max_discount_pct}% and only if asked." if g.max_discount_pct
        else "  - Never offer a discount.",
        "How the engine around you works:",
        "  - Use check_availability before offering a time; offer the slots it returns, nothing else.",
        "  - Use search_knowledge for questions you cannot answer from this briefing.",
        "  - To book or cancel, call the tool with everything you know. The engine will read the "
        "details back to the caller and ask for a yes before anything is written; you never ask "
        "for that confirmation yourself and you never claim something is booked before the tool says so.",
        "  - Call end_call once the caller is done and you have said goodbye.",
        "  - Dates are ISO (YYYY-MM-DD) and times are 24-hour HH:MM in tool arguments.",
    ]
    if today is not None:
        parts.append(f"Today is {DAYS[today.weekday()]}, {today.isoformat()}.")
    return "\n".join(x for x in parts if x)


def tool_schemas(registry) -> list[dict[str, Any]]:
    """The registry's own schemas, untouched. Adapters reshape them."""
    return registry.schemas()
