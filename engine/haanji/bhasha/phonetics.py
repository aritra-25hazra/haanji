"""Indic-aware phonetic keying.

Standard Soundex is a poor fit for Hinglish: it keeps distinctions Indian
speakers routinely merge (v/w, s/sh) and merges ones they keep.  The key below
applies a small, explicit set of normalisation rules *before* encoding, so that
the Roman spellings people actually type and say collapse onto one key.

Every rule is a claim about Indian pronunciation and is listed here so that the
experiment in ``research/benchmark`` can justify or refute it.
"""
from __future__ import annotations
import re
import unicodedata

# (pattern, replacement) applied in order. Order matters: digraphs before singles.
RULES: list[tuple[str, str]] = [
    (r"aa+h?", "a"),      # kaan / kan,  shaam / sham
    (r"(ee|ie|ii|iy)", "i"),   # jee / ji,  teen / tin
    (r"(oo|uu)", "u"),    # doosra / dusra
    (r"ph", "f"),         # phone / fone
    (r"[vw]", "V"),       # vijay / wijay
    (r"(sh|s|z)", "S"),   # shukla / sukla,  zameen / sameen
    (r"(chh|ch|c(?=[hiey]))", "C"),
    (r"(th|dh|[td])", "T"),   # retroflex / dental collapse
    (r"(kh|[kqx]|c(?=[aou]))", "K"),
    (r"c", "K"),        # any surviving c is a k sound (checkup / chekap)
    (r"(gh|g|j(?=[^aeiou]))", "G"),
    (r"(bh|b|p)", "P"),
    (r"j", "J"),
    (r"[nm]", "N"),
    (r"[lr]", "R"),       # many speakers neutralise l/r in loanwords
    (r"[hy]", ""),        # weak, often dropped
]

_VOWELS = re.compile(r"[aeiou]")
_REPEAT = re.compile(r"(.)\1+")
_NONALPHA = re.compile(r"[^a-zA-Z]+")


def _strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def haanji_key(token: str, length: int = 8, rules: list[tuple[str, str]] | None = None) -> str:
    """Return the phonetic bucket for one token.

    >>> haanji_key("Vijay") == haanji_key("Wijay")
    True
    >>> haanji_key("shukla") == haanji_key("sukla")
    True
    """
    t = _strip_diacritics(token.lower().strip())
    t = _NONALPHA.sub("", t)
    if not t:
        return ""
    for pattern, repl in (RULES if rules is None else rules):
        t = re.sub(pattern, repl, t)
    t = _REPEAT.sub(r"\1", t)
    head, tail = t[:1], t[1:]
    tail = _VOWELS.sub("", tail)
    if _VOWELS.match(head):
        # A word-initial vowel is unstable in Hinglish, mostly because a weak
        # /h/ in front of it is dropped by both speakers and recognisers
        # (haircut / hercut, hospital / ospital). Bucket every vowel onset.
        head = "A"
    return (head + tail)[:length]


def haanji_phrase_key(phrase: str, length: int = 16) -> str:
    """Phonetic key for a multi-word entity such as ``root canal``."""
    return "".join(haanji_key(w, 6) for w in phrase.split())[:length]


# The active keyer. Everything in the engine calls phonetic_key/phrase_key;
# the benchmark swaps the implementation to compare against Soundex,
# Metaphone and friends on exactly the same data and matching rules.
_ACTIVE: dict[str, object] = {"token": haanji_key, "phrase": haanji_phrase_key, "name": "haanji"}


def phonetic_key(token: str, length: int = 8) -> str:
    return _ACTIVE["token"](token, length)            # type: ignore[operator]


def phrase_key(phrase: str, length: int = 16) -> str:
    return _ACTIVE["phrase"](phrase, length)          # type: ignore[operator]


def active_keyer() -> str:
    return str(_ACTIVE["name"])


class use_keyer:
    """``with use_keyer("soundex", token_fn, phrase_fn): ...`` — for experiments."""

    def __init__(self, name: str, token_fn, phrase_fn=None):
        self.new = {"token": token_fn, "name": name,
                    "phrase": phrase_fn or (lambda phrase, length=16: "".join(token_fn(w, 6) for w in phrase.split())[:length])}
        self.old: dict[str, object] = {}

    def __enter__(self):
        self.old = dict(_ACTIVE)
        _ACTIVE.update(self.new)
        return self

    def __exit__(self, *exc):
        _ACTIVE.update(self.old)
        return False


def edit_distance(a: str, b: str, cap: int = 4) -> int:
    """Levenshtein distance, short-circuited at ``cap`` (we never care beyond it)."""
    a, b = a.lower(), b.lower()
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]
