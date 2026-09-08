"""The text-turn path: WhatsApp and the browser call. Same hot path, no audio."""
import datetime as dt
import sqlite3

import pytest

from haanji.adapters.mock import NullTTS
from haanji.models import Outcome
from haanji.pipeline import CallSession
from haanji.pramaan.ledger import Ledger
from haanji.tools.builtin import build_registry, open_backend
from haanji.vertical import load_pack

TODAY = dt.date(2026, 9, 7)
TENANT = "t_text"


def fresh(pack):
    backend, _ = open_backend(pack, TENANT, today=TODAY)
    ledger = Ledger(sqlite3.connect(":memory:"))
    registry = build_registry(TENANT, backend, pack, ledger)
    return backend, ledger, registry


def session(pack, backend, registry, ledger):
    return CallSession(tenant_id=TENANT, pack=pack, backend=backend,
                       registry=registry, ledger=ledger, tts=NullTTS())


async def test_a_returning_caller_is_greeted_by_name_and_never_asked_their_number(pack):
    backend, ledger, registry = fresh(pack)
    backend.seed_customer(TENANT, "9876543210", "Vijay Sharma", "root canal")
    s = session(pack, backend, registry, ledger)
    await s.open(phone="9876543210")
    assert "Vijay ji" in s.ctx.last_agent_utterance
    assert "root canal" in s.ctx.last_agent_utterance
    for text in ["kal subah teeth cleaning karwani hai", "haan wahi theek hai"]:
        record = await s.handle_text_turn(text)
    assert "number" not in record.said          # phone came with the channel
    await s.handle_text_turn("haan confirm kar do")
    assert s.finish().outcome is Outcome.BOOKED


async def test_out_of_vocabulary_typos_are_repaired_in_text_mode(pack):
    backend, ledger, registry = fresh(pack)
    s = session(pack, backend, registry, ledger)
    await s.open()
    record = await s.handle_text_turn("kal subah rut kanal ka slot milega")
    assert record.corrected.count("root canal") == 1
    assert any(c.from_token == "rut kanal" for c in record.corrections)


async def test_known_words_are_never_touched_in_text_mode(pack):
    backend, ledger, registry = fresh(pack)
    s = session(pack, backend, registry, ledger)
    await s.open()
    record = await s.handle_text_turn("kal subah root canal ka slot milega")
    assert record.corrections == []


async def test_a_reply_to_a_name_question_is_never_corrected(pack):
    """'Anita Rao' must stay Anita Rao even though the pack knows a place
    called Rau one edit away."""
    backend, ledger, registry = fresh(pack)
    s = session(pack, backend, registry, ledger)
    await s.open(phone="9812345678")
    for text in ["kal subah teeth cleaning karwani hai", "haan theek hai"]:
        record = await s.handle_text_turn(text)
    assert "naam" in record.said.lower()
    record = await s.handle_text_turn("Anita Rao")
    assert record.corrections == []
    assert s.ctx.customer_name == "Anita Rao"
    record = await s.handle_text_turn("haan confirm kar do")
    assert s.finish().outcome is Outcome.BOOKED


async def test_browser_partials_feed_speculation_and_the_real_turn_claims_it(pack):
    backend, ledger, registry = fresh(pack)
    s = session(pack, backend, registry, ledger)
    await s.open()
    await s.handle_partial_text("kal subah root canal ka")
    import asyncio
    await asyncio.sleep(0.01)
    record = await s.handle_text_turn("kal subah root canal ka slot milega")
    assert "check_availability" in record.tools
    assert "check_availability" in record.speculation_hits


async def test_guardrails_hold_on_the_text_path(pack):
    backend, ledger, registry = fresh(pack)
    s = session(pack, backend, registry, ledger)
    await s.open()
    record = await s.handle_text_turn("bahut zyada khoon aa raha hai daant se")
    assert record.guard.startswith("emergency")
    assert s.finish().outcome is Outcome.HANDED_OFF
