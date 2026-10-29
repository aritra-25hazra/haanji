"""Small, shared, deterministic language understanding.

Both the dialogue policy and the speculation predictor read the caller's words
through *this* module. That is deliberate, and it is what makes Speculative
Turn Execution correct rather than lucky: a speculation is only ever used when
its arguments are byte-identical to the arguments the real turn later asks
for, so the two paths must derive those arguments the same way. Sharing one
extractor makes the identity structural instead of coincidental.

Two rules this module follows, learned from probing it with real callers'
phrasings (2026-10-29):

* **Never guess a date or a time.** "15 tarikh" used to become "tomorrow";
  "saade das" used to become 10:00. An unresolved date now stays unresolved
  (the policy asks), and the Hindi, Bengali and Marathi fractions and number
  words are read properly.
* **Never glue digits across words.** "98765 43210 hai aur 2 log" is one
  phone number and a party of two, not the number 8765432102.
"""
from __future__ import annotations
import datetime as dt
import re

# Hindi, English, Bengali and Marathi forms side by side: the same extractor
# serves Hinglish, Benglish and Marathinglish callers, which is what lets one
# engine run a Kolkata clinic without a code fork.
DATE_WORDS = {"kal", "aaj", "parso", "today", "tomorrow", "somvar", "mangalvar", "budhvar",
              "guruvar", "shukravar", "shanivar", "ravivar",
              "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
              "tarikh", "tarik", "tareekh", "date",
              "kalke", "aajke", "porshu", "tarikhe",
              "udya", "parva", "hafte", "week", "din", "baad",
              "january", "february", "march", "april", "may", "june", "july", "august",
              "september", "october", "november", "december",
              "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
              "janvari", "farvari", "agast", "sitambar", "aktubar", "navambar", "disambar"}
TIME_WORDS = {"baje", "subah", "shaam", "dopahar", "raat", "morning", "evening",
              "afternoon", "night", "am", "pm", "bje",
              "saade", "sadhe", "sade", "paune", "poune", "sava", "sawa", "dedh", "dhai", "adhai",
              "shokale", "shokal", "bikele", "bikel", "dupure", "dupur", "shondhe", "raate", "tay", "ta", "share",
              "sakali", "sakalchi", "dupari", "sandhyakali", "ratri", "vajta", "vaajta", "vajata"}
BOOKING_VERBS = {"milega", "milegi", "chahiye", "book", "booking", "appointment",
                 "slot", "lagwana", "dikhana", "aana", "aaunga", "aungi", "aaungi", "time",
                 "khaali", "free", "karwana", "karana", "karwani", "karani",
                 "chai", "lagbe", "hobe", "korate", "korbo", "korano", "nebo",
                 "pahije", "hava", "havi", "hvay", "milel", "kara", "karaychi", "karayche", "karaycha"}
QUESTION_WORDS = {"kitna", "kitne", "kitni", "kya", "kaunsa", "kaun", "kab", "kaise",
                  "charge", "charges", "fees", "fee", "price", "rate", "cost", "how",
                  "what", "when", "timing", "timings", "khulta", "band",
                  "koto", "kokhon", "kothay", "khola", "daam",
                  "kiti", "kadhi", "kuthe", "kay", "kasa", "kashi", "kevha"}
IDENTITY_WORDS = {"mera", "meri", "naam", "number", "purani", "pehle", "last", "previous",
                  "my", "name", "registered"}
CANCEL_WORDS = {"cancel", "hata", "hatao", "cancle", "radd"}
RESCHEDULE_WORDS = {"reschedule", "postpone", "aage", "badalna", "badalni", "badalo", "badal", "badlo", "badli",
                    "badle", "badlna", "change", "shift", "move", "prepone", "peeche", "dusre", "doosre", "alag",
                    "bodlate", "bodlao", "badla", "badlun"}
HANDOFF_WORDS = {"insaan", "aadmi", "human", "manager", "owner", "sir", "madam", "baat",
                 "transfer", "connect"}
YES_WORDS = {"haan", "haanji", "ha", "ji", "yes", "yep", "yeah", "ok", "okay", "theek",
             "thik", "sahi", "bilkul", "confirm", "kardo", "kar", "do", "chalo", "pakka",
             "hyan", "ache", "achha", "hobe", "koro", "korun",
             "ho", "hoy", "barobar", "chalel", "nakki", "kara"}
NO_WORDS = {"nahi", "nahin", "na", "no", "nope", "mat", "ruko", "galat", "cancel", "nhi", "naahi", "nako"}
# Words that end a call on their own. "nahi" alone is *not* here: with a slot
# on the table it is a rejection, and with a date beside it a correction.
FAREWELL_WORDS = {"bye", "byee", "dhanyavaad", "dhanyawad", "dhanyavad", "thanks", "thank", "shukriya",
                  "alvida", "bas", "itna", "yahi", "khatam", "dhonnobad", "thak", "eituku",
                  "evdhach", "evadhach", "itkach", "purey"}

# Number words in the three languages the packs speak. Collisions are
# intentional ("char" is four everywhere); ambiguities with everyday words
# ("do" = two / "kar do") are resolved by only reading a number word when a
# time or date word stands next to it.
NUMBER_WORDS: dict[str, int] = {
    "ek": 1, "do": 2, "teen": 3, "tin": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "pach": 5,
    "chhe": 6, "che": 6, "chhah": 6, "chhoy": 6, "choy": 6, "saha": 6, "saat": 7, "sat": 7, "shat": 7,
    "aath": 8, "ath": 8, "aat": 8, "nau": 9, "noy": 9, "das": 10, "dus": 10, "dosh": 10, "dash": 10, "daha": 10,
    "gyarah": 11, "gyaarah": 11, "egaro": 11, "akra": 11, "baarah": 12, "barah": 12, "bara": 12, "baro": 12,
    "terah": 13, "tera": 13, "chaudah": 14, "chouddo": 14, "pandrah": 15, "pandra": 15, "ponero": 15,
    "solah": 16, "sola": 16, "satrah": 17, "satra": 17, "atharah": 18, "athara": 18, "unnis": 19, "unis": 19,
    "bees": 20, "bis": 20, "ikkis": 21, "ekkis": 21, "bais": 22, "baees": 22, "teis": 23, "tees": 30, "tis": 30,
    "chaubis": 24, "chobis": 24, "pachchis": 25, "pachees": 25, "pochish": 25, "chhabbis": 26, "sattais": 27,
    "atthais": 28, "untees": 29, "ikattis": 31, "ektis": 31,
    "dui": 2, "don": 2, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_HALF = {"saade", "sadhe", "sade", "sarhe", "share", "sare"}
_QUARTER_PAST = {"sava", "sawa", "shoa", "sowa", "sabba"}
_QUARTER_TO = {"paune", "poune", "pauney"}
MORNING_WORDS = {"subah", "morning", "am", "shokale", "shokal", "sakali", "sakalchi", "savere", "sawere"}
AFTERNOON_WORDS = {"dopahar", "afternoon", "dupure", "dupur", "dupari", "noon", "lunch"}
EVENING_WORDS = {"shaam", "raat", "evening", "night", "pm", "bikele", "bikel", "shondhe", "raate",
                 "sandhyakali", "ratri", "sham"}
_WEEK_WORDS = {"hafte", "hafta", "week", "saptah", "shoptaho", "athavda"}
_NEXT_WORDS = {"agle", "agla", "agli", "next", "porer", "pudhchya", "pudhcha"}

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
MONTHS = {"january": 1, "jan": 1, "janvari": 1, "february": 2, "feb": 2, "farvari": 2, "march": 3, "mar": 3,
          "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8,
          "agast": 8, "september": 9, "sep": 9, "sept": 9, "sitambar": 9, "october": 10, "oct": 10,
          "aktubar": 10, "november": 11, "nov": 11, "navambar": 11, "december": 12, "dec": 12, "disambar": 12}
_DAY_MARKERS = {"tarikh", "tarik", "tareekh", "tarikhe", "ko", "th", "st", "nd", "rd", "date"}

NAME_PATTERNS = [
    re.compile(r"(?:mera naam|my name is|naam hai|naam|amar naam|nam|maza naav|naav)\s+"
               r"([a-zA-Z]+(?:\s+[a-zA-Z]+)?)", re.I),
    re.compile(r"^([a-zA-Z]+(?:\s+[a-zA-Z]+)?)\s+(?:bol raha|bol rahi|speaking)", re.I),
]
_NAME_TAIL = {"hai", "hun", "hoon", "se", "ji", "bol", "raha", "rahi", "bolta", "bolti", "aahe", "achhi"}
# Grammar, relations and counting words that can sit beside a phone number
# but are never anybody's name.
_NOT_A_NAME = {"number", "mera", "meri", "mere", "amar", "maza", "naam", "nam", "naav", "phone", "mobile",
               "hai", "hain", "hoon", "hun", "se", "ji", "booking", "karun", "aur", "log", "logon", "logo",
               "dono", "bhi", "ke", "ki", "ka", "ko", "par", "pe", "mein", "me", "liye", "wife", "husband",
               "patni", "pati", "beta", "beti", "bachcha", "bachche", "mummy", "papa", "bhai", "behen",
               "mother", "father", "son", "daughter", "friend", "dost", "hum", "main", "aayenge", "aaunga",
               "aaungi", "aungi", "aayega", "aayegi", "jan", "jon", "people", "persons", "members",
               "ye", "yeh", "wo", "woh", "ye", "likh", "lo", "lijiye", "note", "kar", "karo", "do", "di",
               "ka", "ye", "ha", "haan", "ok", "okay", "theek", "sahi", "confirm"}


def words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text)}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-Zऀ-ॿ]+|\d+", text.lower())


def _number_at(tok: str) -> int | None:
    if tok.isdigit():
        return int(tok)
    return NUMBER_WORDS.get(tok)


# ------------------------------------------------------------------- dates
def normalise_date(text: str, fallback: str | None = None, today: dt.date | None = None) -> str | None:
    """Map date language onto the tokens the availability tool takes:
    ``today`` / ``tomorrow`` / ``day_after_tomorrow`` / a weekday / an ISO date.

    Returns ``fallback`` (which may be ``None``) when the sentence names no
    date it can resolve. It never guesses: "agle hafte" alone is ambiguous
    and the policy asks which day."""
    w = words(text)
    toks = _tokens(text)
    if "parso" in w or "porshu" in w or "parva" in w or ("day" in w and "after" in w):
        return "day_after_tomorrow"
    if "kal" in w or "kalke" in w or "udya" in w or "tomorrow" in w:
        return "tomorrow"
    if "aaj" in w or "aajke" in w or "today" in w:
        return "today"
    for token in w:
        if token in WEEKDAYS:
            return WEEKDAYS[token]
    base = today or dt.date.today()
    # "do din baad", "3 din baad", "in 2 days"
    for i, tok in enumerate(toks):
        if tok in ("din", "days", "day", "dino", "divas", "divsani", "diner") and i > 0:
            n = _number_at(toks[i - 1])
            if n is not None and 1 <= n <= 60 and (i + 1 < len(toks) and toks[i + 1] in ("baad", "bad", "por", "pore", "nantar", "later") or (i > 1 and toks[i - 2] == "in")):
                return (base + dt.timedelta(days=n)).isoformat()
    # "15 tarikh", "15 ko", "pandrah tarikh", "3 november", "nov 3", "15th"
    month = next((MONTHS[t] for t in toks if t in MONTHS), None)
    day_num = None
    for i, tok in enumerate(toks):
        n = _number_at(tok)
        if n is None or not (1 <= n <= 31):
            continue
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        prv = toks[i - 1] if i > 0 else ""
        if nxt in _DAY_MARKERS or (month is not None and (nxt in MONTHS or prv in MONTHS)):
            day_num = n
            break
    if day_num is not None:
        if month is not None:
            year = base.year if (month, day_num) >= (base.month, base.day) else base.year + 1
            try:
                return dt.date(year, month, day_num).isoformat()
            except ValueError:
                return fallback
        # No month: the next time that day-of-month comes round.
        y, m = base.year, base.month
        if day_num < base.day:
            m += 1
            if m > 12:
                m, y = 1, y + 1
        try:
            return dt.date(y, m, day_num).isoformat()
        except ValueError:
            return fallback
    return fallback


def date_unclear(text: str) -> bool:
    """The caller spoke about a day ("agle hafte", "tarikh") but
    :func:`normalise_date` could not pin it down."""
    w = words(text)
    return bool(w & (_WEEK_WORDS | {"tarikh", "tarik", "tareekh", "date"})) and normalise_date(text) is None


# ------------------------------------------------------------------- times
def _hour_minute(text: str) -> tuple[int, int] | None:
    """The clock reading in a sentence, 12-hour and before any am/pm logic."""
    t = text.lower()
    toks = _tokens(t)
    # Fixed idioms first: dedh = 1:30, dhai/adhai = 2:30.
    for i, tok in enumerate(toks):
        if tok == "dedh":
            return 1, 30
        if tok in ("dhai", "adhai"):
            return 2, 30
    # Fraction word + number: saade das / paune 11 / sava 9.
    for i, tok in enumerate(toks[:-1]):
        n = _number_at(toks[i + 1])
        if n is None or not (1 <= n <= 12):
            continue
        if tok in _HALF:
            return n, 30
        if tok in _QUARTER_PAST:
            return n, 15
        if tok in _QUARTER_TO:
            return (n - 1) or 12, 45
    # Digits: "11", "11:30", "11.30", "1130" is not accepted (phone numbers).
    m = re.search(r"(?<!\d)(\d{1,2})(?:[:.](\d{2}))?(?!\d)\s*(am|pm|baje|bje|vajta|vaajta|vajata|tay|ta|o'?clock)?", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if 0 <= hour <= 23 and minute <= 59:
            return hour, minute
    # Number word + clock word: "das baje", "egaro tay", "paanch vajta".
    for i, tok in enumerate(toks[:-1]):
        if toks[i + 1] in ("baje", "bje", "vajta", "vaajta", "vajata", "tay", "ta", "o", "oclock"):
            n = NUMBER_WORDS.get(tok)
            if n is not None and 1 <= n <= 12:
                return n, 0
    return None


def normalise_time(text: str) -> str | None:
    """'11 baje subah' -> '11:00', 'shaam 5 baje' -> '17:00',
    'saade das baje' -> '10:30', 'paune gyarah' -> '10:45'."""
    hm = _hour_minute(text)
    if hm is None:
        return None
    hour, minute = hm
    w = words(text)
    evening = bool(w & EVENING_WORDS)
    morning = bool(w & MORNING_WORDS)
    afternoon = bool(w & AFTERNOON_WORDS)
    if hour > 12:
        return f"{hour:02d}:{minute:02d}"
    if evening and hour < 12:
        hour += 12
    elif afternoon and hour < 12 and hour <= 6:
        hour += 12
    elif morning and hour == 12:
        hour = 0
    elif not evening and not morning and not afternoon and 1 <= hour <= 7:
        hour += 12          # "5 baje" at a clinic means the evening slot
    return f"{hour:02d}:{minute:02d}"


def time_period(text: str) -> str | None:
    """The part of the day the caller asked for, when they gave no clock
    time: 'kal shaam ko' -> 'evening'."""
    w = words(text)
    if w & EVENING_WORDS:
        return "evening"
    if w & AFTERNOON_WORDS:
        return "afternoon"
    if w & MORNING_WORDS:
        return "morning"
    return None


# ----------------------------------------------------------------- people
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


def match_staff(text: str, staff: list[str]) -> str | None:
    """'Dr Iyer se' -> 'Dr Iyer'. Matches on the distinctive part of the
    name (not the honorific), whole word, case-insensitive."""
    w = words(text)
    best: tuple[int, str] | None = None
    for person in staff:
        parts = [p.lower().strip(".") for p in person.split()]
        parts = [p for p in parts if p not in ("dr", "doctor", "mr", "mrs", "ms", "miss", "sir", "madam", "ji")]
        hit = [p for p in parts if len(p) >= 3 and (p in w or (len(p) >= 5 and any(
            len(x) >= 5 and _edit_distance(p, x) <= 1 for x in w)))]
        if hit:
            score = sum(len(p) for p in hit)
            if best is None or score > best[0]:
                best = (score, person)
    return best[1] if best else None


def _edit_distance(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def find_entities(text: str, index: dict[str, str]) -> set[str]:
    """Every catalogue entity named in a sentence, in canonical form."""
    t = f" {text.lower()} "
    return {canonical for alias, canonical in index.items() if f" {alias} " in t}


def extract_name(text: str) -> str | None:
    for pat in NAME_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        parts = [p for p in m.group(1).split() if p.lower() not in _NAME_TAIL and p.lower() not in _NOT_A_NAME]
        if parts:
            return " ".join(p.capitalize() for p in parts[:2])
    # Callers very often answer "naam aur number?" with just "Anita Rao 98…".
    # Only trust this shape when a number is present in the same breath.
    if extract_phone(text):
        skip = _NAME_TAIL | YES_WORDS | _NOT_A_NAME | DATE_WORDS | TIME_WORDS | BOOKING_VERBS | QUESTION_WORDS \
            | {"call", "karo", "kijiye", "please", "plz", "hello", "hi", "namaste"}
        alpha = [w for w in re.findall(r"[A-Za-z]+", text) if w.lower() not in skip]
        if 1 <= len(alpha) <= 3:
            return " ".join(w.capitalize() for w in alpha[:2])
    return None


def bare_name(text: str) -> str | None:
    """The reply to "kis naam se booking karun?" — a name with nothing around
    it. Grammar and yes/no words are filtered so "haan theek hai" never becomes
    a customer called Theek."""
    alpha = [w for w in re.findall(r"[A-Za-z]+", text)
             if w.lower() not in _NAME_TAIL and w.lower() not in YES_WORDS
             and w.lower() not in NO_WORDS and w.lower() not in _NOT_A_NAME]
    if 1 <= len(alpha) <= 3:
        return " ".join(w.capitalize() for w in alpha[:2])
    return None


_PHONE_RUN = re.compile(r"(?<![\d])(\+?\d[\d\s\-.]{8,16}\d)(?![\d])")


def extract_phone(text: str) -> str | None:
    """An Indian mobile number spoken or typed in one breath: ten digits,
    optionally with spaces or dashes between groups, optionally with +91 or a
    leading 0. Digits elsewhere in the sentence ("2 log") are never glued on."""
    for run in _PHONE_RUN.findall(text):
        digits = re.sub(r"\D", "", run)
        if len(digits) == 10 and digits[0] in "6789":
            return digits
        if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
            return digits[2:]
        if len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
            return digits[1:]
        if len(digits) == 13 and digits.startswith("091"):
            return digits[3:]
    return None


_RELATIONS = {"wife", "husband", "patni", "pati", "biwi", "beta", "beti", "bachcha", "bachche", "bachcho",
              "mummy", "papa", "maa", "amma", "bhai", "behen", "mother", "father", "son", "daughter",
              "friend", "dost", "parents", "bhabhi", "didi", "dada", "dadi", "nana", "nani", "saheli",
              "bou", "bor", "chhele", "meye", "bayko", "navra", "mulga", "mulgi"}
_PEOPLE_WORDS = {"log", "logon", "logo", "jan", "jon", "people", "persons", "person", "members", "mansa", "lok"}


def party_size(text: str) -> int | None:
    """How many people the booking is for, when the caller says so:
    'hum do log', '2 logon ke liye', 'mujhe aur meri wife ko', 'dono'."""
    toks = _tokens(text)
    w = set(toks)
    for i, tok in enumerate(toks[:-1]):
        if toks[i + 1] in _PEOPLE_WORDS:
            n = _number_at(tok)
            if n is not None and 2 <= n <= 10:
                return n
    if "dono" in w or "dujon" in w or "doghe" in w or "both" in w:
        return 2
    if w & _RELATIONS and (("aur" in w or "ar" in w or "ani" in w or "and" in w) or "bhi" in w or "shudhdha" in w):
        return 2
    return None


def is_affirmative(text: str) -> bool:
    w = words(text)
    return bool(w & YES_WORDS) and not (w & NO_WORDS)


def is_negative(text: str) -> bool:
    return bool(words(text) & NO_WORDS)


def is_farewell(text: str) -> bool:
    """A sentence that ends the call. "nahi" on its own counts only when it
    carries no new information (no day, time, service or question)."""
    w = words(text)
    if w & FAREWELL_WORDS:
        return True
    if not (w & NO_WORDS) or len(w) > 3:
        return False
    return not (w & (DATE_WORDS | TIME_WORDS | BOOKING_VERBS | QUESTION_WORDS | RESCHEDULE_WORDS)) \
        and not _DIGITS.search(text)


def wants_handoff(text: str) -> bool:
    w = words(text)
    return bool(w & HANDOFF_WORDS) and bool(w & {"baat", "transfer", "connect", "human",
                                                 "insaan", "aadmi", "manager", "owner"})


# ------------------------------------------------- shared tool arguments
def availability_args(text: str, ctx, services, staff: list[str] | None = None,
                      today: dt.date | None = None) -> dict | None:
    """The exact arguments ``check_availability`` will be asked for, derived
    from one sentence plus what the call already knows. The predictor and
    the policy both call this, so a speculated result can be claimed."""
    service = match_service(text, services) or getattr(ctx, "service", None)
    date = normalise_date(text, getattr(ctx, "date", None), today)
    if not date:
        return None
    args = {"service": service or "__default__", "date": date}
    clock = normalise_time(text) if words(text) & TIME_WORDS else None
    clock = clock or getattr(ctx, "time", None)
    if clock:
        args["at"] = clock
    else:
        period = time_period(text) or getattr(ctx, "period", None)
        if period:
            args["period"] = period
    person = match_staff(text, staff or []) or getattr(ctx, "staff", None)
    if person:
        args["staff"] = person
    party = party_size(text) or getattr(ctx, "party_size", 1) or 1
    if party > 1:
        args["party"] = party
    return args
