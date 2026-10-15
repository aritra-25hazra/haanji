#!/usr/bin/env python3
"""Summarise the user study (docs/study/protocol.md) from the server's CSV export.

    curl -s http://localhost:8090/api/study/export > research/study.csv
    python research/harness/study_analysis.py research/study.csv

Prints task success per task with a Wilson 95% interval, median time per
task, the System Usability Scale mean with a t-interval over participants,
per-item means, and the free-text comments, as Markdown for the report.
"""
from __future__ import annotations
import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 15: 2.131, 20: 2.086}
ITEMS = ["use again", "unnecessarily complex", "easy to use", "needs technical help", "well integrated",
         "inconsistent", "quick to learn", "cumbersome", "felt confident", "much to learn first"]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def summarise(rows: list[dict]) -> str:
    by_task: dict[str, list[dict]] = defaultdict(list)
    by_participant: dict[str, dict] = {}
    for r in rows:
        by_task[r["task"]].append(r)
        by_participant.setdefault(r["participant"], r)
    out = [f"Participants: {len(by_participant)} · task attempts: {len(rows)}\n",
           "| task | attempts | success | success rate (%) | Wilson 95% | median time (s) |", "|---|---|---|---|---|---|"]
    for task, rs in by_task.items():
        ok = sum(int(r["success"] or 0) for r in rs)
        lo, hi = wilson(ok, len(rs))
        times = [float(r["seconds"]) for r in rs if r.get("seconds")]
        out.append(f"| {task} | {len(rs)} | {ok} | {100*ok/len(rs):.0f} | {100*lo:.0f}–{100*hi:.0f} | "
                   f"{statistics.median(times):.0f} |" if times else f"| {task} | {len(rs)} | {ok} | {100*ok/len(rs):.0f} | {100*lo:.0f}–{100*hi:.0f} | — |")
    scores = [float(p["sus_score"]) for p in by_participant.values() if p.get("sus_score")]
    if scores:
        n = len(scores)
        mean = statistics.fmean(scores)
        ci = (T95.get(n - 1, 1.96) * statistics.stdev(scores) / math.sqrt(n)) if n > 1 else 0.0
        out += ["", f"**SUS**: {mean:.1f} ± {ci:.1f} (n = {n}; 68 is the conventional average, above 80 is good)", "",
                "| item | statement | mean (1–5) |", "|---|---|---|"]
        for i, label in enumerate(ITEMS):
            vals = [float(p[f"sus{i+1}"]) for p in by_participant.values() if p.get(f"sus{i+1}")]
            if vals:
                out.append(f"| {i+1} | {label} | {statistics.fmean(vals):.2f} |")
    comments = [(p["participant"], p.get("wrong", ""), p.get("good", "")) for p in by_participant.values()
                if (p.get("wrong") or p.get("good"))]
    if comments:
        out += ["", "**What felt wrong / what felt good**", ""]
        for pid, wrong, good in comments:
            out.append(f"- {pid}: wrong: *{wrong.strip() or '—'}* · good: *{good.strip() or '—'}*")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    with Path(argv[0]).open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print("no responses yet")
        return 1
    print(summarise(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
