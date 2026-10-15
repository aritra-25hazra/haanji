"""Property-based tests for the ledger: random receipts, random tampering, always caught."""
import copy
import sqlite3

from hypothesis import given, settings, strategies as st

from haanji.pramaan.ledger import Ledger
from haanji.pramaan.receipt import ConfirmationProof
from haanji.pramaan.verifier import verify_chain, verify_receipt

TENANT = "t_prop"
text = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=0, max_size=40)
field_names = st.sampled_from(["action_args.time", "action_args.service", "confirmation.reply_text",
                               "confirmation.asr_confidence", "transcript_excerpt", "occurred_at",
                               "agent_config_version", "action"])


def sealed(n: int, texts: list[str]):
    ledger = Ledger(sqlite3.connect(":memory:"))
    receipts = []
    for i in range(n):
        proof = ConfirmationProof(prompt_text=texts[i % len(texts)] or "q", prompt_start_ms=1000 + i,
                                  reply_text="haan", reply_start_ms=2000 + i, asr_confidence=0.9, audio_offset_ms=1000)
        receipts.append(ledger.append(tenant_id=TENANT, conversation_id=f"c{i}", action="book_appointment",
                                      action_args={"service": "root canal", "time": f"{9 + i % 8:02d}:00", "seq": i},
                                      confirmation=proof, transcript_excerpt=texts[(i + 1) % len(texts)], agent_config_version=1))
    public = ledger.public_key(ledger.ensure_key(TENANT))
    return receipts, public


def mutate(r, field: str, value):
    r.action_args = dict(r.action_args)
    r.confirmation = dict(r.confirmation)
    if field == "action_args.time":
        r.action_args["time"] = value
    elif field == "action_args.service":
        r.action_args["service"] = value
    elif field == "confirmation.reply_text":
        r.confirmation["reply_text"] = value
    elif field == "confirmation.asr_confidence":
        r.confirmation["asr_confidence"] = 0.123
    elif field == "transcript_excerpt":
        r.transcript_excerpt = value
    elif field == "occurred_at":
        r.occurred_at = "1999-01-01T00:00:00+00:00"
    elif field == "agent_config_version":
        r.agent_config_version = 42
    elif field == "action":
        r.action = "cancel_appointment"


@settings(max_examples=40, deadline=None)
@given(n=st.integers(min_value=1, max_value=8), texts=st.lists(text, min_size=1, max_size=4),
       which=st.integers(min_value=0, max_value=7), field=field_names, value=text)
def test_any_change_to_any_sealed_field_is_detected(n, texts, which, field, value):
    receipts, public = sealed(n, texts)
    assert verify_chain(receipts, lambda _k: public).ok
    tampered = copy.deepcopy(receipts)
    target = tampered[which % n]
    before = (dict(target.action_args), dict(target.confirmation), target.transcript_excerpt,
              target.occurred_at, target.agent_config_version, target.action)
    mutate(target, field, value)
    after = (dict(target.action_args), dict(target.confirmation), target.transcript_excerpt,
             target.occurred_at, target.agent_config_version, target.action)
    if before == after:
        return                                           # the random value happened to equal the original
    report = verify_chain(tampered, lambda _k: public)
    assert not report.ok and report.first_broken_seq <= target.seq


@settings(max_examples=30, deadline=None)
@given(n=st.integers(min_value=3, max_value=8), drop=st.integers(min_value=0, max_value=7))
def test_removing_any_interior_receipt_breaks_the_chain(n, drop):
    """The verifier accepts a chain that starts after genesis (a partial export
    is a valid sub-chain) and one that ends early (see the truncation test);
    anything missing in between is a gap it names."""
    receipts, public = sealed(n, ["q"])
    i = 1 + drop % (n - 2)                               # interior: never the first or the last
    shorter = receipts[:i] + receipts[i + 1:]
    report = verify_chain(shorter, lambda _k: public)
    assert not report.ok and report.first_broken_seq is not None


def test_truncation_is_invisible_to_the_chain_and_visible_to_the_anchor():
    """Cutting the tail off a chain leaves a shorter chain that is internally
    valid — a hash chain cannot know what came after its last link. That is
    what the signed daily Merkle root is for: it pins the day's last receipt."""
    import datetime as dt
    import hashlib
    ledger = Ledger(sqlite3.connect(":memory:"))
    proof = ConfirmationProof(prompt_text="q", prompt_start_ms=1, reply_text="haan", reply_start_ms=2, asr_confidence=0.9)
    receipts = [ledger.append(tenant_id=TENANT, conversation_id=f"c{i}", action="book_appointment",
                              action_args={"seq": i}, confirmation=proof, transcript_excerpt="", agent_config_version=1)
                for i in range(4)]
    public = ledger.public_key(ledger.ensure_key(TENANT))
    assert verify_chain(receipts[:-1], lambda _k: public).ok, "the chain alone accepts a truncated history"
    day = receipts[0].occurred_at[:10]
    root = ledger.anchor_day(TENANT, day)
    layer = [r.chain_hash for r in receipts[:-1]]
    while len(layer) > 1:
        layer = [hashlib.sha256(layer[i] + (layer[i + 1] if i + 1 < len(layer) else layer[i])).digest()
                 for i in range(0, len(layer), 2)]
    assert layer[0].hex() != root, "the published root does not match a truncated day"


@settings(max_examples=30, deadline=None)
@given(n=st.integers(min_value=2, max_value=8), a=st.integers(min_value=0, max_value=7), b=st.integers(min_value=0, max_value=7))
def test_swapping_the_order_of_any_two_receipts_breaks_the_chain(n, a, b):
    """The verifier reads receipts in sequence order, so reordering means
    swapping their sequence numbers; the prev_hash links then disagree."""
    receipts, public = sealed(n, ["q"])
    i, j = a % n, b % n
    if i == j:
        return
    swapped = copy.deepcopy(receipts)
    swapped[i].seq, swapped[j].seq = swapped[j].seq, swapped[i].seq
    assert not verify_chain(swapped, lambda _k: public).ok


@settings(max_examples=20, deadline=None)
@given(n=st.integers(min_value=1, max_value=6), value=text)
def test_a_rehashed_forgery_still_fails_the_signature(n, value):
    receipts, public = sealed(n, ["q"])
    forged = copy.deepcopy(receipts[-1])
    forged.action_args = dict(forged.action_args) | {"time": "23:59", "note": value}
    forged.payload_hash = forged.compute_payload_hash()
    forged.chain_hash = forged.compute_chain_hash()
    ok, _reason = verify_receipt(forged, public)
    assert not ok


def test_another_tenants_key_never_verifies():
    receipts, _ = sealed(3, ["q"])
    _, other = sealed(1, ["z"])
    assert not verify_chain(receipts, lambda _k: other).ok
