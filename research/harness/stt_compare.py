#!/usr/bin/env python3
"""Indic recognisers on the same recordings, before and after Bhasha repair (REPORT §4.12).

For every engine ``research/collect/engines.py`` knows, this looks for the
pairs file ``transcribe.py --engine <name>`` writes next to the manifest and,
when it is there, scores it with exactly the measurement the pilot used
(``haanji.collect.real_pairs_experiment``: word error, entity error with the
bridge off and on, correction precision, harmful corrections). Engines with no
output are reported, not invented: the JSON says ``"status": "not run: key
needed"`` (or which keys) for a vendor whose key is absent, and ``"not run: no
output"`` for one that could run but has not.

    python research/harness/stt_compare.py                       # synthetic pilot set
    python research/harness/stt_compare.py --data research/collect/data/volunteers

Writes ``research/stt_compare.json`` and ``research/stt_compare_tables.md``.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "research" / "collect"))

import engines                                                      # noqa: E402
from haanji.collect import load_pairs, real_pairs_experiment        # noqa: E402
from haanji.vertical import list_packs, load_pack                   # noqa: E402

OUT = ROOT / "research" / "stt_compare.json"
TABLES = ROOT / "research" / "stt_compare_tables.md"
DATA = ROOT / "research" / "collect" / "data" / "synthetic"

# Rows of the comparison: an engine, and the pairs file its run writes. The
# two whisper rows are the pilot's own output (§4.5 and the biased run of §4.11).
RUNS: list[tuple[str, str, str]] = [
    ("whisper", "faster-whisper small, English decoding, no hints", "pairs.jsonl"),
    ("whisper_biased", "faster-whisper small, pack vocabulary as the prompt", "pairs_biased.jsonl"),
    ("sarvam", "Sarvam Saarika, hi-IN (Devanagari, romanised)", "pairs_sarvam.jsonl"),
    ("bhashini", "Bhashini / ULCA ASR, hi (Devanagari, romanised)", "pairs_bhashini.jsonl"),
    ("deepgram", "Deepgram nova-2, hi-Latn", "pairs_deepgram.jsonl"),
    ("google", "Google Speech-to-Text v1, hi-IN (Devanagari, romanised)", "pairs_google.jsonl"),
]


def status_of(run: str, path: Path) -> tuple[str, str]:
    """``("scored", "")`` or ``("skipped", reason)`` for one row."""
    if path.exists():
        return "scored", ""
    engine = run.split("_")[0]
    missing = engines.missing_keys(engine)
    if missing:
        return "skipped", "not run: key needed (" + ", ".join(missing) + ")"
    reason = engines.availability(engine)
    if reason:
        return "skipped", f"not run: {reason}"
    return "skipped", f"not run: no output ({path.name}; run collect/transcribe.py --engine {engine})"


def score(path: Path, packs) -> dict[str, Any]:
    pairs = load_pairs(path)
    res = real_pairs_experiment(packs, pairs)
    recognisers = sorted({p.recogniser for p in pairs if p.recogniser})
    return {"status": "scored", "pairs": len(pairs), "recognisers": recognisers,
            "confidence_source": sources_of(path), "overall": res["overall"], "per_pack": res["per_pack"],
            "examples": res["examples"][:12]}


def sources_of(path: Path) -> list[str]:
    """Where the confidences came from: the vendor, or the text channel's
    out-of-vocabulary model for vendors that score no words. Pairs files
    written before the field existed carry Whisper's own probabilities."""
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            seen.add(json.loads(line).get("confidence_source", "vendor"))
    return sorted(seen)


def compare(data: Path, only: list[str] | None = None) -> dict[str, Any]:
    packs = [load_pack(p) for p in list_packs()]
    rows: dict[str, Any] = {}
    for run, label, filename in RUNS:
        if only and run not in only:
            continue
        path = data / filename
        state, reason = status_of(run, path)
        if state == "scored":
            rows[run] = {"label": label, "source": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                         **score(path, packs)}
        else:
            rows[run] = {"label": label, "status": reason, "source": str(path)}
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "data": str(data.relative_to(ROOT)) if data.is_relative_to(ROOT) else str(data),
        "measurement": "haanji.collect.real_pairs_experiment: WER, entity error rate with the bridge off and on, "
                       "correction precision and harmful corrections, over the same (heard, truth) pairs",
        "engines": rows,
        "scored": [k for k, v in rows.items() if v.get("status") == "scored"],
        "skipped": {k: v["status"] for k, v in rows.items() if v.get("status") != "scored"},
    }


def table(payload: dict[str, Any]) -> str:
    head = ("| engine | pairs | confidence | WER (%) | EER off (%) | EER on (%) | reduction (%) | "
            "precision (%) | beneficial | neutral | harmful |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|\n")
    body = ""
    for run, r in payload["engines"].items():
        if r.get("status") != "scored":
            body += f"| {run} — {r['label']} | — | — | — | — | — | — | — | — | — | — |\n"
            continue
        o = r["overall"]
        c = o["corrections"]
        body += (f"| {run} — {r['label']} | {r['pairs']} | {', '.join(r['confidence_source'])} | "
                 f"{o['word_error_rate']*100:.1f} | {o['entity_error_rate_off']*100:.1f} | "
                 f"{o['entity_error_rate_on']*100:.1f} | {o['relative_reduction_pct']:.1f} | "
                 f"{o['precision']*100:.1f} | {c['beneficial']} | {c['neutral']} | {c['harmful']} |\n")
    notes = ""
    if payload["skipped"]:
        notes = "\nNot run:\n\n" + "".join(f"* `{k}` — {v}\n" for k, v in payload["skipped"].items())
    return (f"# Indic STT comparison\n\nGenerated {payload['generated_at']} over `{payload['data']}`. "
            f"{payload['measurement']}.\n\n" + head + body + notes)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA), help="folder holding manifest.jsonl and the pairs files")
    ap.add_argument("--only", default=None, help="comma-separated run names")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--tables", default=str(TABLES))
    args = ap.parse_args(argv)
    payload = compare(Path(args.data), args.only.split(",") if args.only else None)
    Path(args.out).write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(args.tables).write_text(table(payload), encoding="utf-8")
    print(table(payload))
    for run, reason in payload["skipped"].items():
        print(f"skipped {run}: {reason}")
    print(f"\nwrote {args.out} and {args.tables}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
