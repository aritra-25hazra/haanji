"""The study summary: the arithmetic a reader will check by hand."""
import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research" / "harness"))
import study_analysis as sa   # noqa: E402


def test_wilson_interval_is_sane():
    lo, hi = sa.wilson(8, 10)
    assert 0.45 < lo < 0.8 < 0.9 < hi <= 1.0
    assert sa.wilson(0, 0) == (0.0, 0.0)


def test_summary_counts_participants_tasks_and_sus():
    rows = []
    for pid, score, ok in (("P01", 80.0, (1, 1, 0)), ("P02", 70.0, (1, 0, 1))):
        for task, s in zip(("book", "price", "closed"), ok):
            rows.append({"participant": pid, "task": task, "success": str(s), "seconds": "40", "sus_score": str(score),
                         **{f"sus{i}": "4" for i in range(1, 11)}, "wrong": "x", "good": "y"})
    md = sa.summarise(rows)
    assert "Participants: 2" in md and "| book | 2 | 2 | 100 |" in md and "| price | 2 | 1 | 50 |" in md
    assert "**SUS**: 75.0" in md and "- P01: wrong: *x*" in md
