#!/usr/bin/env python3
"""Real Hindi telephone speech through a real recogniser: the Gram Vaani set.

OpenSLR 118 (Gram Vaani ASR challenge, Bihar and Jharkhand community-radio
phone calls, Devanagari transcripts) is public and small enough to run on a
laptop. This script transcribes a sample with faster-whisper in Hindi mode,
writes (heard, truth) pairs in both scripts, measures word error rate, and
fits the data-driven corruption model (haanji/corrupt_learned.py) on the
Latin-script pairs so the synthetic experiments can run under noise shaped
by real rural telephone Hindi.

    python research/collect/gramvaani.py --limit 300 --model small
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from haanji.collect import word_error_rate                 # noqa: E402
from haanji.corrupt_learned import LearnedCorruption       # noqa: E402
from haanji.devanagari import to_latin                     # noqa: E402

DATA = ROOT / "research" / "collect" / "data" / "gramvaani"
SET = DATA / "GV_Dev_5h"


def read_transcripts() -> dict[str, str]:
    out = {}
    for line in (SET / "text").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        utt, _, text = line.partition(" ")
        out[utt] = text.strip()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--model", default="small")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)
    if not SET.exists():
        print("download and extract GV_Dev_5h.tar.gz from https://www.openslr.org/118/ into research/collect/data/gramvaani/", file=sys.stderr)
        return 2
    from faster_whisper import WhisperModel
    texts = read_transcripts()
    clean = [u for u, t in texts.items() if "<" not in t and len(t.split()) >= 4 and (SET / "Audio" / f"{u}.mp3").exists()]
    rng = random.Random(args.seed)
    rng.shuffle(clean)
    chosen = clean[:args.limit]
    t0 = time.time()
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    print(f"model loaded in {time.time() - t0:.0f}s; {len(chosen)} of {len(clean)} clean utterances", flush=True)
    pairs_path = DATA / "pairs.jsonl"
    wers, rows = [], []
    with pairs_path.open("w", encoding="utf-8") as fh:
        for i, utt in enumerate(chosen, 1):
            segments, _ = model.transcribe(str(SET / "Audio" / f"{utt}.mp3"), language="hi", beam_size=5,
                                           word_timestamps=True, vad_filter=False, condition_on_previous_text=False)
            words, confs = [], []
            for seg in segments:
                for w in (seg.words or []):
                    words.append(w.word.strip()); confs.append(round(float(w.probability), 3))
            heard_dev = " ".join(x for x in words if x)
            truth_dev = texts[utt]
            heard_lat, truth_lat = to_latin(heard_dev), to_latin(truth_dev)
            wer = word_error_rate(truth_lat, heard_lat)
            wers.append(wer)
            row = {"id": utt, "pack": "gramvaani", "truth": truth_lat, "heard": heard_lat, "truth_devanagari": truth_dev,
                   "heard_devanagari": heard_dev, "confidences": confs, "speaker": "gramvaani", "wer": round(wer, 3),
                   "recogniser": f"faster-whisper:{args.model}:hi", "synthetic": False}
            rows.append(row)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            if i % 25 == 0:
                print(f"  {i}/{len(chosen)}  WER so far {statistics.fmean(wers)*100:.1f}%  {time.time() - t0:.0f}s", flush=True)
    model_l = LearnedCorruption().fit((r["truth"], r["heard"]) for r in rows)
    (DATA / "learned.json").write_text(model_l.to_json(), encoding="utf-8")
    all_conf = [c for r in rows for c in r["confidences"]]
    summary = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "source": "OpenSLR 118 Gram Vaani dev (5 h), Hindi telephone speech",
               "recogniser": f"faster-whisper {args.model}, language=hi", "utterances": len(rows),
               "wer_mean": round(statistics.fmean(wers), 4), "wer_median": round(statistics.median(wers), 4),
               "word_confidence_median": round(statistics.median(all_conf), 3) if all_conf else None,
               "frac_words_below_0_85": round(sum(c < 0.85 for c in all_conf) / len(all_conf), 3) if all_conf else None,
               "learned": model_l.rates()}
    (DATA / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    print(f"wrote {pairs_path.relative_to(ROOT)}, learned.json, summary.json in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
