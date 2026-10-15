"""Streaming recognition over Deepgram's WebSocket API.

Audio goes in as 8 kHz μ-law exactly as Twilio delivers it; results come
back as interim and final transcripts with per-word confidence, which is
what Bhasha Bridge and speculation need. ``language=hi-Latn`` asks for
Hinglish in Latin script, the same register the packs are written in.
"""
from __future__ import annotations
import asyncio
import json
import os
from typing import Any, Awaitable, Callable

DEFAULT_URL = ("wss://api.deepgram.com/v1/listen?encoding=mulaw&sample_rate=8000&channels=1"
               "&model=nova-2&interim_results=true&smart_format=false&punctuate=false"
               "&endpointing=400&vad_events=true")

OnText = Callable[[str, list[float], bool], Awaitable[None]]   # (text, word confidences, is_final)


class DeepgramStream:
    def __init__(self, api_key: str | None = None, language: str | None = None, on_text: OnText | None = None):
        self.api_key = api_key or os.environ.get("HAANJI_DEEPGRAM_KEY") or ""
        self.language = language or os.environ.get("HAANJI_STT_LANGUAGE") or "hi-Latn"
        self.on_text = on_text
        self._ws = None
        self._reader: asyncio.Task | None = None

    @property
    def url(self) -> str:
        return f"{DEFAULT_URL}&language={self.language}"

    async def start(self) -> None:
        import websockets                                  # the optional [live] extra
        self._ws = await websockets.connect(self.url, additional_headers={"Authorization": f"Token {self.api_key}"})
        self._reader = asyncio.create_task(self._read())

    async def send(self, mulaw: bytes) -> None:
        if self._ws is not None:
            await self._ws.send(mulaw)

    async def _read(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                await self.handle(json.loads(raw))
        except Exception:                                  # noqa: BLE001 - the call goes on without transcripts
            pass

    async def handle(self, msg: dict[str, Any]) -> None:
        """Deepgram's result shape, kept separate so a test can feed it."""
        if msg.get("type") != "Results":
            return
        alt = (msg.get("channel") or {}).get("alternatives") or [{}]
        text = (alt[0].get("transcript") or "").strip()
        if not text or self.on_text is None:
            return
        confs = [float(w.get("confidence", 0.9)) for w in alt[0].get("words", [])]
        await self.on_text(text, confs, bool(msg.get("is_final")) and bool(msg.get("speech_final", True)))

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await self._ws.close()
            except Exception:                              # noqa: BLE001
                pass
        if self._reader:
            self._reader.cancel()
