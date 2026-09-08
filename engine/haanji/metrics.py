"""Counters, timers and the report the benchmark prints.

Latency is kept as raw samples rather than a running mean: the number that
matters for a phone call is the tail, and a mean hides it.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


@dataclass
class Metrics:
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    samples: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def inc(self, name: str, by: int = 1) -> None:
        self.counters[name] += by

    def observe(self, name: str, value: float) -> None:
        self.samples[name].append(value)

    def merge(self, other: "Metrics") -> None:
        for k, v in other.counters.items():
            self.counters[k] += v
        for k, v in other.samples.items():
            self.samples[k].extend(v)

    def summary(self, name: str) -> dict[str, float]:
        v = self.samples.get(name, [])
        if not v:
            return {"n": 0}
        return {"n": len(v), "mean": round(sum(v) / len(v), 1),
                "p50": round(percentile(v, 0.50), 1),
                "p90": round(percentile(v, 0.90), 1),
                "p95": round(percentile(v, 0.95), 1),
                "max": round(max(v), 1)}

    def as_dict(self) -> dict[str, Any]:
        return {"counters": dict(self.counters),
                "latency": {k: self.summary(k) for k in sorted(self.samples)}}
