"""The ledger's job is to make it impossible to change what a caller agreed to
without the change being visible. These tests are the attacks."""
import copy
import sqlite3

import pytest

from haanji.pramaan.ledger import Ledger, LedgerError
from haanji.pramaan.receipt import ConfirmationProof, Receipt, canonical_json
from haanji.pramaan.verifier import verify_chain, verify_receipt

TENANT = "t_ledger"


def proof(reply="haan confirm kar do", conf=0.94):
    return ConfirmationProof(
        prompt_text="root canal, kal subah 9:30 baje. Confirm kar dun?",
        prompt_start_ms=1000, reply_text=reply, reply_start_ms=4200,
        asr_confidence=conf, audio_offset_ms=3200)


def seal(led, i=0, action="book_appointment", confirmation=None):
    return led.append(tenant_id=TENANT, conversation_id=f"c{i}", action=action,
                      action_args={"service": "root canal", "time": "09:30", "seq": i},
                      confirmation=proof() if confirmation is None else confirmation,
                      transcript_excerpt="caller: haan confirm kar do")


@pytest.fixture
def led():
    return Ledger(sqlite3.connect(":memory:"))


def public(led):
    return led.public_key(led.ensure_key(TENANT))


def test_a_clean_chain_verifies(led):
    receipts = [seal(led, i) for i in range(5)]
    report = verify_chain(receipts, lambda _k: public(led))
    assert report.ok and report.checked == 5


def test_a_write_without_confirmation_is_refused(led):
    with pytest.raises(LedgerError):
        seal(led, 0, confirmation=False or None) if False else led.append(
            tenant_id=TENANT, conversation_id="c", action="book_appointment",
            action_args={}, confirmation=None, transcript_excerpt="")


def test_a_non_committing_action_may_be_sealed_without_a_proof(led):
    r = led.append(tenant_id=TENANT, conversation_id="c", action="capture_lead",
                   action_args={"phone": "9876543210"}, confirmation=None,
                   transcript_excerpt="caller: mera number", require_confirmation=False)
    assert r.seq == 1


@pytest.mark.parametrize("mutate", [
    lambda r: r.action_args.__setitem__("time", "18:00"),
    lambda r: r.action_args.__setitem__("service", "dental implant"),
    lambda r: r.confirmation.__setitem__("reply_text", "haan"),
    lambda r: r.confirmation.__setitem__("asr_confidence", 0.99),
    lambda r: setattr(r, "transcript_excerpt", "caller: haan"),
    lambda r: setattr(r, "occurred_at", "2020-01-01T00:00:00+00:00"),
    lambda r: setattr(r, "agent_config_version", 99),
    lambda r: setattr(r, "action", "cancel_appointment"),
])
def test_every_single_field_edit_is_detected(led, mutate):
    receipts = [seal(led, i) for i in range(5)]
    tampered = copy.deepcopy(receipts)
    victim = tampered[2]
    victim.action_args = dict(victim.action_args)
    victim.confirmation = dict(victim.confirmation)
    mutate(victim)
    report = verify_chain(tampered, lambda _k: public(led))
    assert not report.ok
    assert report.first_broken_seq == 3


def test_deleting_a_receipt_breaks_the_chain(led):
    receipts = [seal(led, i) for i in range(6)]
    report = verify_chain(receipts[:2] + receipts[3:], lambda _k: public(led))
    assert not report.ok


def test_rehashing_a_forged_receipt_still_fails_the_signature(led):
    receipts = [seal(led, i) for i in range(3)]
    forged = copy.deepcopy(receipts[1])
    forged.action_args = dict(forged.action_args) | {"time": "18:00"}
    forged.payload_hash = forged.compute_payload_hash()
    forged.chain_hash = forged.compute_chain_hash()
    ok, reason = verify_receipt(forged, public(led))
    assert not ok and "signature" in reason


def test_a_receipt_signed_by_another_tenant_key_is_rejected(led):
    other = Ledger(sqlite3.connect(":memory:"))
    other.ensure_key("someone_else")
    receipts = [seal(led, 0)]
    ok, _ = verify_receipt(receipts[0], other.public_key(other.ensure_key("someone_else")))
    assert not ok


def test_sequence_numbers_are_dense_and_per_tenant(led):
    a = [seal(led, i) for i in range(3)]
    b = led.append(tenant_id="other_tenant", conversation_id="x", action="capture_lead",
                   action_args={}, confirmation=None, transcript_excerpt="",
                   require_confirmation=False)
    assert [r.seq for r in a] == [1, 2, 3]
    assert b.seq == 1


def test_the_daily_anchor_summarises_the_day(led):
    for i in range(4):
        seal(led, i)
    anchor = led.anchor_day(TENANT)
    assert isinstance(anchor, str) and len(anchor) >= 32
    assert led.anchor_day(TENANT) == anchor        # anchoring twice is stable


def test_the_short_code_is_stable_and_readable(led):
    r = seal(led, 0)
    assert r.short_code() == r.short_code()
    assert len(r.short_code()) == 9 and "-" in r.short_code()


def test_canonical_json_is_order_independent():
    assert canonical_json({"b": 1, "a": [1, {"d": 2, "c": 3}]}) == \
           canonical_json({"a": [1, {"c": 3, "d": 2}]} | {"b": 1})


def test_a_receipt_survives_a_round_trip_through_the_database(led):
    original = seal(led, 0)
    loaded = led.receipts(TENANT)[0]
    assert loaded.chain_hash == original.chain_hash
    ok, _ = verify_receipt(loaded, public(led))
    assert ok
