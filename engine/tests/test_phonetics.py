"""The phonetic key is the foundation of Bhasha Bridge: if it merges too much
the layer corrupts good transcripts, and if it merges too little it repairs
nothing. Both directions are tested."""
import pytest

from haanji.bhasha.phonetics import edit_distance, phonetic_key, phrase_key

SHOULD_MATCH = [
    ("Vijay", "Wijay"), ("shukla", "sukla"), ("chekap", "checkup"),
    ("cleening", "cleaning"), ("rut", "root"), ("kanal", "canal"),
    ("Shaikh", "Sheikh"), ("profail", "profile"), ("dimo", "demo"),
    ("kalar", "colour"), ("hercut", "haircut"),
    ("teeth", "tith"), ("phone", "fone"),
]
SHOULD_DIFFER = [
    ("appointment", "apartment"), ("cleaning", "canal"), ("implant", "important"),
    ("Sheikh", "Malhotra"), ("thyroid", "steroid"), ("cleaning", "checkup"),
]


@pytest.mark.parametrize("a,b", SHOULD_MATCH)
def test_confusable_spellings_share_a_key(a, b):
    assert phonetic_key(a) == phonetic_key(b), (a, phonetic_key(a), b, phonetic_key(b))


@pytest.mark.parametrize("a,b", SHOULD_DIFFER)
def test_distinct_words_keep_distinct_keys(a, b):
    assert phonetic_key(a) != phonetic_key(b)


def test_phrase_key_is_order_sensitive():
    assert phrase_key("root canal") != phrase_key("canal root")


def test_phrase_key_survives_component_noise():
    assert phrase_key("rut kanal") == phrase_key("root canal")


def test_empty_and_punctuation_only_tokens():
    assert phonetic_key("") == ""
    assert phonetic_key("...") == ""


def test_a_known_collision_is_documented_not_hidden():
    """b and p merge for many speakers, so 'braces' and 'prices' land in one
    bucket and the edit-distance condition does not separate them either. The
    confidence condition is what keeps this from mattering in practice: the
    layer only acts on words the recogniser was unsure of. It is recorded here
    so the limitation cannot be lost."""
    assert phonetic_key("braces") == phonetic_key("prices")
    assert edit_distance("braces", "prices") == 2


def test_edit_distance_short_circuits():
    assert edit_distance("abc", "abc") == 0
    assert edit_distance("root", "rut") == 2
    assert edit_distance("a" * 40, "b" * 40, cap=3) == 4
