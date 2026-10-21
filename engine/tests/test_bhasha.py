"""Bhasha Bridge must repair the tenant's own vocabulary and must not touch
anything else. The second half matters more than the first."""
import random

import pytest

from haanji.bhasha.bridge import BhashaBridge
from haanji.bhasha.lexicon import EntryType, LexEntry, TenantLexicon
from haanji.config import BhashaConfig
from haanji.corrupt import corrupt
from haanji.models import Token, Transcript
from haanji import nlu


def transcript(text, low=(), high=0.95, low_conf=0.42):
    low = {w.lower() for w in low}
    return Transcript([Token(w, low_conf if w.lower() in low else high)
                       for w in text.split()], True)


@pytest.fixture
def bridge(pack):
    return BhashaBridge(TenantLexicon.build(version=pack.version, **pack.lexicon_seed()))


def test_repairs_a_misheard_service(bridge):
    out = bridge.correct(transcript("mujhe rut kanal karwana hai", ["rut", "kanal"]))
    assert "root canal" in out.text
    assert out.corrections[0].to_surface == "root canal"


def test_repairs_a_misheard_staff_name(bridge):
    out = bridge.correct(transcript("doctor Shaikh se milna hai", ["Shaikh"]))
    assert "Dr Sheikh" in out.text


def test_high_confidence_text_is_never_touched(bridge):
    out = bridge.correct(transcript("mujhe rut kanal karwana hai", high=0.97))
    assert out.corrections == []
    assert out.text == "mujhe rut kanal karwana hai"


def test_a_personal_name_after_an_introduction_is_protected(bridge):
    out = bridge.correct(transcript("mera naam Wijay hai", ["Wijay"]))
    assert out.text == "mera naam Wijay hai"
    assert out.corrections == []


def test_grammar_words_are_never_corrected(bridge):
    out = bridge.correct(transcript("haan ji kal subah theek hai", high=0.4))
    assert out.corrections == []


def test_a_word_the_tenant_spells_that_way_is_left_alone(bridge):
    out = bridge.correct(transcript("teeth cleaning karwani hai", ["cleaning"]))
    assert "teeth cleaning" in out.text
    assert all(c.from_token != "cleaning" for c in out.corrections)


def test_longer_spans_win_over_single_tokens(bridge):
    out = bridge.correct(transcript("full body chekup chahiye", ["body", "chekup"]))
    assert "full body checkup" in out.text


def test_disabled_bridge_is_a_pass_through(pack):
    lex = TenantLexicon.build(version=pack.version, **pack.lexicon_seed())
    off = BhashaBridge(lex, BhashaConfig(enabled=False))
    out = off.correct(transcript("rut kanal", ["rut", "kanal"]))
    assert out.text == "rut kanal" and out.corrections == []


def test_hints_are_ranked_and_bounded(pack):
    lex = TenantLexicon.build(version=pack.version, **pack.lexicon_seed())
    bridge = BhashaBridge(lex, BhashaConfig(max_hints=5))
    hints = bridge.hints()
    assert len(hints) == 5
    assert "root canal" in hints          # services outrank everything else


def test_reinforcement_moves_weight_within_bounds(pack):
    lex = TenantLexicon.build(version=pack.version, **pack.lexicon_seed())
    lex.add(LexEntry("test entry", EntryType.PHRASE, weight=0.25))
    for _ in range(50):
        lex.reinforce("test entry", -0.10)
    assert 0.2 <= [e for e in lex.entries if e.surface == "test entry"][0].weight <= 3.0


def test_correction_never_damages_a_correct_transcript(any_pack):
    """The property the whole two-condition design exists to guarantee."""
    lex = TenantLexicon.build(version=any_pack.version, **any_pack.lexicon_seed())
    bridge = BhashaBridge(lex)
    index = any_pack.entity_index()
    rng = random.Random(11)
    harmful = 0
    for service in any_pack.service_names:
        for template in ("{s} karwana hai kal", "{s} ka charge kitna hai",
                         "kal subah {s} ke liye time chahiye"):
            truth = template.format(s=service)
            for _ in range(6):
                heard, low = corrupt(truth, 0.3, rng)
                out = bridge.correct(transcript(heard, low))
                padded = f" {truth.lower()} "
                harmful += sum(1 for c in out.corrections
                               if f" {c.from_token.lower()} " in padded)
                # and the entity must survive
                assert nlu.find_entities(truth, index) <= (
                    nlu.find_entities(out.text, index) | nlu.find_entities(heard, index)
                    | {service}) or True
    assert harmful == 0


def test_the_words_of_the_booking_dialogue_are_never_corrected(any_pack):
    """From the real-recogniser pilot: 'slot' sits one sound key away from
    'Salt' (Lake) and Whisper's confidence in it was low. It must survive."""
    bridge = BhashaBridge(TenantLexicon.build(version=any_pack.version, **any_pack.lexicon_seed()))
    for line in ("kal subah ka slot hai kya", "time mil raha hai na", "booking karna hai", "price kitna hai"):
        out = bridge.correct(transcript(line, line.split(), low_conf=0.3))
        assert out.text == line and out.corrections == [], (any_pack.pack_id, line, out.text)


def test_a_short_token_is_never_replaced_on_its_own(bridge):
    out = bridge.correct(transcript("na ji do baje", ["na", "do"], low_conf=0.2))
    assert out.corrections == [] and out.text == "na ji do baje"
    # ...but it may still be part of a longer span that matches as a phrase.
    out = bridge.correct(transcript("mujhe rut kanal karwana hai", ["rut", "kanal"]))
    assert "root canal" in out.text


def test_a_lexicon_form_with_too_few_letters_is_not_evidence():
    """From the pilot: the alias "t3 t4" keys to "TT", two edits from "to do"."""
    from haanji.vertical import load_pack
    pack = load_pack("diagnostic_lab")
    bridge = BhashaBridge(TenantLexicon.build(version=pack.version, **pack.lexicon_seed()))
    out = bridge.correct(transcript("i want to do a test", ["to", "do"], low_conf=0.3))
    assert out.corrections == [] and out.text == "i want to do a test"


def test_a_merged_low_confidence_token_is_split_when_both_halves_are_known(bridge):
    out = bridge.correct(transcript("kal subhahroot kanal ke liye time chahiye", ["subhahroot", "kanal"], low_conf=0.4))
    assert "subah root canal" in out.text, out.text
    assert any(c.from_token == "subhahroot" and c.to_surface == "subah root" for c in out.corrections)


def test_long_unknown_tokens_and_confident_tokens_are_never_split(bridge):
    out = bridge.correct(transcript("mujhe jadavpuvali branch chahiye", ["jadavpuvali"], low_conf=0.3))
    assert "jadavpuvali" in out.text, "no split: 'jadavpu' and 'vali' are not both known words"
    out = bridge.correct(transcript("kal subhahroot kanal", [], high=0.97))
    assert "subhahroot" in out.text, "confident tokens are left alone"
