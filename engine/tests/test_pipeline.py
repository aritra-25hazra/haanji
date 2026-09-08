"""End-to-end: every packaged scenario, plus the properties that only show up
when the whole loop runs."""
import datetime as dt
import re
import sqlite3

import pytest

from haanji.config import BhashaConfig, EngineConfig, SpeculationConfig
from haanji.models import Outcome
from haanji.pipeline import CallSession, run_scenario
from haanji.pramaan.ledger import Ledger
from haanji.pramaan.verifier import verify_chain
from haanji.scenario import Utterance, scenarios_of
from haanji.tools.builtin import build_registry, open_backend
from haanji.vertical import list_packs, load_pack

TODAY = dt.date(2026, 9, 7)
TENANT = "t_e2e"


def fresh(pack):
    backend, _ = open_backend(pack, TENANT, today=TODAY)
    ledger = Ledger(sqlite3.connect(":memory:"))
    registry = build_registry(TENANT, backend, pack, ledger)
    return backend, ledger, registry


def all_scenarios():
    out = []
    for pid in list_packs():
        pack = load_pack(pid)
        for sc in scenarios_of(pack):
            out.append(pytest.param(pid, sc, id=f"{pid}:{sc.name}"))
    return out


@pytest.mark.parametrize("pack_id,scenario", all_scenarios())
async def test_every_scenario_reaches_its_expected_outcome(pack_id, scenario):
    pack = load_pack(pack_id)
    backend, ledger, registry = fresh(pack)
    _, report = await run_scenario(scenario, pack=pack, backend=backend, registry=registry,
                                   ledger=ledger, tenant_id=TENANT)
    assert report.outcome.value == scenario.expect


async def test_a_booking_produces_a_verifiable_receipt(pack):
    backend, ledger, registry = fresh(pack)
    scenario = next(s for s in scenarios_of(pack) if s.expect == "BOOKED")
    _, report = await run_scenario(scenario, pack=pack, backend=backend, registry=registry,
                                   ledger=ledger, tenant_id=TENANT)
    assert report.receipts
    receipts = ledger.receipts(TENANT)
    assert verify_chain(receipts, ledger.public_key).ok
    booking = [b for b in backend.bookings(TENANT) if b.status == "CONFIRMED"][0]
    assert booking.receipt_code == report.receipts[0]


async def test_the_receipt_quotes_the_words_that_authorised_the_booking(pack):
    backend, ledger, registry = fresh(pack)
    scenario = next(s for s in scenarios_of(pack) if s.name == "booking_with_asr_noise")
    await run_scenario(scenario, pack=pack, backend=backend, registry=registry,
                       ledger=ledger, tenant_id=TENANT)
    receipt = ledger.receipts(TENANT)[-1]
    assert "Confirm kar dun" in receipt.confirmation["prompt_text"]
    assert "haan" in receipt.confirmation["reply_text"].lower()
    assert receipt.confirmation["audio_offset_ms"] >= 0


async def test_nothing_is_written_before_the_caller_confirms(pack):
    backend, ledger, registry = fresh(pack)
    session = CallSession(tenant_id=TENANT, pack=pack, backend=backend,
                          registry=registry, ledger=ledger)
    await session.open()
    for text in ["mujhe root canal karwana hai", "kal subah", "haan theek hai",
                 "mera naam Vijay hai number 9876543210"]:
        await session.handle_utterance(Utterance(text))
    assert backend.bookings(TENANT) == []          # the summary was only read out
    assert session.ctx.pending_confirmation is not None
    await session.handle_utterance(Utterance("haan confirm kar do"))
    assert len(backend.bookings(TENANT)) == 1


async def test_saying_no_to_the_summary_cancels_the_write(pack):
    backend, ledger, registry = fresh(pack)
    session = CallSession(tenant_id=TENANT, pack=pack, backend=backend,
                          registry=registry, ledger=ledger)
    await session.open()
    for text in ["mujhe root canal karwana hai", "kal subah", "haan theek hai",
                 "mera naam Vijay hai number 9876543210", "nahi galat hai"]:
        await session.handle_utterance(Utterance(text))
    assert backend.bookings(TENANT) == []
    assert session.ctx.pending_confirmation is None


async def test_an_emergency_never_reaches_the_booking_path(pack):
    backend, ledger, registry = fresh(pack)
    session = CallSession(tenant_id=TENANT, pack=pack, backend=backend,
                          registry=registry, ledger=ledger)
    await session.open()
    record = await session.handle_utterance(
        Utterance("bahut zyada khoon aa raha hai daant se"))
    assert record.guard.startswith("emergency")
    assert session.finish().outcome is Outcome.HANDED_OFF
    assert backend.bookings(TENANT) == []


async def test_the_agent_stops_talking_when_the_caller_starts(pack):
    backend, ledger, registry = fresh(pack)
    session = CallSession(tenant_id=TENANT, pack=pack, backend=backend,
                          registry=registry, ledger=ledger)
    await session.open()
    await session.handle_utterance(Utterance("mujhe root canal karwana hai"))
    # The agent is now part-way through offering a slot; the caller cuts in.
    record = await session.handle_utterance(Utterance("kal subah", barge_in=True))
    assert record.interrupted
    assert session.tts.interruptions >= 1
    assert session.tts.spoken[-1] != ""          # it had started before being cut


async def test_a_polite_caller_hears_the_whole_sentence(pack):
    backend, ledger, registry = fresh(pack)
    session = CallSession(tenant_id=TENANT, pack=pack, backend=backend,
                          registry=registry, ledger=ledger)
    await session.open()
    record = await session.handle_utterance(Utterance("mujhe root canal karwana hai"))
    assert not record.interrupted
    assert session.tts.interruptions == 0


async def test_biasing_hints_reach_the_recogniser(pack):
    backend, ledger, registry = fresh(pack)
    session = CallSession(tenant_id=TENANT, pack=pack, backend=backend,
                          registry=registry, ledger=ledger)
    assert session.stt.hint_calls == 1
    assert "root canal" in session.stt.hints


async def test_the_result_is_identical_with_speculation_on_and_off(pack):
    """Speculation must be a pure latency optimisation. If the transcript of
    the call changes when it is switched on, it is a bug, not a speed-up."""
    scenario = next(s for s in scenarios_of(pack) if s.expect == "BOOKED")
    said = {}
    for enabled in (True, False):
        backend, ledger, registry = fresh(pack)
        cfg = EngineConfig(speculation=SpeculationConfig(enabled=enabled))
        _, report = await run_scenario(scenario, pack=pack, backend=backend,
                                       registry=registry, ledger=ledger, config=cfg,
                                       tenant_id=TENANT)
        said[enabled] = [re.sub(r"[0-9A-F]{4}-[0-9A-F]{4}", "<code>", t.said)
                         for t in report.turns]
        assert report.outcome is Outcome.BOOKED
    assert said[True] == said[False]


async def test_without_the_correction_layer_the_noisy_call_derails(pack):
    scenario = next(s for s in scenarios_of(pack) if s.name == "booking_with_asr_noise")
    backend, ledger, registry = fresh(pack)
    cfg = EngineConfig(bhasha=BhashaConfig(enabled=False))
    _, report = await run_scenario(scenario, pack=pack, backend=backend, registry=registry,
                                   ledger=ledger, config=cfg, tenant_id=TENANT)
    assert report.outcome is not Outcome.BOOKED
