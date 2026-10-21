"""A person at the console takes a live call, talks, and hands it back."""
import json

import pytest
from fastapi.testclient import TestClient

from haanji import server


@pytest.fixture
def client():
    server._buckets.clear()
    server._recent.clear()
    return TestClient(server.app)


def test_a_web_call_can_be_taken_over_and_handed_back(client):
    sid = client.post("/api/sessions", json={"pack": "dental_clinic", "phone": "9876543210"}).json()["session_id"]
    live = client.get("/api/sessions/live", params={"pack": "dental_clinic"}).json()["sessions"]
    assert any(s["sid"] == sid and s["human"] is False and s["phone"] == "…3210" for s in live)
    assert client.post(f"/api/sessions/{sid}/human-reply", json={"text": "hi"}).status_code == 409
    assert client.post(f"/api/sessions/{sid}/takeover").json() == {"ok": True, "human": True}
    t = client.post(f"/api/sessions/{sid}/utterance", json={"text": "mujhe doctor se baat karni hai"}).json()
    assert t["human"] is True and t["reply"] == "" and t["tools"] == [], "the policy did not run"
    r = client.post(f"/api/sessions/{sid}/human-reply", json={"text": "Haan boliye, main Dr Mehta bol raha hoon."}).json()
    assert r["ok"]
    ev = client.get("/api/events/recent", params={"pack": "dental_clinic"}).json()["events"]
    kinds = [e["kind"] for e in ev if e.get("sid") == sid]
    assert "session.takeover" in kinds and any(e.get("awaiting_human") for e in ev) and any(e.get("guard") == "human" and e.get("reply", "").startswith("Haan boliye") for e in ev)
    assert client.post(f"/api/sessions/{sid}/handback").json()["human"] is False
    t = client.post(f"/api/sessions/{sid}/utterance", json={"text": "clinic ke timings kya hain"}).json()
    assert t.get("human") is not True and "search_knowledge" in t["tools"], "the policy is back"
    done = client.delete(f"/api/sessions/{sid}").json()
    call = client.get(f"/api/conversations/{done['call_id']}", params={"pack": "dental_clinic"}).json()
    turns = json.loads(call["turns_json"])
    assert any(t.get("guard") == "human" and t["said"].startswith("Haan boliye") for t in turns), "the human turn is in the record"


def test_whatsapp_messages_wait_for_the_person_during_a_takeover(client, monkeypatch):
    sent = []

    async def fake_send(to, text):
        sent.append((to, text))
    monkeypatch.setattr(server.wa_channel, "send_text", fake_send)
    monkeypatch.setenv("HAANJI_WA_TOKEN", "t"); monkeypatch.setenv("HAANJI_WA_PHONE_ID", "1")
    first = client.post("/api/wa/incoming", json={"pack": "dental_clinic", "phone": "9811100055", "text": "hello"}).json()
    assert first["replies"]
    sid = server._wa_sessions[("dental_clinic", "9811100055")]
    client.post(f"/api/sessions/{sid}/takeover")
    quiet = client.post("/api/wa/incoming", json={"pack": "dental_clinic", "phone": "9811100055", "text": "kya aap insaan ho"}).json()
    assert quiet["replies"] == []
    client.post(f"/api/sessions/{sid}/human-reply", json={"text": "Ji haan, Priya bol rahi hoon."})
    assert sent and sent[-1] == ("9811100055", "Ji haan, Priya bol rahi hoon.")
    thread = client.get("/api/wa/threads/9811100055", params={"pack": "dental_clinic"}).json()
    assert any(m["direction"] == "out" and m["text"].startswith("Ji haan") for m in thread["messages"])


def test_takeover_of_an_unknown_session_is_404(client):
    assert client.post("/api/sessions/nope/takeover").status_code == 404
