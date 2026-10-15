"""The phone bridge, with no phone: Twilio's protocol, a fake recogniser, a fake synthesiser."""
import asyncio
import base64
import json

import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.telephony import twilio as tw


class FakeSTT:
    """Emits a partial and then a final once enough audio has arrived."""
    scripts: list[list[tuple[str, bool]]] = []

    def __init__(self, on_text):
        self.on_text = on_text
        self.frames = 0
        self.closed = False
        self.lines = list(FakeSTT.scripts.pop(0)) if FakeSTT.scripts else []

    async def start(self):
        pass

    async def send(self, mulaw: bytes):
        self.frames += 1
        if self.frames % 5 == 0 and self.lines:
            text, final = self.lines.pop(0)
            await self.on_text(text, [0.9] * len(text.split()), final)

    async def close(self):
        self.closed = True


async def fake_tts(text: str):
    for _ in range(3):
        yield b"\xff" * 160


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setitem(server.PHONE_FACTORIES, "stt", FakeSTT)
    monkeypatch.setitem(server.PHONE_FACTORIES, "tts", fake_tts)
    monkeypatch.setenv("HAANJI_DEEPGRAM_KEY", "d"); monkeypatch.setenv("HAANJI_ELEVENLABS_KEY", "e")
    monkeypatch.setenv("HAANJI_ELEVENLABS_VOICE", "v")
    monkeypatch.setattr(server, "PUBLIC_URL", "https://haanji.example")
    server._buckets.clear()
    return TestClient(server.app)


def test_twiml_and_signature():
    xml = tw.twiml_connect("wss://h/telephony/twilio/stream", "dental_clinic", "+919876543210")
    assert xml.startswith('<?xml') and '<Stream url="wss://h/telephony/twilio/stream">' in xml
    assert '<Parameter name="pack" value="dental_clinic"/>' in xml and 'value="+919876543210"' in xml
    assert tw.stream_url("https://haanji.example/") == "wss://haanji.example/telephony/twilio/stream"
    url, params = "https://haanji.example/telephony/twilio/voice?pack=dental_clinic", {"From": "+911", "CallSid": "CA1"}
    import base64 as b64, hashlib, hmac
    good = b64.b64encode(hmac.new(b"tok", (url + "CallSidCA1From+911").encode(), hashlib.sha1).digest()).decode()
    assert tw.verify_signature("tok", url, params, good) and not tw.verify_signature("tok", url, params, "nope")
    assert not tw.verify_signature("tok", url, params, None)


def test_the_voice_webhook_streams_when_configured_and_checks_the_signature(client, monkeypatch):
    r = client.post("/telephony/twilio/voice", params={"pack": "dental_clinic"}, data={"From": "+919876543210"})
    assert r.status_code == 200 and "<Connect><Stream" in r.text and 'value="dental_clinic"' in r.text
    monkeypatch.setenv("HAANJI_TWILIO_AUTH_TOKEN", "tok")
    assert client.post("/telephony/twilio/voice", data={"From": "+911"}).status_code == 403
    monkeypatch.delenv("HAANJI_TWILIO_AUTH_TOKEN")
    monkeypatch.delenv("HAANJI_DEEPGRAM_KEY")
    r = client.post("/telephony/twilio/voice", data={"From": "+911"})
    assert "<Say>" in r.text and "not configured" in r.text
    assert client.get("/api/status").json()["phone"]["configured"] is False


def frames(ws, n):
    out = []
    for _ in range(n):
        msg = json.loads(ws.receive_text())
        out.append(msg)
    return out


def test_a_call_over_the_bridge_is_greeted_answered_and_recorded(client):
    FakeSTT.scripts = [[("clinic ke", False), ("clinic ke timings kya hain", True), ("nahi bas itna hi tha dhanyavaad", True)]]
    before = client.get("/api/events/recent").json()["latest"]
    with client.websocket_connect("/telephony/twilio/stream") as ws:
        ws.send_text(json.dumps({"event": "connected"}))
        ws.send_text(json.dumps({"event": "start", "start": {"streamSid": "MZ1", "callSid": "CA1",
                                                               "customParameters": {"pack": "dental_clinic", "caller": "+919876543210"}}}))
        greeting = frames(ws, 4)                       # 3 media chunks + the end mark
        assert [m["event"] for m in greeting] == ["media", "media", "media", "mark"]
        assert base64.b64decode(greeting[0]["media"]["payload"]) == b"\xff" * 160 and greeting[0]["streamSid"] == "MZ1"
        payload = base64.b64encode(b"\x00" * 160).decode()
        for _ in range(10):                            # 5 frames -> partial, 10 -> final
            ws.send_text(json.dumps({"event": "media", "media": {"track": "inbound", "payload": payload}}))
        reply = frames(ws, 4)
        assert [m["event"] for m in reply] == ["media", "media", "media", "mark"]
        for _ in range(5):                             # the goodbye: the agent ends the call
            ws.send_text(json.dumps({"event": "media", "media": {"track": "inbound", "payload": payload}}))
        bye = frames(ws, 4)
        assert bye[-1]["event"] == "mark"
    ev = client.get("/api/events/recent", params={"since": before}).json()["events"]
    kinds = [e["kind"] for e in ev]
    assert kinds[0] == "session.started" and ev[0]["channel"] == "PHONE" and ev[0]["phone"] == "…3210"
    assert "partial" in kinds and kinds.count("turn") == 2 and kinds[-1] == "session.ended"
    assert ev[-1]["outcome"] == "FAQ_ANSWERED"
    calls = client.get("/api/conversations", params={"pack": "dental_clinic"}).json()["conversations"]
    assert calls[0]["channel"] == "PHONE" and calls[0]["phone"] == "9876543210"


def test_barge_in_clears_twilio_s_buffer():
    sent = []

    class WS:
        async def send_text(self, t): sent.append(json.loads(t))
        async def receive_text(self): raise RuntimeError("closed")
        async def close(self): pass

    async def slow_tts(text):
        for _ in range(50):
            await asyncio.sleep(0.01)
            yield b"\xff" * 160

    class Holder:
        class session:
            class ctx:
                last_agent_utterance = "Haanji"
                flags = {}
            @staticmethod
            async def handle_partial_text(t): pass

    bridge = tw.TwilioBridge(WS(), open_session=None, close_session=lambda s, h: None, stt_factory=FakeSTT, tts=slow_tts)
    bridge.stream_sid = "MZ9"; bridge.holder = Holder()

    async def go():
        await bridge.say("long sentence")
        await asyncio.sleep(0.05)
        await bridge.on_text("haan", [0.5], False)       # caller interrupts with a partial
        await asyncio.sleep(0.02)
    asyncio.run(go())
    kinds = [m["event"] for m in sent]
    assert "clear" in kinds and kinds.count("media") < 50, "speech stopped and Twilio's buffer was cleared"
