"""Closed-vocabulary repair for the words a booking's date and time are made of.

REPORT §9 item 4: the calls that still fail under noise are the ones where a
date or number word was corrupted, and no tenant lexicon contains "udya" or
"saade". This module is the small second lexicon the bridge consults after
the tenant's own: the number words 1–31, the weekdays, the relative days
(aaj / kal / parso and their Bengali and Marathi forms), the parts of the day,
the clock words (baje, tay, vajta) and the fractions (saade, sava, paune), in
the three romanisations the packs speak. Every word list is imported from
``haanji.nlu``, the module the policy reads dates and times with, so the
repair can only ever produce a word the policy understands.

The rule is the bridge's own two-condition rule (low confidence *and* an exact
sound-key match within the edit bound), with four more guards because a wrong
number is worse than a wrong spelling:

* a token that is already a known date, time or number word is never touched,
  so "saat" is never respelled "sat" and no number becomes a different number;
* when the candidates within the bound disagree about what the word means
  (two different numbers, two different parts of the day) nothing is done;
* the edit bound depends on length. The distance is taken over
  vowel-length-folded spellings (aa/a, ee/i, oo/u are one letter), because a
  doubled vowel is a spelling choice, not a sound, and it is the confusion
  recognisers make most ("oodya" is "udya", not two edits away from it). A
  word of fewer than five folded letters is repaired only when the folding
  alone explains it (kaal/kal, soobah/subah, sham/shaam); five letters tolerate
  one edit (gyara/gyarah, sakli/sakali); the bridge's bound applies from six.
  This closed vocabulary is dense in short words, and a probe of 519 common
  call words showed what one edit on a four-letter word does: "root" became
  "raat", "seat" "saat", "haath" "aath", "thoda" "today", and "tean" would be
  "ten" (10) rather than "teen" (3);
* a word the engine already knows is never a number: the grammar, question,
  booking and farewell vocabularies of ``nlu`` and the call-word table of
  ``devanagari`` are imported as a stop list, so "baar", "bahar", "dono" and
  "late" stay what they are;
* a word of the tenant's own vocabulary is never a number ("Pune" is a
  place, not "paune"), a digit string is never touched, and a token inside a
  run of three or more numbers (a phone number being dictated) is left alone.
"""
from __future__ import annotations
import re
from dataclasses import dataclass

from .. import nlu
from ..devanagari import WORDS as _CALL_WORDS
from .phonetics import edit_distance, phonetic_key

# Relative-day and marker words that are too generic to repair *into*: a
# corrupted "bade" must not become "baad", and "din" is three letters anyway.
_GENERIC_DATE_WORDS = {"din", "baad", "week", "hafte", "date", "may", "mar"}
NUMERIC_WEIGHT = 0.5          # what a temporal repair records as its entry weight
MIN_LEN = 4                   # a shorter token is never evidence of anything (as in the bridge)
_LONG_VOWEL = re.compile(r"aa|ee|ii|oo|uu")
_FOLD = {"aa": "a", "ee": "i", "ii": "i", "oo": "u", "uu": "u"}

# Words the engine already knows as something other than a date, time or
# number. Imported, not retyped: the policy's own vocabularies and the
# transliteration table of the words a booking call is made of, plus the
# everyday words the probe above found one edit from a number.
COMMON_WORDS: frozenset[str] = frozenset(
    set(_CALL_WORDS) | nlu.BOOKING_VERBS | nlu.QUESTION_WORDS | nlu.IDENTITY_WORDS | nlu.CANCEL_WORDS
    | nlu.RESCHEDULE_WORDS | nlu.HANDOFF_WORDS | nlu.YES_WORDS | nlu.NO_WORDS | nlu.FAREWELL_WORDS
    | set(nlu._NOT_A_NAME) | set(nlu._RELATIONS) | set(nlu._PEOPLE_WORDS)      # noqa: SLF001 - same package
    | {"bahar", "andar", "upar", "neeche", "aage", "peeche", "seat", "late", "early", "haath", "pair",
       "adha", "aadha", "seedha", "bura", "bhara", "bhari", "khara", "saath", "sath", "sabhi", "baar"}
)


def fold_vowels(word: str) -> str:
    """The spelling with doubled vowels written once, the way the sound key
    hears them: kaal/kal, soobah/subah, teen/tin."""
    return _LONG_VOWEL.sub(lambda m: _FOLD[m.group(0)], word.lower())


def edits_allowed(folded_len: int, max_edit: int) -> int:
    """How many edits a word of that many folded letters may be from a form."""
    if folded_len < 5:
        return 0
    if folded_len == 5:
        return 1
    return max_edit


@dataclass(frozen=True)
class TemporalEntry:
    surface: str
    meaning: str          # "7" | "tomorrow" | "monday" | "11" (month) | "morning" | "half" | "oclock" | "date"
    kind: str             # NUMBER | DAY | WEEKDAY | MONTH | PERIOD | FRACTION | CLOCK | MARKER


def _time_meaning(word: str) -> tuple[str, str]:
    if word in nlu.MORNING_WORDS:
        return "morning", "PERIOD"
    if word in nlu.AFTERNOON_WORDS:
        return "afternoon", "PERIOD"
    if word in nlu.EVENING_WORDS:
        return "evening", "PERIOD"
    if word in nlu._HALF:                      # noqa: SLF001 - the policy's own tables
        return "half", "FRACTION"
    if word in nlu._QUARTER_PAST:              # noqa: SLF001
        return "quarter_past", "FRACTION"
    if word in nlu._QUARTER_TO:                # noqa: SLF001
        return "quarter_to", "FRACTION"
    if word == "dedh":
        return "1:30", "FRACTION"
    if word in ("dhai", "adhai"):
        return "2:30", "FRACTION"
    return "oclock", "CLOCK"                   # baje, bje, tay, ta, vajta, ...


def _date_meaning(word: str) -> tuple[str, str] | None:
    if word in nlu.WEEKDAYS:
        return nlu.WEEKDAYS[word], "WEEKDAY"
    if word in nlu.MONTHS:
        return f"month:{nlu.MONTHS[word]}", "MONTH"
    if word in _GENERIC_DATE_WORDS:
        return None
    relative = nlu.normalise_date(word)
    if relative:
        return relative, "DAY"
    return "date", "MARKER"                    # tarikh, tarik, tareekh, tarikhe


def build_entries() -> list[TemporalEntry]:
    """Every form the policy understands, in a stable order (the first spelling
    of a meaning is the one a tie falls back to)."""
    entries: list[TemporalEntry] = []
    seen: set[str] = set()

    def add(surface: str, meaning: str, kind: str) -> None:
        if surface.isalpha() and surface not in seen:
            seen.add(surface)
            entries.append(TemporalEntry(surface, meaning, kind))

    for word, value in nlu.NUMBER_WORDS.items():
        add(word, str(value), "NUMBER")
    for word in sorted(nlu.WEEKDAYS):
        add(word, nlu.WEEKDAYS[word], "WEEKDAY")
    for word in sorted(nlu.DATE_WORDS):
        meaning = _date_meaning(word)
        if meaning:
            add(word, *meaning)
    for word in sorted(nlu.TIME_WORDS):
        add(word, *_time_meaning(word))
    return entries


class TemporalLexicon:
    """The closed vocabulary, indexed by sound key like the tenant lexicon."""

    def __init__(self, entries: list[TemporalEntry] | None = None):
        self.entries = entries if entries is not None else build_entries()
        self.forms: set[str] = {e.surface for e in self.entries}
        self.by_key: dict[str, list[TemporalEntry]] = {}
        for e in self.entries:
            key = phonetic_key(e.surface)
            if key:
                self.by_key.setdefault(key, []).append(e)
        self.numbers: set[str] = {e.surface for e in self.entries if e.kind == "NUMBER"}

    def is_form(self, token: str) -> bool:
        return token.lower() in self.forms

    def is_number(self, token: str) -> bool:
        return token.isdigit() or token.lower() in self.numbers

    def candidates(self, token: str, max_edit: int) -> list[tuple[int, TemporalEntry]]:
        """Entries whose key equals the token's, within the length-dependent
        edit bound taken over vowel-folded spellings (see the module note)."""
        low = token.lower()
        key = phonetic_key(low)
        folded = fold_vowels(low)
        out: list[tuple[int, TemporalEntry]] = []
        for entry in self.by_key.get(key, ()):
            form = fold_vowels(entry.surface)
            allowed = edits_allowed(min(len(folded), len(form)), max_edit)
            distance = edit_distance(folded, form, cap=allowed + 1)
            if distance <= allowed:
                out.append((distance, entry))
        return out

    def repair(self, token: str, max_edit: int) -> TemporalEntry | None:
        """The one entry a doubtful token should become, or None when there is
        none, when the token is too short, already a known form or a word the
        engine knows as something else, or when the candidates do not agree on
        a meaning."""
        low = token.lower()
        if not low.isalpha() or len(low) < MIN_LEN or low in self.forms or low in COMMON_WORDS:
            return None
        found = self.candidates(low, max_edit)
        if not found:
            return None
        meanings = {e.meaning for _, e in found}
        if len(meanings) != 1:
            return None                        # could become a different number: refuse
        found.sort(key=lambda pair: pair[0])
        return found[0][1]


_SHARED: TemporalLexicon | None = None


def temporal_lexicon() -> TemporalLexicon:
    global _SHARED
    if _SHARED is None:
        _SHARED = TemporalLexicon()
    return _SHARED


def temporal_tokens(text: str) -> set[str]:
    """The date, time and number words in a sentence, lower-cased; what the
    benchmark's date_time_error_rate is measured over."""
    forms = temporal_lexicon().forms
    return {w.lower().strip(".,?!") for w in text.split() if w.lower().strip(".,?!") in forms}


def number_runs(tokens: list[str], lexicon: TemporalLexicon, max_edit: int,
                min_run: int = 3) -> list[bool]:
    """Mark tokens that sit in a run of ``min_run`` or more number-like tokens:
    digits, number words, or tokens the lexicon would repair into a number.
    That is a phone number or a code being dictated, and nothing in it is
    repaired."""
    numeric = []
    for tok in tokens:
        low = tok.lower()
        if lexicon.is_number(low):
            numeric.append(True)
            continue
        cand = lexicon.repair(low, max_edit)
        numeric.append(bool(cand and cand.kind == "NUMBER"))
    inside = [False] * len(tokens)
    i = 0
    while i < len(tokens):
        if not numeric[i]:
            i += 1
            continue
        j = i
        while j < len(tokens) and numeric[j]:
            j += 1
        if j - i >= min_run:
            for k in range(i, j):
                inside[k] = True
        i = j
    return inside
