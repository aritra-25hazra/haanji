"""One engine, third language: the Pune pack in Marathinglish."""
import datetime as dt
import sqlite3

from haanji.adapters.mock import NullTTS
from haanji.models import Outcome
from haanji.pipeline import CallSession
from haanji.pramaan.ledger import Ledger
from haanji.tools.builtin import build_registry, open_backend
from haanji.vertical import load_pack
from haanji import nlu

TODAY = dt.date(2026, 9, 7)
TENANT = "t_mr"


def test_marathi_date_time_and_yes_words_resolve():
    assert nlu.normalise_date("udya sakali") == "tomorrow"
    assert nlu.normalise_date("parva sandhyakali") == "day_after_tomorrow"
    assert nlu.normalise_time("sandhyakali 5 vajta") == "17:00" and nlu.normalise_time("sakali 10 vajta") == "10:00"
    assert nlu.is_affirmative("ho barobar") and nlu.is_affirmative("chalel, confirm kara")
    assert nlu.is_negative("nako") and not nlu.is_affirmative("nahi nako")


async def test_a_full_marathi_call_books_and_replies_in_marathi():
    pack = load_pack("clinic_pune")
    backend, _ = open_backend(pack, TENANT, today=TODAY)
    ledger = Ledger(sqlite3.connect(":memory:"))
    registry = build_registry(TENANT, backend, pack, ledger)
    s = CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry, ledger=ledger, tts=NullTTS())
    await s.open(phone="9822012399")
    record = await s.handle_text_turn("udya sakali rut kanal cha slot milel ka?")
    assert any(c.to_surface == "root canal" for c in record.corrections)
    assert "rikama aahe" in record.said and "vajta" in record.said      # the offer, in Marathi time words
    record = await s.handle_text_turn("ho barobar")
    assert "naav" in record.said
    await s.handle_text_turn("Rohan Patil")
    record = await s.handle_text_turn("ho confirm kara")
    assert "Zala" in record.said
    assert s.finish().outcome is Outcome.BOOKED and ledger.receipts(TENANT)


async def test_marathi_emergency_escalates():
    pack = load_pack("clinic_pune")
    backend, _ = open_backend(pack, TENANT, today=TODAY)
    ledger = Ledger(sqlite3.connect(":memory:"))
    registry = build_registry(TENANT, backend, pack, ledger)
    s = CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry, ledger=ledger, tts=NullTTS())
    await s.open()
    record = await s.handle_text_turn("khup rakta yet aahe daatatun")
    assert record.guard.startswith("emergency")
    assert s.finish().outcome is Outcome.HANDED_OFF
