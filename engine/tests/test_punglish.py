"""One engine, seventh language: the Ludhiana salon in Punglish."""
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
TENANT = "t_pa"


def _session(pack):
    backend, _ = open_backend(pack, TENANT, today=TODAY)
    ledger = Ledger(sqlite3.connect(":memory:"))
    registry = build_registry(TENANT, backend, pack, ledger)
    return CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry,
                       ledger=ledger, tts=NullTTS()), ledger, backend, registry


def test_punjabi_date_time_and_yes_words_resolve():
    assert nlu.normalise_date("kal savere") == "tomorrow"
    assert nlu.normalise_date("ajj shaam") == "today"
    assert nlu.normalise_date("parson") == "day_after_tomorrow"
    assert nlu.normalise_date("aitvar") == "sunday" and nlu.normalise_date("veervar") == "thursday"
    assert nlu.normalise_time("savere das vaje") == "10:00"
    assert nlu.normalise_time("savere saadhe das vaje") == "10:30"
    assert nlu.normalise_time("shaam panj vaje") == "17:00"
    assert nlu.normalise_time("dupahir tinn vaje") == "15:00"
    assert nlu.time_period("kal dupahir") == "afternoon"
    assert nlu.is_affirmative("hanji changa") and nlu.is_affirmative("aho, confirm kar deo")
    assert nlu.is_negative("nahi ji") and not nlu.is_affirmative("nahi hanji")
    assert nlu.is_farewell("nahi bas dhanvaad")
    assert nlu.party_size("main te mera munda") == 2
    assert nlu.extract_name("Navjot Gill 9815012345") == "Navjot Gill"
    # Punjabi "ki" (what) is deliberately not a question word: it is Hindi grammar.
    assert "ki" not in nlu.QUESTION_WORDS


def test_punjabi_times_are_spoken_in_punjabi():
    assert spoken_time("10:00", "punglish") == "savere 10 vaje"
    assert spoken_time("10:30", "punglish") == "savere saadhe 10 vaje"
    assert spoken_time("17:00", "punglish") == "shaam 5 vaje"


async def test_a_full_punglish_call_books_and_replies_in_punglish():
    pack = load_pack("salon_ludhiana")
    s, ledger, _, _ = _session(pack)
    await s.open(phone="9815012399")
    record = await s.handle_text_turn("kal shaam global kalar karwauna hai")
    assert any(c.to_surface == "global colour" for c in record.corrections)
    assert "khali hai" in record.said and "vaje" in record.said           # the offer, in Punjabi time words
    assert "shaam" in record.said
    record = await s.handle_text_turn("haan ji theek hai")
    assert "naam" in record.said                                          # asks the name, in Punjabi
    await s.handle_text_turn("Navjot Gill")
    record = await s.handle_text_turn("haan ji confirm kar deo")
    assert "Ho gaya ji" in record.said
    assert s.finish().outcome is Outcome.BOOKED and ledger.receipts(TENANT)


async def test_punglish_monday_request_becomes_a_lead():
    pack = load_pack("salon_ludhiana")
    s, _, backend, _ = _session(pack)
    await s.open()
    record = await s.handle_text_turn("somvar nu haircut da slot hai?")
    assert "band" in record.said                                          # closed_day, in Punjabi
    await s.handle_text_turn("Gurpreet 9872012345")
    assert s.finish().outcome is Outcome.LEAD_CAPTURED


async def test_every_ludhiana_scenario_reaches_its_outcome():
    pack = load_pack("salon_ludhiana")
    assert len(pack.scenarios) >= 4
    for sc in scenarios_of(pack):
        _, ledger, backend, registry = _session(pack)
        _, report = await run_scenario(sc, pack=pack, backend=backend, registry=registry,
                                       ledger=ledger, tenant_id=TENANT)
        assert report.outcome.value == sc.expect, (sc.name, report.outcome)
