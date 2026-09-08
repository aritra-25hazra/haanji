"""Provider boundaries.

Every external speech or language service the engine talks to sits behind one
of these three protocols. The engine itself never imports a vendor SDK, so a
provider can be swapped by changing one line of configuration, and the whole
system runs offline against the mock providers used by the demo and the tests.
"""
from __future__ import annotations
from typing import AsyncIterator, Protocol, runtime_checkable

from ..models import ToolCall, Transcript


@runtime_checkable
class STTAdapter(Protocol):
    """Streaming speech recognition."""

    name: str

    def set_hints(self, hints: list[str]) -> None:
        """Accept tenant biasing hints. Providers without biasing ignore this."""

    def stream(self, utterance: str) -> AsyncIterator[Transcript]:
        """Yield growing partials, then exactly one final transcript."""
        ...


@runtime_checkable
class LLMAdapter(Protocol):
    """Dialogue policy: given the state of the call, decide what to do next."""

    name: str

    async def respond(self, system: str, history: list[dict], tools: list[dict]) -> "LLMTurn":
        ...


@runtime_checkable
class TTSAdapter(Protocol):
    """Speech synthesis, streamed so the first audio can start early."""

    name: str

    def speak(self, text: str) -> AsyncIterator[bytes]:
        ...

    async def cancel(self) -> None:
        """Stop mid-sentence when the caller barges in."""


class LLMTurn:
    """What the policy decided: something to say, and/or tools to run."""

    __slots__ = ("say", "tool_calls", "end_call", "needs_confirmation", "tokens")

    def __init__(self, say: str = "", tool_calls: list[ToolCall] | None = None,
                 end_call: bool = False, needs_confirmation: bool = False,
                 tokens: int = 0):
        self.say = say
        self.tool_calls = tool_calls or []
        self.end_call = end_call
        self.needs_confirmation = needs_confirmation
        self.tokens = tokens

    def __repr__(self) -> str:
        tools = ",".join(c.name for c in self.tool_calls) or "-"
        return f"LLMTurn(say={self.say[:40]!r}, tools={tools})"
