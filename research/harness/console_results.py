#!/usr/bin/env python3
"""Write console/src/results.json (and the same file as
engine/haanji/web/results.json, which the engine serves and its help
assistant quotes): the measured numbers the console's "How it works" page shows, copied (never recomputed or rounded differently)
from research/results.json, the file the benchmark writes. When the benchmark
is re-run, this file must be regenerated, or a test fails.

    python research/harness/console_results.py            # rewrite the file
    python research/harness/console_results.py --check    # exit 1 when it is stale
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "research" / "results.json"
OUT = ROOT / "console" / "src" / "results.json"
OUTS = [OUT, ROOT / "engine" / "haanji" / "web" / "results.json"]

HEADLINE = ["noise_rate", "sentences_scored", "entities_scored", "entity_error_rate_without_bhasha",
            "entity_error_rate_with_bhasha", "entity_error_reduction_pct", "correction_precision",
            "harmful_corrections_transcript", "bhasha_median_ms", "task_success_without_bhasha",
            "task_success_with_bhasha", "read_turn_p50_without_speculation", "read_turn_p50_with_speculation",
            "read_turn_p50_reduction_pct", "read_turn_p90_without_speculation", "read_turn_p90_with_speculation",
            "write_turn_p90_without_speculation", "write_turn_p90_with_speculation", "speculation_hit_rate",
            "speculations_started", "saved_ms_per_hit", "outcome_accuracy_clean"]
LEDGER = ["chain_length", "clean_chain_valid", "mutations_attempted", "mutations_detected", "detection_rate",
          "unconfirmed_writes_accepted"]


def render() -> str:
    r = json.loads(SRC.read_text(encoding="utf-8"))
    h, led = r["headline"], r["ledger"]
    out = {
        "generated_from": "research/results.json by research/harness/console_results.py",
        "how_to_reproduce": f"cd engine && python -m haanji.bench --reps {r['reps']} --speed {r['time_scale']:g}",
        "measured_at": r["generated_at"], "reps": r["reps"], "packs": len(r["packs"]), "scenarios": r["scenarios"],
        "headline": {k: h[k] for k in HEADLINE if k in h},
        "ledger": {k: led[k] for k in LEDGER if k in led},
        "configs": {name: {"calls": c["calls"], "outcome_accuracy": c["outcome_accuracy"],
                           "unconfirmed_writes": c["unconfirmed_writes"]} for name, c in r["authored"].items()},
        "noise": [{"noise": float(k), "sentences": v["sentences"], "error_without": v["entity_error_rate_off"],
                   "error_with": v["entity_error_rate_on"]} for k, v in sorted(r["transcripts"].items(), key=lambda kv: float(kv[0]))],
    }
    return json.dumps(out, ensure_ascii=False, indent=1) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 instead of writing when the file is stale")
    args = ap.parse_args(argv)
    text = render()
    stale = 0
    for out in OUTS:
        current = out.read_text(encoding="utf-8") if out.exists() else ""
        if text == current:
            print(f"{out.relative_to(ROOT)} is current")
        elif args.check:
            print(f"stale: {out.relative_to(ROOT)} — run `python research/harness/console_results.py`")
            stale = 1
        else:
            out.write_text(text, encoding="utf-8")
            print(f"wrote {out.relative_to(ROOT)}")
    return stale


if __name__ == "__main__":
    sys.exit(main())
