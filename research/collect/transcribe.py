#!/usr/bin/env python3
"""Run a real recogniser over a manifest of recordings and write (heard, truth)
pairs with per-word confidence, in the format ``haanji.collect`` scores.

Uses faster-whisper on the CPU (``pip install faster-whisper``; the model is
downloaded on first use). The recogniser is run as a general English model
with no hints and no vocabulary, which is the baseline Bhasha Bridge is meant
to sit on top of.

    python research/collect/transcribe.py --manifest research/collect/data/synthetic/manifest.jsonl \
        --out research/collect/data/synthetic/pairs.jsonl --model small
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="small", help="faster-whisper model size: tiny, base, small, medium")
    ap.add_argument("--language", default="en", help="decode as this language; en mirrors a general English recogniser")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("pip install faster-whisper", file=sys.stderr)
        return 2
    manifest = Path(args.manifest)
    base = manifest.parent
    rows = [json.loads(l) for l in manifest.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        rows = rows[:args.limit]
    t0 = time.time()
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    print(f"model {args.model} loaded in {time.time() - t0:.0f}s; {len(rows)} clips", flush=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8") as fh:
        for i, r in enumerate(rows):
            path = base / r["file"]
            if not path.exists():
                print(f"  missing {path}", file=sys.stderr)
                continue
            segments, _info = model.transcribe(str(path), language=args.language, beam_size=5,
                                               word_timestamps=True, vad_filter=False,
                                               condition_on_previous_text=False)
            words, confs = [], []
            for seg in segments:
                for w in (seg.words or []):
                    words.append(w.word.strip())
                    confs.append(round(float(w.probability), 3))
            heard = " ".join(x for x in words if x)
            fh.write(json.dumps({
                "id": r["id"], "pack": r["pack"], "truth": r["truth"], "heard": heard,
                "confidences": confs, "speaker": r.get("speaker", ""), "kind": r.get("kind", ""),
                "synthetic": bool(r.get("synthetic", False)),
                "recogniser": f"faster-whisper:{args.model}:{args.language}",
            }, ensure_ascii=False) + "\n")
            n += 1
            if n % 25 == 0:
                print(f"  {n}/{len(rows)}  {time.time() - t0:.0f}s", flush=True)
    print(f"wrote {n} pairs to {out} in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
