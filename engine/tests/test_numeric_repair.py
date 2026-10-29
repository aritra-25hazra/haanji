"""The closed-vocabulary repair of date, time and number words (REPORT §9 item 4).

The same two conditions as the tenant lexicon — low confidence and an exact
sound-key match within the edit bound — over a second, closed vocabulary
imported from haanji.nlu. What it repairs matters less than what it refuses:
a wrong number is worse than a wrong spelling."""
import re

import pytest

from haanji import nlu
from haanji.bench import classify_correction, score_date_time
from haanji.bhasha.bridge import BhashaBridge
from haanji.bhasha.lexicon import TenantLexicon
from haanji.bhasha.numeric import (COMMON_WORDS, NUMERIC_WEIGHT, edits_allowed, fold_vowels, number_runs,
                                   temporal_lexicon, temporal_tokens)
from haanji.config import BhashaConfig
from haanji.corrupt import CONFUSIONS
from haanji.models import Correction, Token, Transcript
from haanji.vertical import list_packs, load_pack

LEX = temporal_lexicon()
MEANING = {e.surface: e.meaning for e in LEX.entries}


def transcript(text, low=(), high=0.95, low_conf=0.42):
    low = {w.lower() for w in low}
    return Transcript([Token(w, low_conf if w.lower() in low else high) for w in text.split()], True)


def build(pack, **cfg):
    return BhashaBridge(TenantLexicon.build(version=pack.version, **pack.lexicon_seed()), BhashaConfig(**cfg))


@pytest.fixture
def bridge(pack):
    return build(pack)


# ── the vocabulary comes from nlu, not from here ─────────────────────────────
def test_the_vocabulary_is_nlu_s_own_and_covers_three_languages():
    assert LEX.forms >= {w for w in nlu.NUMBER_WORDS if w.isalpha()}
    assert LEX.forms >= set(nlu.WEEKDAYS) and LEX.forms >= {w for w in nlu.TIME_WORDS if w.isalpha()}
    assert {"kal", "kalke", "udya", "subah", "shokale", "sakali", "baje", "tay", "vajta",
            "saade", "share", "sade", "gyarah", "egaro", "akra"} <= LEX.forms
    assert "din" not in LEX.forms and "baad" not in LEX.forms, "generic words are never repaired into"
    assert MEANING["saat"] == MEANING["sat"] == MEANING["shat"] == "7"
    assert MEANING["kal"] == MEANING["kalke"] == MEANING["udya"] == "tomorrow"
    assert MEANING["subah"] == MEANING["shokale"] == MEANING["sakali"] == "morning"
    assert MEANING["saade"] == MEANING["sade"] == MEANING["share"] == "half"
    assert MEANING["somvar"] == MEANING["shombar"] == "monday"


def test_the_bound_folds_vowels_and_tightens_with_length():
    assert fold_vowels("soobah") == "subah" and fold_vowels("kaal") == "kal" and fold_vowels("teen") == "tin"
    assert edits_allowed(4, 2) == 0 and edits_allowed(5, 2) == 1 and edits_allowed(6, 2) == 2
    assert {"root", "baar", "bahar", "dono", "late", "seat", "haath", "thoda", "naav"} <= COMMON_WORDS


# ── repaired ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("heard,bad,good", [
    ("kal soobah root canal chahiye", "soobah", "subah"),
    ("kaal subah ka time chahiye", "kaal", "kal"),
    ("kal sham ka slot chahiye", "sham", "shaam"),
    ("das baaje aana hai", "baaje", "baje"),
    ("oodya sakali", "oodya", "udya"),               # a doubled vowel is one letter, not two edits
    ("dahaa baje aaunga", "dahaa", "daha"),
    ("gyara baje subah", "gyara", "gyarah"),        # five letters: one edit
    ("panchh baje shaam", "panchh", "paanch"),      # six letters: 'paanch' and 'panch' tie, both 5
    ("somwar ko aana hai", "somwar", "somvar"),
    ("paunee paanch baje", "paunee", "paune"),      # five folded letters: one edit
    ("shukrawar ko aana hai", "shukrawar", "shukravar"),
])
def test_a_doubtful_date_or_time_word_is_restored(bridge, heard, bad, good):
    out = bridge.correct(transcript(heard, [bad]))
    [c] = [c for c in out.corrections if c.from_token == bad]
    assert c.to_surface in LEX.forms and MEANING[c.to_surface] == MEANING[good], (out.text, c)
    assert c.entry_weight == NUMERIC_WEIGHT and c.ngram == 1
    assert bad not in out.text.split() and c.to_surface in out.text.split()


def test_marathi_date_words_are_restored_in_the_pune_pack():
    bridge = build(load_pack("clinic_pune"))
    out = bridge.correct(transcript("oodya sakli root canal cha slot milel ka", ["oodya", "sakli"]))
    assert out.text.startswith("udya sakali root canal"), out.text


def test_the_repaired_sentence_is_one_the_policy_reads(bridge):
    out = bridge.correct(transcript("saadhe das baaje subah", ["saadhe", "baaje"]))
    assert nlu.normalise_time(out.text) == "10:30"
    out = bridge.correct(transcript("kaal shaam paunee paanch baje", ["kaal", "paunee"]))
    assert nlu.normalise_date(out.text) == "tomorrow" and nlu.normalise_time(out.text) == "16:45"


def test_the_tenant_pass_runs_first_and_both_repairs_land(bridge):
    out = bridge.correct(transcript("kal soobah rut kanal karwana hai", ["soobah", "rut", "kanal"]))
    assert out.text == "kal subah root canal karwana hai"
    assert {c.to_surface for c in out.corrections} == {"subah", "root canal"}


def test_the_text_channel_confidence_model_lets_a_typo_through_to_the_repair(pack, backend, registry):
    from haanji.adapters.mock import NullTTS
    from haanji.pipeline import CallSession
    s = CallSession(tenant_id="t_test", pack=pack, backend=backend, registry=registry, tts=NullTTS())
    out = s.bhasha.correct(s._text_transcript("kal soobah root canal chahiye", final=True))
    assert out.text == "kal subah root canal chahiye"


# ── never ────────────────────────────────────────────────────────────────────
def test_a_known_word_is_never_respelled(bridge):
    for line in ("saat baje", "sat baje", "shat tay", "nau baje", "kal subah", "udya sakali", "paanch baje"):
        out = bridge.correct(transcript(line, line.split(), low_conf=0.3))
        assert out.text == line and out.corrections == [], line


def test_a_number_never_becomes_a_different_number():
    assert LEX.repair("nau", 2) is None and LEX.repair("saat", 2) is None
    assert LEX.repair("no", 2) is None, "too short to be evidence, whatever its sound key says"
    assert LEX.repair("naya", 2) is None, "four letters: only vowel folding may explain it, not an edit"
    assert LEX.repair("uday", 2) is None, "a name two edits from 'udya' stays a name"
    assert LEX.repair("tean", 2) is None, "one edit from 'ten' (10), two from 'teen' (3): refused"
    assert LEX.repair("baes", 2) is None, "between bees (20) and bais (22): refused"
    assert LEX.repair("sath", 2) is None, "'sath' is 'with' as often as it is seven"


def test_ambiguous_and_short_tokens_stay_as_heard(bridge):
    for line, low in (("no baje", ["no"]), ("naya number hai", ["naya"]), ("baes tarikh ko", ["baes"]),
                      ("uday ka appointment", ["uday"]), ("tean baje", ["tean"]), ("sath baje", ["sath"])):
        out = bridge.correct(transcript(line, low, low_conf=0.3))
        assert out.text == line and out.corrections == [], out.text


PROBE_COLLISIONS = ["root", "seat", "haath", "thoda", "late", "dono", "baar", "bahar", "adha", "seedha", "bura",
                    "bhara", "naav", "kaam", "baat", "paas", "naam", "bade", "pani"]


@pytest.mark.parametrize("word", PROBE_COLLISIONS)
def test_an_everyday_word_is_never_turned_into_a_date_or_number(word):
    """Found by probing 519 common call words at low confidence: each of these
    sat one edit from a number or time word under a looser bound."""
    for pid in list_packs():
        out = build(load_pack(pid)).correct(transcript(f"mujhe {word} chahiye", [word], low_conf=0.3))
        assert not any(c.to_surface in LEX.forms for c in out.corrections), (pid, word, out.text)


def test_digits_and_dictated_numbers_are_never_touched(bridge):
    out = bridge.correct(transcript("9876543210 par call karo 9 baje", ["9876543210", "9"], low_conf=0.2))
    assert out.corrections == []
    dictated = "mera number nau aath gyara chhe paanch do teen char ek shunya hai"
    out = bridge.correct(transcript(dictated, ["gyara"], low_conf=0.3))
    assert out.text == dictated and out.corrections == [], "a run of numbers is a phone number being read out"
    alone = bridge.correct(transcript("gyara baje aaunga", ["gyara"], low_conf=0.3))
    assert "gyarah" in alone.text, "the same token outside a run is repaired"


def test_number_runs_mark_phone_dictation_only():
    assert number_runs(["nau", "aath", "gyara", "chhe"], LEX, 2) == [True, True, True, True]
    assert number_runs(["gyara", "baje"], LEX, 2) == [False, False]
    assert number_runs(["saade", "das", "baje"], LEX, 2) == [False, False, False]
    assert number_runs(["98", "76", "gyara"], LEX, 2) == [True, True, True]


def test_the_tenants_own_words_are_never_numbers():
    pune = build(load_pack("clinic_pune"))
    out = pune.correct(transcript("smile dental pune mein slot hai", ["pune"], low_conf=0.3))
    assert "pune" in out.text and out.corrections == [], "'Pune' is a place, not 'paune'"
    coaching = build(load_pack("coaching_institute"))
    out = coaching.correct(transcript("sat ka demo kab hai", ["sat"], low_conf=0.3))
    assert out.text == "sat ka demo kab hai"


def test_grammar_yes_no_and_frame_words_are_never_numbers(bridge):
    for line in ("time mil raha hai", "haan theek hai", "nahi parso", "mein aaunga", "ache hobe"):
        out = bridge.correct(transcript(line, line.split(), low_conf=0.3))
        assert out.text == line and out.corrections == [], line


def test_a_personal_name_after_an_introduction_is_protected(bridge):
    out = bridge.correct(transcript("mera naam Sakli hai", ["Sakli"]))
    assert out.text == "mera naam Sakli hai" and out.corrections == []


def test_confident_words_and_a_disabled_pass_are_left_alone(pack):
    on = build(pack)
    assert on.correct(transcript("kal soobah", high=0.97)).corrections == []
    off = build(pack, numeric_repair=False)
    out = off.correct(transcript("kal soobah root canal", ["soobah"]))
    assert "soobah" in out.text and out.corrections == []


# ── the safety property under the corruption model's own confusions ──────────
TEMPORAL_SENTENCES = [
    "udya sakali root canal cha slot milel ka", "saade das baje aana hai", "paanch baje shaam ka slot",
    "gyarah baje subah", "somvar ko aaunga", "shukravar dopahar chalega", "kalke shokale slot hobe",
    "egaro tay slot hobe", "sava nau baje", "paune barah baje", "aath tarikh ko", "teen baje dopahar",
]


def _variants(word: str) -> set[str]:
    out = set()
    for pattern, repl in CONFUSIONS:
        if re.search(pattern, word, flags=re.IGNORECASE):
            noisy = re.sub(pattern, repl, word, count=1, flags=re.IGNORECASE)
            if noisy.lower() != word.lower():
                out.add(noisy)
    return out


def test_no_corruption_of_a_temporal_word_ever_changes_its_meaning(bridge):
    """Every single substitution the corruption model can make to a date, time
    or number word is fed back at low confidence. The pass may restore the word
    or leave it; it may never produce a word that means something else.
    Restoration is counted so the test also records how much the pass helps."""
    tried = restored = 0
    for sentence in TEMPORAL_SENTENCES:
        truth = temporal_tokens(sentence)
        for word in sentence.split():
            if word not in LEX.forms:
                continue
            for noisy in _variants(word):
                heard = sentence.replace(word, noisy, 1)
                tried += 1
                out = bridge.correct(transcript(heard, [noisy], low_conf=0.35))
                got = temporal_tokens(out.text)
                assert {MEANING[w] for w in got} <= {MEANING[w] for w in truth}, (heard, out.text)
                assert all(c.from_token.lower() not in truth for c in out.corrections), (heard, out.corrections)
                if word in out.text.split():
                    restored += 1
    assert tried >= 40 and restored >= tried // 3, (tried, restored)


# ── what the benchmark measures ──────────────────────────────────────────────
def test_temporal_tokens_and_the_date_time_score():
    assert temporal_tokens("kal subah 11 baje root canal") == {"kal", "subah", "baje"}

    class Rec:
        def __init__(self, heard, corrected, truth):
            self.heard, self.corrected, self.truth = heard, corrected, truth

    class Utt:
        def __init__(self, truth):
            self.truth = truth

    class Report:
        turns = [Rec("oodya sakli rut kanal", "udya sakali root canal", "udya sakali root canal"),
                 Rec("kal sham", "kal sham", "kal shaam"),
                 Rec("rut kanal chahiye", "root canal chahiye", "root canal chahiye")]

    class Scenario:
        utterances = [Utt(r.truth) for r in Report.turns]

    assert score_date_time(Report, Scenario, use_corrected=True) == (2, 2, 1)
    assert score_date_time(Report, Scenario, use_corrected=False) == (2, 2, 2)


def test_temporal_repairs_are_classified_apart_from_entity_repairs():
    truth = "udya sakali root canal"
    gold, temporal = {"root canal"}, temporal_tokens(truth)

    def c(frm, to):
        return Correction(frm, to, 0.4, NUMERIC_WEIGHT)
    assert classify_correction(c("oodya", "udya"), truth, gold, temporal) == "temporal_restored"
    assert classify_correction(c("kaal", "kal"), truth, gold, temporal) == "temporal_neutral"
    assert classify_correction(c("rut kanal", "root canal"), truth, gold, temporal) == "beneficial"
    assert classify_correction(c("udya", "kal"), truth, gold, temporal) == "harmful"
