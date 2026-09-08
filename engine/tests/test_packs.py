"""A pack is data a non-programmer will edit, so the loader has to be strict."""
import pytest

from haanji.vertical import Pack, PackError, from_dict, list_packs, load_pack


def test_at_least_four_packs_ship():
    assert len(list_packs()) >= 4


def test_every_shipped_pack_is_valid(any_pack):
    assert any_pack.validate() == []


def test_every_pack_declares_guardrails(any_pack):
    assert any_pack.guardrails.refuse_topics
    assert any_pack.guardrails.escalate_on
    assert any_pack.guardrails.refusal_line
    assert any_pack.guardrails.escalation_line


def test_every_pack_ships_scenarios_covering_more_than_the_happy_path(any_pack):
    expectations = {s.expect for s in any_pack.scenarios}
    assert len(expectations) >= 2


def test_service_aliases_resolve_to_catalogue_names(any_pack):
    aliases = any_pack.service_aliases()
    assert set(aliases.values()) <= set(any_pack.service_names)


def test_working_hours_expand_from_day_ranges():
    pack = from_dict({"pack": "x", "staff": ["A"], "hours": {"mon-wed": ["09:00", "17:00"]},
                      "services": [{"name": "s"}]})
    assert sorted(pack.hours) == [0, 1, 2]


def test_a_pack_without_an_id_is_rejected():
    with pytest.raises(PackError):
        from_dict({"display_name": "no id"})


def test_validation_catches_a_service_naming_unknown_staff():
    pack = from_dict({"pack": "x", "staff": ["A"], "hours": {"mon": ["09:00", "17:00"]},
                      "services": [{"name": "s", "staff": ["Ghost"]}]})
    assert any("Ghost" in p for p in pack.validate())


def test_a_missing_pack_raises():
    with pytest.raises(PackError):
        load_pack("no_such_pack")
