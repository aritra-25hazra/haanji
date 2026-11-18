"""Demo reset: a public demo can be emptied (by its operator's token, or
nightly) without ever rewriting a ledger — the old chain is archived whole —
and a real shop (sign-in on) can never be reset."""
import datetime as dt
import os

import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.pramaan.verifier import verify_chain
from haanji.scenario import scenarios_of
from haanji.vertical import load_pack

PACK = "dental_clinic"


@pytest.fixture
def client():
    server._buckets.clear()
    return TestClient(server.app)


def book(client, phone="9811100011"):
    sc = next(s for s in scenarios_of(load_pack(PACK)) if s.name == "booking_with_asr_noise")
    for u in sc.utterances:
        client.post("/api/wa/incoming", json={"pack": PACK, "phone": phone, "text": u.truth.replace("9876543210", phone)})


def test_a_reset_empties_the_pack_and_archives_the_old_chain_whole(client):
    book(client)
    rt = server.runtime(PACK)
    old = rt.ledger.receipts(PACK)
    assert old and server.store.calls(PACK, 50)
    r = client.post("/api/admin/demo-reset", params={"pack": PACK})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["removed"]["receipts"] == len(old) and body["removed"]["bookings"] >= 1
    fresh = server.runtime(PACK)
    assert fresh is not rt and fresh.ledger.receipts(PACK) == [] and server.store.calls(PACK, 50) == []
    assert [c["phone"] for c in fresh.backend.customers(PACK)] == ["9876543210"]     # only the seeded returning caller
    import sqlite3
    from haanji import db
    from haanji.pramaan.ledger import Ledger
    where = body["archived"]["ledger"]                # a file under var/archive/, or a renamed Postgres schema
    conn = db.open_schema(where) if db.database_url() else sqlite3.connect(os.path.join(server.VAR_DIR, where))
    kept = Ledger(conn, key_secret=server.LEDGER_KEY_SECRET)
    receipts = kept.receipts(PACK)
    assert len(receipts) == len(old)
    public = kept.public_key(kept.ensure_key(PACK))
    assert verify_chain(receipts, lambda _k: public).ok
    book(client, "9811100012")                       # the new chain works
    assert server.runtime(PACK).ledger.receipts(PACK)


def test_a_public_demo_needs_the_operator_s_token(client, monkeypatch):
    monkeypatch.setattr(server, "IS_PUBLIC", True)
    monkeypatch.setattr(server, "DEMO_RESET_TOKEN", None)
    assert client.post("/api/admin/demo-reset", params={"pack": PACK}).status_code == 403
    monkeypatch.setattr(server, "DEMO_RESET_TOKEN", "s3cret")
    assert client.post("/api/admin/demo-reset", params={"pack": PACK}, headers={"X-HaanJi-Reset": "wrong"}).status_code == 403
    assert client.post("/api/admin/demo-reset", params={"pack": PACK}, headers={"X-HaanJi-Reset": "s3cret"}).status_code == 200


def test_a_real_shop_is_never_reset(monkeypatch):
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    with pytest.raises(server.HTTPException) as e:
        server.demo_reset(PACK)
    assert e.value.status_code == 403
    monkeypatch.setattr(server, "DEMO_RESET_HOUR", "4")
    assert server._nightly_demo_reset(dt.datetime(2026, 11, 18, 4, 5, tzinfo=server.IST)) == []


def test_the_nightly_reset_runs_once_at_its_hour(monkeypatch):
    server.runtime(PACK)
    monkeypatch.setattr(server, "DEMO_RESET_HOUR", "4")
    monkeypatch.setattr(server, "_last_auto_reset", {})
    assert server._nightly_demo_reset(dt.datetime(2026, 11, 18, 3, 59, tzinfo=server.IST)) == []
    assert PACK in server._nightly_demo_reset(dt.datetime(2026, 11, 18, 4, 1, tzinfo=server.IST))
    assert server._nightly_demo_reset(dt.datetime(2026, 11, 18, 4, 30, tzinfo=server.IST)) == []
