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

from ..config import BhashaConfig
from ..models import Correction, CorrectedTranscript, Token, Transcript
from .lexicon import TYPE_PRIOR, LexEntry, TenantLexicon
from .phonetics import edit_distance, phonetic_key, phrase_key

# Tokens that are never corrected: grammar words, and anything that looks like a
# personal name the caller just introduced.
STOPWORDS = {
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
        corrections: list[Correction] = []
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

        text = " ".join(w for w in out if w)
        return CorrectedTranscript(text, corrections, (time.perf_counter() - t0) * 1000)

    # ------------------------------------------------------------------ helpers
    def _correctable(self, span: list[str], conf: float, words: list[str], i: int) -> bool:
        if conf >= self.cfg.conf_high:
            return False                       # condition 1 fails
        if len(span) == 1 and span[0].lower() in STOPWORDS:
            return False
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
