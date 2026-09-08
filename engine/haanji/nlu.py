"""Small, shared, deterministic language understanding.

Both the dialogue policy and the speculation predictor read the caller's words
through *this* module. That is deliberate, and it is what makes Speculative
Turn Execution correct rather than lucky: a speculation is only ever used when
its arguments are byte-identical to the arguments the real turn later asks
for, so the two paths must derive those arguments the same way. Sharing one
extractor makes the identity structural instead of coincidental.
"""
from __future__ import annotations
import re

# Hindi, English and Bengali forms side by side: the same extractor serves
# Hinglish and Benglish callers, which is what lets one engine run a Kolkata
# clinic without a code fork.
DATE_WORDS = {"kal", "aaj", "parso", "today", "tomorrow", "somvar", "mangalvar", "budhvar",
              "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
              "tarikh", "date",
              "kalke", "aajke", "porshu", "tarikhe"}
TIME_WORDS = {"baje", "subah", "shaam", "dopahar", "raat", "morning", "evening",
              "afternoon", "night", "am", "pm", "bje",
              "shokale", "shokal", "bikele", "shondhe", "raate", "tay", "ta"}
BOOKING_VERBS = {"milega", "milegi", "chahiye", "book", "booking", "appointment",
                 "slot", "lagwana", "dikhana", "aana", "aaunga", "aungi", "aaungi", "time",
                 "khaali", "free", "karwana", "karana",
                 "chai", "lagbe", "hobe", "korate", "korbo", "korano", "nebo"}
QUESTION_WORDS = {"kitna", "kitne", "kitni", "kya", "kaunsa", "kaun", "kab", "kaise",
                  "charge", "charges", "fees", "fee", "price", "rate", "cost", "how",
                  "what", "when", "timing", "timings", "khulta", "band",
                  "koto", "kokhon", "kothay", "khola", "daam"}
IDENTITY_WORDS = {"mera", "meri", "naam", "number", "purani", "pehle", "last", "previous",
                  "my", "name", "registered"}
CANCEL_WORDS = {"cancel", "reschedule", "postpone", "aage", "badalna", "change", "hata"}
HANDOFF_WORDS = {"insaan", "aadmi", "human", "manager", "owner", "sir", "madam", "baat",
                 "transfer", "connect"}
YES_WORDS = {"haan", "haanji", "ha", "ji", "yes", "yep", "yeah", "ok", "okay", "theek",
             "thik", "sahi", "bilkul", "confirm", "kardo", "kar", "do", "chalo", "pakka",
             "hyan", "ache", "achha", "hobe", "koro", "korun"}
NO_WORDS = {"nahi", "nahin", "na", "no", "nope", "mat", "ruko", "galat", "cancel", "nhi"}

_WORD = re.compile(r"[a-zA-Zऀ-ॿ]+")
_DIGITS = re.compile(r"\d")
WEEKDAYS = {"somvar": "monday", "mangalvar": "tuesday", "budhvar": "wednesday",
            "guruvar": "thursday", "shukravar": "friday", "shanivar": "saturday",
            "ravivar": "sunday", "monday": "monday", "tuesday": "tuesday",
            "wednesday": "wednesday", "thursday": "thursday", "friday": "friday",
            "saturday": "saturday", "sunday": "sunday",
            "shombar": "monday", "mongolbar": "tuesday", "budhbar": "wednesday",
            "brihoshpotibar": "thursday", "shukrobar": "friday", "shonibar": "saturday",
            "robibar": "sunday"}

NAME_PATTERNS = [
    re.compile(r"(?:mera naam|my name is|naam hai|naam|amar naam|nam)\s+"
               r"([a-zA-Z]+(?:\s+[a-zA-Z]+)?)", re.I),
    re.compile(r"^([a-zA-Z]+(?:\s+[a-zA-Z]+)?)\s+(?:bol raha|bol rahi|speaking)", re.I),
]
_NAME_TAIL = {"hai", "hun", "hoon", "se", "ji", "bol", "raha", "rahi", "bolta", "bolti"}


def words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)}


def normalise_date(text: str, fallback: str | None = None) -> str:
    """Map date language onto the canonical tokens the availability tool takes."""
    w = words(text)
    if "parso" in w or "porshu" in w or ("day" in w and "after" in w):
        return "day_after_tomorrow"
    if "kal" in w or "kalke" in w or "tomorrow" in w:
        return "tomorrow"
    if "aaj" in w or "aajke" in w or "today" in w:
        return "today"
    for token in w:
        if token in WEEKDAYS:
            return WEEKDAYS[token]
    return fallback or "tomorrow"


def normalise_time(text: str) -> str | None:
    """'11 baje subah' -> '11:00', 'shaam 5 baje' -> '17:00'."""
    t = text.lower()
    m = re.search(r"\b(\d{1,2})[:. ]?(\d{2})?\s*(am|pm|baje|bje)?", t)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    if hour > 23 or minute > 59:
        return None
    evening = any(k in t for k in ("pm", "shaam", "raat", "evening", "night",
                                   "bikele", "shondhe", "raate"))
    morning = any(k in t for k in ("am", "subah", "morning", "shokal"))
    if evening and hour < 12:
        hour += 12
    elif morning and hour == 12:
        hour = 0
    elif not evening and not morning and hour <= 7:
        hour += 12          # "5 baje" at a clinic means the evening slot
    return f"{hour:02d}:{minute:02d}"


def match_service(text: str, services) -> str | None:
    """Longest surface match, so 'root canal' beats 'canal'.

    ``services`` may be a list of catalogue names or an alias map produced by
    :meth:`Pack.service_aliases`; the alias map is what production uses, so
    that "rct" and "root canal treatment" both resolve to one service."""
    t = f" {text.lower()} "
    if isinstance(services, dict):
        hits = [(k, v) for k, v in services.items() if f" {k} " in t]
        return max(hits, key=lambda p: len(p[0]))[1] if hits else None
    hits = [s for s in services if f" {s.lower()} " in t]
    return max(hits, key=len) if hits else None


def find_entities(text: str, index: dict[str, str]) -> set[str]:
    """Every catalogue entity named in a sentence, in canonical form."""
    t = f" {text.lower()} "
    return {canonical for alias, canonical in index.items() if f" {alias} " in t}


def extract_name(text: str) -> str | None:
    for pat in NAME_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        parts = [p for p in m.group(1).split() if p.lower() not in _NAME_TAIL]
        if parts:
            return " ".join(p.capitalize() for p in parts[:2])
    # Callers very often answer "naam aur number?" with just "Anita Rao 98…".
    # Only trust this shape when a number is present in the same breath.
    if extract_phone(text):
        alpha = [w for w in re.findall(r"[A-Za-z]+", text)
                 if w.lower() not in _NAME_TAIL and w.lower() not in YES_WORDS
                 and w.lower() not in {"number", "mera", "meri", "naam", "phone", "mobile", "hai"}]
        if 1 <= len(alpha) <= 3:
            return " ".join(w.capitalize() for w in alpha[:2])
    return None


def bare_name(text: str) -> str | None:
    """The reply to "kis naam se booking karun?" — a name with nothing around
    it. Grammar and yes/no words are filtered so "haan theek hai" never becomes
    a customer called Theek."""
    alpha = [w for w in re.findall(r"[A-Za-z]+", text)
             if w.lower() not in _NAME_TAIL and w.lower() not in YES_WORDS
             and w.lower() not in NO_WORDS
             and w.lower() not in {"number", "mera", "meri", "amar", "naam", "nam",
                                   "phone", "mobile", "se", "booking", "karun"}]
    if 1 <= len(alpha) <= 3:
        return " ".join(w.capitalize() for w in alpha[:2])
    return None


def extract_phone(text: str) -> str | None:
    digits = "".join(_DIGITS.findall(text))
    if len(digits) >= 10:
        return digits[-10:]
    return None


def is_affirmative(text: str) -> bool:
    w = words(text)
    return bool(w & YES_WORDS) and not (w & NO_WORDS)


def is_negative(text: str) -> bool:
    return bool(words(text) & NO_WORDS)


def wants_handoff(text: str) -> bool:
    w = words(text)
    return bool(w & HANDOFF_WORDS) and bool(w & {"baat", "transfer", "connect", "human",
                                                 "insaan", "aadmi", "manager", "owner"})
