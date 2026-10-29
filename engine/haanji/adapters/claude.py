"""A hosted model behind the dialogue boundary.

The model decides what to say and which read-only tools to run. It does not
decide when something is written: a request to book or cancel is turned into
the pack's own read-back question, and the caller's yes is handled by the
deterministic policy, which is the only path that produces a tool call the
ledger will accept. If the vendor is unreachable the turn falls back to the
policy and the call carries on.

The ``anthropic`` SDK is imported here and nowhere else, lazily, so the engine
runs without it unless this adapter is actually configured.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
from typing import Any

from ..models import ConversationContext, Speaker, ToolCall, ToolResult
from ..tools import ToolRegistry
from ..vertical import Pack
from . import LLMTurn
from .prompt import build_system_prompt, tool_schemas

log = logging.getLogger("haanji.claude")

DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_EFFORT = "low"
END_CALL = {
    "name": "end_call",
    "description": "End the call once the caller is done and you have said goodbye. "
                   "Put the goodbye in your text in the same reply.",
    "input_schema": {"type": "object", "properties": {}},
}
CONFIRMATION_NOTE = (" The engine will read the details back to the caller and ask for a "
                     "yes before this happens; do not ask for that yourself.")


def build_tools(registry: ToolRegistry) -> list[dict[str, Any]]:
    """The registry's schemas in the Messages API shape, plus ``end_call``."""
    out: list[dict[str, Any]] = []
    for s in tool_schemas(registry):
        meta = s.get("x-haanji", {})
        desc = s["description"] + (CONFIRMATION_NOTE if meta.get("requires_confirmation") else "")
        out.append({"name": s["name"], "description": desc, "input_schema": s["parameters"]})
    out.append(dict(END_CALL))
    return out


class ClaudeLLM:
    """Dialogue adapter over Anthropic's Messages API."""

    name = "claude"

    def __init__(self, policy, pack: Pack, registry: ToolRegistry, *, client=None,
                 model: str | None = None, effort: str | None = None,
                 timeout: float = 20.0, max_tokens: int = 1024):
        self.policy = policy
        self.pack = pack
        self.registry = registry
        self.model = model or os.environ.get("HAANJI_LLM_MODEL") or DEFAULT_MODEL
        self.effort = effort or os.environ.get("HAANJI_LLM_EFFORT") or DEFAULT_EFFORT
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.system = build_system_prompt(pack, today=getattr(policy.backend, "today", None))
        self.tools = build_tools(registry)
        self._client = client
        self.calls = 0
        self.fallbacks = 0
        self.usage = {"input": 0, "output": 0}
        self._in_flight: dict[str, list[Any]] = {}     # conversation_id -> assistant blocks

    # ------------------------------------------------------------- the client
    @property
    def client(self):
        if self._client is None:
            import anthropic  # the optional extra, imported late
            self._client = anthropic.AsyncAnthropic(timeout=self.timeout, max_retries=1)
        return self._client

    # ---------------------------------------------------------------- the turn
    async def respond(self, system: str, history: list[dict], tools: list[dict]) -> LLMTurn:
        last = history[-1]
        text: str = last["content"]
        ctx: ConversationContext = last["context"]
        results: list[ToolResult] | None = last.get("results")

        # 1. A pending confirmation is the policy's turn, never the model's.
        if ctx.pending_confirmation and results is None:
            return self.policy.plan(text, ctx)
        # 2. The result of a write (or of a cancel) is reported by the policy,
        #    whose wording the tests and the ledger already agree on.
        if results is not None and any(
                not self.registry.is_read_only(r.name) for r in results if r.name in self.registry):
            return self.policy.after_tools(text, ctx, results)

        try:
            return await self._ask_model(text, ctx, results)
        except Exception as exc:                  # noqa: BLE001 - vendor boundary
            self.fallbacks += 1
            log.warning("claude adapter fell back to the policy: %s: %s", type(exc).__name__, exc)
            self._in_flight.pop(ctx.conversation_id, None)
            if results is not None:
                return self.policy.after_tools(text, ctx, results)
            return self.policy.plan(text, ctx)

    async def _ask_model(self, text: str, ctx: ConversationContext,
                         results: list[ToolResult] | None) -> LLMTurn:
        messages = self._messages(ctx, text, results)
        self.calls += 1
        reply = await asyncio.wait_for(self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            tools=self.tools,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
        ), timeout=self.timeout)
        usage = getattr(reply, "usage", None)
        if usage is not None:
            self.usage["input"] += int(getattr(usage, "input_tokens", 0) or 0)
            self.usage["output"] += int(getattr(usage, "output_tokens", 0) or 0)
        return self._interpret(reply, ctx)

    # ------------------------------------------------------------- messages
    def _messages(self, ctx: ConversationContext, text: str,
                  results: list[ToolResult] | None) -> list[dict[str, Any]]:
        """Rebuild the conversation from the call's own turn log, which already
        ends with the current caller turn. The greeting is in the system
        prompt, so the log starts at the caller; adjacent same-speaker turns
        are folded so user and assistant strictly alternate."""
        msgs: list[dict[str, Any]] = []
        for t in ctx.turns:
            role = "user" if t.speaker is Speaker.CALLER else "assistant"
            if not t.text or (role == "assistant" and not msgs):
                continue
            if msgs and msgs[-1]["role"] == role:
                msgs[-1]["content"] += "\n" + t.text
            else:
                msgs.append({"role": role, "content": t.text})
        if not msgs or msgs[-1]["role"] != "user" or not msgs[-1]["content"].endswith(text):
            if msgs and msgs[-1]["role"] == "user":
                msgs[-1]["content"] += "\n" + text
            else:
                msgs.append({"role": "user", "content": text})
        if results is None:
            return msgs
        blocks = self._in_flight.pop(ctx.conversation_id, None) or []
        by_name: dict[str, list[ToolResult]] = {}
        for r in results:
            by_name.setdefault(r.name, []).append(r)
        answers = []
        for b in blocks:
            if getattr(b, "type", None) != "tool_use":
                continue
            queue = by_name.get(b.name) or []
            body = self._result_text(queue.pop(0)) if queue else json.dumps({"ok": True})
            answers.append({"type": "tool_result", "tool_use_id": b.id, "content": body})
        msgs.append({"role": "assistant", "content": blocks})
        msgs.append({"role": "user", "content": answers})
        return msgs

    @staticmethod
    def _result_text(r: ToolResult) -> str:
        body = {"ok": r.ok, "spoken": r.spoken or "", "data": r.data or {}}
        if r.error:
            body["error"] = r.error
        return json.dumps(body, ensure_ascii=False, default=str)

    # ------------------------------------------------------------ interpret
    def _interpret(self, reply, ctx: ConversationContext) -> LLMTurn:
        say_parts: list[str] = []
        calls: list[ToolCall] = []
        end = False
        for block in reply.content:
            kind = getattr(block, "type", None)
            if kind == "text" and block.text.strip():
                say_parts.append(block.text.strip())
            elif kind == "tool_use":
                if block.name == "end_call":
                    end = True
                    continue
                if block.name not in self.registry:
                    log.warning("model asked for unknown tool %s", block.name)
                    continue
                if self.registry.requires_confirmation(block.name):
                    # The gate: a write becomes the pack's own read-back question.
                    asked = self.policy.ask_confirmation(ctx, block.name, dict(block.input))
                    lead = " ".join(say_parts).strip()
                    asked.say = f"{lead} {asked.say}".strip() if lead else asked.say
                    return asked
                calls.append(ToolCall(block.name, dict(block.input), call_id=block.id))
        say = " ".join(say_parts).strip()
        if calls:
            # The whole reply goes back next round, thinking blocks included,
            # so the model continues the turn it started.
            self._in_flight[ctx.conversation_id] = list(reply.content)
            return LLMTurn(say=say, tool_calls=calls)
        if end:
            return LLMTurn(say=say or self.policy.closing(), end_call=True)
        if not say:
            raise ValueError("empty reply from the model")
        return LLMTurn(say=say)
