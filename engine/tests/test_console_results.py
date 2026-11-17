"""The console's "How it works" page quotes research/results.json through
console/src/results.json; the copy must be current and must not change a
single measured number on the way."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "harness"))

import console_results    # noqa: E402


def test_the_console_results_file_is_current():
    """Run `python research/harness/console_results.py` after re-running the benchmark."""
    assert console_results.main(["--check"]) == 0


def test_every_number_is_the_benchmark_s_own():
    src = json.loads(console_results.SRC.read_text(encoding="utf-8"))
    out = json.loads(console_results.OUT.read_text(encoding="utf-8"))
    for k, v in out["headline"].items():
        assert src["headline"][k] == v, k
    for k, v in out["ledger"].items():
        assert src["ledger"][k] == v, k
    assert out["scenarios"] == src["scenarios"] and out["measured_at"] == src["generated_at"]
