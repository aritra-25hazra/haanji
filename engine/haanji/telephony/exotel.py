"""Exotel AgentStream (the Voicebot applet) on the wire.

Exotel opens a WebSocket to the URL set in the call flow's Voicebot applet
and sends ``connected``, ``start``, ``media``, ``dtmf``, ``mark`` and
``stop`` events; it plays back ``media`` the bot sends, and drops queued
audio on ``clear``. Audio both ways is raw 16-bit little-endian PCM, mono,
8 kHz, base64; what the bot sends must come in chunks of at least 3,200
bytes (100 ms) and a multiple of 320 bytes. Up to three query parameters on
the applet's URL arrive in ``start.custom_parameters``: HaanJi reads ``pack``
and ``key`` (HAANJI_EXOTEL_STREAM_KEY, since the socket carries no signature).
Ending the socket hands the call to the flow's next applet.
Reference: https://developer.exotel.com/docs/agentstream/stream-voicebot-applet
"""
from __future__ import annotations
import base64
import json
from typing import Any

from .g711 import pcm16_to_ulaw, ulaw_to_pcm16

STEP = 320                 # bytes: every chunk a multiple of this
CHUNK_MIN = 3200           # 100 ms of 8 kHz 16-bit audio
CHUNK_MAX = 16000          # half a second: small enough for barge-in to clear quickly


class ExotelWire:
    name = "exotel"

    def __init__(self) -> None:
        self._out = bytearray()            # PCM waiting to make up a whole chunk

    def start(self, msg: dict[str, Any]) -> tuple[str | None, dict[str, Any], str | None]:
        st = msg.get("start") or {}
        params = dict(st.get("custom_parameters") or {})
        sid = st.get("stream_sid") or msg.get("stream_sid")
        return sid, params, st.get("from") or params.get("caller") or None

    def inbound(self, msg: dict[str, Any]) -> bytes | None:
        payload = (msg.get("media") or {}).get("payload")
        return pcm16_to_ulaw(base64.b64decode(payload)) if payload else None

    def _frame(self, sid: str | None, pcm: bytes) -> str:
        return json.dumps({"event": "media", "stream_sid": sid, "media": {"payload": base64.b64encode(pcm).decode()}})

    def media(self, sid: str | None, ulaw: bytes) -> list[str]:
        self._out += ulaw_to_pcm16(ulaw)
        frames = []
        while len(self._out) >= CHUNK_MIN:
            n = min(len(self._out) // STEP * STEP, CHUNK_MAX)
            frames.append(self._frame(sid, bytes(self._out[:n])))
            del self._out[:n]
        return frames

    def flush(self, sid: str | None) -> list[str]:
        """The end of a line: what is left, padded with silence to a valid chunk."""
        if not self._out:
            return []
        size = max(CHUNK_MIN, -(-len(self._out) // STEP) * STEP)
        pcm = bytes(self._out) + b"\x00" * (size - len(self._out))
        self._out.clear()
        return [self._frame(sid, pcm)]

    def drop(self) -> None:
        self._out.clear()

    def clear(self, sid: str | None) -> str:
        return json.dumps({"event": "clear", "stream_sid": sid})

    def mark(self, sid: str | None, name: str) -> str:
        return json.dumps({"event": "mark", "stream_sid": sid, "mark": {"name": name}})
