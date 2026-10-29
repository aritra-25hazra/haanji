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
     _rx(r"\b(khoon|blood|bleeding|rakt\w*|rokto)\b"),
     _rx(r"(aa rah|nahi ruk|ruk nahi|band nahi|bahut|zyada|non ?stop|porche|"
         r"bondho hochhe na|khub|besh|khup|yet aahe|thambat nahi)")),
    ("emergency.acute", Action.ESCALATE,
     _rx(r"\b(accident|fracture|behosh|faint|chakkar|saans nahi|emergency|"
         r"unbearable|bardasht nahi|asahniya|asahya|shwas yet nahi)\b"), None),
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
    # "dawai ki dukaan paas hai?" is a directions question; "kaunsi dawai lun"
    # is a request for a prescription. The qualifier tells them apart.
    ("advice.medicine", Action.REFUSE,
     _rx(r"\b(dawai|dawa|medicine|tablet|goli|dose|antibiotic|painkiller|prescri\w*|oshudh|aushadh)\b"),
     _rx(r"(lun|loon|le lu|le sakt|le lena|khaun|kha sakt|khana|batao|bataiye|bata do|suggest|recommend|"
         r"kaunsi|konsi|kaun si|kitni|likh|prescri|chahiye|de do|dijiye|kon|kokhon|kitna|kaise)")),
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


# Refusals that are not about the business's expertise get their own line:
# a discount question at a dental clinic should not be answered with "only
# the doctor can tell you that".
RULE_LINES = {
    "promise.discount": ("no_discount", "Discount ka faisla main nahi le sakta, par rate zaroor bata sakta hoon. "
                                        "Kaunsi service ke liye?"),
}


class Guard:
    """Pack-aware. A pack can switch a built-in rule off and add rules of its
    own (``guardrails.rules`` in the YAML); it cannot invent an exception to
    a built-in rule's intent."""

    def __init__(self, pack: Pack):
        self.pack = pack
        self.enabled = {rid for rid, *_ in RULES}
        if pack.guardrails.max_discount_pct > 0:
            self.enabled.discard("promise.discount")
        for rid in getattr(pack.guardrails, "disable", []) or []:
            self.enabled.discard(rid)
        self.extra: list[tuple[str, Action, re.Pattern, re.Pattern | None, str | None]] = []
        for r in getattr(pack.guardrails, "rules", []) or []:
            action = Action.ESCALATE if r.get("action") == "escalate" else Action.REFUSE
            self.extra.append((r["id"], action, _rx(r["match"]),
                               _rx(r["unless"]) if r.get("unless") else None, r.get("line")))

    def _line(self, rid: str, action: Action) -> str:
        from .speak import phrase
        if action is Action.ESCALATE:
            return self.pack.guardrails.escalation_line
        if rid in RULE_LINES:
            key, default = RULE_LINES[rid]
            return phrase(self.pack.language, key, default)
        return self.pack.guardrails.refusal_line

    def check(self, text: str) -> Verdict:
        for rid, action, subject, qualifier in RULES:
            if rid not in self.enabled:
                continue
            if not subject.search(text):
                continue
            if qualifier is not None and not qualifier.search(text):
                continue
            return Verdict(action, rid, self._line(rid, action))
        for rid, action, subject, unless, line in self.extra:
            if not subject.search(text):
                continue
            if unless is not None and unless.search(text):
                continue
            return Verdict(action, rid, line or self._line(rid, action))
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
