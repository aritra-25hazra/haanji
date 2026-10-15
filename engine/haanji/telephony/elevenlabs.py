"""Streaming synthesis from ElevenLabs, straight to telephone audio.

``output_format=ulaw_8000`` returns the 8 kHz μ-law Twilio plays, so no
resampling happens on the way back; chunks are forwarded as they arrive so
the caller hears the first word before the sentence is finished.
"""
from __future__ import annotations
import os
from typing import AsyncIterator

import httpx

BASE = "https://api.elevenlabs.io/v1/text-to-speech"


async def synth_ulaw(text: str, api_key: str | None = None, voice_id: str | None = None,
                     model_id: str | None = None, client: httpx.AsyncClient | None = None) -> AsyncIterator[bytes]:
    key = api_key or os.environ.get("HAANJI_ELEVENLABS_KEY") or ""
    voice = voice_id or os.environ.get("HAANJI_ELEVENLABS_VOICE") or ""
    model = model_id or os.environ.get("HAANJI_ELEVENLABS_MODEL") or "eleven_multilingual_v2"
    own = client is None
    client = client or httpx.AsyncClient(timeout=30.0)
    try:
        async with client.stream("POST", f"{BASE}/{voice}/stream", params={"output_format": "ulaw_8000"},
                                 headers={"xi-api-key": key, "Content-Type": "application/json"},
                                 json={"text": text, "model_id": model}) as r:
            r.raise_for_status()
            async for chunk in r.aiter_bytes(chunk_size=1600):      # 200 ms of 8 kHz μ-law
                if chunk:
                    yield chunk
    finally:
        if own:
            await client.aclose()
