"""What the agent must not do.

A voice agent that answers everything is a liability. These rules run on the
corrected transcript *before* the dialogue policy sees it, so a refusal or an
escalation can never be argued away by the model. Each rule is a pair of
patterns — a subject and a qualifier — because single keywords produce absurd
false positives: "report kab milegi" is a scheduling question, while "report
mein sugar zyada hai kya khatra hai" is a request for a diagnosis.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from enum import Enum

from .vertical import Pack


class Action(str, Enum):
    ALLOW = "ALLOW"
    REFUSE = "REFUSE"
    ESCALATE = "ESCALATE"


@dataclass
class Verdict:
    action: Action
    rule: str = ""
    line: str = ""

    @property
    def blocked(self) -> bool:
        return self.action is not Action.ALLOW


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


# (rule id, action, subject pattern, qualifier pattern or None)
RULES: list[tuple[str, Action, re.Pattern, re.Pattern | None]] = [
    ("emergency.bleeding", Action.ESCALATE,
     _rx(r"\b(khoon|blood|bleeding|rakt|rokto)\b"),
     _rx(r"(aa rah|nahi ruk|ruk nahi|band nahi|bahut|zyada|non ?stop|porche|"
         r"bondho hochhe na|khub|besh)")),
    ("emergency.acute", Action.ESCALATE,
     _rx(r"\b(accident|fracture|behosh|faint|chakkar|saans nahi|emergency|"
         r"unbearable|bardasht nahi|asahniya)\b"), None),
    ("emergency.swelling", Action.ESCALATE,
     _rx(r"\b(sujan|swelling|sooj)\w*\b"), _rx(r"(bukhar|fever|dard|pain)")),
    ("commercial.refund", Action.ESCALATE,
     _rx(r"\b(refund|paisa wapas|paise wapas|money back)\b"), None),
    ("commercial.complaint", Action.ESCALATE,
     _rx(r"\b(shikayat|complaint|kharab|ganda|badtameez|rude)\b"),
     _rx(r"(service|kaam|treatment|staff|pichhli|pichli|last time|baar)")),
    ("handoff.request", Action.ESCALATE,
     _rx(r"\b(manager|owner|senior|insaan|human|aadmi|kisi se)\b"),
     _rx(r"(baat|transfer|connect|jod|bulao|bula)")),
    ("advice.medicine", Action.REFUSE,
     _rx(r"\b(dawai|dawa|medicine|tablet|goli|dose|antibiotic|prescri\w*)\b"), None),
    ("advice.diagnosis", Action.REFUSE,
     _rx(r"\b(bimari|disease|infection|problem kya|kya hua hai|diagnos\w*)\b"),
     _rx(r"(batao|bataiye|kya|kaun|hai)")),
    ("advice.report", Action.REFUSE,
     _rx(r"\b(report|result|value|level|hemoglobin|sugar|tsh|cholesterol|x ?ray)\b"),
     _rx(r"(matlab|khatra|danger|serious|normal|kam hai|zyada hai|theek hai|"
         r"chinta|worry|kya hai ye)")),
    ("promise.outcome", Action.REFUSE,
     _rx(r"\b(guarantee|guranty|garanti|pakka|zaroor|surely)\b"),
     _rx(r"(selection|rank|result|ho jayega|mil jayega|thik ho jay|theek ho jay|"
         r"ho jayegi|score)")),
    ("promise.discount", Action.REFUSE,
     _rx(r"\b(discount|chhoot|chhut|kam kar|sasta|kam karo|bargain)\b"), None),
]

PHONE = re.compile(r"\b(\d{2})\d{4,6}(\d{2})\b")


class Guard:
    """Pack-aware. A pack can switch a category off, but not invent an exception."""

    def __init__(self, pack: Pack):
        self.pack = pack
        self.enabled = {rid for rid, *_ in RULES}
        if pack.guardrails.max_discount_pct > 0:
            self.enabled.discard("promise.discount")

    def check(self, text: str) -> Verdict:
        for rid, action, subject, qualifier in RULES:
            if rid not in self.enabled:
                continue
            if not subject.search(text):
                continue
            if qualifier is not None and not qualifier.search(text):
                continue
            line = (self.pack.guardrails.escalation_line if action is Action.ESCALATE
                    else self.pack.guardrails.refusal_line)
            return Verdict(action, rid, line)
        return Verdict(Action.ALLOW)

    def price_allowed(self, service: str | None) -> bool:
        """A price may only be spoken for something in the tenant's catalogue."""
        if not self.pack.guardrails.never_quote_outside_catalogue:
            return True
        return bool(service) and service.lower() in {s.lower() for s in self.pack.service_names}

    @staticmethod
    def redact(text: str) -> str:
        """Logs and transcript excerpts keep the shape of a number, not the number."""
        return PHONE.sub(lambda m: f"{m.group(1)}XXXXXX{m.group(2)}", text)
