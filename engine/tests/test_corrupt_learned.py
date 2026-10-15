"""The data-driven corruption model: fits what a recogniser did, replays it at a chosen rate."""
import random

from haanji.corrupt_learned import LearnedCorruption

PAIRS = [
    ("mujhe root canal karwana hai", "mujhe rut kanal karwana hai"),
    ("kal subah root canal ke liye time chahiye", "kal subhahroot kanal ke liye taim chahiye"),
    ("Gariahat wali branch mein root canal ka slot hai kya", "what is the slot of root canal in giriyatwali branch"),
    ("teeth cleaning ka kitna charge hai", "teeth cleaning ka kitna charge hai"),
    ("Vijay Nagar mein aap log hain na", "vijay nagar main aap log hai na"),
] * 3


def test_fit_counts_substitutions_drops_and_merges():
    m = LearnedCorruption().fit(PAIRS)
    r = m.rates()
    assert r["pairs"] == 15 and r["tokens"] > 0 and 0 < r["substitution_rate"] < 1
    assert m.word_subs["root"]["rut"] == 3 and m.word_subs["canal"]["kanal"] >= 3
    assert m.n_merged >= 3, "'kal subah root' heard as one long token is a merge"
    assert any(a == "oo" and b == "u" for (a, b) in m.char_subs), "learned the oo→u confusion"


def test_replay_reuses_learned_confusions_and_respects_the_rate():
    m = LearnedCorruption().fit(PAIRS)
    rng = random.Random(1)
    heard, low = m.corrupt("mujhe root canal karwana hai", rate=0.99, rng=rng)
    assert "rut" in heard or "kanal" in heard
    assert all(w in heard.split() for w in low)
    quiet, low0 = m.corrupt("mujhe root canal karwana hai", rate=0.0, rng=random.Random(2))
    assert quiet == "mujhe root canal karwana hai" and low0 == []
    assert m.corrupt("haan ji", 0.99, random.Random(3))[0] == "haan ji", "grammar words are protected"


def test_round_trips_through_json():
    m = LearnedCorruption().fit(PAIRS)
    m2 = LearnedCorruption.from_json(m.to_json())
    assert m2.rates() == m.rates() and m2.word_subs["root"] == m.word_subs["root"]
