"""One engine, second language: the Kolkata pack in Benglish."""
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
TENANT = "t_bn"


def test_benglish_date_and_time_words_resolve():
    assert nlu.normalise_date("kalke shokale") == "tomorrow"
    assert nlu.normalise_date("porshu bikele") == "day_after_tomorrow"
    assert nlu.normalise_date("robibar") == "sunday"
    assert nlu.is_affirmative("hyan thik ache")
    assert nlu.is_affirmative("hobe, confirm koro")


async def test_a_full_benglish_call_books_and_replies_in_benglish():
    pack = load_pack("clinic_kolkata")
    backend, _ = open_backend(pack, TENANT, today=TODAY)
    ledger = Ledger(sqlite3.connect(":memory:"))
    registry = build_registry(TENANT, backend, pack, ledger)
    s = CallSession(tenant_id=TENANT, pack=pack, backend=backend,
                    registry=registry, ledger=ledger, tts=NullTTS())
    await s.open(phone="9830012399")

    record = await s.handle_text_turn("kalke shokale teeth clining er slot hobe?")
    assert any(c.to_surface == "teeth cleaning" for c in record.corrections)
    assert "khali ache" in record.said           # the offer is spoken in Benglish
    assert "tay" in record.said                  # …with Bengali time words

    record = await s.handle_text_turn("hyan thik ache")
    assert "naame" in record.said                # asks the name, in Benglish
    await s.handle_text_turn("Rohan Sen")
    record = await s.handle_text_turn("hyan confirm koro")
    assert "Hoye gechhe" in record.said
    assert s.finish().outcome is Outcome.BOOKED
    assert ledger.receipts(TENANT)


async def test_benglish_emergency_escalates():
    pack = load_pack("clinic_kolkata")
    backend, _ = open_backend(pack, TENANT, today=TODAY)
    ledger = Ledger(sqlite3.connect(":memory:"))
    registry = build_registry(TENANT, backend, pack, ledger)
    s = CallSession(tenant_id=TENANT, pack=pack, backend=backend,
                    registry=registry, ledger=ledger, tts=NullTTS())
    await s.open()
    record = await s.handle_text_turn("khub rokto porche dat theke")
    assert record.guard.startswith("emergency")
    assert s.finish().outcome is Outcome.HANDED_OFF
