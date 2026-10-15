#!/usr/bin/env python3
"""Score (heard, truth) pairs from a real recogniser with the Bhasha Bridge
off and on, and write research/real_asr.json plus a Markdown table.

    python research/collect/evaluate.py --pairs research/collect/data/synthetic/pairs.jsonl
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from haanji.collect import load_pairs, real_pairs_experiment   # noqa: E402
from haanji.vertical import list_packs, load_pack              # noqa: E402


def row(label: str, r: dict) -> str:
    c = r["corrections"]
    return (f"| {label} | {r['utterances']} | {r['entities']} | {r['word_error_rate']*100:.1f} | "
            f"{r['entity_error_rate_off']*100:.1f} | {r['entity_error_rate_on']*100:.1f} | "
            f"{r['relative_reduction_pct']:.1f} | {r['precision']*100:.1f} | {c['beneficial']} | {c['neutral']} | {c['harmful']} |")


def table(res: dict) -> str:
    head = ("| slice | utterances | entities | WER (%) | EER off (%) | EER on (%) | reduction (%) | precision (%) | beneficial | neutral | harmful |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|\n")
    body = row("**all**", res["overall"]) + "\n"
    body += "\n".join(row(k, v) for k, v in res["per_pack"].items()) + "\n"
    body += "\n".join(row(k, v) for k, v in res["per_speaker"].items()) + "\n"
    return head + body


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", required=True, nargs="+")
    ap.add_argument("--out", default=str(ROOT / "research" / "real_asr.json"))
    ap.add_argument("--label", default=None, help="what this set is, e.g. 'synthetic speech, faster-whisper small'")
    args = ap.parse_args(argv)
    pairs = [p for path in args.pairs for p in load_pairs(path)]
    packs = [load_pack(p) for p in list_packs()]
    res = real_pairs_experiment(packs, pairs)
    recognisers = sorted({p.recogniser for p in pairs if p.recogniser})
    synthetic = all(getattr(p, "speaker", "").startswith("say:") for p in pairs)
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "label": args.label or ("synthetic speech through a real recogniser" if synthetic else "recorded speech"),
        "sources": args.pairs, "recognisers": recognisers, "synthetic_speech": synthetic,
        "pairs": len(pairs), **res,
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{payload['label']} · recogniser {', '.join(recognisers) or '?'} · {len(pairs)} pairs\n")
    print(table(res))
    print("\nexamples:")
    for ex in res["examples"][:8]:
        print(f"  truth   : {ex['truth']}\n  heard   : {ex['heard']}\n  bridged : {ex['corrected']}   "
              f"{ex['corrections']}\n")
    print(f"wrote {Path(args.out).relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
