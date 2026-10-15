"""A corruption model learned from a real recogniser's output.

``corrupt.py`` substitutes a fixed list of confusions. This module fits the
substitutions, drops and merges a real recogniser actually made — from
(heard, truth) pairs such as the pilot in ``research/collect/`` — and
replays them at a chosen rate, so the synthetic experiments can be re-run
under noise shaped by data rather than by the authors. Same signature as
``corrupt.corrupt`` so the benchmark can swap one for the other.
"""
from __future__ import annotations
import difflib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .corrupt import PROTECTED

_ALPHA = re.compile(r"^[A-Za-z]+$")


def _norm(text: str) -> list[str]:
    return re.sub(r"[^\w\s']", " ", text.lower()).split()


class LearnedCorruption:
    """Token-level substitutions, character-level edits, drops and merges,
    each with the rate the data showed."""

    def __init__(self) -> None:
        self.word_subs: dict[str, Counter] = defaultdict(Counter)     # truth word -> heard words
        self.char_subs: Counter = Counter()                            # (truth ngram, heard ngram)
        self.n_tokens = 0
        self.n_substituted = 0
        self.n_dropped = 0
        self.n_merged = 0
        self.n_pairs = 0

    # ------------------------------------------------------------------ fit
    def fit(self, pairs: Iterable[tuple[str, str]]) -> "LearnedCorruption":
        for truth, heard in pairs:
            t, h = _norm(truth), _norm(heard)
            self.n_pairs += 1
            self.n_tokens += len(t)
            sm = difflib.SequenceMatcher(a=t, b=h, autojunk=False)
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    continue
                tw, hw = t[i1:i2], h[j1:j2]
                if tag == "delete" or (tag == "replace" and not hw):
                    self.n_dropped += len(tw)
                elif tag == "replace":
                    i = j = 0
                    while i < len(tw) and j < len(hw):
                        a, b = tw[i], hw[j]
                        # Two truth words heard as one long token: a merge.
                        if i + 1 < len(tw) and len(b) >= len(a) + len(tw[i + 1]) - 2 and b[:2] == a[:2]:
                            self.n_merged += 2
                            self.word_subs[f"{a} {tw[i + 1]}"][b] += 1
                            i += 2
                            j += 1
                            continue
                        self.n_substituted += 1
                        self.word_subs[a][b] += 1
                        if difflib.SequenceMatcher(a=a, b=b, autojunk=False).ratio() >= 0.5:
                            self._char_edits(a, b)            # a mishearing, not a different word
                        i += 1
                        j += 1
                    self.n_dropped += max(0, len(tw) - i)
        return self

    def _char_edits(self, a: str, b: str) -> None:
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            src, dst = a[i1:i2], b[j1:j2]
            if 0 < len(src) <= 3 and len(dst) <= 3:
                self.char_subs[(src, dst)] += 1

    # ------------------------------------------------------------- summary
    def rates(self) -> dict[str, Any]:
        n = max(self.n_tokens, 1)
        return {"pairs": self.n_pairs, "tokens": self.n_tokens,
                "substitution_rate": round(self.n_substituted / n, 4),
                "drop_rate": round(self.n_dropped / n, 4), "merge_rate": round(self.n_merged / n, 4),
                "word_substitutions": sum(sum(c.values()) for c in self.word_subs.values()),
                "char_confusions": len(self.char_subs),
                "top_char_confusions": [{"from": a, "to": b, "n": c} for (a, b), c in self.char_subs.most_common(15)]}

    def to_json(self) -> str:
        return json.dumps({"word_subs": {k: dict(v) for k, v in self.word_subs.items()},
                           "char_subs": [[a, b, c] for (a, b), c in self.char_subs.items()],
                           "counts": {"tokens": self.n_tokens, "substituted": self.n_substituted,
                                      "dropped": self.n_dropped, "merged": self.n_merged, "pairs": self.n_pairs}},
                          ensure_ascii=False, indent=1)

    @classmethod
    def from_json(cls, text: str) -> "LearnedCorruption":
        d = json.loads(text)
        m = cls()
        for k, v in d["word_subs"].items():
            m.word_subs[k] = Counter(v)
        m.char_subs = Counter({(a, b): c for a, b, c in d["char_subs"]})
        c = d["counts"]
        m.n_tokens, m.n_substituted, m.n_dropped, m.n_merged, m.n_pairs = (
            c["tokens"], c["substituted"], c["dropped"], c["merged"], c["pairs"])
        return m

    @classmethod
    def load(cls, path: str | Path) -> "LearnedCorruption":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- replay
    def corrupt_token(self, token: str, rng: random.Random) -> str:
        low = token.lower()
        seen = self.word_subs.get(low)
        if seen:
            heard = rng.choices(list(seen), weights=list(seen.values()))[0]
            if heard and heard != low:
                return heard
        # Otherwise apply one learned character confusion that fits this token.
        fits = [((a, b), c) for (a, b), c in self.char_subs.items() if a and a in low and b != a]
        if not fits:
            return token
        (a, b), _ = rng.choices([f for f, _ in fits], weights=[c for _, c in fits])[0], None
        return low.replace(a, b, 1)

    def corrupt(self, text: str, rate: float, rng: random.Random) -> tuple[str, list[str]]:
        """Same contract as ``corrupt.corrupt``: the heard text and the words
        to mark low-confidence. ``rate`` scales the learned per-token rates
        so the experiment can sweep noise as before; at rate = the learned
        substitution rate the output matches the recogniser's own mix."""
        out: list[str] = []
        low: list[str] = []
        base = max(self.n_substituted / max(self.n_tokens, 1), 1e-6)
        scale = rate / base
        p_sub = min(0.95, rate)
        p_drop = min(0.5, (self.n_dropped / max(self.n_tokens, 1)) * scale)
        tokens = text.split()
        for token in tokens:
            eligible = _ALPHA.match(token) and len(token) >= 4 and token.lower() not in PROTECTED
            if not eligible:
                out.append(token)
                continue
            r = rng.random()
            if r < p_drop:
                continue                                            # the recogniser dropped it
            if r < p_drop + p_sub:
                noisy = self.corrupt_token(token, rng)
                if noisy.lower() != token.lower():
                    out.append(noisy)
                    low.append(noisy)
                    continue
            out.append(token)
        return " ".join(out), low
