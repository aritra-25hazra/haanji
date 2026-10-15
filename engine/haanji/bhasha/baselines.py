"""The keys Bhasha Bridge is compared against.

Every baseline plugs into the same lexicon, the same two-condition rule and
the same edit-distance bound; only the bucketing function changes. That is
the fair comparison: it isolates the Indic-aware key from everything else
the layer does.
"""
from __future__ import annotations
import re
from typing import Callable

from .phonetics import RULES, haanji_key

_ALPHA = re.compile(r"[^a-z]+")
Keyer = Callable[[str, int], str]


def _clean(token: str) -> str:
    return _ALPHA.sub("", token.lower())


def key_exact(token: str, length: int = 8) -> str:
    """No phonetics: a bucket per spelling. Only exact spellings collide."""
    return _clean(token)


def key_edit_only(token: str, length: int = 8) -> str:
    """No bucketing at all: every form is a candidate and edit distance decides."""
    return "*" if _clean(token) else ""


def key_soundex(token: str, length: int = 8) -> str:
    import jellyfish
    t = _clean(token)
    return jellyfish.soundex(t) if t else ""


def key_metaphone(token: str, length: int = 8) -> str:
    import jellyfish
    t = _clean(token)
    return jellyfish.metaphone(t)[:length] if t else ""


def key_nysiis(token: str, length: int = 8) -> str:
    import jellyfish
    t = _clean(token)
    return jellyfish.nysiis(t)[:length] if t else ""


def key_double_metaphone(token: str, length: int = 8) -> str:
    from metaphone import doublemetaphone
    t = _clean(token)
    if not t:
        return ""
    primary, _secondary = doublemetaphone(t)
    return (primary or "")[:length]


def key_without_rule(index: int) -> Keyer:
    """Our key with one normalisation rule removed, for the per-rule ablation."""
    rules = [r for i, r in enumerate(RULES) if i != index]

    def keyer(token: str, length: int = 8) -> str:
        return haanji_key(token, length, rules)
    keyer.__name__ = f"haanji_without_rule_{index}"
    return keyer


BASELINES: dict[str, Keyer] = {
    "edit distance only": key_edit_only,
    "exact spelling": key_exact,
    "Soundex": key_soundex,
    "Metaphone": key_metaphone,
    "NYSIIS": key_nysiis,
    "Double Metaphone": key_double_metaphone,
    "Bhasha (ours)": haanji_key,
}

RULE_LABELS = [
    "long a shortens (aa→a)", "ee/ie/ii/iy→i", "oo/uu→u", "ph→f", "v/w merge", "s/sh/z merge",
    "ch/chh merge", "t/d/th/dh collapse", "k/kh/q/c merge", "surviving c→k", "g/gh/j-cluster merge",
    "b/bh/p merge", "j", "n/m merge", "l/r merge", "h/y dropped",
]
