#!/usr/bin/env python3
"""Learn the confidence gate per recogniser, and show what it changes.

For every (heard, truth) set with per-word confidences — the synthetic
pilot (plain and biased) and the Gram Vaani telephone sample — label each
heard word right or wrong by alignment, draw the ROC of "treat as unsure
below t", pick the threshold that maximises Youden's J, and write
research/calibration.json. Then re-score the pilot with the learned
threshold instead of 0.85 so the effect on entity error, precision and
harmful corrections is a measured number, not a hope.

    python research/harness/calibrate.py
"""
from __future__ import annotations
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from haanji.bhasha.calibration import fit_threshold          # noqa: E402
from haanji.collect import load_pairs, real_pairs_experiment  # noqa: E402
from haanji.config import BhashaConfig                         # noqa: E402
from haanji.vertical import list_packs, load_pack              # noqa: E402

OUT = ROOT / "research" / "calibration.json"
SETS = {
    "faster-whisper:small:en": ROOT / "research" / "collect" / "data" / "synthetic" / "pairs.jsonl",
    "faster-whisper:small:en:biased": ROOT / "research" / "collect" / "data" / "synthetic" / "pairs_biased.jsonl",
    "faster-whisper:small:hi": ROOT / "research" / "collect" / "data" / "gramvaani" / "pairs.jsonl",
}


def main() -> int:
    packs = [load_pack(p) for p in list_packs()]
    recognisers = {}
    for name, path in SETS.items():
        if not path.exists():
            print(f"skip {name}: {path.relative_to(ROOT)} missing")
            continue
        pairs = load_pairs(path)
        fit = fit_threshold(pairs)
        recognisers[name] = {k: v for k, v in fit.items() if k != "curve"}
        recognisers[name]["curve"] = fit["curve"][::max(1, len(fit["curve"]) // 25)]   # a sketch is enough
        print(f"{name:32s} tokens {fit['tokens']:5d}  wrong {fit['wrong_rate']:.0%}  AUC {fit['auc']:.2f}  "
              f"threshold {fit['threshold']:.2f}  (TPR {fit['tpr']:.2f}, FPR {fit['fpr']:.2f})")
    # Effect on the pilot: 0.85 versus the learned threshold, same bridge, same data.
    effects = {}
    for name in ("faster-whisper:small:en", "faster-whisper:small:en:biased"):
        path = SETS[name]
        if not path.exists() or name not in recognisers:
            continue
        pairs = load_pairs(path)
        rows = {}
        for label, thr in (("0.85 (default)", 0.85), (f"{recognisers[name]['threshold']:.2f} (learned)", recognisers[name]["threshold"])):
            r = real_pairs_experiment(packs, pairs, BhashaConfig(enabled=True, conf_high=thr))["overall"]
            rows[label] = {k: r[k] for k in ("entity_error_rate_off", "entity_error_rate_on", "relative_reduction_pct", "precision", "corrections")}
            print(f"  {name:32s} gate {label:16s} EER {r['entity_error_rate_off']*100:.1f} -> {r['entity_error_rate_on']*100:.1f}  "
                  f"precision {r['precision']*100:.0f}%  harmful {r['corrections']['harmful']}")
        effects[name] = rows
    # The gate that matters is the one that minimises entity error downstream
    # with no harmful corrections — not the one that best classifies words.
    sweeps = {}
    # Gram Vaani speech carries no pack entity, so only the pilot sets are swept.
    for name in ("faster-whisper:small:en", "faster-whisper:small:en:biased"):
        path = SETS[name]
        if not path.exists():
            continue
        pairs = load_pairs(path)
        rows = []
        for thr in (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.01):
            r = real_pairs_experiment(packs, pairs, BhashaConfig(enabled=True, conf_high=thr))["overall"]
            rows.append({"threshold": thr, "eer_on": r["entity_error_rate_on"], "precision": r["precision"],
                         "harmful": r["corrections"]["harmful"], "beneficial": r["corrections"]["beneficial"]})
            print(f"  sweep {name:28s} gate {thr:4.2f}  EER on {r['entity_error_rate_on']*100:5.1f}  "
                  f"precision {r['precision']*100:3.0f}%  beneficial {r['corrections']['beneficial']:2d}  harmful {r['corrections']['harmful']}")
        sweeps[name] = rows
    OUT.write_text(json.dumps({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                               "downstream_sweep": sweeps,
                               "method": "Youden's J on the ROC of 'confidence < t' against alignment-labelled wrong words",
                               "recognisers": recognisers, "effect_on_pilot": effects}, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
