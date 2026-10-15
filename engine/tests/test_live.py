"""The live feed: every call publishes, the console listens."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from haanji import server


@pytest.fixture
def client():
    server._buckets.clear()
    server._recent.clear()
    return TestClient(server.app)


def test_a_web_call_publishes_start_turns_and_end(client):
    before = client.get("/api/events/recent").json()["latest"]
    sid = client.post("/api/sessions", json={"pack": "dental_clinic", "phone": "9876543210"}).json()["session_id"]
    client.post(f"/api/sessions/{sid}/partial", json={"text": "kal subah"})
    client.post(f"/api/sessions/{sid}/utterance", json={"text": "clinic ke timings kya hain"})
    client.delete(f"/api/sessions/{sid}")
    ev = client.get("/api/events/recent", params={"pack": "dental_clinic", "since": before}).json()["events"]
    kinds = [e["kind"] for e in ev]
    assert kinds == ["session.started", "partial", "turn", "session.ended"]
    assert ev[0]["phone"] == "…3210" and ev[0]["greeting"]
    assert ev[2]["reply"] and ev[2]["sid"] == sid and "search_knowledge" in ev[2]["tools"]
    assert ev[3]["outcome"] == "FAQ_ANSWERED" and ev[3]["call_id"]
    assert client.get("/api/events/recent", params={"pack": "salon_spa", "since": before}).json()["events"] == []


def test_the_stream_formats_server_sent_events_and_filters_by_pack():
    async def go():
        q = asyncio.Queue()
        gen = server._event_stream("salon_spa", q)
        assert (await gen.__anext__()).startswith(": connected")
        server.publish("turn", pack="dental_clinic", reply="nahi")
        server.publish("turn", pack="salon_spa", reply="haan")
        chunk = await asyncio.wait_for(gen.__anext__(), 2)
        await gen.aclose()
        return chunk
    chunk = asyncio.run(go())
    assert chunk.startswith("id: ") and "event: turn\n" in chunk and '"reply": "haan"' in chunk and "dental" not in chunk
    assert not server._subscribers, "the subscriber is removed when the stream closes"


def test_an_idle_stream_sends_keepalives(monkeypatch):
    monkeypatch.setattr(server, "KEEPALIVE_S", 0.05)

    async def go():
        gen = server._event_stream(None, asyncio.Queue())
        first = await gen.__anext__()
        second = await asyncio.wait_for(gen.__anext__(), 2)
        await gen.aclose()
        return first, second
    first, second = asyncio.run(go())
    assert first.startswith(": connected") and second.startswith(": keepalive")


def test_the_sse_route_is_registered():
    paths = {r.path for r in server.app.routes}
    assert "/api/events" in paths and "/api/events/recent" in paths
