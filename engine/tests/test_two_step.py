"""Two-step sign-in with an authenticator app (RFC 6238 TOTP): the codes match
the RFC's own test vectors, a code works once, recovery codes work once,
the ticket between the steps is signed, short-lived and single-use, and
every first step (password, email code, WhatsApp code, Google) stops at it."""
import time
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from haanji import google_login, server, totp
from haanji.auth import AuthStore

OWNER, EMAIL, PASSWORD = "9800000001", "owner@clinic.test", "a-long-passphrase"
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"          # base32 of ASCII "12345678901234567890"


@pytest.mark.parametrize("t,code", [(59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"),
                                    (1234567890, "89005924"), (2000000000, "69279037"), (20000000000, "65353130")])
def test_codes_match_the_rfc_6238_test_vectors(t, code):
    assert totp.code_at(RFC_SECRET, t // 30, digits=8) == code


def test_a_code_works_in_its_window_and_never_twice():
    s, now = totp.new_secret(), 1_700_000_000
    step = int(now // 30)
    assert totp.verify(s, totp.code_at(s, step), now) == step
    assert totp.verify(s, totp.code_at(s, step - 1), now) == step - 1          # a slow phone clock
    assert totp.verify(s, totp.code_at(s, step - 2), now) is None             # too old
    assert totp.verify(s, totp.code_at(s, step), now, last_step=step) is None  # replay
    assert totp.verify(s, "12345", now) is None and totp.verify(s, "abcdef", now) is None
    assert totp.uri(s, "owner@clinic.test").startswith("otpauth://totp/HaanJi%3Aowner%40clinic.test?secret=")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "auth", AuthStore(str(tmp_path / "auth.sqlite"), "test-secret"))
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    monkeypatch.setattr(server, "AUTH_DEV", True)
    server._buckets.clear()
    server.auth.upsert_user(OWNER, "owner", ["*"], name="Owner")
    server.auth.set_password(OWNER, EMAIL, PASSWORD)
    yield TestClient(server.app, follow_redirects=False)
    server._buckets.clear()


def login(client):
    return client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()


def app_code(secret, offset=0):
    return totp.code_at(secret, int(time.time() // 30) + offset)


def turn_on(client):
    hdr = {"Authorization": "Bearer " + login(client)["token"]}
    setup = client.post("/api/auth/2fa/setup", headers=hdr).json()
    assert setup["qr_svg"].startswith("<svg") and "<script" not in setup["qr_svg"] and setup["uri"].startswith("otpauth://")
    assert client.get("/api/auth/2fa", headers=hdr).json() == {"enabled": False, "recovery_codes_left": 0}
    assert client.post("/api/auth/2fa/enable", headers=hdr, json={"code": "000000"}).status_code == 422
    on = client.post("/api/auth/2fa/enable", headers=hdr, json={"code": app_code(setup["secret"], -1)}).json()
    assert on["enabled"] is True and len(on["recovery_codes"]) == 8
    assert client.get("/api/auth/2fa", headers=hdr).json() == {"enabled": True, "recovery_codes_left": 8}
    return setup["secret"], on["recovery_codes"], hdr


def test_turning_it_on_needs_a_signed_in_user_and_a_code_from_the_app(client):
    assert client.post("/api/auth/2fa/setup").status_code == 401
    secret, _, hdr = turn_on(client)
    assert client.post("/api/auth/2fa/setup", headers=hdr).status_code == 409          # already on
    stored = server.auth.conn.execute("SELECT secret FROM twofactor").fetchone()["secret"]
    assert secret not in stored                                                         # kept encrypted
    assert any(a["path"] == "/api/auth/2fa/enable" for a in server.auth.audit())


def test_the_password_then_the_app_code_signs_in_and_the_ticket_works_once(client):
    secret, _, _ = turn_on(client)
    first = login(client)
    assert first.keys() == {"needs_2fa", "ticket"} and first["needs_2fa"] is True     # no token yet
    bad = client.post("/api/auth/2fa/verify", json={"ticket": first["ticket"], "code": "000000"})
    assert bad.status_code == 401                                                       # a typo can be retried
    ok = client.post("/api/auth/2fa/verify", json={"ticket": first["ticket"], "code": app_code(secret)})
    assert ok.status_code == 200 and ok.json()["user"]["phone"] == OWNER
    me = client.get("/api/auth/me", headers={"Authorization": "Bearer " + ok.json()["token"]})
    assert me.json()["user"]["phone"] == OWNER
    again = client.post("/api/auth/2fa/verify", json={"ticket": first["ticket"], "code": app_code(secret, 1)})
    assert again.status_code == 401                                                     # the ticket is spent


def test_the_same_app_code_is_refused_the_second_time(client):
    secret, _, _ = turn_on(client)
    code = app_code(secret)
    assert client.post("/api/auth/2fa/verify", json={"ticket": login(client)["ticket"], "code": code}).status_code == 200
    assert client.post("/api/auth/2fa/verify", json={"ticket": login(client)["ticket"], "code": code}).status_code == 401


def test_a_recovery_code_works_once_however_it_is_typed(client):
    _, backup, hdr = turn_on(client)
    typed = backup[0].replace("-", " ").upper()
    assert client.post("/api/auth/2fa/verify", json={"ticket": login(client)["ticket"], "code": typed}).status_code == 200
    assert client.post("/api/auth/2fa/verify", json={"ticket": login(client)["ticket"], "code": backup[0]}).status_code == 401
    assert client.get("/api/auth/2fa", headers=hdr).json()["recovery_codes_left"] == 7


def test_a_forged_or_old_ticket_is_refused(client):
    secret, _, _ = turn_on(client)
    forged = server.auth.twofa_ticket(OWNER)[:-4] + "0000"
    old = server.auth.twofa_ticket(OWNER, now=time.time() - 301)
    for ticket in (forged, old, "", "x.y"):
        r = client.post("/api/auth/2fa/verify", json={"ticket": ticket, "code": app_code(secret)})
        assert r.status_code == 401


def test_ten_wrong_codes_lock_the_second_step(client):
    secret, _, _ = turn_on(client)
    ticket = login(client)["ticket"]
    for _ in range(10):
        client.post("/api/auth/2fa/verify", json={"ticket": ticket, "code": "000000"})
    assert client.post("/api/auth/2fa/verify", json={"ticket": ticket, "code": app_code(secret)}).status_code == 401


def test_every_first_step_stops_at_the_second(client, monkeypatch):
    turn_on(client)
    code = client.post("/api/auth/email-code", json={"email": EMAIL}).json()["dev_code"]
    assert client.post("/api/auth/email-verify", json={"email": EMAIL, "code": code}).json()["needs_2fa"] is True
    wa = server.auth.issue_otp(OWNER)
    assert client.post("/api/auth/verify", json={"phone": OWNER, "code": wa}).json()["needs_2fa"] is True
    monkeypatch.setenv("HAANJI_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("HAANJI_GOOGLE_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("HAANJI_CONSOLE_URL", "https://console.example")

    async def fake_exchange(code, redirect_uri):
        return {"email": EMAIL, "email_verified": True}
    monkeypatch.setattr(google_login, "exchange", fake_exchange)
    start = client.get("/api/auth/google/start").headers["location"]
    state = urllib.parse.parse_qs(urllib.parse.urlparse(start).query)["state"][0]
    loc = client.get("/api/auth/google/callback", params={"code": "c", "state": state}).headers["location"]
    assert loc.startswith("https://console.example/login#twofa=") and "token=" not in loc


def test_turning_it_off_needs_a_current_code(client):
    secret, _, hdr = turn_on(client)
    assert client.post("/api/auth/2fa/disable", headers=hdr, json={"code": "000000"}).status_code == 401
    assert client.post("/api/auth/2fa/disable", headers=hdr, json={"code": app_code(secret)}).json() == {"enabled": False}
    assert "token" in login(client)
    assert any(a["path"] == "/api/auth/2fa/disable" for a in server.auth.audit())


def test_after_the_auth_secret_changes_recovery_codes_still_work_and_nothing_crashes(client, tmp_path):
    secret, backup, _ = turn_on(client)
    server.auth = AuthStore(str(tmp_path / "auth.sqlite"), "a-different-secret")   # the fixture restores it
    ticket = server.auth.twofa_ticket(OWNER)
    assert client.post("/api/auth/2fa/verify", json={"ticket": ticket, "code": app_code(secret)}).status_code == 401
    assert client.post("/api/auth/2fa/verify", json={"ticket": ticket, "code": backup[1]}).status_code == 200


def test_removing_a_user_clears_their_two_step_so_the_owner_can_add_them_back(client):
    turn_on(client)
    assert server.auth.twofa_enabled(OWNER)
    server.auth.remove_user(OWNER)
    server.auth.upsert_user(OWNER, "owner", ["*"], name="Owner")
    assert not server.auth.twofa_enabled(OWNER)


def test_the_operator_can_turn_off_a_lost_owner_s_two_step_at_boot(client, monkeypatch):
    turn_on(client)
    monkeypatch.setenv("HAANJI_2FA_RESET", EMAIL.upper())
    server.seed_owner()
    assert not server.auth.twofa_enabled(OWNER)
    assert "token" in login(client)
