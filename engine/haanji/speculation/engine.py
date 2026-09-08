"""The speculation engine: predict, budget, execute, claim."""
from __future__ import annotations
import time
from typing import Any, Callable, Awaitable

from ..config import SpeculationConfig
from ..models import ConversationContext
from .cache import SpeculationCache, speculation_key
from .predictor import IntentPredictor, ToolGuess


class SpeculationEngine:
    """Owns prediction, the budget and the cache for one session.

    ``executor`` runs a tool and returns its result; it is the *same* function
    the real turn uses, which is what guarantees a speculative result is
    indistinguishable from a normally-computed one.
    """

    def __init__(self, tenant_id: str, executor: Callable[[str, dict], Awaitable[Any]],
                 is_read_only: Callable[[str], bool],
                 config: SpeculationConfig | None = None,
                 predictor: IntentPredictor | None = None):
        self.tenant_id = tenant_id
        self.cfg = config or SpeculationConfig()
        self.executor = executor
        self.is_read_only = is_read_only
        self.predictor = predictor or IntentPredictor()
        self.cache = SpeculationCache(self.cfg.ttl_ms)
        self._this_turn = 0
        self._last_keys: set[str] = set()
        self.events: list[dict[str, Any]] = []

    # ---------------------------------------------------------------- lifecycle
    def begin_turn(self) -> None:
        self._this_turn = 0
        self._last_keys.clear()

    async def end_turn(self) -> None:
        await self.cache.drain()

    def on_write(self) -> None:
        """A write happened: everything computed against the old world is void."""
        self.cache.invalidate()

    # ---------------------------------------------------------------- prediction
    def on_partial(self, partial: str, ctx: ConversationContext) -> list[ToolGuess]:
        """Called on every partial transcript. Fires speculations within budget."""
        if not self.cfg.enabled:
            return []
        if len(partial.split()) < self.cfg.min_partial_words:
            return []
        if self._this_turn >= self.cfg.max_per_turn:
            self.cache.stats.suppressed += 1
            return []

        fired: list[ToolGuess] = []
        for guess in self.predictor.predict(partial, ctx):
            if guess.confidence < self.cfg.min_confidence:
                continue
            if not self.is_read_only(guess.tool):
                continue                       # purity: writes are never speculated
            key = speculation_key(self.tenant_id, guess.tool, guess.key_args())
            if key in self._last_keys or self.cache.has(key):
                continue                       # same prediction, no new call
            if len(self._last_keys) >= self.cfg.max_inflight:
                self.cache.stats.suppressed += 1
                break
            self._last_keys.add(key)
            self._this_turn += 1
            self.cache.start(key, self._run(guess))
            self.events.append({"predicted_tool": guess.tool, "confidence": guess.confidence,
                                "at_ms": int(time.time() * 1000), "hit": None})
            fired.append(guess)
        return fired

    async def _run(self, guess: ToolGuess):
        t0 = time.perf_counter()
        result = await self.executor(guess.tool, guess.args)
        return {"result": result, "cost_ms": (time.perf_counter() - t0) * 1000}

    # ------------------------------------------------------------------- claim
    async def claim(self, tool: str, args: dict[str, Any]):
        """Return a speculative result for this exact call, or None."""
        if not self.cfg.enabled:
            return None
        key = speculation_key(self.tenant_id, tool, dict(sorted(args.items())))
        payload = await self.cache.claim(key)
        if payload is None:
            for ev in self.events:
                if ev["predicted_tool"] == tool and ev["hit"] is None:
                    ev["hit"] = False
            return None
        self.cache.stats.saved_ms += payload["cost_ms"]
        for ev in reversed(self.events):
            if ev["predicted_tool"] == tool and ev["hit"] is None:
                ev["hit"] = True
                ev["saved_ms"] = round(payload["cost_ms"], 1)
                break
        return payload["result"]

    @property
    def stats(self):
        return self.cache.stats
