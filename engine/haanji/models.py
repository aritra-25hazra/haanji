"""Core value objects shared by the pipeline, the contributions and the tools."""
from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id() -> str:
    return str(uuid.uuid4())


class Speaker(str, Enum):
    CALLER = "caller"
    AGENT = "agent"


class Outcome(str, Enum):
    BOOKED = "BOOKED"
    FAQ_ANSWERED = "FAQ_ANSWERED"
    LEAD_CAPTURED = "LEAD_CAPTURED"
    HANDED_OFF = "HANDED_OFF"
    ABANDONED = "ABANDONED"


@dataclass
class Token:
    """One recognised word with the recogniser's confidence in it."""
    text: str
    confidence: float = 1.0
    start_ms: int = 0
    end_ms: int = 0


@dataclass
class Transcript:
    tokens: list[Token]
    is_final: bool = False

    @property
    def text(self) -> str:
        return " ".join(t.text for t in self.tokens)

    @classmethod
    def of(cls, text: str, confidence: float = 1.0, final: bool = True) -> "Transcript":
        return cls([Token(w, confidence) for w in text.split()], final)


@dataclass
class Correction:
    """One repair made by Bhasha Bridge, kept so every change can be audited."""
    from_token: str
    to_surface: str
    asr_confidence: float
    entry_weight: float
    ngram: int = 1


@dataclass
class CorrectedTranscript:
    text: str
    corrections: list[Correction] = field(default_factory=list)
    elapsed_ms: float = 0.0


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    call_id: str = field(default_factory=new_id)


@dataclass
class ToolResult:
    name: str
    ok: bool
    data: Any = None
    error: str | None = None
    spoken: str | None = None
    duration_ms: int = 0
    from_speculation: bool = False


@dataclass
class Turn:
    seq: int
    speaker: Speaker
    text: str
    start_ms: int = 0
    end_ms: int = 0
    interrupted: bool = False
    tool_calls: list[ToolCall] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)
    latency_ms: int | None = None


@dataclass
class ConversationContext:
    """What the agent has learned so far in this call. Used by the predictor."""
    tenant_id: str
    conversation_id: str = field(default_factory=new_id)
    service: str | None = None
    date: str | None = None
    time: str | None = None
    staff: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    pending_confirmation: dict[str, Any] | None = None
    last_offered_slots: list[dict[str, Any]] = field(default_factory=list)
    last_agent_utterance: str = ""
    last_agent_started_ms: int = 0
    answered_questions: int = 0
    outcome: Outcome | None = None
    handoff_reason: str | None = None
    flags: dict[str, Any] = field(default_factory=dict)
    turns: list[Turn] = field(default_factory=list)

    def add(self, turn: Turn) -> None:
        self.turns.append(turn)

    @property
    def slots_ready(self) -> bool:
        return bool(self.service and self.date and self.time and self.customer_phone)

    def missing(self) -> str | None:
        for field_name in ("service", "date", "time", "customer_phone"):
            if not getattr(self, field_name):
                return field_name
        return None

    def transcript(self, last: int = 4) -> str:
        return " | ".join(f"{t.speaker.value}: {t.text}" for t in self.turns[-last:])
