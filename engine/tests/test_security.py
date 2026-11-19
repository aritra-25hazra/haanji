"""The security review, kept as tests: which writes are public and why, where
the token secret lives, the password policy, the live feed's ticket, the
sign-in rate limit, and answers that do not reveal which accounts exist."""
import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from haanji import server
from haanji.auth import AuthStore

OWNER = "9800000001"

# Every route that changes something without a signed-in user, and why that
# is safe. A new public write route fails this test until it is listed here.
PUBLIC_WRITES = {
    ("POST", "/api/auth/login"): "sign-in: per-email lock and the sign-in rate limit",
    ("POST", "/api/auth/otp"): "sign-in code: per-number throttle and lock; same answer for unknown numbers",
    ("POST", "/api/auth/verify"): "sign-in code check: attempt limit and lock",
    ("POST", "/api/auth/logout"): "acts only on the caller's own token",
    ("POST", "/api/auth/refresh"): "needs a valid token",
    ("DELETE", "/api/auth/sessions/{sid}"): "needs a valid token; ends only the caller's own devices",
    ("POST", "/api/events/ticket"): "needs a valid token when sign-in is on",
    ("POST", "/api/auth/email-code"): "sign-in or reset code by email: throttle and lock; same answer for unknown emails",
    ("POST", "/api/auth/email-verify"): "email code check: attempt limit and lock",
    ("POST", "/api/auth/reset"): "needs the emailed reset code",
    ("POST", "/api/auth/2fa/verify"): "needs a fresh single-use ticket from a first factor",
    ("POST", "/api/sessions"): "a web call: the product's own public channel",
    ("POST", "/api/sessions/{sid}/partial"): "the call's id is the capability",
    ("POST", "/api/sessions/{sid}/utterance"): "the call's id is the capability",
    ("DELETE", "/api/sessions/{sid}"): "the call's id is the capability",
    ("POST", "/api/devanagari"): "pure transliteration, no state",
    ("POST", "/api/help/chat"): "the help assistant: per-client limit and a daily cap",
    ("POST", "/api/privacy/request"): "a customer's data request, proved by a code to their number",
    ("POST", "/api/privacy/request/verify"): "code check for a data request",
    ("POST", "/api/admin/demo-reset"): "needs X-HaanJi-Reset on a public server",
    ("POST", "/api/telephony/missed-call"): "needs X-HaanJi-Secret on a public server",
    ("POST", "/telephony/twilio/voice"): "needs Twilio's signature on a public server",
    ("POST", "/wa/webhook"): "needs Meta's signature on a public server",
    ("POST", "/wa/twilio"): "needs Twilio's signature on a public server",
}


class _Req:
    def __init__(self, method, path):
        self.method = method
        self.url = type("U", (), {"path": path})()


def public_writes():
    out = set()
    for r in server.app.routes:
        if not isinstance(r, APIRoute):
            continue
        for m in r.methods - {"GET", "HEAD"}:
            if server.required_role(_Req(m, re.sub(r"\{[^}]+\}", "x1234567890", r.path))) is None:
                out.add((m, r.path))
    return out


def test_every_public_write_route_is_listed_with_a_reason():
    unlisted = public_writes() - set(PUBLIC_WRITES)
    assert not unlisted, f"public write routes with no stated reason: {sorted(unlisted)}"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "auth", AuthStore(str(tmp_path / "auth.sqlite"), "test-secret"))
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    monkeypatch.setattr(server, "AUTH_DEV", True)
    server._buckets.clear()
    server.auth.upsert_user(OWNER, "owner", ["*"], name="Owner")
    server.auth.set_password(OWNER, "owner@clinic.test", "a-long-passphrase")
    yield TestClient(server.app)
    server._buckets.clear()


def bearer(client):
    tok = client.post("/api/auth/login", json={"email": "owner@clinic.test", "password": "a-long-passphrase"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_the_token_secret_survives_a_new_server_without_a_file(tmp_path):
    db = str(tmp_path / "auth.sqlite")
    first = AuthStore(db)
    assert first.secret_source == "database"
    (tmp_path / "auth.sqlite.secret").unlink(missing_ok=True)       # a throwaway disk loses files
    assert AuthStore(db).secret == first.secret
    assert AuthStore(db, "from-env").secret_source == "env"


def test_an_old_secret_file_is_adopted_once(tmp_path):
    db = str(tmp_path / "auth.sqlite")
    (tmp_path / "auth.sqlite.secret").write_text("legacy-secret")
    assert AuthStore(db).secret == b"legacy-secret"


def test_a_new_password_must_be_long_and_not_the_email(client):
    with pytest.raises(ValueError, match="at least 10"):
        server.auth.set_password(OWNER, "owner@clinic.test", "short1234")
    with pytest.raises(ValueError, match="not the email"):
        server.auth.set_password(OWNER, "receptionist@clinic.test", "receptionist")


def test_unknown_and_known_emails_get_the_same_answer(client):
    a = client.post("/api/auth/login", json={"email": "nobody@clinic.test", "password": "a-long-passphrase"})
    b = client.post("/api/auth/login", json={"email": "owner@clinic.test", "password": "wrong-passphrase"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_the_live_feed_opens_with_a_one_use_ticket_never_the_token(client):
    hdr = bearer(client)
    token = hdr["Authorization"][7:]
    assert client.post("/api/events/ticket").status_code == 401
    ticket = client.post("/api/events/ticket", headers=hdr).json()["ticket"]
    assert server.principal_of(type("R", (), {"headers": {}, "url": type("U", (), {"path": "/api/events"})(),
                                               "query_params": {"ticket": ticket}})()).phone == OWNER
    again = type("R", (), {"headers": {}, "url": type("U", (), {"path": "/api/events"})(), "query_params": {"ticket": ticket}})()
    assert server.principal_of(again) is None                                 # used once
    old_way = type("R", (), {"headers": {}, "url": type("U", (), {"path": "/api/events"})(), "query_params": {"token": token}})()
    assert server.principal_of(old_way) is None                               # a token in the URL is not accepted


def test_sign_in_attempts_from_one_address_are_slowed(client, monkeypatch):
    monkeypatch.setattr(server, "RATE_LIMIT_AUTH_PER_MIN", 5)
    codes = [client.post("/api/auth/login", json={"email": f"x{i}@clinic.test", "password": "a-long-passphrase"}).status_code
             for i in range(8)]
    assert codes[:5] == [401] * 5 and 429 in codes[5:]
