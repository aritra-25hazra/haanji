#!/usr/bin/env python3
"""The numbers in research/REPORT.md, with confidence intervals.

``haanji.bench`` runs the four-way ablation once, with fixed seeds, and writes
``research/results.json``. This script runs the same experiments under K
independent seeds and reports mean and 95% confidence interval for every
headline quantity, so the report can say how much of a difference is noise.
It also draws the report's figures as plain SVG (no plotting library) into
``research/figures/``.

    python research/harness/report_data.py --seeds 5 --reps 3 --speed 90
"""
from __future__ import annotations
import argparse
import asyncio
import datetime as dt
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from haanji import bench                                   # noqa: E402
from haanji.clock import set_speed                        # noqa: E402
from haanji.vertical import list_packs, load_pack         # noqa: E402

OUT = ROOT / "research" / "report_data.json"
FIG = ROOT / "research" / "figures"

# Two-sided 95% t critical values by degrees of freedom; 1.96 beyond the table.
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 15: 2.131, 20: 2.086}


def ci(values: list[float]) -> dict[str, float]:
    n = len(values)
    mean = statistics.fmean(values)
    if n < 2:
        return {"mean": round(mean, 4), "sd": 0.0, "ci95": 0.0, "n": n, "min": round(min(values), 4), "max": round(max(values), 4)}
    sd = statistics.stdev(values)
    t = T95.get(n - 1, 1.96)
    return {"mean": round(mean, 4), "sd": round(sd, 4), "ci95": round(t * sd / math.sqrt(n), 4),
            "n": n, "min": round(min(values), 4), "max": round(max(values), 4)}


def fmt_pct(c: dict[str, float], digits: int = 1) -> str:
    return f"{c['mean']*100:.{digits}f} ± {c['ci95']*100:.{digits}f}"


def fmt_ms(c: dict[str, float]) -> str:
    return f"{c['mean']:.0f} ± {c['ci95']:.0f}"


# ------------------------------------------------------------------- runs
async def one_seed(seed: int, packs, reps: int, trials: int) -> dict[str, Any]:
    authored = {name: await bench.run_config(name, packs, reps, seed=seed) for name in bench.CONFIGS}
    transcripts = bench.transcript_experiment(packs, bench.NOISE_RATES, trials=trials, seed=seed)
    sweep = {}
    for rate in bench.NOISE_RATES:
        sweep[f"{rate:.2f}"] = {name: await bench.run_config(name, packs, reps, noise=rate, seed=seed)
                                for name in ("full", "no_bhasha")}
    return {"authored": authored, "transcripts": transcripts, "noise_sweep": sweep}


def aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    def col(path):
        vals = []
        for r in runs:
            v = r
            for k in path:
                v = v[k]
            vals.append(float(v))
        return ci(vals)

    agg: dict[str, Any] = {"authored": {}, "transcripts": {}, "noise_sweep": {}}
    for name in bench.CONFIGS:
        agg["authored"][name] = {
            "outcome_accuracy": col(("authored", name, "outcome_accuracy")),
            "entity_error_rate": col(("authored", name, "entity_error_rate")),
            "read_p50": col(("authored", name, "read_turn_latency_ms", "p50")),
            "read_p90": col(("authored", name, "read_turn_latency_ms", "p90")),
            "read_mean": col(("authored", name, "read_turn_latency_ms", "mean")),
            "tool_p90": col(("authored", name, "tool_turn_latency_ms", "p90")),
            "write_p50": col(("authored", name, "write_turn_latency_ms", "p50")),
            "write_p90": col(("authored", name, "write_turn_latency_ms", "p90")),
            "any_p50": col(("authored", name, "latency_ms", "p50")),
            "hit_rate": col(("authored", name, "speculation", "hit_rate")),
            "wasted": col(("authored", name, "speculation", "wasted")),
            "started": col(("authored", name, "speculation", "started")),
            "saved_ms_per_hit": col(("authored", name, "speculation", "saved_ms_per_hit")),
            "unconfirmed_writes": col(("authored", name, "unconfirmed_writes")),
            "harmful": col(("authored", name, "correction_quality", "harmful")),
        }
    for rate in bench.NOISE_RATES:
        key = f"{rate:.2f}"
        agg["transcripts"][key] = {
            "eer_off": col(("transcripts", key, "entity_error_rate_off")),
            "eer_on": col(("transcripts", key, "entity_error_rate_on")),
            "reduction_pct": col(("transcripts", key, "relative_reduction_pct")),
            "precision": col(("transcripts", key, "precision")),
            "harmful": col(("transcripts", key, "corrections", "harmful")),
            "beneficial": col(("transcripts", key, "corrections", "beneficial")),
            "neutral": col(("transcripts", key, "corrections", "neutral")),
            "median_ms": col(("transcripts", key, "median_correct_ms")),
            "sentences": runs[0]["transcripts"][key]["sentences"],
            "entities": runs[0]["transcripts"][key]["entities"],
        }
        agg["noise_sweep"][key] = {
            "eer_off": col(("noise_sweep", key, "no_bhasha", "entity_error_rate")),
            "eer_on": col(("noise_sweep", key, "full", "entity_error_rate")),
            "task_off": col(("noise_sweep", key, "no_bhasha", "outcome_accuracy")),
            "task_on": col(("noise_sweep", key, "full", "outcome_accuracy")),
            "harmful": col(("noise_sweep", key, "full", "correction_quality", "harmful")),
            "beneficial": col(("noise_sweep", key, "full", "correction_quality", "beneficial")),
            "neutral": col(("noise_sweep", key, "full", "correction_quality", "neutral")),
            "calls": runs[0]["noise_sweep"][key]["full"]["calls"],
        }
    # Per pack, at the middle noise rate, averaged over seeds.
    mid = f"{bench.NOISE_RATES[1]:.2f}"
    per_pack = {}
    for pid in runs[0]["noise_sweep"][mid]["full"]["per_pack"]:
        per_pack[pid] = {
            "task_on": col(("noise_sweep", mid, "full", "per_pack", pid, "outcome_accuracy")),
            "task_off": col(("noise_sweep", mid, "no_bhasha", "per_pack", pid, "outcome_accuracy")),
            "eer_on": col(("noise_sweep", mid, "full", "per_pack", pid, "entity_error_rate")),
            "eer_off": col(("noise_sweep", mid, "no_bhasha", "per_pack", pid, "entity_error_rate")),
            "calls": runs[0]["noise_sweep"][mid]["full"]["per_pack"][pid]["calls"],
        }
    agg["per_pack"] = per_pack
    return agg


# ----------------------------------------------------------------- tables
def tables(agg: dict[str, Any], ledger: dict[str, Any], meta: dict[str, Any]) -> str:
    out = []
    out.append(f"Seeds: {meta['seeds']} · reps per seed: {meta['reps']} · packs: {len(meta['packs'])} · "
               f"scenarios: {meta['scenarios']} · time scale: {meta['speed']}× · "
               f"values are mean ± 95% CI over seeds\n")
    out.append("**Table 1 — Transcript-level correction (Bhasha Bridge alone)**\n")
    out.append("| noise rate | sentences | entities | EER off (%) | EER on (%) | reduction (%) | precision (%) | harmful |")
    out.append("|---|---|---|---|---|---|---|---|")
    for k, r in agg["transcripts"].items():
        out.append(f"| {float(k):.0%} | {r['sentences']} | {r['entities']} | {fmt_pct(r['eer_off'])} | "
                   f"{fmt_pct(r['eer_on'], 2)} | {r['reduction_pct']['mean']:.1f} ± {r['reduction_pct']['ci95']:.1f} | "
                   f"{fmt_pct(r['precision'])} | {r['harmful']['mean']:.1f} |")
    out.append("\n**Table 2 — End-to-end calls under the same noise (Bhasha on vs off)**\n")
    out.append("| noise rate | calls | EER off (%) | EER on (%) | task success off (%) | task success on (%) | beneficial | neutral | harmful |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    for k, r in agg["noise_sweep"].items():
        out.append(f"| {float(k):.0%} | {r['calls']} | {fmt_pct(r['eer_off'])} | {fmt_pct(r['eer_on'])} | "
                   f"{fmt_pct(r['task_off'])} | {fmt_pct(r['task_on'])} | {r['beneficial']['mean']:.1f} | "
                   f"{r['neutral']['mean']:.1f} | {r['harmful']['mean']:.1f} |")
    out.append("\n**Table 3 — Per pack at 30% noise**\n")
    out.append("| pack | language | calls | task success off (%) | task success on (%) | EER off (%) | EER on (%) |")
    out.append("|---|---|---|---|---|---|---|")
    for pid, r in agg["per_pack"].items():
        out.append(f"| {pid} | {load_pack(pid).language} | {r['calls']} | {fmt_pct(r['task_off'])} | "
                   f"{fmt_pct(r['task_on'])} | {fmt_pct(r['eer_off'])} | {fmt_pct(r['eer_on'])} |")
    out.append("\n**Table 4 — Ablation on the authored scenarios (clean transcripts)**\n")
    out.append("| configuration | task success (%) | EER (%) | read-turn p50 (ms) | read-turn p90 (ms) | write-turn p90 (ms) | all-tool p90 (ms) | spec. hit rate (%) | wasted | unconfirmed writes |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for name, r in agg["authored"].items():
        out.append(f"| {name} | {fmt_pct(r['outcome_accuracy'])} | {fmt_pct(r['entity_error_rate'])} | "
                   f"{fmt_ms(r['read_p50'])} | {fmt_ms(r['read_p90'])} | {fmt_ms(r['write_p90'])} | {fmt_ms(r['tool_p90'])} | "
                   f"{fmt_pct(r['hit_rate'])} | {r['wasted']['mean']:.1f} | {r['unconfirmed_writes']['mean']:.0f} |")
    out.append("\n**Table 5 — Pramaan Ledger under attack (deterministic)**\n")
    out.append("| attack | attempted | detected |")
    out.append("|---|---|---|")
    for field, v in ledger["per_field"].items():
        out.append(f"| mutate `{field}` | {v['attempted']} | {v['detected']} |")
    out.append(f"| delete a receipt from the middle | 1 | {1 if ledger['deletion_detected'] else 0} |")
    out.append(f"| forge a receipt and re-hash it | 1 | {1 if ledger['forged_signature_rejected'] else 0} |")
    out.append(f"| write without a confirmation proof | 1 | {1 - ledger['unconfirmed_writes_accepted']} |")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- figures
INK, BLUE, MARIGOLD, GREY, PAPER = "#1d2433", "#1f4fd8", "#f2b705", "#8a8f99", "#ffffff"


def _svg(width: int, height: int, body: list[str], title: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif" font-size="12">'
            f'<title>{title}</title><rect width="100%" height="100%" fill="{PAPER}"/>'
            + "".join(body) + "</svg>")


def grouped_bars(path: Path, title: str, groups: list[str], series: list[tuple[str, str, list[dict]]],
                 ylabel: str, scale: float = 1.0, ymax: float | None = None, fmt: str = "{:.1f}") -> None:
    """Grouped bars with CI whiskers. ``series`` = [(label, colour, [ci dicts per group])]."""
    W, H, L, R, T, B = 640, 360, 70, 20, 50, 60
    pw, ph = W - L - R, H - T - B
    top = ymax or max((c["mean"] + c["ci95"]) * scale for _, _, cs in series for c in cs) * 1.15 or 1
    y = lambda v: T + ph - (v * scale / top) * ph
    body = [f'<text x="{L}" y="24" font-size="15" font-weight="700" fill="{INK}">{title}</text>']
    for i in range(6):
        v = top * i / 5
        body.append(f'<line x1="{L}" x2="{W-R}" y1="{y(v/scale):.1f}" y2="{y(v/scale):.1f}" stroke="#e6e8ee"/>')
        body.append(f'<text x="{L-8}" y="{y(v/scale)+4:.1f}" text-anchor="end" fill="{GREY}">{v:.0f}</text>')
    body.append(f'<text transform="translate(16 {T+ph/2:.0f}) rotate(-90)" text-anchor="middle" fill="{GREY}">{ylabel}</text>')
    gw = pw / len(groups)
    bw = gw * 0.7 / len(series)
    for gi, g in enumerate(groups):
        x0 = L + gi * gw + gw * 0.15
        body.append(f'<text x="{L + gi*gw + gw/2:.1f}" y="{H-B+20}" text-anchor="middle" fill="{INK}">{g}</text>')
        for si, (label, colour, cs) in enumerate(series):
            c = cs[gi]
            x = x0 + si * bw
            yb, yt = y(0), y(c["mean"])
            body.append(f'<rect x="{x:.1f}" y="{yt:.1f}" width="{bw-4:.1f}" height="{yb-yt:.1f}" fill="{colour}" rx="2"/>')
            if c["ci95"]:
                cx = x + (bw - 4) / 2
                body.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(c["mean"]-c["ci95"]):.1f}" y2="{y(c["mean"]+c["ci95"]):.1f}" stroke="{INK}" stroke-width="1.5"/>')
            top_y = min(yt, y(c["mean"] + c["ci95"])) - 6
            body.append(f'<text x="{x + (bw-4)/2:.1f}" y="{top_y:.1f}" text-anchor="middle" font-size="11" fill="{INK}">{fmt.format(c["mean"]*scale)}</text>')
    lx = L
    for label, colour, _ in series:
        body.append(f'<rect x="{lx}" y="{H-B+34}" width="12" height="12" fill="{colour}" rx="2"/>')
        body.append(f'<text x="{lx+16}" y="{H-B+44}" fill="{INK}">{label}</text>')
        lx += 16 + 8 * len(label) + 24
    path.write_text(_svg(W, H, body, title), encoding="utf-8")


def figures(agg: dict[str, Any]) -> list[str]:
    FIG.mkdir(parents=True, exist_ok=True)
    rates = [f"{float(k):.0%}" for k in agg["transcripts"]]
    tx = list(agg["transcripts"].values())
    grouped_bars(FIG / "fig1_eer.svg", "Entity error rate, Bhasha Bridge off vs on (transcript level)",
                 rates, [("off", GREY, [r["eer_off"] for r in tx]), ("on", BLUE, [r["eer_on"] for r in tx])],
                 "entity error rate (%)", scale=100)
    sw = list(agg["noise_sweep"].values())
    grouped_bars(FIG / "fig2_task.svg", "Task success in end-to-end calls, Bhasha Bridge off vs on",
                 rates, [("off", GREY, [r["task_off"] for r in sw]), ("on", MARIGOLD, [r["task_on"] for r in sw])],
                 "calls reaching the expected outcome (%)", scale=100, ymax=115)
    a = agg["authored"]
    grouped_bars(FIG / "fig3_latency.svg", "Turn latency with and without speculation (nominal ms)",
                 ["read p50", "read p90", "write p90"],
                 [("no speculation", GREY, [a["no_speculation"]["read_p50"], a["no_speculation"]["read_p90"], a["no_speculation"]["write_p90"]]),
                  ("speculation", BLUE, [a["full"]["read_p50"], a["full"]["read_p90"], a["full"]["write_p90"]])],
                 "milliseconds", fmt="{:.0f}")
    return ["fig1_eer.svg", "fig2_task.svg", "fig3_latency.svg"]


# ------------------------------------------------------------------ driver
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--speed", type=float, default=90.0)
    ap.add_argument("--figures-only", action="store_true", help="redraw the figures from report_data.json")
    args = ap.parse_args(argv)
    if args.figures_only:
        agg = json.loads(OUT.read_text(encoding="utf-8"))["aggregate"]
        print("redrew", ", ".join(figures(agg)))
        return 0
    set_speed(args.speed)
    packs = [load_pack(p) for p in list_packs()]
    started = time.time()
    runs = []
    for seed in range(args.seeds):
        t0 = time.time()
        runs.append(asyncio.run(one_seed(seed, packs, args.reps, trials=max(6, args.reps * 3))))
        print(f"seed {seed}: {time.time() - t0:.0f}s", flush=True)
    ledger = bench.ledger_experiment(packs[0])
    meta = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "seeds": args.seeds, "reps": args.reps, "speed": args.speed,
            "packs": [p.pack_id for p in packs], "scenarios": sum(len(p.scenarios) for p in packs),
            "wall_seconds": round(time.time() - started, 1)}
    agg = aggregate(runs)
    figs = figures(agg)
    md = tables(agg, ledger, meta)
    OUT.write_text(json.dumps({"meta": meta, "aggregate": agg, "ledger": ledger, "figures": figs,
                               "runs": runs}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (ROOT / "research" / "report_tables.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"wrote {OUT.relative_to(ROOT)}, research/report_tables.md and {', '.join(figs)} "
          f"in {meta['wall_seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
