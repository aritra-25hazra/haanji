"""Moving a booking: found by number, re-slotted through the ordinary flow, sealed as one receipt."""
import datetime as dt
import sqlite3

import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.adapters.mock import NullTTS
from haanji.models import Outcome
from haanji.pipeline import CallSession
from haanji.pramaan.ledger import Ledger
from haanji.pramaan.verifier import verify_chain
from haanji.tools.builtin import build_registry, open_backend
from haanji.vertical import load_pack

TODAY = dt.date(2026, 9, 7)
TENANT = "t_move"


async def session(pack, backend, registry, ledger, phone=None):
    s = CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry, ledger=ledger, tts=NullTTS())
    await s.open(phone=phone)
    return s


async def test_a_booking_is_moved_in_a_second_call_and_the_receipt_links_both():
    pack = load_pack("dental_clinic")
    backend, _ = open_backend(pack, TENANT, today=TODAY)
    ledger = Ledger(sqlite3.connect(":memory:"))
    registry = build_registry(TENANT, backend, pack, ledger)
    s = await session(pack, backend, registry, ledger)
    for line in ("mujhe root canal karwana hai", "kal subah ka time mil jayega", "haan ji wahi theek hai",
                 "mera naam Vijay Sharma hai number 9876543210", "haan confirm kar do"):
        await s.handle_text_turn(line)
    assert s.finish().outcome is Outcome.BOOKED
    old = backend.find_booking(TENANT, "9876543210")
    assert old is not None and old.date == "2026-09-08"

    s2 = await session(pack, backend, registry, ledger, phone="9876543210")
    rec = await s2.handle_text_turn("mujhe apni booking parso shaam ko badalni hai")
    assert "booking mili" in rec.said and s2.ctx.flags.get("reschedule_booking_id") == old.booking_id
    assert "check_availability" in rec.tools, "the new day was in the sentence, so slots are offered at once"
    rec = await s2.handle_text_turn("haan ji wahi theek hai")
    assert "badal dun" in rec.said.lower() or "confirm" in rec.said.lower()
    assert s2.ctx.pending_confirmation["action"] == "reschedule_appointment"
    rec = await s2.handle_text_turn("haan confirm kar do")
    assert "Badal diya" in rec.said and "reschedule_appointment" in rec.tools
    assert s2.finish().outcome is Outcome.RESCHEDULED
    moved = backend.find_booking(TENANT, "9876543210")
    assert moved.booking_id != old.booking_id and moved.date == "2026-09-09" and moved.status == "CONFIRMED"
    assert all(b.status == "CANCELLED" for b in backend.bookings(TENANT) if b.booking_id == old.booking_id)
    receipts = ledger.receipts(TENANT)
    assert receipts[-1].action == "reschedule_appointment"
    assert receipts[-1].action_args["previous_booking_id"] == old.booking_id
    assert receipts[-1].action_args["previous_receipt"] == old.receipt_code
    public = ledger.public_key(ledger.ensure_key(TENANT))
    assert verify_chain(receipts, lambda _k: public).ok


async def test_no_booking_on_that_number_is_said_plainly():
    pack = load_pack("dental_clinic")
    backend, _ = open_backend(pack, TENANT, today=TODAY)
    registry = build_registry(TENANT, backend, pack, Ledger(sqlite3.connect(":memory:")))
    s = await session(pack, backend, registry, None)
    rec = await s.handle_text_turn("booking ka time change karna hai")
    assert "number" in rec.said and s.ctx.flags.get("await_reschedule")
    rec = await s.handle_text_turn("9811100099")
    assert "koi booking nahi mili" in rec.said


async def test_cancel_words_still_cancel_and_reschedule_words_do_not():
    from haanji import nlu
    assert nlu.words("booking cancel kar do") & nlu.CANCEL_WORDS
    assert not (nlu.words("booking aage badalni hai") & nlu.CANCEL_WORDS)
    assert nlu.words("booking aage badalni hai") & nlu.RESCHEDULE_WORDS


def test_over_whatsapp_the_moved_booking_gets_a_receipt_link(monkeypatch):
    monkeypatch.setattr(server, "PUBLIC_URL", "https://haanji.example")
    server._buckets.clear()
    c = TestClient(server.app)
    phone = "9811100077"
    for line in ("mujhe teeth cleaning karwani hai", "kal subah ka time mil jayega", "haan ji wahi theek hai",
                 "mera naam Anita Rao hai", "haan confirm kar do"):
        c.post("/api/wa/incoming", json={"pack": "dental_clinic", "phone": phone, "text": line})
    replies = []
    for line in ("meri booking parso shaam ko shift kar do", "haan ji wahi theek hai", "haan pakka"):
        replies += c.post("/api/wa/incoming", json={"pack": "dental_clinic", "phone": phone, "text": line}).json()["replies"]
    last = [r for r in replies if r.get("receipts")][-1]
    assert "Badal diya" in last["text"] and "verify?code=" in last["text"]
