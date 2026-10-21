"""Web push: subscribe from the console, buzz the owner when a call ends in a booking."""
import json

import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.push import PushStore
from haanji.scenario import scenarios_of
from haanji.vertical import load_pack


def test_the_store_keeps_vapid_keys_and_drops_dead_subscriptions(tmp_path):
    sent = []

    def sender(sub, payload):
        if "dead" in sub["endpoint"]:
            class R: status_code = 410
            e = Exception("gone"); e.response = R(); raise e
        sent.append((sub["endpoint"], json.loads(payload)))
    p = PushStore(str(tmp_path / "push.sqlite"), str(tmp_path / "vapid.json"), sender=sender)
    again = PushStore(str(tmp_path / "push.sqlite"), str(tmp_path / "vapid.json"), sender=sender)
    assert p.public_key == again.public_key and len(p.public_key) > 60, "keys persist beside the data"
    assert p.subscribe("dental_clinic", {"endpoint": "https://push.example/a", "keys": {"p256dh": "x", "auth": "y"}}, "Aritra's phone") == 1
    p.subscribe("dental_clinic", {"endpoint": "https://push.example/dead", "keys": {}})
    with pytest.raises(ValueError):
        p.subscribe("dental_clinic", {"endpoint": "http://insecure"})
    r = p.send("dental_clinic", "Nayi booking", "root canal kal 9:30", "/calls/1")
    assert r == {"sent": 1, "dropped": 1, "failed": 0} and sent[0][1]["title"] == "Nayi booking"
    assert p.count("dental_clinic") == 1 and p.count("salon_spa") == 0


def test_a_booking_buzzes_the_subscribed_owner(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(server, "push", PushStore(str(tmp_path / "p.sqlite"), str(tmp_path / "v.json"),
                                                  sender=lambda sub, payload: sent.append(json.loads(payload))))
    monkeypatch.setenv("HAANJI_CONSOLE_URL", "https://console.example")
    server._buckets.clear()
    c = TestClient(server.app)
    assert c.get("/api/push/vapid-public-key").json()["public_key"] == server.push.public_key
    r = c.post("/api/push/subscribe", json={"pack": "dental_clinic", "subscription": {"endpoint": "https://push.example/me", "keys": {}}, "label": "phone"})
    assert r.json() == {"ok": True, "subscribers": 1}
    assert c.post("/api/push/subscribe", json={"pack": "dental_clinic", "subscription": {"endpoint": "nope"}}).status_code == 422
    assert c.post("/api/push/test", params={"pack": "dental_clinic"}).json()["sent"] == 1
    sent.clear()
    sid = c.post("/api/sessions", json={"pack": "dental_clinic", "phone": "9811100066"}).json()["session_id"]
    sc = next(s for s in scenarios_of(load_pack("dental_clinic")) if s.name == "booking_with_asr_noise")
    for u in sc.utterances:
        c.post(f"/api/sessions/{sid}/utterance", json={"text": u.truth})
    assert sent and sent[-1]["title"].startswith("Nayi booking") and "receipt" in sent[-1]["body"] and sent[-1]["url"].startswith("https://console.example/calls/")
    assert c.delete("/api/push/unsubscribe", params={"endpoint": "https://push.example/me"}).json()["removed"] is True
