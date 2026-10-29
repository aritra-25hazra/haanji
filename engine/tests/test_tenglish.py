"""One engine, fifth language: the Hyderabad lab in Tenglish."""
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
TENANT = "t_te"


def _session(pack):
    backend, _ = open_backend(pack, TENANT, today=TODAY)
    ledger = Ledger(sqlite3.connect(":memory:"))
    registry = build_registry(TENANT, backend, pack, ledger)
    return CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry,
                       ledger=ledger, tts=NullTTS()), ledger, backend, registry


def test_telugu_date_time_and_yes_words_resolve():
    assert nlu.normalise_date("repu udayam") == "tomorrow"
    assert nlu.normalise_date("ellundi sayantram") == "day_after_tomorrow"
    assert nlu.normalise_date("ivala") == "today" and nlu.normalise_date("ee roju") == "today"
    assert nlu.normalise_date("aadivaram") == "sunday"
    assert nlu.normalise_date("15 tedi", today=TODAY) == "2026-09-15"
    assert nlu.normalise_time("udayam padi gantalaku") == "10:00"
    assert nlu.normalise_time("sayantram aaru gantalaku") == "18:00"
    assert nlu.normalise_time("padi ara gantalaku") == "10:30"      # the half comes after the hour
    assert nlu.normalise_time("padinnara gantalaku") == "10:30"     # ...or merged into it
    assert nlu.time_period("repu sayantram") == "evening"
    assert nlu.is_affirmative("avunu alage") and nlu.is_affirmative("sarle, confirm cheyandi")
    assert nlu.is_negative("ledu vaddu") and not nlu.is_affirmative("kaadu avunu")
    assert nlu.is_farewell("ledu inthe dhanyavadalu")
    assert nlu.party_size("memu iddaram") == 2
    assert nlu.extract_name("naa peru Ravi Kumar 9848012345") == "Ravi Kumar"
    # "sare" stays Hindi "half" (sare das = 10:30); the Telugu yes is avunu / sarle.
    assert not nlu.is_affirmative("sare das baje")


def test_telugu_times_are_spoken_with_the_fraction_after_the_hour():
    assert spoken_time("07:00", "tenglish") == "udayam 7 gantalaku"
    assert spoken_time("10:30", "tenglish") == "udayam 10 ara gantalaku"
    assert spoken_time("17:00", "tenglish") == "sayantram 5 gantalaku"


async def test_a_full_tenglish_call_books_and_replies_in_tenglish():
    pack = load_pack("lab_hyderabad")
    s, ledger, _, _ = _session(pack)
    await s.open(phone="9848012399")
    record = await s.handle_text_turn("repu udayam lipid profail test cheyali")
    assert any(c.to_surface == "lipid profile" for c in record.corrections)
    assert "khali undi" in record.said and "gantalaku" in record.said     # the offer, in Telugu time words
    record = await s.handle_text_turn("avunu alage")
    assert "peru" in record.said                                           # asks the name, in Telugu
    await s.handle_text_turn("Ravi Kumar")
    record = await s.handle_text_turn("avunu confirm cheyandi")
    assert "Ayipoyindi" in record.said
    assert s.finish().outcome is Outcome.BOOKED and ledger.receipts(TENANT)


async def test_tenglish_report_question_is_refused_not_answered():
    pack = load_pack("lab_hyderabad")
    s, _, _, _ = _session(pack)
    await s.open()
    record = await s.handle_text_turn("naa report lo sugar ekkuva undi, danger aa?")
    assert record.guard == "advice.report"
    assert pack.guardrails.refusal_line in record.said
    assert s.finish().outcome is Outcome.REFUSED


async def test_every_hyderabad_scenario_reaches_its_outcome():
    pack = load_pack("lab_hyderabad")
    assert len(pack.scenarios) >= 4
    for sc in scenarios_of(pack):
        _, ledger, backend, registry = _session(pack)
        _, report = await run_scenario(sc, pack=pack, backend=backend, registry=registry,
                                       ledger=ledger, tenant_id=TENANT)
        assert report.outcome.value == sc.expect, (sc.name, report.outcome)
