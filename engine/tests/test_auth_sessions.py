"""Sign-in for a real shop, past the first login: each device is a session
the owner can see and end; a device unused for two weeks is signed out; a
device in use is refreshed instead of expiring; every change an owner or
staff member makes lands in an activity log only the owner can read."""
import time

import pytest
from fastapi.testclient import TestClient

from haanji import auth as auth_mod
from haanji import server
from haanji.auth import AuthStore

OWNER, STAFF = "9800000101", "9800000102"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "auth", AuthStore(str(tmp_path / "auth.sqlite"), "test-secret"))
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    monkeypatch.setattr(server, "AUTH_DEV", True)
    monkeypatch.delenv("HAANJI_WA_TOKEN", raising=False)
    server._buckets.clear()
    server.auth.upsert_user(OWNER, "owner", ["*"], name="Dr Mehta")
    server.auth.upsert_user(STAFF, "staff", ["dental_clinic"], name="Priya")
    return TestClient(server.app)


def login(client, phone, agent="pytest-phone"):
    code = client.post("/api/auth/otp", json={"phone": phone}).json()["dev_code"]
    r = client.post("/api/auth/verify", json={"phone": phone, "code": code}, headers={"User-Agent": agent})
    return r.json()["token"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_each_sign_in_is_a_device_the_owner_can_see_and_end(client):
    phone_tok = login(client, OWNER, "Android phone")
    laptop_tok = login(client, OWNER, "Laptop")
    seen = client.get("/api/auth/sessions", headers=bearer(phone_tok)).json()["sessions"]
    assert {d["agent"] for d in seen} == {"Android phone", "Laptop"}
    assert [d["current"] for d in seen if d["agent"] == "Android phone"] == [True]
    laptop = next(d for d in seen if d["agent"] == "Laptop")
    assert client.delete(f"/api/auth/sessions/{laptop['sid']}", headers=bearer(phone_tok)).json() == {"ok": True}
    assert client.get("/api/auth/me", headers=bearer(laptop_tok)).status_code == 401
    assert client.get("/api/auth/me", headers=bearer(phone_tok)).status_code == 200


def test_staff_cannot_end_someone_else_s_device(client):
    owner_tok = login(client, OWNER)
    staff_tok = login(client, STAFF)
    sid = client.get("/api/auth/sessions", headers=bearer(owner_tok)).json()["sessions"][0]["sid"]
    assert client.delete(f"/api/auth/sessions/{sid}", headers=bearer(staff_tok)).status_code == 404
    assert client.get("/api/auth/me", headers=bearer(owner_tok)).status_code == 200


def test_a_device_unused_for_two_weeks_is_signed_out(tmp_path):
    a = AuthStore(str(tmp_path / "a.sqlite"), "s")
    p = a.upsert_user(OWNER, "owner", ["*"])
    t0 = 1_800_000_000.0
    tok = a.token_for(p, t0)
    assert a.verify_token(tok, t0 + 13 * 86400) is not None, "used on day 13"
    assert a.verify_token(tok, t0 + 26 * 86400) is not None, "day 13 counted as use; day 26 is 13 days later"
    assert a.verify_token(tok, t0 + 26 * 86400 + auth_mod.IDLE_TTL_S + 1) is None


def test_a_device_in_use_is_refreshed_not_expired(tmp_path):
    a = AuthStore(str(tmp_path / "a.sqlite"), "s")
    p = a.upsert_user(OWNER, "owner", ["*"])
    t0 = 1_800_000_000.0
    tok = a.token_for(p, t0)
    assert a.refresh(tok, t0 + 3600) == tok, "too young to refresh"
    newer = a.refresh(tok, t0 + 8 * 86400)
    assert newer and newer != tok
    assert a.claims(newer, t0 + 8 * 86400)["sid"] == a.claims(tok, t0 + 8 * 86400)["sid"], "the same device"
    assert a.verify_token(newer, t0 + 20 * 86400) is not None, "used on day 20"
    assert a.verify_token(newer, t0 + 33 * 86400) is not None, "past the old token's 30 days"
    assert a.verify_token(tok, t0 + 33 * 86400) is None
    assert len(a.sessions_of(OWNER, t0 + 33 * 86400)) == 1


def test_every_change_lands_in_an_activity_log_only_the_owner_reads(client):
    owner_tok = login(client, OWNER)
    staff_tok = login(client, STAFF)
    r = client.put("/api/settings", params={"pack": "dental_clinic"}, json={"deposit_inr": 300}, headers=bearer(owner_tok))
    assert r.status_code == 200
    log = client.get("/api/audit", headers=bearer(owner_tok)).json()["entries"]
    assert log[0]["phone"] == OWNER and log[0]["method"] == "PUT" and log[0]["path"] == "/api/settings"
    assert log[0]["pack"] == "dental_clinic" and log[0]["status"] == 200
    assert client.get("/api/audit", headers=bearer(staff_tok)).status_code == 403
    client.get("/api/insights", params={"pack": "dental_clinic"}, headers=bearer(staff_tok))
    assert len(client.get("/api/audit", headers=bearer(owner_tok)).json()["entries"]) == len(log), "reads are not logged"


def test_a_token_from_before_devices_still_works_until_it_expires(tmp_path):
    import base64, hashlib, hmac, json
    a = AuthStore(str(tmp_path / "a.sqlite"), "s")
    p = a.upsert_user(OWNER, "owner", ["*"])
    now = time.time()
    body = json.dumps({"phone": p.phone, "role": "owner", "packs": ["*"], "name": "", "iat": int(now), "exp": int(now + 60)},
                      separators=(",", ":"))
    payload = base64.urlsafe_b64encode(body.encode()).rstrip(b"=")
    sig = base64.urlsafe_b64encode(hmac.new(b"s", payload, hashlib.sha256).digest()).rstrip(b"=").decode()
    assert a.verify_token(payload.decode() + "." + sig) is not None
