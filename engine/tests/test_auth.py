"""Opt-in sign-in for the owner console: OTP on WhatsApp, two roles, per-pack scope."""
import time

import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.auth import AuthStore, Principal
from haanji.channels import whatsapp as wa

OWNER, STAFF, STRANGER = "9800000001", "9800000002", "9800000009"


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


def login(client, phone):
    code = client.post("/api/auth/otp", json={"phone": phone}).json()["dev_code"]
    r = client.post("/api/auth/verify", json={"phone": phone, "code": code})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_with_auth_off_the_demo_is_open(monkeypatch):
    monkeypatch.setattr(server, "AUTH_ENABLED", False)
    c = TestClient(server.app)
    assert c.get("/api/insights", params={"pack": "dental_clinic"}).status_code == 200
    assert c.post("/api/auth/otp", json={"phone": OWNER}).status_code == 409
    assert c.get("/api/auth/me").json() == {"enabled": False, "user": None}


def test_protected_endpoints_need_a_token_and_public_ones_do_not(client):
    assert client.get("/api/insights", params={"pack": "dental_clinic"}).status_code == 401
    assert client.get("/api/status").status_code == 200
    assert client.get("/api/receipts/export", params={"pack": "dental_clinic"}).status_code == 200
    assert client.post("/api/sessions", json={"pack": "dental_clinic"}).status_code == 200
    assert client.get("/talk").status_code == 200


def test_the_owner_signs_in_with_a_whatsapp_code(client, monkeypatch):
    sent = []

    async def fake_send(to, text):
        sent.append((to, text))
    monkeypatch.setattr(wa, "send_text", fake_send)
    monkeypatch.setenv("HAANJI_WA_TOKEN", "t"); monkeypatch.setenv("HAANJI_WA_PHONE_ID", "1")
    r = client.post("/api/auth/otp", json={"phone": "+91 " + OWNER}).json()
    assert r == {"sent": True, "channel": "whatsapp"} and sent and sent[0][0] == OWNER
    code = sent[0][1].split("code: ")[1].split()[0]
    assert client.post("/api/auth/verify", json={"phone": OWNER, "code": "000000"}).status_code == 401
    tok = client.post("/api/auth/verify", json={"phone": OWNER, "code": code}).json()
    assert tok["user"]["role"] == "owner" and tok["user"]["name"] == "Dr Mehta"
    me = client.get("/api/auth/me", headers={"Authorization": "Bearer " + tok["token"]}).json()
    assert me["user"]["phone"] == OWNER
    assert client.post("/api/auth/verify", json={"phone": OWNER, "code": code}).status_code == 401, "a code works once"


def test_unknown_numbers_get_the_same_answer_and_no_code(client):
    r = client.post("/api/auth/otp", json={"phone": STRANGER}).json()
    assert r["sent"] is True and "dev_code" not in r


def test_roles_and_pack_scope(client):
    owner, staff = login(client, OWNER), login(client, STAFF)
    assert client.get("/api/insights", params={"pack": "dental_clinic"}, headers=staff).status_code == 200
    assert client.get("/api/insights", params={"pack": "salon_spa"}, headers=staff).status_code == 403
    assert client.get("/api/insights", params={"pack": "salon_spa"}, headers=owner).status_code == 200
    yaml_text = client.get("/api/packs/dental_clinic", headers=staff).json()["yaml"]
    assert client.post("/api/packs/validate", json={"yaml": yaml_text}, headers=staff).status_code == 403
    assert client.post("/api/packs/validate", json={"yaml": yaml_text}, headers=owner).status_code == 200
    assert client.get("/api/events/recent", params={"pack": "dental_clinic"}, headers=staff).status_code == 200
    assert client.get("/api/auth/users", headers=staff).status_code == 403
    users = client.get("/api/auth/users", headers=owner).json()["users"]
    assert {u["phone"] for u in users} == {OWNER, STAFF}


def test_the_owner_manages_users_but_not_themselves(client):
    owner = login(client, OWNER)
    r = client.post("/api/auth/users", json={"phone": "9800000003", "role": "staff", "packs": ["salon_spa"], "name": "Ravi"}, headers=owner)
    assert r.status_code == 200 and r.json()["user"]["packs"] == ["salon_spa"]
    assert client.post("/api/auth/users", json={"phone": "9800000004", "role": "god"}, headers=owner).status_code == 422
    assert client.delete("/api/auth/users/9800000003", headers=owner).json()["removed"] is True
    assert client.delete(f"/api/auth/users/{OWNER}", headers=owner).status_code == 409


def test_tokens_are_signed_scoped_and_expire(tmp_path):
    a = AuthStore(str(tmp_path / "a.sqlite"), "s1")
    p = Principal("9800000001", "staff", ["salon_spa"])
    tok = a.token_for(p, now=1000.0)
    assert a.verify_token(tok, now=1001.0).packs == ["salon_spa"]
    assert a.verify_token(tok, now=1000.0 + 31 * 24 * 3600) is None, "expired"
    assert a.verify_token(tok[:-2] + "zz", now=1001.0) is None, "tampered signature"
    assert AuthStore(str(tmp_path / "b.sqlite"), "s2").verify_token(tok, now=1001.0) is None, "another secret"
    assert p.allows("salon_spa") and not p.allows("dental_clinic") and Principal("x", "owner").allows("anything")


def test_otp_expires_and_locks_after_too_many_tries(tmp_path):
    a = AuthStore(str(tmp_path / "a.sqlite"), "s")
    code = a.issue_otp("9800000001", now=1000.0)
    assert not a.check_otp("9800000001", code, now=1000.0 + 301), "expired"
    code = a.issue_otp("9800000001", now=2000.0)
    for _ in range(5):
        assert not a.check_otp("9800000001", "111111", now=2001.0)
    assert not a.check_otp("9800000001", code, now=2001.0), "locked after five wrong tries"


def test_a_fresh_deployment_seeds_the_owner_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "auth", AuthStore(str(tmp_path / "auth.sqlite"), "s"))
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    monkeypatch.setattr(server, "OWNER_PHONE", "9811111111")
    server.seed_owner()
    assert server.auth.user("9811111111").role == "owner"
    server.auth.upsert_user("9811111111", "staff")
    server.seed_owner()
    assert server.auth.user("9811111111").role == "staff", "never overrides an existing user table"
    assert time.time() > 0
