"""A synthetic model of Hinglish recognition error.

The scenarios shipped in the packs carry corruptions written by hand, which is
the right material for a demo but a weak basis for a claim: the author of the
corruption is also the author of the repair. This module generates errors
independently, from a list of substitutions that are *properties of the
language*, not of this system — the same v/w, s/sh, aspirate and long-vowel
confusions that every Indian-English recogniser makes.

It corrupts content words indiscriminately, including words that appear in no
lexicon. That is the point: a correction layer is only worth having if it
repairs what it can and leaves everything else alone, and the harness has to
be able to catch it doing damage.
"""
from __future__ import annotations
import random
import re

# (pattern, replacement) — each is a confusion an Indian-English recogniser
# genuinely makes, in the direction it usually makes it.
CONFUSIONS: list[tuple[str, str]] = [
    (r"v", "w"), (r"w", "v"),
    (r"sh", "s"), (r"s(?![h])", "sh"),
    (r"ee", "i"), (r"i(?=[a-z])", "ee"),
    (r"oo", "u"), (r"u(?=[a-z])", "oo"),
    (r"th", "t"), (r"ph", "f"), (r"kh", "k"), (r"gh", "g"), (r"bh", "b"),
    (r"c(?=[aou])", "k"), (r"k(?=[aou])", "c"),
    (r"aa", "a"), (r"a(?=[a-z]{2})", "aa"),
    (r"ai", "e"), (r"e(?=[a-z])", "ai"),
    (r"o(?=[a-z])", "au"), (r"^h", ""),
]

# Never corrupted: grammar words carry the dialogue, and a harness that breaks
# "haan" is measuring nothing but its own noise.
PROTECTED = {
    "haan", "haanji", "nahi", "nahin", "hai", "hain", "ji", "kal", "aaj", "parso",
    "ka", "ki", "ke", "ko", "se", "me", "mein", "aur", "ya", "bas", "theek", "thik",
    "confirm", "ok", "okay", "yes", "no", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday", "subah", "shaam", "dopahar", "raat",
    "kalke", "aajke", "porshu", "hyan", "ache", "hobe", "chai", "lagbe", "koro",
    "korun", "shokale", "bikele", "shondhe", "dhonnobad", "koto", "kokhon", "khola",
}
_ALPHA = re.compile(r"^[A-Za-z]+$")


def corrupt_token(token: str, rng: random.Random) -> str:
    order = list(range(len(CONFUSIONS)))
    rng.shuffle(order)
    for i in order:
        pattern, repl = CONFUSIONS[i]
        if re.search(pattern, token, flags=re.IGNORECASE):
            return re.sub(pattern, repl, token, count=1, flags=re.IGNORECASE)
    return token


def corrupt(text: str, rate: float, rng: random.Random) -> tuple[str, list[str]]:
    """Return the recogniser's version of ``text`` and the words it doubted."""
    out: list[str] = []
    low: list[str] = []
    for token in text.split():
        eligible = (_ALPHA.match(token) and len(token) >= 4
                    and token.lower() not in PROTECTED)
        if eligible and rng.random() < rate:
            noisy = corrupt_token(token, rng)
            if noisy.lower() != token.lower():
                out.append(noisy)
                low.append(noisy)
                continue
        out.append(token)
    return " ".join(out), low
