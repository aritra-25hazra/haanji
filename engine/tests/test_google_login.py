"""Sign in with Google: Google proves the email, HaanJi decides who may enter
(only an email already given to an owner or staff member); the state is
signed and expires; the ID token is checked for audience, issuer, expiry and
a verified email; the token reaches the console in the URL fragment."""
import asyncio
import base64
import json
import time
import urllib.parse

import httpx
import pytest
from fastapi.testclient import TestClient

from haanji import google_login, server
from haanji.auth import AuthStore

OWNER = "9800000301"


def id_token(**claims):
    body = {"iss": "https://accounts.google.com", "aud": "cid.apps.googleusercontent.com", "exp": int(time.time()) + 300,
            "email": "owner@clinic.in", "email_verified": True, **claims}
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()   # noqa: E731
    return f"{enc({'alg': 'RS256'})}.{enc(body)}.sig"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "auth", AuthStore(str(tmp_path / "auth.sqlite"), "test-secret"))
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    monkeypatch.setenv("HAANJI_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("HAANJI_GOOGLE_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("HAANJI_CONSOLE_URL", "https://console.example")
    server._buckets.clear()
    server.auth.upsert_user(OWNER, "owner", ["*"], name="Owner")
    server.auth.set_password(OWNER, "owner@clinic.in", "correct horse")
    return TestClient(server.app, follow_redirects=False)


def google_says(monkeypatch, **claims):
    async def fake_exchange(code, redirect_uri):
        assert code == "the-code" and redirect_uri.endswith("/api/auth/google/callback")
        return {"email": "owner@clinic.in", "email_verified": True, **claims}
    monkeypatch.setattr(google_login, "exchange", fake_exchange)


def start_state(client):
    r = client.get("/api/auth/google/start")
    assert r.status_code == 302
    q = urllib.parse.parse_qs(urllib.parse.urlparse(r.headers["location"]).query)
    assert q["scope"] == ["openid email"] and q["client_id"] == ["cid.apps.googleusercontent.com"]
    return q["state"][0]


def test_an_allowed_email_signs_in_and_the_token_rides_in_the_fragment(client, monkeypatch):
    google_says(monkeypatch)
    r = client.get("/api/auth/google/callback", params={"code": "the-code", "state": start_state(client)})
    loc = r.headers["location"]
    assert r.status_code == 302 and loc.startswith("https://console.example/login#token=")
    token = loc.split("#token=")[1]
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["user"]["phone"] == OWNER


def test_an_unknown_email_is_turned_away(client, monkeypatch):
    google_says(monkeypatch, email="stranger@gmail.com")
    r = client.get("/api/auth/google/callback", params={"code": "the-code", "state": start_state(client)})
    assert r.headers["location"].endswith("/login#error=not-allowed")


def test_a_forged_or_old_state_is_refused(client, monkeypatch):
    google_says(monkeypatch)
    assert client.get("/api/auth/google/callback", params={"code": "the-code", "state": "1.x.forged"}).status_code == 400
    old = google_login.make_state(server.auth.secret, now=time.time() - 3600)
    assert client.get("/api/auth/google/callback", params={"code": "the-code", "state": old}).status_code == 400


def test_the_id_token_is_checked(monkeypatch):
    monkeypatch.setenv("HAANJI_GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("HAANJI_GOOGLE_CLIENT_SECRET", "csecret")

    def run(token):
        transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"id_token": token}))
        return asyncio.run(google_login.exchange("c", "https://x/cb", transport=transport))

    assert run(id_token())["email"] == "owner@clinic.in"
    for bad in (id_token(aud="someone-else"), id_token(iss="https://evil.example"),
                id_token(exp=int(time.time()) - 10), id_token(email_verified=False)):
        with pytest.raises(ValueError):
            run(bad)


def test_without_sign_in_or_a_google_client_there_is_no_google_button(client, monkeypatch):
    assert client.get("/api/status").json()["auth"]["google"] is True
    monkeypatch.delenv("HAANJI_GOOGLE_CLIENT_SECRET")
    assert client.get("/api/status").json()["auth"]["google"] is False
    assert client.get("/api/auth/google/start").status_code == 409
