#!/usr/bin/env python3
"""The synthetic experiment under noise learned from real recognisers.

Two learned models: one fitted on the Gram Vaani telephone-Hindi pairs
(research/collect/gramvaani.py) and one on the synthetic-speech pilot
(research/collect/data/synthetic/pairs.jsonl). Each replays its own word
and character confusions, drops and merges over the benchmark corpus at the
recogniser's native rate and at the three standard rates, with the bridge
off and on. Writes research/learned_noise.json and a Markdown table.

    python research/harness/learned_noise.py
"""
from __future__ import annotations
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from haanji import bench                                   # noqa: E402
from haanji.collect import load_pairs                      # noqa: E402
from haanji.corrupt_learned import LearnedCorruption       # noqa: E402
from haanji.vertical import list_packs, load_pack          # noqa: E402

OUT = ROOT / "research" / "learned_noise.json"
SOURCES = {
    "Gram Vaani (real Hindi telephone speech, Whisper hi)": ROOT / "research" / "collect" / "data" / "gramvaani" / "learned.json",
    "pilot (synthetic Indian-English speech, Whisper en)": ROOT / "research" / "collect" / "data" / "synthetic" / "pairs.jsonl",
}


def model_for(path: Path) -> LearnedCorruption:
    if path.suffix == ".json":
        return LearnedCorruption.load(path)
    return LearnedCorruption().fit((p.truth, p.heard) for p in load_pairs(path))


def main() -> int:
    packs = [load_pack(p) for p in list_packs()]
    results = {}
    for label, path in SOURCES.items():
        if not path.exists():
            print(f"skip {label}: {path.relative_to(ROOT)} missing")
            continue
        m = model_for(path)
        native = m.rates()["substitution_rate"]
        rates = sorted({round(native, 2), 0.15, 0.30, 0.45})
        res = bench.transcript_experiment(packs, rates, trials=9, seed=0, corruptor=m.corrupt)
        results[label] = {"learned": m.rates(), "native_rate": round(native, 3), "rates": res}
        print(f"\n{label}: native substitution rate {native:.1%}, drops {m.rates()['drop_rate']:.1%}, merges {m.rates()['merge_rate']:.1%}")
        for r, v in res.items():
            print(f"  rate {r}: EER {v['entity_error_rate_off']*100:5.1f}% -> {v['entity_error_rate_on']*100:5.2f}%  "
                  f"precision {v['precision']*100:5.1f}%  harmful {v['corrections']['harmful']}")
    if not results:
        return 1
    OUT.write_text(json.dumps({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "results": results},
                              indent=1, ensure_ascii=False) + "\n")
    lines = ["**Table 11 — The correction layer under noise learned from real recognisers (transcript level)**", "",
             "| noise source | rate | EER off | EER on | reduction | precision | harmful |", "|---|---|---|---|---|---|---|"]
    for label, r in results.items():
        for rate, v in r["rates"].items():
            tag = " (native)" if abs(float(rate) - r["native_rate"]) < 0.006 else ""
            lines.append(f"| {label} | {float(rate):.0%}{tag} | {v['entity_error_rate_off']*100:.1f}% | {v['entity_error_rate_on']*100:.2f}% | "
                         f"{v['relative_reduction_pct']:.1f}% | {v['precision']*100:.1f}% | {v['corrections']['harmful']} |")
    (ROOT / "research" / "learned_noise_tables.md").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
