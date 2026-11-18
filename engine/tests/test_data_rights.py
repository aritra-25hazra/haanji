"""A customer's own data rights: a WhatsApp code proves the number; a copy
comes back at once; an erasure waits for the owner's yes and leaves a log
that holds only a keyed hash of the number. Backups age out with the data."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from haanji import backup, server
from haanji.scenario import scenarios_of
from haanji.vertical import load_pack

PACK = "dental_clinic"
PHONE = "9811100031"


@pytest.fixture
def client(monkeypatch):
    server._buckets.clear()
    monkeypatch.setattr(server, "IS_PUBLIC", False)
    monkeypatch.delenv("HAANJI_WA_TOKEN", raising=False)
    return TestClient(server.app)


def book(client, phone=PHONE):
    sc = next(s for s in scenarios_of(load_pack(PACK)) if s.name == "booking_with_asr_noise")
    for u in sc.utterances:
        client.post("/api/wa/incoming", json={"pack": PACK, "phone": phone, "text": u.truth.replace("9876543210", phone)})


def code_for(client, phone=PHONE):
    r = client.post("/api/privacy/request", json={"pack": PACK, "phone": phone})
    assert r.status_code == 200, r.text
    return r.json()["dev_code"]


def test_a_customer_downloads_their_own_data_with_a_code(client):
    book(client)
    assert client.post("/api/privacy/request/verify", json={"pack": PACK, "phone": PHONE, "code": "000000", "kind": "export"}).status_code == 401
    r = client.post("/api/privacy/request/verify", json={"pack": PACK, "phone": PHONE, "code": code_for(client), "kind": "export"})
    assert r.status_code == 200 and r.json()["record"]["bookings"]
    log = client.get("/api/privacy/requests", params={"pack": PACK}).json()["requests"]
    assert log[0]["kind"] == "export" and log[0]["status"] == "DONE" and PHONE not in str(log[0])


def test_an_erasure_waits_for_the_owner_and_leaves_only_a_hash(client):
    book(client, "9811100032")
    code = code_for(client, "9811100032")
    r = client.post("/api/privacy/request/verify", json={"pack": PACK, "phone": "9811100032", "code": code, "kind": "erase"}).json()
    rid = r["request"]["request_id"]
    assert r["request"]["status"] == "PENDING"
    held = client.get("/api/privacy/customer/9811100032", params={"pack": PACK}).json()
    assert held["bookings"], "nothing is erased before the owner says yes"
    done = client.post(f"/api/privacy/requests/{rid}", params={"pack": PACK}, json={"approve": True}).json()
    assert done["status"] == "ERASED" and done["result"]["key_shredded"] and done["result"]["calls_deleted"] >= 1
    assert "9811100032" not in str(server.store.privacy_request(PACK, rid, with_phone=True))
    assert done["subject"] and done["shown"] != "9811100032"
    assert client.post(f"/api/privacy/requests/{rid}", params={"pack": PACK}, json={"approve": True}).status_code == 409


def test_the_owner_can_refuse_and_nothing_is_erased(client):
    book(client, "9811100033")
    code = code_for(client, "9811100033")
    rid = client.post("/api/privacy/request/verify", json={"pack": PACK, "phone": "9811100033", "code": code, "kind": "erase"}).json()["request"]["request_id"]
    assert client.post(f"/api/privacy/requests/{rid}", params={"pack": PACK}, json={"approve": False}).json()["status"] == "REJECTED"
    assert client.get("/api/privacy/customer/9811100033", params={"pack": PACK}).json()["bookings"]


def test_a_public_server_never_shows_a_code_and_strangers_cannot_decide(client, monkeypatch):
    monkeypatch.setattr(server, "IS_PUBLIC", True)
    assert client.post("/api/privacy/request", json={"pack": PACK, "phone": "9811100034"}).status_code == 503
    monkeypatch.setattr(server, "DEMO_READONLY", True)
    assert client.post("/api/privacy/requests/abc", params={"pack": PACK}, json={"approve": True}).status_code == 403


def test_the_my_data_page_is_served(client):
    r = client.get("/my-data")
    assert r.status_code == 200 and "My data" in r.text and "api/privacy/request" in r.text


class FakeS3:
    def __init__(self, objects):
        self.objects, self.deleted = objects, []

    def list_objects_v2(self, Bucket, Prefix):
        return {"Contents": [{"Key": k, "LastModified": t} for k, t in self.objects.items()]}

    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)


def test_backups_older_than_the_retention_period_are_deleted_but_never_the_newest(monkeypatch):
    monkeypatch.setenv("HAANJI_BACKUP_S3_BUCKET", "b")
    now = dt.datetime(2026, 11, 18, tzinfo=dt.timezone.utc)
    s3 = FakeS3({"haanji/old.tgz": now - dt.timedelta(days=200), "haanji/mid.tgz": now - dt.timedelta(days=30),
                 "haanji/new.tgz": now - dt.timedelta(days=1)})
    assert backup.prune_s3(180, now=now, client=s3) == ["haanji/old.tgz"] and s3.deleted == ["haanji/old.tgz"]
    lone = FakeS3({"haanji/only.tgz": now - dt.timedelta(days=400)})
    assert backup.prune_s3(180, now=now, client=lone) == []
