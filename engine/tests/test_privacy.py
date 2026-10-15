"""DPDP in code: encrypted personal fields in an immutable ledger, erasure by key-shredding, retention, consent."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.pramaan.vault import Vault
from haanji.pramaan.verifier import verify_chain
from haanji.scenario import scenarios_of
from haanji.vertical import load_pack

PHONE = "9876543210"


@pytest.fixture
def client():
    server._buckets.clear()
    return TestClient(server.app)


def book(client, phone=PHONE):
    sc = next(s for s in scenarios_of(load_pack("dental_clinic")) if s.name == "booking_with_asr_noise")
    codes = []
    for u in sc.utterances:
        text = u.truth.replace("9876543210", phone)
        r = client.post("/api/wa/incoming", json={"pack": "dental_clinic", "phone": phone, "text": text}).json()
        codes += [c for rep in r["replies"] for c in rep.get("receipts", [])]
    return codes


def test_the_vault_seals_opens_and_shreds(tmp_path):
    v = Vault(str(tmp_path / "v.sqlite"))
    sealed = v.seal_args({"service": "root canal", "phone": "+91 98765 43210", "customer_name": "Vijay Sharma"})
    assert "phone" not in sealed and "customer_name" not in sealed and sealed["service"] == "root canal"
    assert sealed["subject"] == v.subject("9876543210") and sealed["phone_enc"] != "9876543210"
    opened = v.open_args(sealed)
    assert opened["phone"] == "+91 98765 43210" and opened["customer_name"] == "Vijay Sharma"
    assert v.forget("9876543210") and v.is_shredded("9876543210")
    assert v.open_args(sealed)["customer_name"] is None, "the key is gone: unreadable"
    assert v.seal_args({"phone": "9876543210", "customer_name": "X"}).get("pii") == "erased", "no new key for a forgotten customer"
    assert v.seal_args({"service": "x"}) == {"service": "x"}, "nothing personal, nothing changed"
    assert v.count() == {"keys": 0, "shredded": 1}


def test_receipts_carry_ciphertext_and_the_chain_survives_erasure(client):
    codes = book(client, "9811122233")
    assert codes
    rt = server.runtime("dental_clinic")
    receipt = rt.ledger.by_code("dental_clinic", codes[-1])
    assert "phone" not in receipt.action_args and "customer_name" not in receipt.action_args
    assert receipt.action_args["phone_enc"] and receipt.action_args["subject"]
    public = rt.ledger.public_key(rt.ledger.ensure_key("dental_clinic"))
    assert verify_chain(rt.ledger.receipts("dental_clinic"), lambda _k: public).ok
    opened = client.get(f"/api/receipts/{codes[-1]}/open", params={"pack": "dental_clinic"}).json()
    assert opened["fields"]["phone"] == "9811122233" and opened["fields"]["customer_name"] == "Vijay Sharma" and not opened["erased"]
    held = client.get("/api/privacy/customer/9811122233", params={"pack": "dental_clinic"}).json()
    assert held["bookings"] and held["receipts"] and held["calls"] and held["whatsapp_messages"] > 0 and not held["erased"]
    gone = client.delete("/api/privacy/customer/9811122233", params={"pack": "dental_clinic"}).json()
    assert gone["key_shredded"] and gone["bookings_anonymised"] >= 1 and gone["calls_deleted"] >= 1 and gone["whatsapp_messages_deleted"] >= 1
    assert verify_chain(rt.ledger.receipts("dental_clinic"), lambda _k: public).ok, "receipts untouched, chain intact"
    opened = client.get(f"/api/receipts/{codes[-1]}/open", params={"pack": "dental_clinic"}).json()
    assert opened["erased"] and opened["fields"]["phone"] is None and opened["fields"]["service"] == "root canal"
    held = client.get("/api/privacy/customer/9811122233", params={"pack": "dental_clinic"}).json()
    assert held["erased"] and held["bookings"] == [] and held["calls"] == []
    assert client.get("/api/receipts/NOPE-0000/open", params={"pack": "dental_clinic"}).status_code == 404


def test_retention_purges_old_call_records_only(client, monkeypatch):
    book(client, "9811122244")
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=400)).isoformat(timespec="seconds")
    with server.store.conn:
        server.store.conn.execute("UPDATE calls SET started_at=? WHERE phone LIKE '%9811122244'", (old,))
    assert server.purge_old_records(0) == {"calls": 0, "whatsapp_messages": 0, "missed_calls": 0}
    purged = server.purge_old_records(90)
    assert purged["calls"] >= 1
    rt = server.runtime("dental_clinic")
    assert any(b.phone == "9811122244" for b in rt.backend.bookings("dental_clinic")), "bookings are the business's records"
    policy = client.get("/api/privacy/policy").json()
    assert "retention_days" in policy and "vault" in policy


def test_the_consent_line_opens_every_call(client, monkeypatch):
    monkeypatch.setattr(server, "CONSENT_LINE", "Yeh call AI receptionist HaanJi utha raha hai aur record ho rahi hai.")
    r = client.post("/api/sessions", json={"pack": "dental_clinic"}).json()
    assert r["greeting"].endswith("record ho rahi hai.") and r["greeting"].startswith("Haanji")
    assert client.get("/api/status").json()["privacy"]["consent"] is True
