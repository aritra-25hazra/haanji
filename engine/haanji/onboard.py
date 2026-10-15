"""From five answers to a working pack.

Pack Studio edits YAML, which is a developer's tool. Onboarding is the
owner's: name the business, list the services and the staff, say when you
are open, and a complete pack comes out — persona, guardrails fitted to the
kind of business, a knowledge base for the questions callers always ask,
lexicon seeds, and two scenarios that prove the pack books and answers
before it is saved. The result is ordinary YAML that Pack Studio can keep
editing.
"""
from __future__ import annotations
import re
from typing import Any

import yaml

from .vertical import PackError, from_dict

TEMPLATES: dict[str, dict[str, Any]] = {
    "clinic": {
        "staff_role": "doctor",
        "style": "Warm, brief Hinglish. Confirms the doctor by name. Never diagnoses.",
        "refuse": ["diagnosing a symptom", "recommending a medicine or a dose", "interpreting a report"],
        "escalate_on": ["severe pain or bleeding", "an accident or emergency", "a complaint about treatment"],
        "refusal_line": "Yeh doctor hi dekh kar bata payenge; main aapka appointment laga deta hoon.",
        "escalation_line": "Yeh urgent lag raha hai — main abhi aapko clinic ke staff se jodta hoon.",
    },
    "salon": {
        "staff_role": "stylist",
        "style": "Friendly, upbeat, short Hinglish sentences. Confirms the stylist by name.",
        "refuse": ["promising a hair or skin result", "advice on a scalp or skin condition", "matching a competitor's price"],
        "escalate_on": ["allergic reaction after a service", "complaint about a previous service", "refund request"],
        "refusal_line": "Ye stylist aapko dekh kar hi bata payenge, main aapka slot laga deta hoon.",
        "escalation_line": "Ye main manager ko de raha hoon, wo abhi baat karengi.",
    },
    "lab": {
        "staff_role": "technician",
        "style": "Calm, precise Hinglish. Always mentions fasting or prep when the test needs it.",
        "refuse": ["interpreting a test result", "saying whether a value is normal", "recommending a test for a symptom"],
        "escalate_on": ["a wrong or missing report", "a billing dispute", "severe symptoms"],
        "refusal_line": "Report ka matlab doctor hi batayenge; main aapka sample collection book kar deta hoon.",
        "escalation_line": "Yeh main lab manager ko de raha hoon, wo abhi dekhte hain.",
    },
    "coaching": {
        "staff_role": "teacher",
        "style": "Encouraging, clear Hinglish. Talks about batches and demo classes, never about guaranteed results.",
        "refuse": ["guaranteeing a rank or a score", "comparing with another institute", "fee discounts beyond the catalogue"],
        "escalate_on": ["a refund request", "a complaint about a teacher", "a safety concern"],
        "refusal_line": "Result student ki mehnat se aata hai; main aapko demo class dila deta hoon.",
        "escalation_line": "Yeh main counsellor ko de raha hoon, wo abhi baat karenge.",
    },
    "other": {
        "staff_role": "staff",
        "style": "Warm, brief Hinglish. Confirms the person by name.",
        "refuse": ["anything not in the catalogue", "legal or medical advice"],
        "escalate_on": ["a complaint", "a refund request", "an emergency"],
        "refusal_line": "Iska sahi jawab hamari team hi de payegi, main aapko unse jodta hoon.",
        "escalation_line": "Yeh main team ko de raha hoon, wo abhi baat karenge.",
    },
}
DAY_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_HINDI = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
             "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:40] or "my_business"


def _spoken_hours(hours: dict[str, Any]) -> str:
    open_days = []
    closed = []
    for spec, val in hours.items():
        (open_days if val else closed).append(spec)
    parts = []
    for spec in open_days:
        a, b = hours[spec]
        parts.append(f"{spec} {a} se {b} tak")
    line = "Hum " + ", ".join(parts) + " khule hain." if parts else "Timing abhi tay nahi."
    if closed:
        line += " " + ", ".join(closed) + " band rehta hai."
    return line


def _price_words(price: int | None) -> str:
    return f"{price:,} rupaye" if price else "catalogue ke hisaab se"


def _first_open_dayword(hours: dict[str, Any]) -> str:
    """The selftest's today is a Monday; pick 'kal' or 'parso' so the
    generated booking scenario lands on an open day."""
    from .vertical import _expand_days
    opened: set[int] = set()
    for spec, val in hours.items():
        if val:
            try:
                opened.update(_expand_days(spec))
            except (KeyError, ValueError):
                pass
    if 1 in opened:
        return "kal"
    if 2 in opened:
        return "parso"
    return "kal"


def draft(spec: dict[str, Any]) -> tuple[str, list[str], dict[str, Any]]:
    """Build the pack. Returns (yaml_text, problems, pack_dict)."""
    kind = spec.get("business_type") or "other"
    t = TEMPLATES.get(kind, TEMPLATES["other"])
    business = (spec.get("business_name") or "").strip()
    if not business:
        raise PackError("business_name is required")
    pack_id = slug(spec.get("pack_id") or business)
    agent = (spec.get("agent_name") or "Haanji").strip()
    staff = [s.strip() for s in spec.get("staff", []) if str(s).strip()]
    hours_in = spec.get("hours") or {}
    hours: dict[str, Any] = {}
    for spec_days, val in hours_in.items():
        if val and len(val) == 2:
            hours[str(spec_days)] = [str(val[0]), str(val[1])]
        else:
            hours[str(spec_days)] = None
    services = []
    for s in spec.get("services", []):
        name = str(s.get("name", "")).strip().lower()
        if not name:
            continue
        who = [p for p in s.get("staff", []) if p in staff] or staff
        services.append({"name": name, "duration_min": int(s.get("duration_min") or 30),
                         "price_inr": int(s["price_inr"]) if s.get("price_inr") not in (None, "") else None,
                         "staff": who, "aliases": [a.strip() for a in s.get("aliases", []) if str(a).strip()]})
    places = [p.strip() for p in spec.get("places", []) if str(p).strip()]
    language = spec.get("language") or "hinglish"

    knowledge = [{"q": f"{business} ke timings kya hain?", "a": _spoken_hours(hours),
                  "tags": ["timing", "timings", "khulta", "band", "hours", "kab", "open", "time"]}]
    for s in services:
        words = [w for w in s["name"].split() if len(w) > 2]
        knowledge.append({"q": f"{s['name']} ka kitna charge hai?",
                          "a": f"{s['name'].capitalize()} {_price_words(s['price_inr'])} hai, "
                               f"lagbhag {s['duration_min']} minute lagte hain.",
                          "tags": words + s["aliases"][:3] + ["charge", "charges", "price", "kitna", "cost", "fees"]})
    if places:
        knowledge.append({"q": "Aap kahan hain?", "a": f"Hum {places[0]} mein hain.",
                          "tags": ["kahan", "address", "location", "branch", "pata"]})

    scenarios = []
    if services:
        first = services[0]["name"]
        day = _first_open_dayword(hours)
        scenarios.append({"name": "booking", "expect": "BOOKED",
                          "note": "Generated by onboarding: the first service, the next open morning.",
                          "turns": [{"heard": f"mujhe {first} karwana hai", "truth": f"mujhe {first} karwana hai"},
                                    {"heard": f"{day} subah ka time mil jayega", "truth": f"{day} subah ka time mil jayega"},
                                    {"heard": "haan ji wahi theek hai", "truth": "haan ji wahi theek hai"},
                                    {"heard": "mera naam Test User hai number 9876543210",
                                     "truth": "mera naam Test User hai number 9876543210"},
                                    {"heard": "haan confirm kar do", "truth": "haan confirm kar do"}]})
        scenarios.append({"name": "price_faq", "expect": "FAQ_ANSWERED",
                          "turns": [{"heard": f"{first} ke kitne charges hain", "truth": f"{first} ke kitne charges hain"},
                                    {"heard": "nahi bas itna hi tha dhanyavaad", "truth": "nahi bas itna hi tha dhanyavaad"}]})

    data: dict[str, Any] = {
        "pack": pack_id,
        "display_name": spec.get("display_name") or business,
        "version": 1,
        "language": language,
        "persona": {
            "agent_name": agent, "business_name": business,
            "greeting": spec.get("greeting") or f"Haanji, {business}. Main aapki kya madad karun?",
            "closing": spec.get("closing") or "Dhanyavaad, aapka din shubh ho.",
            "style": t["style"],
        },
        "guardrails": {"never_quote_outside_catalogue": True, "max_discount_pct": 0,
                       "refuse": list(t["refuse"]), "escalate_on": list(t["escalate_on"]),
                       "refusal_line": t["refusal_line"], "escalation_line": t["escalation_line"]},
        "staff_role": spec.get("staff_role") or t["staff_role"],
        "staff": staff,
        "hours": hours,
        "services": services,
        "lexicon": {"places": places, "brands": [], "phrases": []},
        "knowledge": knowledge,
        "scenarios": scenarios,
    }
    pack = from_dict(data)
    problems = pack.validate()
    text = (f"# Vertical Pack — {business} (generated by onboarding; edit freely in Pack Studio)\n"
            + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))
    return text, problems, data
