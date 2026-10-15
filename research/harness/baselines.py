#!/usr/bin/env python3
"""Bhasha Bridge's key against the classics, and against itself minus one rule.

Same lexicon, same two-condition rule, same edit-distance bound; only the
bucketing function changes (haanji/bhasha/baselines.py). Three experiments:

  1. transcript level, synthetic noise at 15/30/45 %, every keyer;
  2. the real-recogniser pilot pairs, every keyer;
  3. per-rule ablation of our key at 30 % noise.

McNemar's test on per-sentence outcomes says whether a difference between
two keyers is more than noise. Writes research/baselines.json, a Markdown
table and a figure.

    python research/harness/baselines.py
"""
from __future__ import annotations
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from haanji import bench                                              # noqa: E402
from haanji.bhasha.baselines import BASELINES, RULE_LABELS, key_without_rule   # noqa: E402
from haanji.bhasha.phonetics import RULES, use_keyer                  # noqa: E402
from haanji.collect import load_pairs, real_pairs_experiment          # noqa: E402
from haanji.vertical import list_packs, load_pack                     # noqa: E402
import stats                                                          # noqa: E402
from report_data import grouped_bars, BLUE, GREY, MARIGOLD            # noqa: E402

OUT = ROOT / "research" / "baselines.json"
FIG = ROOT / "research" / "figures" / "fig5_baselines.svg"
PAIRS = ROOT / "research" / "collect" / "data" / "synthetic" / "pairs.jsonl"
RATES = [0.15, 0.30, 0.45]


def synthetic(packs, trials: int) -> dict:
    out = {}
    for name, keyer in BASELINES.items():
        with use_keyer(name, keyer):
            out[name] = bench.transcript_experiment(packs, RATES, trials=trials, seed=0, detail=True)
        r = out[name]["0.30"]
        print(f"  {name:20s} 30%: EER {r['entity_error_rate_off']*100:5.1f} -> {r['entity_error_rate_on']*100:5.2f}  "
              f"precision {r['precision']*100:5.1f}  harmful {r['corrections']['harmful']}", flush=True)
    return out


def real(packs, pairs) -> dict:
    out = {}
    for name, keyer in BASELINES.items():
        with use_keyer(name, keyer):
            out[name] = real_pairs_experiment(packs, pairs)["overall"]
    return out


def per_rule(packs, trials: int) -> list[dict]:
    rows = []
    with use_keyer("full", BASELINES["Bhasha (ours)"]):
        full = bench.transcript_experiment(packs, [0.30], trials=trials, seed=0)["0.30"]
    for i, (pattern, repl) in enumerate(RULES):
        with use_keyer(f"minus_{i}", key_without_rule(i)):
            r = bench.transcript_experiment(packs, [0.30], trials=trials, seed=0)["0.30"]
        rows.append({"rule": i, "label": RULE_LABELS[i] if i < len(RULE_LABELS) else pattern, "pattern": pattern,
                     "replacement": repl, "eer_on": r["entity_error_rate_on"], "precision": r["precision"],
                     "harmful": r["corrections"]["harmful"],
                     "delta_eer_points": round((r["entity_error_rate_on"] - full["entity_error_rate_on"]) * 100, 3)})
        print(f"  without rule {i:2d} ({rows[-1]['label']}): EER on {r['entity_error_rate_on']*100:.2f}% "
              f"({rows[-1]['delta_eer_points']:+.2f} pts)", flush=True)
    return rows


def mcnemar_vs_ours(syn: dict, rate: str = "0.30") -> dict:
    ours = syn["Bhasha (ours)"][rate]
    out = {}
    for name, res in syn.items():
        if name == "Bhasha (ours)":
            continue
        a, b = res[rate]["wrong_on"], ours["wrong_on"]
        bb = sum(1 for x, y in zip(a, b) if x and not y)       # baseline wrong, ours right
        cc = sum(1 for x, y in zip(a, b) if not x and y)       # baseline right, ours wrong
        out[name] = stats.mcnemar(bb, cc)
    off, on = ours["wrong_off"], ours["wrong_on"]
    out["off vs ours"] = stats.mcnemar(sum(1 for x, y in zip(off, on) if x and not y),
                                       sum(1 for x, y in zip(off, on) if not x and y))
    return out


def tables(syn, realr, rules, mc) -> str:
    out = ["**Table 8 — Keyers on synthetic noise (transcript level, 2,097 sentences per rate)**\n",
           "| keyer | EER on @15% | EER on @30% | EER on @45% | precision @30% | harmful @30% | McNemar vs ours @30% |",
           "|---|---|---|---|---|---|---|"]
    for name, res in syn.items():
        m = mc.get(name)
        p = f"b={m['b']}, c={m['c']}, p {stats.fmt_p(m['p'])}" if m else "—"
        out.append(f"| {name} | {res['0.15']['entity_error_rate_on']*100:.2f}% | {res['0.30']['entity_error_rate_on']*100:.2f}% | "
                   f"{res['0.45']['entity_error_rate_on']*100:.2f}% | {res['0.30']['precision']*100:.1f}% | "
                   f"{res['0.30']['corrections']['harmful']} | {p} |")
    off = syn["Bhasha (ours)"]["0.30"]["entity_error_rate_off"] * 100
    out.append(f"\nEntity error with no correction at 30%: {off:.1f}% (identical for every keyer). "
               f"Bridge off vs ours: b={mc['off vs ours']['b']}, c={mc['off vs ours']['c']}, p {stats.fmt_p(mc['off vs ours']['p'])}.\n")
    if realr:
        out += ["**Table 9 — Keyers on the real-recogniser pilot (300 utterances, faster-whisper small)**\n",
                "| keyer | EER off | EER on | reduction | precision | beneficial | neutral | harmful |", "|---|---|---|---|---|---|---|---|"]
        for name, r in realr.items():
            c = r["corrections"]
            out.append(f"| {name} | {r['entity_error_rate_off']*100:.1f}% | {r['entity_error_rate_on']*100:.1f}% | "
                       f"{r['relative_reduction_pct']:.1f}% | {r['precision']*100:.1f}% | {c['beneficial']} | {c['neutral']} | {c['harmful']} |")
        out.append("")
    out += ["**Table 10 — Per-rule ablation of the Bhasha key (30% noise; higher delta = the rule matters more)**\n",
            "| # | rule | EER on without it | Δ vs full (points) | precision | harmful |", "|---|---|---|---|---|---|"]
    for r in sorted(rules, key=lambda x: -x["delta_eer_points"]):
        out.append(f"| {r['rule']} | {r['label']} | {r['eer_on']*100:.2f}% | {r['delta_eer_points']:+.2f} | {r['precision']*100:.1f}% | {r['harmful']} |")
    return "\n".join(out) + "\n"


def main() -> int:
    packs = [load_pack(p) for p in list_packs()]
    print("synthetic:")
    syn = synthetic(packs, trials=9)
    realr = {}
    if PAIRS.exists():
        print("real pairs:")
        realr = real(packs, load_pairs(PAIRS))
        for k, v in realr.items():
            print(f"  {k:20s} EER {v['entity_error_rate_off']*100:.1f} -> {v['entity_error_rate_on']*100:.1f}  harmful {v['corrections']['harmful']}")
    print("per-rule ablation:")
    rules = per_rule(packs, trials=9)
    mc = mcnemar_vs_ours(syn)
    slim = {k: {r: {kk: vv for kk, vv in res.items() if kk not in ("wrong_off", "wrong_on")} for r, res in v.items()} for k, v in syn.items()}
    payload = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "trials": 9,
               "synthetic": slim, "real": realr, "per_rule": rules, "mcnemar_30": mc}
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    md = tables(syn, realr, rules, mc)
    (ROOT / "research" / "baselines_tables.md").write_text(md)
    names = list(syn)
    grouped_bars(FIG, "Entity error after correction at 30% noise, by keyer", names,
                 [("EER on (%)", BLUE, [{"mean": syn[n]["0.30"]["entity_error_rate_on"], "ci95": 0} for n in names]),
                  ("harmful corrections (count ÷ 10)", MARIGOLD, [{"mean": syn[n]["0.30"]["corrections"]["harmful"] / 1000, "ci95": 0} for n in names])],
                 "percent / count÷10", scale=100, fmt="{:.1f}")
    print("\n" + md)
    print(f"wrote {OUT.relative_to(ROOT)}, research/baselines_tables.md, {FIG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
