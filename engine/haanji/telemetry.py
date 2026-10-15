"""Process-wide counters and histograms, exposed in Prometheus text format.

No client library: the exposition format is a few lines of text, and the
engine's own ``Metrics`` already keeps the per-call samples the benchmark
reports. This registry is what ``ops/prometheus.yml`` scrapes at /metrics
and what ``ops/alerts.yml`` alerts on; the names there and here are the
same by construction (see ``NAMES``).
"""
from __future__ import annotations
import threading
import time
from collections import defaultdict
from typing import Iterable

LATENCY_BUCKETS_MS = (50.0, 100.0, 200.0, 400.0, 800.0, 1500.0, 3000.0, 6000.0)
TOOL_BUCKETS_MS = (10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0)

NAMES = {
    "calls_total": "Calls finished, by pack, channel and outcome",
    "turns_total": "Caller turns answered, by pack",
    "bhasha_corrections_total": "Tokens repaired by Bhasha Bridge",
    "speculation_started_total": "Read-only tools started on a partial transcript",
    "speculation_hits_total": "Speculative results claimed by the real turn",
    "speculation_wasted_total": "Speculative results discarded",
    "ledger_receipts_total": "Receipts sealed",
    "ledger_unconfirmed_refused_total": "Writes refused for lacking a confirmation proof",
    "guardrail_total": "Turns stopped by a guardrail, by rule",
    "http_rate_limited_total": "Requests answered 429",
    "auth_denied_total": "Requests answered 401 or 403, by status",
    "events_published_total": "Live events published",
    "adapter_fallbacks_total": "Hosted-model turns that fell back to the policy",
}


def _labels(labels: dict[str, str] | None) -> str:
    if not labels:
        return ""
    body = ",".join(f'{k}="{str(v).replace(chr(34), chr(39))}"' for k, v in sorted(labels.items()))
    return "{" + body + "}"


class Telemetry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started = time.time()
        self._counters: dict[str, dict[tuple, float]] = defaultdict(dict)
        self._hist: dict[str, dict[tuple, dict]] = defaultdict(dict)
        self._gauges: dict[str, float] = {}

    # ------------------------------------------------------------ recording
    def inc(self, name: str, by: float = 1, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._counters[name][key] = self._counters[name].get(key, 0.0) + by

    def observe(self, name: str, value_ms: float, buckets: Iterable[float] = LATENCY_BUCKETS_MS, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        with self._lock:
            h = self._hist[name].get(key)
            if h is None:
                h = {"buckets": tuple(buckets), "counts": [0] * (len(tuple(buckets)) + 1), "sum": 0.0, "count": 0, "samples": []}
                self._hist[name][key] = h
            for i, edge in enumerate(h["buckets"]):
                if value_ms <= edge:
                    h["counts"][i] += 1
            h["counts"][-1] += 1
            h["sum"] += value_ms
            h["count"] += 1
            h["samples"].append(value_ms)
            if len(h["samples"]) > 2000:
                del h["samples"][:1000]

    def gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    # ---------------------------------------------------------------- reading
    def counter(self, name: str, **labels: str) -> float:
        key = tuple(sorted(labels.items()))
        return self._counters.get(name, {}).get(key, 0.0)

    def total(self, name: str) -> float:
        return sum(self._counters.get(name, {}).values())

    def samples(self, name: str) -> list[float]:
        out: list[float] = []
        for h in self._hist.get(name, {}).values():
            out.extend(h["samples"])
        return out

    def render(self) -> str:
        """Prometheus text exposition format, version 0.0.4."""
        lines: list[str] = []
        with self._lock:
            for name, series in sorted(self._counters.items()):
                full = f"haanji_{name}"
                lines.append(f"# HELP {full} {NAMES.get(name, name)}")
                lines.append(f"# TYPE {full} counter")
                for key, value in sorted(series.items()):
                    lines.append(f"{full}{_labels(dict(key))} {value:g}")
            for name, series in sorted(self._hist.items()):
                full = f"haanji_{name}"
                lines.append(f"# HELP {full} {NAMES.get(name, name + ' in milliseconds')}")
                lines.append(f"# TYPE {full} histogram")
                for key, h in sorted(series.items()):
                    base = dict(key)
                    for edge, count in zip(h["buckets"], h["counts"]):
                        lines.append(f"{full}_bucket{_labels({**base, 'le': f'{edge:g}'})} {count}")
                    lines.append(f"{full}_bucket{_labels({**base, 'le': '+Inf'})} {h['counts'][-1]}")
                    lines.append(f"{full}_sum{_labels(base)} {h['sum']:g}")
                    lines.append(f"{full}_count{_labels(base)} {h['count']}")
            for name, value in sorted(self._gauges.items()):
                full = f"haanji_{name}"
                lines.append(f"# TYPE {full} gauge")
                lines.append(f"{full} {value:g}")
            lines.append("# TYPE haanji_uptime_seconds gauge")
            lines.append(f"haanji_uptime_seconds {time.time() - self.started:.0f}")
        return "\n".join(lines) + "\n"


TELEMETRY = Telemetry()
