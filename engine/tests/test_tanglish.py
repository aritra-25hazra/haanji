"""One engine, fourth language: the Chennai pack in Tanglish."""
import datetime as dt
import sqlite3

from haanji.adapters.mock import NullTTS
from haanji.models import Outcome
from haanji.pipeline import CallSession, run_scenario
from haanji.pramaan.ledger import Ledger
from haanji.scenario import scenarios_of
from haanji.tools.builtin import build_registry, open_backend
from haanji.vertical import load_pack
from haanji import nlu
from haanji.speak import spoken_time

TODAY = dt.date(2026, 9, 7)
TENANT = "t_ta"


def _session(pack, phone=None):
    backend, _ = open_backend(pack, TENANT, today=TODAY)
    ledger = Ledger(sqlite3.connect(":memory:"))
    registry = build_registry(TENANT, backend, pack, ledger)
    return CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry,
                       ledger=ledger, tts=NullTTS()), ledger, backend, registry


def test_tamil_date_time_and_yes_words_resolve():
    assert nlu.normalise_date("naalai kaalai") == "tomorrow"
    assert nlu.normalise_date("naalai marunaal madhiyam") == "day_after_tomorrow"
    assert nlu.normalise_date("innaiku saayangalam") == "today"
    assert nlu.normalise_date("gnayiru kaalai") == "sunday"
    assert nlu.normalise_date("15 thedhi", today=TODAY) == "2026-09-15"
    assert nlu.normalise_time("kaalai pathu mani") == "10:00"
    assert nlu.normalise_time("saayangalam 5 mani") == "17:00"
    assert nlu.normalise_time("pathu arai manikku") == "10:30"      # the half comes after the hour
    assert nlu.normalise_time("10 mukkaal mani") == "10:45"         # ten and three quarters
    assert nlu.time_period("naalai kaalai") == "morning"
    assert nlu.is_affirmative("aama sari") and nlu.is_affirmative("sari, confirm pannunga")
    assert nlu.is_negative("illa vendam") and not nlu.is_affirmative("illa aama")
    assert nlu.is_farewell("illa adhu dhaan nandri")
    assert not nlu.is_farewell("cleaning evlo aagum")
    assert nlu.party_size("naanga rendu per") == 2
    assert nlu.extract_name("en peru Karthik Raman 9840012345") == "Karthik Raman"


def test_tamil_times_are_spoken_with_the_fraction_after_the_hour():
    assert spoken_time("10:00", "tanglish") == "kaalai 10 mani"
    assert spoken_time("10:30", "tanglish") == "kaalai 10 arai mani"
    assert spoken_time("10:45", "tanglish") == "kaalai 10 mukkaal mani"
    assert spoken_time("17:00", "tanglish") == "saayangalam 5 mani"
    assert spoken_time("10:45", "hinglish") == "subah paune 11 baje"   # Hindi still rolls the hour forward


async def test_a_full_tanglish_call_books_and_replies_in_tanglish():
    pack = load_pack("clinic_chennai")
    s, ledger, _, _ = _session(pack)
    await s.open(phone="9840012399")
    record = await s.handle_text_turn("naalai kaalai teeth clining slot irukka?")
    assert any(c.to_surface == "teeth cleaning" for c in record.corrections)
    assert "irukku" in record.said and "mani" in record.said       # the offer, in Tamil time words
    assert "kaalai" in record.said
    record = await s.handle_text_turn("aama sari")
    assert "peru" in record.said                                    # asks the name, in Tamil
    await s.handle_text_turn("Karthik Raman")
    record = await s.handle_text_turn("aama confirm pannunga")
    assert "Aayiduchu" in record.said
    assert s.finish().outcome is Outcome.BOOKED and ledger.receipts(TENANT)


async def test_tanglish_emergency_escalates():
    pack = load_pack("clinic_chennai")
    s, _, _, _ = _session(pack)
    await s.open()
    record = await s.handle_text_turn("pallula romba blood varudhu, nikkave illa")
    assert record.guard.startswith("emergency")
    assert s.finish().outcome is Outcome.HANDED_OFF


async def test_every_chennai_scenario_reaches_its_outcome():
    pack = load_pack("clinic_chennai")
    assert len(pack.scenarios) >= 4
    for sc in scenarios_of(pack):
        _, ledger, backend, registry = _session(pack)
        _, report = await run_scenario(sc, pack=pack, backend=backend, registry=registry,
                                       ledger=ledger, tenant_id=TENANT)
        assert report.outcome.value == sc.expect, (sc.name, report.outcome)
