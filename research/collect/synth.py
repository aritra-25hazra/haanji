#!/usr/bin/env python3
"""Synthetic speech for the pilot: the operating system's Indian-English voices
read the prompt sentences, so a real recogniser can be run on them before any
volunteer has been recorded.

This is honest only if labelled: it measures a real recogniser's errors on
Indian-English *synthesis*, not on Indian callers. The manifest rows carry
``synthetic: true`` and the speaker is ``say:<Voice>`` so nothing downstream
can confuse the two.

    python research/collect/synth.py --out research/collect/data/synthetic --per-pack 20
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from haanji.collect import prompts_for                 # noqa: E402
from haanji.vertical import list_packs, load_pack     # noqa: E402

DEFAULT_VOICES = ["Rishi", "Aman", "Tara"]            # macOS en_IN voices


def available_voices() -> set[str]:
    if not shutil.which("say"):
        return set()
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    return {line.split()[0] for line in out.splitlines() if line.strip()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "research" / "collect" / "data" / "synthetic"))
    ap.add_argument("--per-pack", type=int, default=20)
    ap.add_argument("--voices", default=",".join(DEFAULT_VOICES))
    ap.add_argument("--rate", type=int, default=175, help="words per minute")
    ap.add_argument("--packs", default=None, help="comma-separated; default all")
    args = ap.parse_args(argv)
    have = available_voices()
    if not have:
        print("no `say` command: synthetic speech needs macOS", file=sys.stderr)
        return 2
    voices = [v for v in args.voices.split(",") if v in have]
    missing = [v for v in args.voices.split(",") if v not in have]
    if missing:
        print(f"voices not installed, skipped: {missing}", file=sys.stderr)
    if not voices:
        return 2
    out = Path(args.out)
    audio = out / "audio"
    audio.mkdir(parents=True, exist_ok=True)
    manifest = out / "manifest.jsonl"
    packs = args.packs.split(",") if args.packs else list_packs()
    n = 0
    with manifest.open("w", encoding="utf-8") as fh:
        for pid in packs:
            for i, prompt in enumerate(prompts_for(load_pack(pid), limit=args.per_pack)):
                for voice in voices:
                    rid = f"{pid}-{i:03d}-{voice.lower()}"
                    path = audio / f"{rid}.aiff"
                    subprocess.run(["say", "-v", voice, "-r", str(args.rate), "-o", str(path), prompt["truth"]],
                                   check=True)
                    fh.write(json.dumps({
                        "id": rid, "file": f"audio/{rid}.aiff", "pack": pid, "truth": prompt["truth"],
                        "kind": prompt["kind"], "speaker": f"say:{voice}", "mime": "audio/aiff",
                        "synthetic": True, "rate_wpm": args.rate,
                        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                    }, ensure_ascii=False) + "\n")
                    n += 1
            print(f"  {pid}: done", flush=True)
    print(f"wrote {n} clips and {manifest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
