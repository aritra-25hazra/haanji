"""Rate limiting and response headers on the public demo server."""
import pytest
from fastapi.testclient import TestClient

from haanji import server


@pytest.fixture
def client():
    server._buckets.clear()
    return TestClient(server.app)


def test_every_response_carries_the_hardening_headers(client):
    h = client.get("/api/status").headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert "microphone=(self)" in h["permissions-policy"] and "strict-origin" in h["referrer-policy"]
    assert "strict-transport-security" not in h, "only over https"
    https = client.get("/api/status", headers={"x-forwarded-proto": "https"}).headers
    assert https["strict-transport-security"].startswith("max-age=")


def test_writes_are_rate_limited_per_client_and_reads_are_not(client, monkeypatch):
    monkeypatch.setattr(server, "RATE_LIMIT_PER_MIN", 5)
    server._buckets.clear()
    codes = [client.post("/api/wa/incoming", json={"pack": "dental_clinic", "phone": "9000000001", "text": "hi"},
                         headers={"x-forwarded-for": "203.0.113.9"}).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5] == 429 and codes[6] == 429
    assert all(client.get("/api/status", headers={"x-forwarded-for": "203.0.113.9"}).status_code == 200 for _ in range(10))
    other = client.post("/api/wa/incoming", json={"pack": "dental_clinic", "phone": "9000000002", "text": "hi"},
                        headers={"x-forwarded-for": "203.0.113.10"})
    assert other.status_code == 200, "another client has its own bucket"


def test_the_bucket_refills_with_time():
    server._buckets.clear()
    server.RATE_LIMIT_PER_MIN, old = 60, server.RATE_LIMIT_PER_MIN
    try:
        assert not any(server.rate_limited("c", now=0.0) for _ in range(60))
        assert server.rate_limited("c", now=0.0)
        assert not server.rate_limited("c", now=1.0)       # one token per second at 60/min
    finally:
        server.RATE_LIMIT_PER_MIN = old


def test_the_signed_webhook_is_exempt(client, monkeypatch):
    monkeypatch.setattr(server, "RATE_LIMIT_PER_MIN", 1)
    monkeypatch.delenv("HAANJI_WA_APP_SECRET", raising=False)
    server._buckets.clear()
    for _ in range(3):
        assert client.post("/wa/webhook", json={"object": "whatsapp_business_account", "entry": []}).status_code == 200
