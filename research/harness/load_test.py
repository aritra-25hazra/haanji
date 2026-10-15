#!/usr/bin/env python3
"""How many callers one engine process answers at once, and what it costs them.

Starts a demo server (mock providers, rate limiting off), then runs N
simulated callers in parallel, each holding a full scripted conversation
through the web-call API with a short think time between turns, for N in a
ladder. Reports per-turn HTTP latency (what the browser or the telephony
bridge waits for), throughput and errors, and writes research/load_test.json
plus an SVG. Engine-side only: no speech vendor is on the path.

    python research/harness/load_test.py --levels 5,10,25,50 --calls-per-level 60
"""
from __future__ import annotations
import argparse
import asyncio
import datetime as dt
import json
import os
import random
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from haanji.scenario import scenarios_of            # noqa: E402
from haanji.vertical import list_packs, load_pack   # noqa: E402
from report_data import grouped_bars, BLUE, GREY, MARIGOLD  # noqa: E402

OUT = ROOT / "research" / "load_test.json"
FIG = ROOT / "research" / "figures" / "fig4_load.svg"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int, var_dir: Path) -> subprocess.Popen:
    env = {**os.environ, "HAANJI_RATE_LIMIT_PER_MIN": "0", "HAANJI_SCHEDULER": "0", "HAANJI_AUTH": "off",
           "HAANJI_VAR_DIR": str(var_dir), "HAANJI_PROVIDER_LLM": os.environ.get("HAANJI_PROVIDER_LLM", "mock")}
    return subprocess.Popen([sys.executable, "-m", "haanji.cli", "serve", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=str(ROOT / "engine"), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def wait_up(client: httpx.AsyncClient, deadline: float = 30.0) -> None:
    t0 = time.time()
    while time.time() - t0 < deadline:
        try:
            if (await client.get("/api/status")).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.3)
    raise RuntimeError("server did not come up")


async def one_call(client: httpx.AsyncClient, pack: str, lines: list[str], think_s: float,
                   latencies: list[float], errors: list[str]) -> str | None:
    try:
        r = await client.post("/api/sessions", json={"pack": pack, "phone": f"98{random.randint(10**7, 10**8 - 1)}"})
        r.raise_for_status()
        sid = r.json()["session_id"]
        outcome = None
        for line in lines:
            await asyncio.sleep(random.uniform(0, think_s))
            t0 = time.perf_counter()
            r = await client.post(f"/api/sessions/{sid}/utterance", json={"text": line})
            latencies.append((time.perf_counter() - t0) * 1000)
            if r.status_code != 200:
                errors.append(f"{r.status_code} {r.text[:80]}")
                break
            body = r.json()
            outcome = body.get("outcome")
            if body.get("end_call"):
                break
        r = await client.delete(f"/api/sessions/{sid}")
        if r.status_code == 200 and r.json().get("outcome"):
            outcome = r.json()["outcome"]
        return outcome
    except Exception as exc:                        # noqa: BLE001 - the error is the measurement
        errors.append(type(exc).__name__)
        return None


async def level(base: str, concurrency: int, calls: int, scripts: list[tuple[str, list[str], str]], think_s: float) -> dict:
    latencies: list[float] = []
    errors: list[str] = []
    outcomes: list[tuple[str | None, str]] = []
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(base_url=base, timeout=30.0, limits=httpx.Limits(max_connections=concurrency + 5)) as client:
        async def worker(i: int):
            pack, lines, expect = scripts[i % len(scripts)]
            async with sem:
                out = await one_call(client, pack, lines, think_s, latencies, errors)
                outcomes.append((out, expect))
        t0 = time.perf_counter()
        await asyncio.gather(*(worker(i) for i in range(calls)))
        wall = time.perf_counter() - t0
    lat = sorted(latencies)
    pct = lambda p: round(lat[min(len(lat) - 1, int(p * (len(lat) - 1)))], 1) if lat else 0.0
    ok = sum(1 for o, e in outcomes if o == e)
    from collections import Counter
    mismatches = Counter(f"{e}->{o}" for o, e in outcomes if o != e)
    return {"concurrency": concurrency, "calls": calls, "turns": len(lat), "errors": len(errors),
            "error_samples": errors[:5], "expected_outcome": ok, "outcome_rate": round(ok / max(len(outcomes), 1), 4),
            "mismatches": dict(mismatches.most_common(6)),
            "wall_s": round(wall, 1), "calls_per_min": round(calls / wall * 60, 1), "turns_per_s": round(len(lat) / wall, 1),
            "turn_http_ms": {"p50": pct(0.5), "p90": pct(0.9), "p95": pct(0.95), "max": round(lat[-1], 1) if lat else 0.0,
                             "mean": round(statistics.fmean(lat), 1) if lat else 0.0}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", default="5,10,25,50")
    ap.add_argument("--calls-per-level", type=int, default=60)
    ap.add_argument("--think", type=float, default=0.3, help="max seconds a caller pauses between turns")
    ap.add_argument("--base", default=None, help="an already running engine instead of starting one")
    args = ap.parse_args(argv)
    scripts = []
    for pid in list_packs():
        for sc in scenarios_of(load_pack(pid)):
            scripts.append((pid, [u.truth for u in sc.utterances], sc.expect))
    proc = None
    base = args.base
    var_dir = ROOT / "engine" / "var-load"
    if base is None:
        port = free_port()
        import shutil
        shutil.rmtree(var_dir, ignore_errors=True)       # a fresh calendar every run
        var_dir.mkdir(exist_ok=True)
        proc = start_server(port, var_dir)
        base = f"http://127.0.0.1:{port}"
    try:
        asyncio.run(_wait(base))
        results = []
        for c in [int(x) for x in args.levels.split(",")]:
            r = asyncio.run(level(base, c, max(args.calls_per_level, c), scripts, args.think))
            results.append(r)
            print(f"  {c:3d} concurrent  p50 {r['turn_http_ms']['p50']:6.1f} ms  p95 {r['turn_http_ms']['p95']:6.1f} ms  "
                  f"{r['calls_per_min']:6.1f} calls/min  errors {r['errors']}  outcomes {r['outcome_rate']:.0%}  "
                  f"mismatches {r['mismatches']}", flush=True)
    finally:
        cpu_s = None
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            import resource
            ru = resource.getrusage(resource.RUSAGE_CHILDREN)
            cpu_s = ru.ru_utime + ru.ru_stime
    total_calls = sum(r["calls"] for r in results)
    total_turns = sum(r["turns"] for r in results)
    # Engine compute per call, and what it costs on a small cloud VM
    # (Render starter, $7/month ≈ ₹600, one shared vCPU): the "infra" line of
    # the README's cost model, now measured instead of assumed.
    vm_inr_per_cpu_s = 600.0 / (30 * 24 * 3600)
    cost = None
    if cpu_s is not None and total_calls:
        cost = {"engine_cpu_s_total": round(cpu_s, 2), "engine_cpu_s_per_call": round(cpu_s / total_calls, 4),
                "engine_cpu_ms_per_turn": round(1000 * cpu_s / max(total_turns, 1), 2),
                "vm_inr_per_month": 600.0, "infra_inr_per_call": round(cpu_s / total_calls * vm_inr_per_cpu_s, 5),
                "note": "mock providers; speech vendors are billed per minute and dominate (see insights.py)"}
    payload = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "machine": os.uname().machine if hasattr(os, "uname") else "", "python": sys.version.split()[0],
               "providers": "mock (engine-side only)", "scripts": len(scripts), "levels": results, "cost": cost}
    OUT.write_text(json.dumps(payload, indent=1) + "\n")
    grouped_bars(FIG, "Turn latency over HTTP vs concurrent callers (one process, mock providers)",
                 [str(r["concurrency"]) for r in results],
                 [("p50", BLUE, [{"mean": r["turn_http_ms"]["p50"], "ci95": 0} for r in results]),
                  ("p95", MARIGOLD, [{"mean": r["turn_http_ms"]["p95"], "ci95": 0} for r in results]),
                  ("max", GREY, [{"mean": r["turn_http_ms"]["max"], "ci95": 0} for r in results])],
                 "milliseconds", fmt="{:.0f}")
    print("\n| concurrent callers | calls | turns | p50 (ms) | p95 (ms) | max (ms) | calls/min | errors | expected outcome |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        t = r["turn_http_ms"]
        print(f"| {r['concurrency']} | {r['calls']} | {r['turns']} | {t['p50']} | {t['p95']} | {t['max']} | {r['calls_per_min']} | {r['errors']} | {r['outcome_rate']:.0%} |")
    if cost:
        print(f"\nengine compute: {cost['engine_cpu_s_per_call']} CPU-s per call, {cost['engine_cpu_ms_per_turn']} CPU-ms per turn, "
              f"≈ ₹{cost['infra_inr_per_call']:.5f} per call on a ₹600/month VM")
    print(f"\nwrote {OUT.relative_to(ROOT)} and {FIG.relative_to(ROOT)}")
    return 0


async def _wait(base: str) -> None:
    async with httpx.AsyncClient(base_url=base, timeout=5.0) as client:
        await wait_up(client)


if __name__ == "__main__":
    sys.exit(main())
