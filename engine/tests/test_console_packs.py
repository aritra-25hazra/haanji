"""The console's sample mode reads the packs from console/src/packs.json; it
must say what packs/*.yaml say, or a sample booking could use a service or a
person the pack does not have."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "harness"))

import console_packs    # noqa: E402


def test_the_console_pack_file_is_current():
    """Run `python research/harness/console_packs.py` after editing a pack."""
    assert console_packs.main(["--check"]) == 0


def test_every_service_names_only_the_pack_s_own_staff():
    import json
    for p in json.loads(console_packs.OUT.read_text(encoding="utf-8"))["packs"]:
        for s in p["services"]:
            assert set(s["staff"]) <= set(p["staff"]), (p["pack_id"], s["name"], s["staff"])
