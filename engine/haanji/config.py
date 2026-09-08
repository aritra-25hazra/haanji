"""Engine configuration. Every knob in the SDD Appendix B appears here."""
from __future__ import annotations
import os
from dataclasses import dataclass, field


def _f(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _i(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _b(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class SpeculationConfig:
    enabled: bool = field(default_factory=lambda: _b("HAANJI_SPEC_ENABLED", True))
    max_inflight: int = field(default_factory=lambda: _i("HAANJI_SPEC_MAX_INFLIGHT", 2))
    max_per_turn: int = field(default_factory=lambda: _i("HAANJI_SPEC_MAX_PER_TURN", 3))
    min_confidence: float = field(default_factory=lambda: _f("HAANJI_SPEC_MIN_CONFIDENCE", 0.60))
    ttl_ms: int = field(default_factory=lambda: _i("HAANJI_SPEC_TTL_MS", 4000))
    min_partial_words: int = field(default_factory=lambda: _i("HAANJI_SPEC_MIN_WORDS", 3))


@dataclass(frozen=True)
class BhashaConfig:
    enabled: bool = field(default_factory=lambda: _b("HAANJI_BHASHA_ENABLED", True))
    conf_high: float = field(default_factory=lambda: _f("HAANJI_BHASHA_CONF_HIGH", 0.85))
    max_edit: int = field(default_factory=lambda: _i("HAANJI_BHASHA_MAX_EDIT", 2))
    max_hints: int = field(default_factory=lambda: _i("HAANJI_BHASHA_MAX_HINTS", 60))
    max_ngram: int = field(default_factory=lambda: _i("HAANJI_BHASHA_MAX_NGRAM", 3))


@dataclass(frozen=True)
class LedgerConfig:
    enabled: bool = field(default_factory=lambda: _b("HAANJI_LEDGER_ENABLED", True))
    require_confirmation: bool = field(default_factory=lambda: _b("HAANJI_LEDGER_REQUIRE_CONF", True))


@dataclass(frozen=True)
class EngineConfig:
    stt: str = field(default_factory=lambda: os.environ.get("HAANJI_PROVIDER_STT", "mock"))
    llm: str = field(default_factory=lambda: os.environ.get("HAANJI_PROVIDER_LLM", "mock"))
    tts: str = field(default_factory=lambda: os.environ.get("HAANJI_PROVIDER_TTS", "mock"))
    endpoint_silence_ms: int = field(default_factory=lambda: _i("HAANJI_ENDPOINT_SILENCE_MS", 500))
    max_turn_latency_ms: int = field(default_factory=lambda: _i("HAANJI_MAX_TURN_LATENCY_MS", 1500))
    barge_in_cancel_ms: int = field(default_factory=lambda: _i("HAANJI_BARGE_IN_CANCEL_MS", 200))
    max_concurrent_calls: int = field(default_factory=lambda: _i("HAANJI_MAX_CONCURRENT_CALLS", 25))
    speculation: SpeculationConfig = field(default_factory=SpeculationConfig)
    bhasha: BhashaConfig = field(default_factory=BhashaConfig)
    ledger: LedgerConfig = field(default_factory=LedgerConfig)
