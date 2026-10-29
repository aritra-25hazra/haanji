"""One engine, sixth language: the Ahmedabad coaching institute in Gujlish."""
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
TENANT = "t_gu"


def _session(pack):
    backend, _ = open_backend(pack, TENANT, today=TODAY)
    ledger = Ledger(sqlite3.connect(":memory:"))
    registry = build_registry(TENANT, backend, pack, ledger)
    return CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry,
                       ledger=ledger, tts=NullTTS()), ledger, backend, registry


def test_gujarati_date_time_and_yes_words_resolve():
    assert nlu.normalise_date("kale savare") == "tomorrow"
    assert nlu.normalise_date("param divase") == "day_after_tomorrow"
    assert nlu.normalise_date("aaje sanje") == "today"
    assert nlu.normalise_date("ravivar") == "sunday" and nlu.normalise_date("somvaar") == "monday"
    assert nlu.normalise_time("savare das vage") == "10:00"
    assert nlu.normalise_time("savare sada das vage") == "10:30"
    assert nlu.normalise_time("bapore be vage") == "14:00"        # "be" is two only beside a clock word
    assert nlu.normalise_time("sanje chha vage") == "18:00"
    assert nlu.normalise_time("dodh vage") == "13:30"
    assert nlu.time_period("kale bapore") == "afternoon"
    assert nlu.is_affirmative("haa barabar") and nlu.is_affirmative("chalse, confirm karo")
    assert nlu.is_negative("na nathi") and not nlu.is_affirmative("nathi haa")
    assert nlu.is_farewell("na bas etlu j aabhar")
    assert nlu.party_size("hu ane maro dikro") == 2
    assert nlu.extract_name("maru naam Aditya Mehta 9825012345") == "Aditya Mehta"
    # Hindi "nai" (new) is not a Gujarati no, and Hindi "baar" (time) is not twelve in a sentence.
    assert not nlu.is_negative("nai booking karni hai")
    assert nlu.normalise_time("pichhli baar service kharab thi") is None


def test_gujarati_times_are_spoken_in_gujarati():
    assert spoken_time("10:00", "gujlish") == "savare 10 vage"
    assert spoken_time("10:30", "gujlish") == "savare sada 10 vage"
    assert spoken_time("17:45", "gujlish") == "sanje pona 6 vage"


async def test_a_full_gujlish_call_books_and_replies_in_gujlish():
    pack = load_pack("coaching_ahmedabad")
    s, ledger, _, _ = _session(pack)
    await s.open(phone="9825012399")
    record = await s.handle_text_turn("kale savare dimo class no slot malse?")
    assert any(c.to_surface == "demo class" for c in record.corrections)
    assert "khali che" in record.said and "vage" in record.said        # the offer, in Gujarati time words
    record = await s.handle_text_turn("haa barabar")
    assert "naam" in record.said                                         # asks the name, in Gujarati
    await s.handle_text_turn("Aditya Mehta")
    record = await s.handle_text_turn("haa confirm karo")
    assert "Thai gayu" in record.said
    assert s.finish().outcome is Outcome.BOOKED and ledger.receipts(TENANT)


async def test_gujlish_selection_promise_is_refused():
    pack = load_pack("coaching_ahmedabad")
    s, _, _, _ = _session(pack)
    await s.open()
    record = await s.handle_text_turn("guarantee aapo ke selection thashe")
    assert record.guard == "promise.outcome"
    assert s.finish().outcome is Outcome.REFUSED


async def test_every_ahmedabad_scenario_reaches_its_outcome():
    pack = load_pack("coaching_ahmedabad")
    assert len(pack.scenarios) >= 4
    for sc in scenarios_of(pack):
        _, ledger, backend, registry = _session(pack)
        _, report = await run_scenario(sc, pack=pack, backend=backend, registry=registry,
                                       ledger=ledger, tenant_id=TENANT)
        assert report.outcome.value == sc.expect, (sc.name, report.outcome)
