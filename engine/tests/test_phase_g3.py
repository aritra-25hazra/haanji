"""Phase G3: the second review's findings — a public demo that cannot be
operated by strangers, a body cap that counts bytes, a cancellation the
customer hears about, privacy defaults that protect by default."""
import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.channels import whatsapp as wa

PACK = "dental_clinic"


@pytest.fixture
def client(monkeypatch):
    server._buckets.clear()
    monkeypatch.setattr(server, "AUTH_ENABLED", False)
    monkeypatch.setattr(server, "DEMO_READONLY", False)
    return TestClient(server.app)


def _book(client, phone):
    for line in ("mujhe teeth cleaning karwani hai", "kal subah ka time mil jayega", "haan ji wahi theek hai",
                 f"mera naam Rina hai number {phone}", "haan confirm kar do"):
        client.post("/api/wa/incoming", json={"pack": PACK, "phone": phone, "text": line})
    return server.runtime(PACK).backend.find_booking(PACK, phone)


def test_a_chunked_body_without_a_length_header_is_still_capped(client):
    def chunks():
        yield b'{"text": "'
        for _ in range(40):
            yield b"x" * 32768                     # 1.25 MB, no Content-Length
        yield b'"}'
    sid = client.post("/api/sessions", json={"pack": PACK}).json()["session_id"]
    r = client.post(f"/api/sessions/{sid}/utterance", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413, r.text
    small = client.post(f"/api/sessions/{sid}/utterance", content=iter([b'{"text": "hello"}']),
                        headers={"Content-Type": "application/json"})
    assert small.status_code == 200


def test_the_public_demo_refuses_the_console_s_destructive_operations(client, monkeypatch):
    monkeypatch.setattr(server, "DEMO_READONLY", True)
    phone = "9844400011"
    b = _book(client, phone)
    assert client.get("/api/settings", params={"pack": PACK}).status_code == 200, "reading is fine"
    assert client.get("/api/bookings", params={"pack": PACK, "from": b.date, "to": b.date}).status_code == 200
    for method, path, body in (
        ("PUT", "/api/settings", {"deposit_inr": 100}),
        ("POST", f"/api/bookings/{b.booking_id}/cancel", None),
        ("POST", f"/api/bookings/{b.booking_id}/status", {"status": "NO_SHOW"}),
        ("DELETE", f"/api/privacy/customer/{phone}", None),
        ("GET", "/api/admin/backup", None),
        ("GET", "/api/auth/users", None),
        ("POST", "/api/digest/send", None),
    ):
        r = client.request(method, path, params={"pack": PACK}, json=body)
        assert r.status_code == 403 and "read-only" in r.json()["detail"], (method, path, r.status_code, r.text)
    assert server.runtime(PACK).backend.booking(PACK, b.booking_id).status == "CONFIRMED"
    assert client.get("/api/status").json()["demo_readonly"] is True
    monkeypatch.setattr(server, "DEMO_READONLY", False)
    assert client.post(f"/api/bookings/{b.booking_id}/status", params={"pack": PACK}, json={"status": "NO_SHOW"}).status_code == 200


def test_backups_leave_a_public_server_only_with_sign_in(client, monkeypatch):
    monkeypatch.setattr(server, "IS_PUBLIC", True)
    r = client.get("/api/admin/backup")
    assert r.status_code == 409 and "HAANJI_AUTH" in r.json()["detail"]
    monkeypatch.setattr(server, "IS_PUBLIC", False)
    assert client.get("/api/admin/backup").status_code == 200


def test_a_console_cancellation_tells_the_customer(client, monkeypatch):
    phone = "9844400022"
    b = _book(client, phone)
    sent = []

    async def fake_template(to, kind, params, *, fallback_text=None, language=None):
        sent.append((to, kind, fallback_text))
        return True

    monkeypatch.setattr(wa, "send_template", fake_template)
    monkeypatch.setenv("HAANJI_WA_TOKEN", "t"); monkeypatch.setenv("HAANJI_WA_PHONE_ID", "1")
    r = client.post(f"/api/bookings/{b.booking_id}/cancel", params={"pack": PACK}).json()
    assert r["ok"] and r["customer_notified"] is True
    assert sent and sent[0][0] == phone and "cancel kar di gayi" in sent[0][2]
    thread = client.get(f"/api/wa/threads/{phone}", params={"pack": PACK}).json()["messages"]
    assert "cancel kar di gayi" in thread[-1]["text"]
    monkeypatch.delenv("HAANJI_WA_TOKEN"); monkeypatch.delenv("HAANJI_WA_PHONE_ID")
    b2 = _book(client, "9844400033")
    r2 = client.post(f"/api/bookings/{b2.booking_id}/cancel", params={"pack": PACK}).json()
    assert r2["customer_notified"] is None, "no number connected: recorded in the thread, nothing to send with"


def test_privacy_defaults_protect_by_default(monkeypatch):
    import importlib, os
    monkeypatch.delenv("HAANJI_RETENTION_DAYS", raising=False)
    assert int(os.environ.get("HAANJI_RETENTION_DAYS", "180")) == 180
    assert server.RETENTION_DAYS in (180, int(os.environ.get("HAANJI_RETENTION_DAYS", "180")))
    assert "HAANJI_CONSENT_LINE" in open(os.path.join(os.path.dirname(server.__file__), "..", "..", "render.yaml")).read()
    assert "HAANJI_RETENTION_DAYS" in open(os.path.join(os.path.dirname(server.__file__), "..", "..", "render.yaml")).read()
