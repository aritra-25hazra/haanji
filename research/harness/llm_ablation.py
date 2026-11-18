#!/usr/bin/env python3
"""Deterministic policy versus a hosted model, on the same packaged scenarios (44 over 10 packs).

Runs every packaged scenario under the ``mock`` adapter and, when an API key
is configured, under ``claude``; writes ``research/llm_ablation.json`` and
prints a Markdown table. The point is not that one wins: it is that the
outcomes, the receipts and the guarantees are the same whichever one talks,
and that the cost of the model (latency, tokens, fallbacks, lost speculation)
is measured rather than guessed.

    python research/harness/llm_ablation.py --only mock                         # free
    python research/harness/llm_ablation.py --only claude --pack dental_clinic  # prints the estimate, stops
    python research/harness/llm_ablation.py --only claude --pack dental_clinic --yes   # a paid pilot
    python research/harness/llm_ablation.py --only claude --yes                 # the paid full run
    python research/harness/llm_ablation.py --only gemini --pack dental_clinic --yes   # Gemini (free tier: no charge)

A paid run never starts without --yes; before it, the script prints how many
model calls to expect and what they may cost at the model's list price. A run
on one pack is stored under "claude:<pack>" so it never replaces a full run.
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
        "model": (os.environ.get("HAANJI_LLM_MODEL", "claude-opus-4-8") if provider == "claude" else
                  os.environ.get("HAANJI_GEMINI_DIALOGUE_MODEL", "gemini-3.5-flash-lite") if provider == "gemini" else None),
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


# List prices per million tokens (input, output), USD; check the provider's
# pricing page before a large run. Unknown models get no estimate.
PRICES = {"claude-opus-4-8": (5.0, 25.0), "claude-sonnet-4-6": (3.0, 15.0), "claude-haiku-4-5": (1.0, 5.0)}
USD_INR = 85.0


def estimate(packs: list[str], model: str) -> dict:
    """How many model calls a run makes, and a cost range, from the scenarios
    and the measured size of the system prompt and tool list. A range, not a
    measurement: the real tokens are counted during the run and written out."""
    from haanji.adapters.claude import build_tools
    from haanji.adapters.prompt import build_system_prompt
    turns, prefix_chars = 0, []
    for pid in packs:
        pack = load_pack(pid)
        backend, _ = open_backend(pack, "t_estimate", today=TODAY)
        registry = build_registry("t_estimate", backend, pack, Ledger(sqlite3.connect(":memory:")))
        prefix_chars.append(len(build_system_prompt(pack, today=TODAY)) + len(json.dumps(build_tools(registry))))
        turns += sum(len(sc.utterances) for sc in scenarios_of(pack))
    prefix = statistics.fmean(prefix_chars) / 3.3               # ≈ tokens for Hinglish and JSON
    low_calls, high_calls = turns, 2 * turns                    # one call per turn, two with a tool round
    low_in, high_in = low_calls * (prefix + 300), high_calls * (prefix + 1200)
    low_out, high_out = low_calls * 120, high_calls * 450       # replies, plus a little adaptive thinking
    price = PRICES.get(model)
    out = {"turns": turns, "calls": [low_calls, high_calls], "input_tokens": [int(low_in), int(high_in)],
           "output_tokens": [low_out, high_out], "model": model}
    if price:
        usd = [(low_in * price[0] + low_out * price[1]) / 1e6, (high_in * price[0] + high_out * price[1]) / 1e6]
        out["usd"] = [round(usd[0], 2), round(usd[1], 2)]
        out["inr"] = [round(usd[0] * USD_INR), round(usd[1] * USD_INR)]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["mock", "claude", "gemini"], default=None)
    ap.add_argument("--pack", default=None)
    ap.add_argument("--speed", type=float, default=40.0)
    ap.add_argument("--yes", action="store_true", help="run the paid provider after printing the estimate")
    args = ap.parse_args(argv)
    set_speed(args.speed)
    packs = [args.pack] if args.pack else list_packs()
    providers = [args.only] if args.only else ["mock", "claude", "gemini"]
    results = json.loads(OUT.read_text()) if OUT.exists() else {}
    for provider in providers:
        if provider == "gemini":
            model = os.environ.get("HAANJI_GEMINI_DIALOGUE_MODEL", "gemini-3.5-flash-lite")
            est = estimate(packs, model)
            os.environ.setdefault("HAANJI_GEMINI_RPM", "10")           # a free-tier key's pace
            print(f"gemini ({model}): {est['turns']} caller turns -> about {est['calls'][0]}–{est['calls'][1]} model calls "
                  f"at {os.environ['HAANJI_GEMINI_RPM']}/min (≈ {est['calls'][1] / float(os.environ['HAANJI_GEMINI_RPM']):.0f} min at most). "
                  "A free-tier key is not charged; a paid key is billed at Google's price for this model.")
            if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
                print("gemini: skipped — no GEMINI_API_KEY in the environment or engine/.env")
                continue
            if not args.yes:
                print("gemini: not run — add --yes to start it")
                continue
        if provider == "claude":
            model = os.environ.get("HAANJI_LLM_MODEL", "claude-opus-4-8")
            est = estimate(packs, model)
            cost = (f"≈ ${est['usd'][0]}–{est['usd'][1]} (≈ ₹{est['inr'][0]}–{est['inr'][1]}) at list price"
                    if "usd" in est else "no price known for this model")
            print(f"claude ({model}): {est['turns']} caller turns -> about {est['calls'][0]}–{est['calls'][1]} model calls, "
                  f"{est['input_tokens'][0]:,}–{est['input_tokens'][1]:,} input tokens; {cost}. An estimate, not a measurement.")
            if not os.environ.get("ANTHROPIC_API_KEY"):
                print("claude: skipped — no ANTHROPIC_API_KEY in the environment or engine/.env")
                continue
            if not args.yes:
                print("claude: not run — add --yes to spend this")
                continue
        key = f"{provider}:{args.pack}" if args.pack else provider
        print(f"\n== {key} ==")
        results[key] = asyncio.run(run_provider(provider, packs))
        results[key]["ran_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if not results or not any(k in results for k in [f"{p}:{args.pack}" if args.pack else p for p in providers]):
        return 1
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    print(f"\nwrote {OUT.relative_to(ROOT)}\n")
    print(table(results))
    return 0 if all(r["passed"] == r["total"] for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
