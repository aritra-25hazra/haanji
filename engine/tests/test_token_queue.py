"""The token queue: check-in, walk-ins, calling the next patient, no-shows, a
caller's place in line (and asking for it in a call), and a waiting-room
screen that never shows a name or a number."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.auth import AuthStore
from haanji.token_queue import spoken_position

CLINIC = "smile_care_clinic"
OWNER = "9800000001"
DAY = dt.datetime(2026, 11, 20, 9, 0, tzinfo=server.IST)        # a Friday, the clinic is open


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "auth", AuthStore(str(tmp_path / "auth.sqlite"), "test-secret"))
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    monkeypatch.setattr(server, "AUTH_DEV", True)
    monkeypatch.setattr(server, "PRODUCT", True)
    monkeypatch.setattr(server, "PUBLIC_SIMULATOR", False)
    monkeypatch.delenv("HAANJI_WA_TOKEN", raising=False)
    server._buckets.clear()
    server.auth.upsert_user(OWNER, "owner", ["*"], name="Owner")
    # A fresh shop pinned to a morning, so check-in and "now" do not depend on the clock.
    server._runtimes.pop(CLINIC, None)
    server._queues.pop(CLINIC, None)
    monkeypatch.setattr(server, "VAR_DIR", str(tmp_path))
    rt = server.runtime(CLINIC)
    rt.backend._now = DAY
    before = set(server._sessions)
    yield TestClient(server.app)
    for sid in set(server._sessions) - before:
        server._sessions.pop(sid, None)
    for key, sid in list(server._wa_sessions.items()):
        if sid not in server._sessions:
            server._wa_sessions.pop(key, None)
    server._runtimes.pop(CLINIC, None)
    server._queues.pop(CLINIC, None)


@pytest.fixture
def hdr(client):
    code = client.post("/api/auth/otp", json={"phone": OWNER}).json()["dev_code"]
    tok = client.post("/api/auth/verify", json={"phone": OWNER, "code": code}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def book(time, phone, name, service="general consultation", staff="Dr Mehta"):
    rt = server.runtime(CLINIC)
    return rt.backend.book(tenant_id=CLINIC, service=service, date=DAY.date().isoformat(), time=time,
                           staff=staff, customer_name=name, phone=phone)


def q(client, hdr, path, body):
    r = client.post(f"/api/queue/{path}", params={"pack": CLINIC}, json=body, headers=hdr)
    assert r.status_code == 200, r.text
    return r.json()


def test_check_in_gives_a_department_token_once(client, hdr):
    bk = book("10:00", "9811155501", "Ravi Kumar")
    tok = q(client, hdr, "checkin", {"booking_id": bk.booking_id})
    assert tok["label"] == "GP-01" and tok["status"] == "waiting" and tok["department"] == "General Physician"
    assert q(client, hdr, "checkin", {"booking_id": bk.booking_id})["token_id"] == tok["token_id"]
    view = client.get("/api/queue", params={"pack": CLINIC}, headers=hdr).json()
    assert view["to_check_in"] == []
    line = next(x for x in view["lines"] if x["staff"] == "Dr Mehta")
    assert [t["label"] for t in line["waiting"]] == ["GP-01"]


def test_a_booking_for_another_day_cannot_check_in(client, hdr):
    rt = server.runtime(CLINIC)
    other = rt.backend.book(tenant_id=CLINIC, service="general consultation", staff="Dr Mehta",
                            date=(DAY.date() + dt.timedelta(days=1)).isoformat(), time="10:00",
                            customer_name="Asha", phone="9811155502")
    r = client.post("/api/queue/checkin", params={"pack": CLINIC}, json={"booking_id": other.booking_id}, headers=hdr)
    assert r.status_code == 422 and "not today" in r.json()["detail"]


def test_walk_ins_go_to_the_shortest_line_and_next_calls_in_order(client, hdr):
    bk = book("10:00", "9811155503", "Ravi Kumar")
    first = q(client, hdr, "checkin", {"booking_id": bk.booking_id})                    # Dr Mehta: 1 waiting
    walk = q(client, hdr, "walkin", {"service": "general consultation", "name": "Asha", "phone": "9811155504"})
    assert walk["staff"] != "Dr Mehta" and walk["label"] == "GP-02"                    # a shorter line
    second = q(client, hdr, "walkin", {"staff": "Dr Mehta", "name": "Kiran", "phone": "9811155505"})
    out = q(client, hdr, "next", {"staff": "Dr Mehta"})
    assert out["serving"]["label"] == first["label"]
    out = q(client, hdr, "next", {"staff": "Dr Mehta"})
    assert out["serving"]["label"] == second["label"]
    line = next(x for x in client.get("/api/queue", params={"pack": CLINIC}, headers=hdr).json()["lines"]
                if x["staff"] == "Dr Mehta")
    assert line["done"] == 1 and line["serving"]["label"] == second["label"] and line["waiting"] == []
    gone = q(client, hdr, f"{second['token_id']}/status", {"status": "no_show"})
    assert gone["status"] == "no_show"


def test_a_place_in_line_and_a_rough_wait(client, hdr):
    for i, phone in enumerate(["9811155511", "9811155512", "9811155513"]):
        q(client, hdr, "walkin", {"staff": "Dr Verma", "name": f"P{i}", "phone": phone})
    q(client, hdr, "next", {"staff": "Dr Verma"})                                          # P0 is being seen
    pos = server.queue_for(CLINIC).position("+91 98111 55513")
    assert pos["kind"] == "token" and pos["ahead"] == 2 and pos["wait_min"] == 30         # 2 x the 15-min consult
    assert "lagbhag 30 minute" in spoken_position(pos)
    now = server.queue_for(CLINIC).position("9811155511")
    assert now["status"] == "serving" and "ab aapki baari hai" in spoken_position(now)
    assert server.queue_for(CLINIC).position("9811155599") is None


def test_a_caller_asks_for_their_place_in_a_chat(client, hdr):
    for i, phone in enumerate(["9811155521", "9811155522"]):
        q(client, hdr, "walkin", {"staff": "Dr Nair", "name": f"P{i}", "phone": phone})
    r = client.post("/api/wa/incoming", json={"pack": CLINIC, "phone": "9811155522", "text": "mera number kab aayega"},
                    headers=hdr).json()
    said = " ".join(x["text"] for x in r["replies"])
    assert "GP-02" in said and "Aapse pehle 1 log" in said


def test_the_waiting_room_screen_is_public_and_shows_no_names(client, hdr):
    q(client, hdr, "walkin", {"staff": "Dr Joshi", "name": "Secret Name", "phone": "9811155531"})
    assert client.get("/api/queue", params={"pack": CLINIC}).status_code == 401
    shown = client.get("/api/queue/display", params={"pack": CLINIC})
    assert shown.status_code == 200
    text = shown.text
    assert "PD-01" in text and "Secret Name" not in text and "9811155531" not in text


def test_the_tv_page_is_served(client):
    page = client.get("/queue")
    assert page.status_code == 200 and "api/queue/display" in page.text and "content-security-policy" in page.headers
