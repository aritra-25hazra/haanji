"""The same phone bridge on Exotel's wire: 16-bit PCM in and out, snake_case
events, chunks of at least 100 ms in multiples of 320 bytes, a key on the
applet's URL in place of a signature. One conversation runs through both
providers' wires with the same fake recogniser and synthesiser."""
import base64
import json
import struct

import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.telephony import exotel as ex
from haanji.telephony import g711
from tests.test_telephony import FakeSTT, fake_tts, frames


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setitem(server.PHONE_FACTORIES, "stt", FakeSTT)
    monkeypatch.setitem(server.PHONE_FACTORIES, "tts", fake_tts)
    monkeypatch.setattr(server, "PUBLIC_URL", "https://haanji.example")
    monkeypatch.setattr(server, "IS_PUBLIC", False)
    monkeypatch.delenv("HAANJI_EXOTEL_STREAM_KEY", raising=False)
    server._buckets.clear()
    return TestClient(server.app)


def start(params, caller="+919876543210"):
    return json.dumps({"event": "start", "sequence_number": 1, "stream_sid": "ex1",
                       "start": {"stream_sid": "ex1", "call_sid": "c1", "account_sid": "a1", "from": caller, "to": "+911234567890",
                                 "custom_parameters": params, "media_format": {"encoding": "raw", "sample_rate": "8000", "bit_rate": "128"}}})


def pcm_media(n_bytes=320):
    return json.dumps({"event": "media", "sequence_number": 3, "stream_sid": "ex1",
                       "media": {"chunk": 2, "timestamp": "10", "payload": base64.b64encode(b"\x00" * n_bytes).decode()}})


def test_g711_round_trips_and_silence_stays_silence():
    pcm = struct.pack("<6h", 0, 1000, -1000, 8000, -8000, 30000)
    back = struct.unpack("<6h", g711.ulaw_to_pcm16(g711.pcm16_to_ulaw(pcm)))
    assert all(abs(a - b) <= max(16, abs(a) // 16) for a, b in zip(struct.unpack("<6h", pcm), back))
    assert g711.pcm16_to_ulaw(b"\x00\x00") == b"\xff" and g711.ulaw_to_pcm16(b"\xff") == b"\x00\x00"


def test_outgoing_audio_comes_in_valid_exotel_chunks():
    w = ex.ExotelWire()
    out = w.media("s", b"\xff" * 160) + w.media("s", b"\xff" * 2000) + w.flush("s")
    sizes = [len(base64.b64decode(json.loads(m)["media"]["payload"])) for m in out]
    assert sizes and all(n % ex.STEP == 0 and ex.CHUNK_MIN <= n <= ex.CHUNK_MAX for n in sizes)
    assert sum(sizes) >= 2 * (160 + 2000), "every sample is sent, the tail padded with silence"
    assert all(json.loads(m)["stream_sid"] == "s" for m in out)
    assert json.loads(w.clear("s")) == {"event": "clear", "stream_sid": "s"}


def test_a_call_over_exotel_is_greeted_answered_and_recorded(client):
    FakeSTT.scripts = [[("clinic ke", False), ("clinic ke timings kya hain", True), ("nahi bas itna hi tha dhanyavaad", True)]]
    with client.websocket_connect("/telephony/exotel/stream?pack=dental_clinic") as ws:
        ws.send_text(json.dumps({"event": "connected"}))
        ws.send_text(start({"pack": "dental_clinic"}))
        greeting = frames(ws, 2)                       # 3 x 160 μ-law -> one padded PCM chunk, then the mark
        assert [m["event"] for m in greeting] == ["media", "mark"]
        assert greeting[0]["stream_sid"] == "ex1" and len(base64.b64decode(greeting[0]["media"]["payload"])) == ex.CHUNK_MIN
        for _ in range(10):
            ws.send_text(pcm_media())
        assert [m["event"] for m in frames(ws, 2)] == ["media", "mark"]
        for _ in range(5):
            ws.send_text(pcm_media())
        assert frames(ws, 2)[-1]["event"] == "mark"
    calls = client.get("/api/conversations", params={"pack": "dental_clinic"}).json()["conversations"]
    assert any(c["channel"] == "PHONE" and c["phone"] == "9876543210" and c["outcome"] == "FAQ_ANSWERED" for c in calls[:5])


def test_the_recogniser_hears_mulaw_whatever_the_provider_sends():
    w = ex.ExotelWire()
    assert w.inbound(json.loads(pcm_media(320))) == b"\xff" * 160


def test_a_public_server_needs_the_applet_s_key(client, monkeypatch):
    import asyncio
    monkeypatch.setattr(server, "IS_PUBLIC", True)
    assert asyncio.run(server._exotel_open("dental_clinic", "+919876543210", {"key": "x"})) is None
    monkeypatch.setenv("HAANJI_EXOTEL_STREAM_KEY", "k3y")
    assert asyncio.run(server._exotel_open("dental_clinic", "+919876543210", {"key": "wrong"})) is None
    opened = asyncio.run(server._exotel_open("dental_clinic", "+919876543210", {"key": "k3y"}))
    assert opened is not None and opened[1].channel == "PHONE"
    server._finish(*opened)
