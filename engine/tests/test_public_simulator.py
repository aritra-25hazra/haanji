"""A demo server with sign-in on: strangers can try the WhatsApp simulator and
/talk's lines, but never list or read anyone else's chat."""
import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.auth import AuthStore

PACK = "dental_clinic"
OWNER = "9800000001"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "auth", AuthStore(str(tmp_path / "auth.sqlite"), "test-secret"))
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    monkeypatch.setattr(server, "AUTH_DEV", True)
    monkeypatch.setattr(server, "PUBLIC_SIMULATOR", True)
    monkeypatch.delenv("HAANJI_WA_TOKEN", raising=False)
    server._buckets.clear()
    server.auth.upsert_user(OWNER, "owner", ["*"], name="Owner")
    return TestClient(server.app)


def owner(client):
    code = client.post("/api/auth/otp", json={"phone": OWNER}).json()["dev_code"]
    tok = client.post("/api/auth/verify", json={"phone": OWNER, "code": code}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def send(client, phone, text, visitor=None):
    r = client.post("/api/wa/incoming", json={"pack": PACK, "phone": phone, "text": text, "visitor": visitor})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_stranger_can_chat_and_reads_back_only_their_own_chat(client):
    first = send(client, "9811100001", "haan ji mujhe appointment chahiye")
    assert first["replies"] and first["visitor"]
    again = send(client, "9811100001", "kal subah", first["visitor"])
    thread = client.get("/api/wa/threads/9811100001", params={"pack": PACK, "visitor": again["visitor"]})
    texts = [m["text"] for m in thread.json()["messages"]]
    assert "haan ji mujhe appointment chahiye" in texts and "kal subah" in texts


def test_a_stranger_cannot_list_threads_or_read_without_a_pass(client):
    send(client, "9811100002", "hello")
    assert client.get("/api/wa/threads", params={"pack": PACK}).json() == {"threads": [], "hidden": True}
    assert client.get("/api/wa/threads/9811100002", params={"pack": PACK}).json() == {"messages": []}
    forged = "2000-01-01T00:00:00.000+00:00~" + "0" * 32
    assert client.get("/api/wa/threads/9811100002",
                      params={"pack": PACK, "visitor": forged}).json() == {"messages": []}


def test_typing_someone_elses_number_starts_a_fresh_chat(client):
    send(client, "9811100003", "mera naam Kavya hai")
    stranger = send(client, "9811100003", "hello")
    seen = client.get("/api/wa/threads/9811100003", params={"pack": PACK, "visitor": stranger["visitor"]}).json()
    assert all("Kavya" not in m["text"] for m in seen["messages"])


def test_a_pass_for_one_number_does_not_open_another(client):
    mine = send(client, "9811100004", "hello")["visitor"]
    send(client, "9811100005", "mera naam Kavya hai")
    assert client.get("/api/wa/threads/9811100005", params={"pack": PACK, "visitor": mine}).json() == {"messages": []}


def test_the_owner_still_sees_every_thread(client):
    send(client, "9811100006", "hello")
    threads = client.get("/api/wa/threads", params={"pack": PACK}, headers=owner(client)).json()["threads"]
    assert any(t["phone"] == "9811100006" for t in threads)


def test_the_rest_of_the_console_stays_closed(client):
    assert client.get("/api/insights", params={"pack": PACK}).status_code == 401
    assert client.get(f"/api/packs/{PACK}").status_code == 401


def test_a_real_shop_keeps_the_simulator_behind_sign_in(client, monkeypatch):
    monkeypatch.setattr(server, "PUBLIC_SIMULATOR", False)
    assert client.post("/api/wa/incoming", json={"pack": PACK, "phone": "9811100007", "text": "hi"}).status_code == 401
    assert client.get("/api/wa/threads", params={"pack": PACK}).status_code == 401


def test_talk_lines_are_public_and_only_lines(client):
    r = client.get(f"/api/packs/{PACK}/lines")
    assert r.status_code == 200
    body = r.json()
    assert list(body) == ["lines"] and body["lines"] and all(isinstance(x, str) for x in body["lines"])
    assert client.get("/api/packs/no_such_pack/lines").status_code == 404
