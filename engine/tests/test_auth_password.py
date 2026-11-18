"""Email + password sign-in, beside the WhatsApp code: a salted scrypt hash
and never the password, a lockout after ten wrong tries, the same token and
device session as a code sign-in, staff by email, and an owner made from
HAANJI_OWNER_EMAIL / HAANJI_OWNER_PASSWORD at boot."""
import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.auth import LOGIN_MAX_FAILURES, AuthStore, OtpThrottled

OWNER = "9800000201"


@pytest.fixture
def store(tmp_path):
    return AuthStore(str(tmp_path / "auth.sqlite"), "test-secret")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "auth", AuthStore(str(tmp_path / "auth.sqlite"), "test-secret"))
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    server._buckets.clear()
    server.auth.upsert_user(OWNER, "owner", ["*"], name="Dr Mehta")
    server.auth.set_password(OWNER, "Owner@Clinic.in", "correct horse")
    return TestClient(server.app)


def test_only_a_salted_hash_is_kept(store):
    store.upsert_user(OWNER, "owner")
    store.set_password(OWNER, "a@b.in", "correct horse")
    row = store.conn.execute("SELECT * FROM credentials").fetchone()
    assert row["pw_hash"].startswith("scrypt$") and "correct horse" not in row["pw_hash"]
    store.set_password(OWNER, "a@b.in", "correct horse")
    again = store.conn.execute("SELECT pw_hash FROM credentials").fetchone()["pw_hash"]
    assert again != row["pw_hash"], "a fresh salt every time"
    with pytest.raises(ValueError):
        store.set_password(OWNER, "a@b.in", "short")
    with pytest.raises(ValueError):
        store.set_password("9800000999", "x@y.in", "long enough")


def test_ten_wrong_passwords_lock_the_email_for_a_while(store):
    store.upsert_user(OWNER, "owner")
    store.set_password(OWNER, "a@b.in", "correct horse")
    t0 = 1_800_000_000.0
    for i in range(LOGIN_MAX_FAILURES):
        assert store.check_password("a@b.in", "wrong", now=t0 + i) is None
    with pytest.raises(OtpThrottled):
        store.check_password("a@b.in", "correct horse", now=t0 + 60)
    assert store.check_password("a@b.in", "correct horse", now=t0 + 60 + 16 * 60).phone == OWNER


def test_the_owner_signs_in_with_email_and_gets_a_device_session(client):
    assert client.post("/api/auth/login", json={"email": "owner@clinic.in", "password": "wrong one"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": " OWNER@clinic.in ", "password": "correct horse"},
                    headers={"User-Agent": "Laptop"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "owner" and r.json()["user"]["email"] == "owner@clinic.in"
    tok = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.get("/api/auth/me", headers=tok).json()["user"]["phone"] == OWNER
    assert [d["agent"] for d in client.get("/api/auth/sessions", headers=tok).json()["sessions"]] == ["Laptop"]
    assert client.get("/api/insights", params={"pack": "dental_clinic"}, headers=tok).status_code == 200


def test_the_owner_adds_staff_who_sign_in_by_email(client):
    owner = client.post("/api/auth/login", json={"email": "owner@clinic.in", "password": "correct horse"}).json()["token"]
    r = client.post("/api/auth/users", headers={"Authorization": f"Bearer {owner}"},
                    json={"phone": "9800000202", "role": "staff", "packs": ["dental_clinic"], "name": "Priya",
                          "email": "priya@clinic.in", "password": "front desk 1"})
    assert r.status_code == 200 and r.json()["user"]["email"] == "priya@clinic.in"
    staff = client.post("/api/auth/login", json={"email": "priya@clinic.in", "password": "front desk 1"}).json()
    assert staff["user"]["role"] == "staff"
    assert client.get("/api/audit", headers={"Authorization": f"Bearer {staff['token']}"}).status_code == 403


def test_with_sign_in_off_there_is_no_password_login(client, monkeypatch):
    monkeypatch.setattr(server, "AUTH_ENABLED", False)
    assert client.post("/api/auth/login", json={"email": "owner@clinic.in", "password": "correct horse"}).status_code == 409


def test_the_owner_comes_from_the_environment_at_boot(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "auth", AuthStore(str(tmp_path / "boot.sqlite"), "s"))
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    monkeypatch.setattr(server, "OWNER_PHONE", None)
    monkeypatch.setenv("HAANJI_OWNER_EMAIL", "me@haanji.in")
    monkeypatch.setenv("HAANJI_OWNER_PASSWORD", "a long password")
    server.seed_owner()
    user = server.auth.check_password("me@haanji.in", "a long password")
    assert user and user.role == "owner" and user.phone.startswith("0"), "a placeholder no mobile number can be"
    server.seed_owner()                                   # a restart changes nothing
    assert len(server.auth.users()) == 1
    monkeypatch.setenv("HAANJI_OWNER_PASSWORD", "a new long password")
    server.seed_owner()                                   # changing the env changes the password
    assert server.auth.check_password("me@haanji.in", "a new long password")
