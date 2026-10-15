"""The real WhatsApp webhook: Meta's shapes, Meta's signature, Meta's habits."""
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.channels import whatsapp as wa

SENDER = "919876543210"
TEXT = "haan ji mujhe rut kanal karwana tha"


def meta_payload(msg_id: str = "wamid.1", sender: str = SENDER, text: str = TEXT) -> dict:
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15550001111", "phone_number_id": "111222333"},
        "contacts": [{"profile": {"name": "Vijay"}, "wa_id": sender}],
        "messages": [{"from": sender, "id": msg_id, "timestamp": "1", "type": "text", "text": {"body": text}}],
    }}]}]}


def status_payload() -> dict:
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": "111222333"},
        "statuses": [{"id": "wamid.x", "status": "delivered", "recipient_id": SENDER}],
    }}]}]}


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def client():
    return TestClient(server.app)


@pytest.fixture
def sent(monkeypatch):
    out: list[tuple[str, str]] = []

    async def fake_send(to: str, text: str) -> None:
        out.append((to, text))

    monkeypatch.setattr(wa, "send_text", fake_send)
    server._wa_seen.clear()
    return out


def test_the_verification_handshake_echoes_the_challenge_for_the_right_token(client, monkeypatch):
    monkeypatch.setenv("HAANJI_WA_VERIFY_TOKEN", "secret-v")
    ok = client.get("/wa/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "secret-v", "hub.challenge": "4242"})
    assert ok.status_code == 200 and ok.text == "4242"
    assert client.get("/wa/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"}).status_code == 403
    assert client.get("/wa/webhook", params={"hub.mode": "unsubscribe", "hub.verify_token": "secret-v", "hub.challenge": "1"}).status_code == 403


def test_a_signed_delivery_is_answered_on_whatsapp_and_recorded(client, monkeypatch, sent):
    monkeypatch.setenv("HAANJI_WA_APP_SECRET", "app-secret")
    monkeypatch.delenv("HAANJI_WA_PACK", raising=False)
    body = json.dumps(meta_payload()).encode()
    r = client.post("/wa/webhook", content=body, headers={"X-Hub-Signature-256": sign("app-secret", body), "Content-Type": "application/json"})
    assert r.status_code == 200 and r.json() == {"ok": True, "handled": 1}
    assert sent and all(to == SENDER for to, _ in sent)
    thread = client.get(f"/api/wa/threads/{SENDER[-10:]}", params={"pack": "dental_clinic"}).json()
    assert any(m["direction"] == "in" and m["text"] == TEXT for m in thread["messages"])


def test_a_bad_or_missing_signature_is_rejected_when_a_secret_is_set(client, monkeypatch, sent):
    monkeypatch.setenv("HAANJI_WA_APP_SECRET", "app-secret")
    body = json.dumps(meta_payload(msg_id="wamid.bad")).encode()
    assert client.post("/wa/webhook", content=body, headers={"X-Hub-Signature-256": sign("other", body), "Content-Type": "application/json"}).status_code == 403
    assert client.post("/wa/webhook", content=body, headers={"Content-Type": "application/json"}).status_code == 403
    assert sent == []


def test_without_a_secret_unsigned_deliveries_are_accepted(client, monkeypatch, sent):
    monkeypatch.delenv("HAANJI_WA_APP_SECRET", raising=False)
    r = client.post("/wa/webhook", json=meta_payload(msg_id="wamid.dev"))
    assert r.status_code == 200 and r.json()["handled"] == 1
    assert len(sent) >= 1


def test_a_redelivered_message_is_handled_once(client, monkeypatch, sent):
    monkeypatch.delenv("HAANJI_WA_APP_SECRET", raising=False)
    first = client.post("/wa/webhook", json=meta_payload(msg_id="wamid.dup")).json()
    n = len(sent)
    second = client.post("/wa/webhook", json=meta_payload(msg_id="wamid.dup")).json()
    assert first["handled"] == 1 and second == {"ok": True, "handled": 0}
    assert len(sent) == n


def test_status_only_deliveries_are_acknowledged_and_ignored(client, monkeypatch, sent):
    monkeypatch.delenv("HAANJI_WA_APP_SECRET", raising=False)
    r = client.post("/wa/webhook", json=status_payload())
    assert r.status_code == 200 and r.json() == {"ok": True, "handled": 0}
    assert sent == []


def test_the_answering_pack_comes_from_the_environment(client, monkeypatch, sent):
    monkeypatch.delenv("HAANJI_WA_APP_SECRET", raising=False)
    monkeypatch.setenv("HAANJI_WA_PACK", "salon_spa")
    client.post("/wa/webhook", json=meta_payload(msg_id="wamid.salon", sender="919700000001", text="haircut chahiye"))
    threads = client.get("/api/wa/threads", params={"pack": "salon_spa"}).json()["threads"]
    assert any(t["phone"] == "9700000001" for t in threads)


def test_status_reports_whether_a_real_number_is_connected(client, monkeypatch):
    monkeypatch.delenv("HAANJI_WA_TOKEN", raising=False)
    monkeypatch.delenv("HAANJI_WA_PHONE_ID", raising=False)
    assert client.get("/api/status").json()["whatsapp"] == {"configured": False, "number": None}
    monkeypatch.setenv("HAANJI_WA_TOKEN", "t")
    monkeypatch.setenv("HAANJI_WA_PHONE_ID", "111222333")
    s = client.get("/api/status").json()["whatsapp"]
    assert s["configured"] is True and s["number"].endswith("2333")
    monkeypatch.setenv("HAANJI_WA_DISPLAY_NUMBER", "+91 98765 43210")
    assert client.get("/api/status").json()["whatsapp"]["number"] == "+91 98765 43210"


def test_extract_incoming_yields_ids_senders_and_text():
    assert list(wa.extract_incoming(meta_payload())) == [("wamid.1", SENDER, TEXT)]
    assert list(wa.extract_incoming(status_payload())) == []
    assert wa.verify_signature("s", b"body", sign("s", b"body")) is True
    assert wa.verify_signature("s", b"body", "sha256=00") is False
    assert wa.verify_signature("s", b"body", None) is False
