#!/usr/bin/env python3
"""Deterministic policy versus a hosted model, on the same 21 scenarios.

Runs every packaged scenario under the ``mock`` adapter and, when an API key
is configured, under ``claude``; writes ``research/llm_ablation.json`` and
prints a Markdown table. The point is not that one wins: it is that the
outcomes, the receipts and the guarantees are the same whichever one talks,
and that the cost of the model (latency, tokens, fallbacks, lost speculation)
is measured rather than guessed.

    python research/harness/llm_ablation.py            # both, if a key exists
    python research/harness/llm_ablation.py --only mock
"""
from __future__ import annotations
import argparse
import asyncio
import datetime as dt
import json
import os
import sqlite3
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from haanji.clock import set_speed                              # noqa: E402
from haanji.config import EngineConfig                          # noqa: E402
from haanji.pipeline import run_scenario                        # noqa: E402
from haanji.pramaan.ledger import Ledger                        # noqa: E402
from haanji.scenario import scenarios_of                        # noqa: E402
from haanji.tools.builtin import build_registry, open_backend   # noqa: E402
from haanji.vertical import list_packs, load_pack               # noqa: E402

OUT = ROOT / "research" / "llm_ablation.json"
TODAY = dt.date(2026, 9, 7)


async def run_provider(provider: str, packs: list[str]) -> dict:
    os.environ["HAANJI_PROVIDER_LLM"] = provider
    rows, latencies = [], []
    spec_started = spec_hits = llm_calls = fallbacks = 0
    tokens = {"input": 0, "output": 0}
    t_wall = time.perf_counter()
    for pid in packs:
        pack = load_pack(pid)
        for sc in scenarios_of(pack):
            backend, _ = open_backend(pack, "t_ablation", today=TODAY)
            ledger = Ledger(sqlite3.connect(":memory:"))
            registry = build_registry("t_ablation", backend, pack, ledger)
            session, report = await run_scenario(sc, pack=pack, backend=backend, registry=registry,
                                                 ledger=ledger, tenant_id="t_ablation",
                                                 config=EngineConfig())
            passed = report.outcome.value == sc.expect
            rows.append({"pack": pid, "name": sc.name, "expect": sc.expect,
                         "outcome": report.outcome.value, "passed": passed,
                         "turns": len(report.turns), "receipts": len(report.receipts),
                         "said": [t.said for t in report.turns]})
            latencies += report.latencies
            spec_started += report.speculation.get("started", 0)
            spec_hits += report.speculation.get("hits", 0)
            llm = session.llm
            llm_calls += getattr(llm, "calls", 0)
            fallbacks += getattr(llm, "fallbacks", 0)
            for k in tokens:
                tokens[k] += getattr(llm, "usage", {}).get(k, 0)
            print(f"  {'PASS' if passed else 'FAIL'}  {provider:6s} {pid:18s} {sc.name:28s} "
                  f"{report.outcome.value}", flush=True)
    return {
        "scenarios": rows, "passed": sum(r["passed"] for r in rows), "total": len(rows),
        "speculation": {"started": spec_started, "hits": spec_hits},
        "latency_p50_ms": round(statistics.median(latencies), 1) if latencies else 0.0,
        "latency_p95_ms": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 1) if latencies else 0.0,
        "llm_calls": llm_calls, "fallbacks": fallbacks, "tokens": tokens,
        "wall_s": round(time.perf_counter() - t_wall, 1),
        "model": os.environ.get("HAANJI_LLM_MODEL", "claude-opus-4-8") if provider == "claude" else None,
    }


def table(results: dict) -> str:
    cols = list(results)
    head = "| | " + " | ".join(cols) + " |\n|---|" + "---|" * len(cols) + "\n"
    def row(label, f):
        return f"| {label} | " + " | ".join(str(f(results[c])) for c in cols) + " |\n"
    body = row("scenarios reaching expected outcome", lambda r: f"{r['passed']}/{r['total']}")
    body += row("receipts written", lambda r: sum(s["receipts"] for s in r["scenarios"]))
    body += row("turn latency p50 (engine-side, ms)", lambda r: r["latency_p50_ms"])
    body += row("turn latency p95 (ms)", lambda r: r["latency_p95_ms"])
    body += row("speculation hits / started", lambda r: f"{r['speculation']['hits']}/{r['speculation']['started']}")
    body += row("model calls", lambda r: r["llm_calls"])
    body += row("fallbacks to the policy", lambda r: r["fallbacks"])
    body += row("tokens in / out", lambda r: f"{r['tokens']['input']}/{r['tokens']['output']}")
    body += row("wall clock (s)", lambda r: r["wall_s"])
    return head + body


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["mock", "claude"], default=None)
    ap.add_argument("--pack", default=None)
    ap.add_argument("--speed", type=float, default=40.0)
    args = ap.parse_args(argv)
    set_speed(args.speed)
    packs = [args.pack] if args.pack else list_packs()
    providers = [args.only] if args.only else ["mock", "claude"]
    results = json.loads(OUT.read_text()) if OUT.exists() else {}
    for provider in providers:
        if provider == "claude" and not os.environ.get("ANTHROPIC_API_KEY"):
            print("claude: skipped — no ANTHROPIC_API_KEY in the environment or engine/.env")
            continue
        print(f"\n== {provider} ==")
        results[provider] = asyncio.run(run_provider(provider, packs))
        results[provider]["ran_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if not results:
        return 1
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    print(f"\nwrote {OUT.relative_to(ROOT)}\n")
    print(table(results))
    return 0 if all(r["passed"] == r["total"] for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
