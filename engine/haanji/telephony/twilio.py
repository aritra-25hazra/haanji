"""Twilio Media Streams: the call itself.

Twilio calls ``/telephony/twilio/voice`` when the number rings; the TwiML
there tells it to open a WebSocket to ``/telephony/twilio/stream`` and send
the caller's audio. ``TwilioBridge`` runs one call: a ``CallSession`` with
``NullTTS`` (we play audio ourselves), a streaming recogniser whose partials
go to ``handle_partial_text`` (speculation) and whose finals go to
``handle_text_turn``, and a synthesiser whose μ-law chunks go back as media
frames. When the caller speaks over the agent, Twilio is told to clear its
audio buffer: that is barge-in on a real line.
"""
from __future__ import annotations
import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, AsyncIterator, Awaitable, Callable
from xml.sax.saxutils import escape

TTSFactory = Callable[[str], AsyncIterator[bytes]]
STTFactory = Callable[..., Any]        # (on_text) -> object with start/send/close


def twiml_connect(stream_url: str, pack: str, caller: str | None = None) -> str:
    params = [f'<Parameter name="pack" value="{escape(pack)}"/>']
    if caller:
        params.append(f'<Parameter name="caller" value="{escape(caller)}"/>')
    return ('<?xml version="1.0" encoding="UTF-8"?><Response><Connect>'
            f'<Stream url="{escape(stream_url)}">{"".join(params)}</Stream></Connect></Response>')


def twiml_say(text: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Say>{escape(text)}</Say></Response>'


def verify_signature(auth_token: str, url: str, params: dict[str, str], header: str | None) -> bool:
    """Twilio signs url + sorted form params with HMAC-SHA1, base64."""
    if not header:
        return False
    body = url + "".join(k + params[k] for k in sorted(params))
    want = base64.b64encode(hmac.new(auth_token.encode(), body.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(want, header)


def stream_url(public_url: str) -> str:
    base = public_url.replace("https://", "wss://").replace("http://", "ws://").rstrip("/")
    return f"{base}/telephony/twilio/stream"


class TwilioBridge:
    """One phone call over one WebSocket."""

    def __init__(self, ws, *, open_session, close_session, stt_factory: STTFactory, tts: TTSFactory,
                 on_turn: Callable[[Any, Any], Awaitable[None]] | None = None,
                 on_partial: Callable[[str, Any], Any] | None = None,
                 human_hook: Callable[[Any, Any, str], bool] | None = None):
        self.ws = ws
        self.open_session = open_session          # async (pack, caller) -> (sid, holder)
        self.close_session = close_session        # (sid, holder) -> None
        self.stt_factory = stt_factory
        self.tts = tts
        self.on_turn = on_turn
        self.on_partial = on_partial
        self.human_hook = human_hook
        self.stream_sid: str | None = None
        self.sid = None
        self.holder = None
        self.stt = None
        self._speaking: asyncio.Task | None = None
        self._turn_lock = asyncio.Lock()
        self.frames_in = 0
        self.frames_out = 0
        self.started = time.monotonic()

    # ---------------------------------------------------------------- audio
    async def _send_media(self, mulaw: bytes) -> None:
        await self.ws.send_text(json.dumps({"event": "media", "streamSid": self.stream_sid,
                                            "media": {"payload": base64.b64encode(mulaw).decode()}}))
        self.frames_out += 1

    async def _clear(self) -> None:
        await self.ws.send_text(json.dumps({"event": "clear", "streamSid": self.stream_sid}))

    async def say(self, text: str) -> None:
        """Start speaking; returns at once so the caller can interrupt."""
        if not text:
            return
        await self.stop_speaking()
        self._speaking = asyncio.create_task(self._speak(text))

    async def _speak(self, text: str) -> None:
        try:
            async for chunk in self.tts(text):
                await self._send_media(chunk)
            await self.ws.send_text(json.dumps({"event": "mark", "streamSid": self.stream_sid, "mark": {"name": "end"}}))
        except asyncio.CancelledError:
            raise
        except Exception:                                  # noqa: BLE001 - audio failed, the call survives
            pass

    async def stop_speaking(self) -> None:
        if self._speaking and not self._speaking.done():
            self._speaking.cancel()
            try:
                await self._speaking
            except (asyncio.CancelledError, Exception):    # noqa: BLE001
                pass
            await self._clear()
        self._speaking = None

    # ----------------------------------------------------------- transcripts
    async def on_text(self, text: str, confs: list[float], is_final: bool) -> None:
        if self.holder is None:
            return
        session = self.holder.session
        if self._speaking and not self._speaking.done():
            await self.stop_speaking()                     # barge-in: the caller wins
        if not is_final:
            await session.handle_partial_text(text)
            if self.on_partial:
                self.on_partial(text, self.holder)
            return
        async with self._turn_lock:
            if self.human_hook and self.human_hook(self.sid, self.holder, text):
                return                                     # a person answers from the console
            confidence = min(confs) if confs else None
            record = await session.handle_text_turn(text, confidence=confidence)
            if self.on_turn:
                await self.on_turn(record, self.holder)
            await self.say(record.said)
            if session.ctx.flags.get("ended"):
                await self._finish_speaking_then_hangup()

    async def _finish_speaking_then_hangup(self) -> None:
        if self._speaking:
            try:
                await self._speaking
            except Exception:                              # noqa: BLE001
                pass
        await asyncio.sleep(0.2)
        await self.hangup()

    # ---------------------------------------------------------------- events
    async def run(self) -> None:
        try:
            while True:
                raw = await self.ws.receive_text()
                msg = json.loads(raw)
                ev = msg.get("event")
                if ev == "start":
                    await self._on_start(msg["start"])
                elif ev == "media":
                    self.frames_in += 1
                    if self.stt is not None and msg["media"].get("track", "inbound") == "inbound":
                        await self.stt.send(base64.b64decode(msg["media"]["payload"]))
                elif ev == "stop":
                    break
        except Exception:                                  # noqa: BLE001 - the socket closed
            pass
        finally:
            await self.hangup()

    async def _on_start(self, start: dict[str, Any]) -> None:
        self.stream_sid = start.get("streamSid")
        params = start.get("customParameters") or {}
        pack = params.get("pack") or os.environ.get("HAANJI_PHONE_PACK") or os.environ.get("HAANJI_PACK", "dental_clinic")
        caller = params.get("caller") or None
        self.sid, self.holder = await self.open_session(pack, caller)
        self.holder.speak = self.say                           # lets a human reply be spoken on the line
        self.stt = self.stt_factory(self.on_text)
        await self.stt.start()
        await self.say(self.holder.session.ctx.last_agent_utterance)

    async def hangup(self) -> None:
        if self.stt is not None:
            await self.stt.close()
            self.stt = None
        if self._speaking and not self._speaking.done():
            self._speaking.cancel()
        if self.holder is not None:
            self.close_session(self.sid, self.holder)
            self.holder = None
        try:
            await self.ws.close()
        except Exception:                                  # noqa: BLE001
            pass

