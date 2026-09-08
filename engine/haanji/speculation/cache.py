"""Claim-once, TTL-bounded cache for speculative results."""
from __future__ import annotations
import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


def speculation_key(tenant_id: str, tool: str, args: dict[str, Any]) -> str:
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(f"{tenant_id}|{tool}|{canonical}".encode()).hexdigest()[:32]


@dataclass
class SpecStats:
    started: int = 0
    hits: int = 0
    misses: int = 0
    wasted: int = 0
    saved_ms: float = 0.0
    suppressed: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.wasted
        return self.hits / total if total else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {"started": self.started, "hits": self.hits, "misses": self.misses,
                "wasted": self.wasted, "suppressed": self.suppressed,
                "saved_ms": round(self.saved_ms, 1), "hit_rate": round(self.hit_rate, 3)}


@dataclass
class _Entry:
    task: asyncio.Task
    created_ms: float
    claimed: bool = False


class SpeculationCache:
    def __init__(self, ttl_ms: int = 4000):
        self.ttl_ms = ttl_ms
        self._entries: dict[str, _Entry] = {}
        self.stats = SpecStats()

    def has(self, key: str) -> bool:
        self._evict()
        return key in self._entries

    def start(self, key: str, coro) -> None:
        """Begin executing a speculation. Never blocks the caller."""
        self._evict()
        if key in self._entries:
            coro.close()
            return
        self._entries[key] = _Entry(asyncio.ensure_future(coro), time.monotonic() * 1000)
        self.stats.started += 1

    async def claim(self, key: str):
        """Return the speculative result at most once, or None on a miss."""
        self._evict()
        entry = self._entries.pop(key, None)
        if entry is None or entry.claimed:
            self.stats.misses += 1
            return None
        try:
            result = await entry.task
        except Exception:
            self.stats.misses += 1
            return None
        self.stats.hits += 1
        return result

    def invalidate(self) -> None:
        """Any write in the session invalidates everything computed before it."""
        for entry in self._entries.values():
            self.stats.wasted += 1
            entry.task.cancel()
        self._entries.clear()

    async def drain(self) -> None:
        """Cancel anything still in flight at end of turn or end of call."""
        for entry in self._entries.values():
            self.stats.wasted += 1
            entry.task.cancel()
        pending = [e.task for e in self._entries.values()]
        self._entries.clear()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def _evict(self) -> None:
        now = time.monotonic() * 1000
        for key in [k for k, e in self._entries.items() if now - e.created_ms > self.ttl_ms]:
            entry = self._entries.pop(key)
            entry.task.cancel()
            self.stats.wasted += 1
