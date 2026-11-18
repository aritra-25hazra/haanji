"""Gemini behind the same dialogue boundary as Claude.

Everything that keeps a hosted model safe in a call is inherited from
:class:`ClaudeLLM` unchanged: a pending confirmation is the policy's turn, the
result of a write is reported by the policy, a request to book or cancel is
turned into the pack's own read-back question, and any vendor failure falls
back to the deterministic policy. Only the wire differs: Gemini's REST
``generateContent`` with function declarations, called over httpx (no SDK).

The model's own parts (including Gemini 3's ``thoughtSignature``) go back
unchanged with the function responses, which is what lets it continue the
turn it started. HAANJI_GEMINI_RPM paces the calls for a free-tier key.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from typing import Any

from ..models import ConversationContext, Speaker, ToolCall, ToolResult
from . import LLMTurn
from .claude import ClaudeLLM

log = logging.getLogger("haanji.gemini")

DEFAULT_MODEL = "gemini-3.5-flash-lite"
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_KEEP = {"type", "description", "properties", "required", "enum", "items", "nullable", "format"}


def gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """A JSON Schema reduced to the OpenAPI subset Gemini's declarations take:
    the type names in capitals, unknown keys (``additionalProperties``,
    ``x-haanji``, ``default``…) dropped, a union type narrowed to its first
    non-null member and marked nullable."""
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key not in _KEEP:
            continue
        if key == "type":
            types = value if isinstance(value, list) else [value]
            concrete = [t for t in types if t != "null"]
            out["type"] = (concrete[0] if concrete else "string").upper()
            if "null" in types:
                out["nullable"] = True
        elif key == "properties":
            out["properties"] = {k: gemini_schema(v) for k, v in value.items()}
        elif key == "items":
            out["items"] = gemini_schema(value)
        elif key == "format" and value not in ("date-time", "enum"):
            continue                                     # Gemini accepts only a few formats
        else:
            out[key] = value
    if out.get("type") == "OBJECT" and not out.get("properties"):
        out.pop("required", None)
    return out


class GeminiLLM(ClaudeLLM):
    """Dialogue adapter over Gemini's generateContent."""

    name = "gemini"

    def __init__(self, policy, pack, registry, *, client=None, model: str | None = None,
                 api_key: str | None = None, timeout: float = 30.0, max_tokens: int = 1024,
                 rpm: float | None = None, **_ignored):
        super().__init__(policy, pack, registry, client=client, model="unused", timeout=timeout, max_tokens=max_tokens)
        self.model = model or os.environ.get("HAANJI_GEMINI_DIALOGUE_MODEL") or DEFAULT_MODEL
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        self.declarations = [{"name": t["name"], "description": t["description"],
                              **({"parameters": gemini_schema(t["input_schema"])}
                                 if t["input_schema"].get("properties") else {})} for t in self.tools]
        self.rpm = rpm if rpm is not None else float(os.environ.get("HAANJI_GEMINI_RPM", "0") or 0)
        self._last_call = 0.0

    @property
    def client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def _pace(self) -> None:
        if self.rpm <= 0:
            return
        gap = 60.0 / self.rpm - (time.monotonic() - self._last_call)
        if gap > 0:
            await asyncio.sleep(gap)
        self._last_call = time.monotonic()

    # ------------------------------------------------------------------ wire
    async def _ask_model(self, text: str, ctx: ConversationContext,
                         results: list[ToolResult] | None) -> LLMTurn:
        body = {"systemInstruction": {"parts": [{"text": self.system}]},
                "contents": self._messages(ctx, text, results),
                "tools": [{"functionDeclarations": self.declarations}],
                "generationConfig": {"maxOutputTokens": self.max_tokens * 2,
                                     "thinkingConfig": {"thinkingLevel": "LOW" if "3.8-flash" in self.model
                                                        and "lite" not in self.model else "MINIMAL"}}}
        await self._pace()
        self.calls += 1
        started = time.perf_counter()                    # after the pacing wait: only the round trip
        r = await asyncio.wait_for(self.client.post(URL.format(model=self.model), json=body,
                                                    headers={"x-goog-api-key": self.api_key}), timeout=self.timeout)
        self.call_ms.append((time.perf_counter() - started) * 1000)
        r.raise_for_status()
        data = r.json()
        meta = data.get("usageMetadata") or {}
        self.usage["input"] += int(meta.get("promptTokenCount", 0) or 0)
        self.usage["output"] += int(meta.get("candidatesTokenCount", 0) or 0) + int(meta.get("thoughtsTokenCount", 0) or 0)
        content = ((data.get("candidates") or [{}])[0].get("content") or {})
        return self._interpret_parts(content.get("parts") or [], ctx)

    def _messages(self, ctx: ConversationContext, text: str,
                  results: list[ToolResult] | None) -> list[dict[str, Any]]:
        msgs: list[dict[str, Any]] = []
        for t in ctx.turns:
            role = "user" if t.speaker is Speaker.CALLER else "model"
            if not t.text or (role == "model" and not msgs):
                continue
            if msgs and msgs[-1]["role"] == role:
                msgs[-1]["parts"][0]["text"] += "\n" + t.text
            else:
                msgs.append({"role": role, "parts": [{"text": t.text}]})
        if not msgs or msgs[-1]["role"] != "user" or not msgs[-1]["parts"][0]["text"].endswith(text):
            if msgs and msgs[-1]["role"] == "user":
                msgs[-1]["parts"][0]["text"] += "\n" + text
            else:
                msgs.append({"role": "user", "parts": [{"text": text}]})
        if results is None:
            return msgs
        parts = self._in_flight.pop(ctx.conversation_id, None) or []
        by_name: dict[str, list[ToolResult]] = {}
        for r in results:
            by_name.setdefault(r.name, []).append(r)
        answers = []
        for p in parts:
            call = p.get("functionCall") if isinstance(p, dict) else None
            if not call:
                continue
            queue = by_name.get(call["name"]) or []
            body = json.loads(self._result_text(queue.pop(0))) if queue else {"ok": True}
            answer: dict[str, Any] = {"name": call["name"], "response": body}
            if call.get("id"):
                answer["id"] = call["id"]
            answers.append({"functionResponse": answer})
        msgs.append({"role": "model", "parts": parts})      # unchanged, thought signatures and all
        msgs.append({"role": "user", "parts": answers})
        return msgs

    def _interpret_parts(self, parts: list[dict[str, Any]], ctx: ConversationContext) -> LLMTurn:
        say_parts: list[str] = []
        calls: list[ToolCall] = []
        end = False
        for p in parts:
            if p.get("thought"):
                continue
            if p.get("text", "").strip():
                say_parts.append(p["text"].strip())
            call = p.get("functionCall")
            if not call:
                continue
            name, args = call.get("name", ""), dict(call.get("args") or {})
            if name == "end_call":
                end = True
                continue
            if name not in self.registry:
                log.warning("model asked for unknown tool %s", name)
                continue
            if self.registry.requires_confirmation(name):
                asked = self.policy.ask_confirmation(ctx, name, args)     # the same gate as Claude's
                lead = " ".join(say_parts).strip()
                asked.say = f"{lead} {asked.say}".strip() if lead else asked.say
                return asked
            calls.append(ToolCall(name, args, call_id=call.get("id") or f"g{len(calls)}"))
        say = " ".join(say_parts).strip()
        if calls:
            self._in_flight[ctx.conversation_id] = list(parts)
            return LLMTurn(say=say, tool_calls=calls)
        if end:
            return LLMTurn(say=say or self.policy.closing(), end_call=True)
        if not say:
            raise ValueError("empty reply from the model")
        return LLMTurn(say=say)
