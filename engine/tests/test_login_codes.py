"""Sign-in and password-reset codes by email (SMTP, e.g. a Gmail App Password):
the mail goes out, the answer never reveals an account, codes are single-use,
throttled and expire, and a reset signs every device out."""
import re
import smtplib

import pytest
from fastapi.testclient import TestClient

from haanji import mailer, server
from haanji.auth import AuthStore

OWNER, EMAIL, PASSWORD = "9800000001", "owner@clinic.test", "a-long-passphrase"


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port, context=None, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, password):
        if password != "app-password":
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials app-password-wrong")

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "auth", AuthStore(str(tmp_path / "auth.sqlite"), "test-secret"))
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    monkeypatch.setattr(server, "AUTH_DEV", False)
    for k, v in {"HAANJI_SMTP_HOST": "smtp.test", "HAANJI_SMTP_PORT": "465", "HAANJI_SMTP_USER": "me@gmail.test",
                 "HAANJI_SMTP_PASSWORD": "app-password", "HAANJI_MAIL_FROM": "HaanJi <me@gmail.test>"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    FakeSMTP.sent = []
    server._buckets.clear()
    server.auth.upsert_user(OWNER, "owner", ["*"], name="Owner")
    server.auth.set_password(OWNER, EMAIL, PASSWORD)
    yield TestClient(server.app)
    server._buckets.clear()


def code_from_last_mail() -> str:
    return re.search(r"\b(\d{6})\b", FakeSMTP.sent[-1]["Subject"]).group(1)


def test_a_sign_in_code_arrives_by_email_and_signs_in_once(client):
    assert client.post("/api/auth/email-code", json={"email": EMAIL}).json() == {"sent": True}
    msg = FakeSMTP.sent[-1]
    assert msg["To"] == EMAIL and "sign-in code" in msg["Subject"] and "5 minute" in msg.get_content()
    code = code_from_last_mail()
    r = client.post("/api/auth/email-verify", json={"email": EMAIL.upper(), "code": code})
    assert r.status_code == 200 and r.json()["token"]
    assert client.post("/api/auth/email-verify", json={"email": EMAIL, "code": code}).status_code == 401


def test_an_unknown_email_gets_the_same_answer_and_no_mail(client):
    assert client.post("/api/auth/email-code", json={"email": "nobody@clinic.test"}).json() == {"sent": True}
    assert FakeSMTP.sent == []


def test_codes_are_throttled_silently_and_wrong_guesses_lock(client):
    for _ in range(5):
        r = client.post("/api/auth/email-code", json={"email": EMAIL})
        assert r.status_code == 200 and r.json() == {"sent": True}       # a 429 would reveal the account
    assert len(FakeSMTP.sent) == 3
    good = code_from_last_mail()
    for _ in range(10):
        assert client.post("/api/auth/email-verify", json={"email": EMAIL, "code": "000000"}).status_code == 401
    assert client.post("/api/auth/email-verify", json={"email": EMAIL, "code": good}).status_code == 401  # locked


def test_a_reset_lifts_the_wrong_password_lock(client):
    for _ in range(10):
        client.post("/api/auth/login", json={"email": EMAIL, "password": "wrong-passphrase"})
    assert client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 429
    client.post("/api/auth/email-code", json={"email": EMAIL, "purpose": "reset"})
    assert client.post("/api/auth/reset", json={"email": EMAIL, "code": code_from_last_mail(),
                                                "password": "a-newer-passphrase"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": EMAIL, "password": "a-newer-passphrase"}).status_code == 200


def test_a_reset_code_sets_a_new_password_and_signs_every_device_out(client):
    old = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()["token"]
    client.post("/api/auth/email-code", json={"email": EMAIL, "purpose": "reset"})
    assert "password reset" in FakeSMTP.sent[-1]["Subject"]
    code = code_from_last_mail()
    weak = client.post("/api/auth/reset", json={"email": EMAIL, "code": code, "password": "short"})
    assert weak.status_code == 422 and "at least 10" in weak.json()["detail"]
    ok = client.post("/api/auth/reset", json={"email": EMAIL, "code": code, "password": "a-newer-passphrase"})
    assert ok.status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": EMAIL, "password": "a-newer-passphrase"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 401
    assert any(a["path"] == "/api/auth/reset" for a in server.auth.audit())


def test_a_login_code_cannot_reset_a_password(client):
    client.post("/api/auth/email-code", json={"email": EMAIL, "purpose": "login"})
    code = code_from_last_mail()
    r = client.post("/api/auth/reset", json={"email": EMAIL, "code": code, "password": "a-newer-passphrase"})
    assert r.status_code == 401


def test_without_mail_set_up_the_server_says_so(client, monkeypatch):
    monkeypatch.delenv("HAANJI_SMTP_HOST")
    r = client.post("/api/auth/email-code", json={"email": EMAIL})
    assert r.status_code == 409 and "HAANJI_SMTP" in r.json()["detail"]
    assert client.get("/api/status").json()["auth"]["email_codes"] is False


def test_a_failed_send_is_reported_without_the_password(client, monkeypatch):
    monkeypatch.setenv("HAANJI_SMTP_PASSWORD", "app-password-wrong")
    assert client.post("/api/auth/email-code", json={"email": EMAIL}).json() == {"sent": True}
    st = client.get("/api/status").json()["mail"]
    assert st["configured"] is True and st["last_send"]["ok"] is False
    assert "SMTPAuthenticationError" in st["last_send"]["error"] and "app-password-wrong" not in str(st)
    assert st["last_send"]["to"] == "o…@clinic.test"
    assert mailer.status()["last_send"]["ok"] is False
