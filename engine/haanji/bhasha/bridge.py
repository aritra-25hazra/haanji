"""The runtime half of Bhasha Bridge: biasing hints and post-correction.

Two independent conditions must hold before any token is changed:

1. the recogniser was *not* confident about it, and
2. its phonetic key matches a lexicon entry exactly, and the surface edit
   distance is small.

Both are required because either one alone produces false corrections, and a
layer that damages good transcripts is worse than no layer at all.
"""
from __future__ import annotations
import re
import time

from .. import nlu
from ..config import BhashaConfig
from ..models import CorrectedTranscript, Correction, Transcript
from .lexicon import TYPE_PRIOR, LexEntry, TenantLexicon
from .numeric import NUMERIC_WEIGHT, number_runs, temporal_lexicon
from .phonetics import edit_distance, phonetic_key, phrase_key

# Tokens that are never corrected: grammar words, the words of the booking
# dialogue itself (a "slot" is never a tenant's entity, however close its sound
# key sits to one), and anything that looks like a personal name the caller
# just introduced. The second group was added after the real-recogniser pilot
# (research/collect/), where "slot" became "Salt" six times.
FRAME_WORDS = {
    "slot", "slots", "time", "timing", "timings", "book", "booking", "appointment",
    "branch", "number", "phone", "call", "price", "charge", "rate", "fees", "fee",
    "raha", "rahi", "rahe", "chahiye", "chahie", "milega", "milegi", "hoga", "hogi",
    "karna", "karni", "karwana", "karwani", "karana", "lena", "leni", "dena", "deni",
    "wala", "wali", "wale", "mein", "liye", "saath", "khali", "available",
}
# A span of three letters or fewer is never replaced on its own: too little
# signal to tell a mishearing from a different short word, and the corruption
# model (haanji/corrupt.py) never corrupts them either.
MIN_SINGLE_LEN = 4
STOPWORDS = FRAME_WORDS | {
    "ka", "ki", "ke", "ko", "se", "me", "mein", "par", "hai", "hain", "ho", "hu",
    "hoon", "kya", "kab", "kaun", "kitna", "kitne", "aur", "ya", "nahi", "haan",
    "ji", "aap", "main", "mera", "meri", "kal", "aaj", "parso", "subah", "shaam",
    "dopahar", "raat", "baje", "the", "a", "an", "is", "for", "at", "on", "of",
    "kalke", "aajke", "porshu", "hyan", "ache", "hobe", "chai", "lagbe", "amar",
    "ekta", "er", "ta", "tay", "shokale", "bikele", "khub",
}
NAME_INTRO = re.compile(
    r"(mera naam|naam hai|naam se|my name is|name is|ke naam)\s*$", re.IGNORECASE
)


class BhashaBridge:
    """Wraps a speech adapter with tenant-specific biasing and correction."""

    def __init__(self, lexicon: TenantLexicon, config: BhashaConfig | None = None):
        self.lexicon = lexicon
        self.cfg = config or BhashaConfig()
        self.temporal = temporal_lexicon()      # the closed date/time/number vocabulary

    # ------------------------------------------------------------------ biasing
    def hints(self) -> list[str]:
        """Surfaces to hand the recogniser as recognition hints."""
        if not self.cfg.enabled:
            return []
        return self.lexicon.hints(self.cfg.max_hints)

    # --------------------------------------------------------------- correction
    def correct(self, transcript: Transcript) -> CorrectedTranscript:
        t0 = time.perf_counter()
        if not self.cfg.enabled or not len(self.lexicon):
            return CorrectedTranscript(transcript.text, [], (time.perf_counter() - t0) * 1000)

        words = [t.text for t in transcript.tokens]
        confs = [t.confidence for t in transcript.tokens]
        words, confs, splits = self._split_merged(words, confs)
        corrections: list[Correction] = list(splits)
        used = [False] * len(words)
        out = list(words)

        # Longest n-grams first so "full body checkup" is not broken by a
        # single-token repair of "body".
        for n in range(min(self.cfg.max_ngram, len(words)), 0, -1):
            for i in range(0, len(words) - n + 1):
                if any(used[i:i + n]):
                    continue
                span = words[i:i + n]
                span_conf = min(confs[i:i + n])
                if not self._correctable(span, span_conf, words, i):
                    continue
                phrase = " ".join(span)
                key = phrase_key(phrase) if n > 1 else phonetic_key(phrase)
                if not key:
                    continue
                found = self._best_candidate(phrase, key, span_conf, n)
                if found is None:
                    continue
                best, matched_form = found
                out[i] = best.surface
                for k in range(i + 1, i + n):
                    out[k] = ""
                for k in range(i, i + n):
                    used[k] = True
                corrections.append(Correction(
                    from_token=phrase, to_surface=best.surface,
                    asr_confidence=span_conf, entry_weight=best.weight, ngram=n))

        if self.cfg.numeric_repair:
            corrections += self._repair_temporal(words, confs, used, out)

        text = " ".join(w for w in out if w)
        return CorrectedTranscript(text, corrections, (time.perf_counter() - t0) * 1000)

    # --------------------------------------------------------- dates and times
    def _tenant_words(self) -> set[str]:
        """Every word of every form the tenant registered. A tenant's own word
        is never a number: "Pune" is a place, not "paune"."""
        cache = getattr(self, "_tenant_word_cache", None)
        if cache is None or cache[0] != len(self.lexicon):
            table = {w.lower() for e in self.lexicon.entries for f in e.forms() for w in f.split()}
            self._tenant_word_cache = (len(self.lexicon), table)
            cache = self._tenant_word_cache
        return cache[1]

    def _repair_temporal(self, words: list[str], confs: list[float], used: list[bool],
                         out: list[str]) -> list[Correction]:
        """The closed-vocabulary pass (haanji/bhasha/numeric.py) over the tokens
        the tenant pass left alone: the same two conditions, single tokens
        only, plus the guards the module states."""
        found: list[Correction] = []
        inside_number = number_runs(words, self.temporal, self.cfg.max_edit)
        for i, word in enumerate(words):
            if used[i] or inside_number[i]:
                continue
            low = word.lower()
            if not low.isalpha() or len(low) < MIN_SINGLE_LEN:
                continue
            if not self._correctable([word], confs[i], words, i):
                continue
            if low in nlu.YES_WORDS or low in nlu.NO_WORDS or low in self._tenant_words():
                continue
            entry = self.temporal.repair(low, self.cfg.max_edit)
            if entry is None:
                continue
            out[i] = entry.surface
            used[i] = True
            found.append(Correction(from_token=word, to_surface=entry.surface,
                                    asr_confidence=confs[i], entry_weight=NUMERIC_WEIGHT, ngram=1))
        return found

    # ------------------------------------------------------------ merged tokens
    MIN_MERGED_LEN = 8

    def _known_word(self, token: str) -> tuple[str, bool] | None:
        """A single word the engine would recognise on its own: a grammar or
        frame word (within one edit), or a one-word lexicon form (exact key
        and within one edit). Returns (canonical spelling, from the lexicon),
        or None."""
        low = token.lower()
        if low in STOPWORDS:
            return low, False
        if len(low) >= 3:
            for w in STOPWORDS:
                if abs(len(w) - len(low)) <= 1 and edit_distance(low, w, cap=1) <= 1:
                    return w, False
        key = phonetic_key(low)
        if key:
            for entry in self.lexicon.candidates(key):
                for form in entry.forms_matching(key, 1):
                    if edit_distance(low, form, cap=1) <= 1:
                        return form, True
            # a word of a longer form ("root" of "root canal"): the n-gram
            # pass will repair the phrase once the halves are apart
            for w in self._component_words().get(key, ()):
                if edit_distance(low, w, cap=1) <= 1:
                    return w, True
        return None

    def _component_words(self) -> dict[str, set[str]]:
        cache = getattr(self, "_components", None)
        if cache is None or cache[0] is not len(self.lexicon):
            table: dict[str, set[str]] = {}
            for entry in self.lexicon.entries:
                for form in entry.forms():
                    for w in form.lower().split():
                        if len(w) >= 3:
                            table.setdefault(phonetic_key(w), set()).add(w)
            self._components = (len(self.lexicon), table)
            cache = self._components
        return cache[1]

    def _split_merged(self, words: list[str], confs: list[float]):
        """Real recognisers run words together ("subhahroot"). A long,
        low-confidence token that is not itself a known word is split at the
        point where *both* halves are known words and at least one of them
        is a catalogue word; two grammar words glued together ("ko karni")
        are not worth touching. The n-gram pass then repairs the halves."""
        out_w: list[str] = []
        out_c: list[float] = []
        splits: list[Correction] = []
        for word, conf in zip(words, confs):
            low = word.lower()
            if (len(low) < self.MIN_MERGED_LEN or conf >= self.cfg.conf_high or not low.isalpha()
                    or self._known_word(low) is not None):
                out_w.append(word)
                out_c.append(conf)
                continue
            # A token the lexicon can explain as a whole ("koolkarni" is two
            # edits from Kulkarni) is the n-gram pass's job; splitting it
            # first would hand it to the grammar words ("ko karni") instead.
            key = phonetic_key(low)
            if key and self._best_candidate(low, key, conf, 1) is not None:
                out_w.append(word)
                out_c.append(conf)
                continue
            found = None
            for cut in range(3, len(low) - 2):
                left, right = self._known_word(low[:cut]), self._known_word(low[cut:])
                if left and right and (left[1] or right[1]):
                    found = (left[0], right[0])
                    break
            if found is None:
                out_w.append(word)
                out_c.append(conf)
                continue
            left, right = found
            out_w += [left, right]
            out_c += [conf, conf]
            splits.append(Correction(from_token=word, to_surface=f"{left} {right}",
                                     asr_confidence=conf, entry_weight=0.0, ngram=1))
        return out_w, out_c, splits

    # ------------------------------------------------------------------ helpers
    def _correctable(self, span: list[str], conf: float, words: list[str], i: int) -> bool:
        if conf >= self.cfg.conf_high:
            return False                       # condition 1 fails
        if len(span) == 1 and span[0].lower() in STOPWORDS:
            return False
        if len(span) == 1 and len(span[0]) < MIN_SINGLE_LEN:
            return False                       # too short to be evidence of anything
        preceding = " ".join(words[max(0, i - 3):i])
        if NAME_INTRO.search(preceding):
            return False                       # never "correct" a personal name
        return True

    def _best_candidate(self, phrase: str, key: str, conf: float,
                        n: int) -> tuple[LexEntry, str] | None:
        """Pick the lexicon entry whose *matched form* is closest to the span.

        The comparison is against the form that produced the key, and the
        replacement is the entry's canonical surface. That is what lets
        "cleening" become "teeth cleaning" without letting "teeth cleaning"
        sit two edits away from every short word in the language."""
        allowed = self.cfg.max_edit + (1 if n > 1 else 0)
        best: tuple[float, LexEntry, str] | None = None
        for entry in self.lexicon.candidates(key):
            for form in entry.forms_matching(key, n):
                if form.lower() == phrase.lower():
                    return None                # heard exactly as the tenant spells it
                if sum(ch.isalpha() for ch in form) < MIN_SINGLE_LEN:
                    continue                   # "t3 t4" is not evidence for "to do"
                distance = edit_distance(phrase, form, cap=allowed + 1)
                if distance > allowed:
                    continue                   # condition 2 fails
                score = self._score(entry, conf) - 0.15 * distance
                if best is None or score > best[0]:
                    best = (score, entry, form)
        if best is None:
            return None
        return best[1], best[2]

    @staticmethod
    def _score(entry: LexEntry, conf: float) -> float:
        return entry.weight * (1.0 - conf) * TYPE_PRIOR.get(entry.entry_type, 1.0)

    # ------------------------------------------------------------------ feedback
    def reinforce(self, corrections: list[Correction], *, succeeded: bool) -> None:
        delta = 0.05 if succeeded else -0.10
        for c in corrections:
            self.lexicon.reinforce(c.to_surface, delta)
