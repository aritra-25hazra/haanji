"""The README and the report quote counts the repository can prove."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "harness"))

import readme_sync as rs    # noqa: E402

FAKE = rs.Facts(
    tests=321, tests_per_file={"test_a.py": 300, "test_new.py": 21},
    packs=[{"id": "dental_clinic", "language": "Hinglish", "services": 6, "staff": 3, "scenarios": 8},
           {"id": "clinic_pune", "language": "Marathinglish", "services": 4, "staff": 2, "scenarios": 3}],
    scenarios=11, languages=2)

README_SNIPPET = """![tests](https://img.shields.io/badge/tests-223%20passing-1F6B45)
python -m haanji.cli selftest      # all 24 packaged scenarios, all six packs
pytest -q                          # 317 tests
│   └── tests/               317 tests, including the safety properties and the demo pages
├── packs/           five Vertical Packs — the commercial moat, as YAML
scenarios the pack must pass before it ships. Five are included — dental clinic,
haanji selftest --llm claude                  # the 21 scenarios, with a model talking
* **The Python engine is fully executed here.** 317 tests, 24 scenarios across
  six packs and three languages, and the entire benchmark run on this
* **Install the engine alone:** `pip install "haanji-engine[web]"` — the six
  packs are bundled; `HAANJI_PACKS_DIR` points it at your own.
push in CI: 16 tests, including the ArchUnit rules
"""

REPORT_SNIPPET = """the scenarios the pack must pass before it ships. Five packs are included:

| pack | language | services | staff | scenarios |
|---|---|---|---|---|
| dental_clinic | Hinglish | 6 | 3 | 8 |
| salon_spa | Hinglish | 6 | 4 | 4 |

(The Pune pack was added after the evaluation runs below, which cover the first five packs and 21 scenarios.)
pytest -q                                   # 317 tests, about 6 s
python -m haanji.cli selftest               # 24 scenarios reach their expected outcome
## Appendix B. The packaged scenarios (24)
## Appendix C. Test inventory (317 tests)

| file | tests | what it guards |
|---|---|---|
| test_a.py | 34 | the turn controller |
"""


def test_every_readme_phrase_is_rewritten_and_the_java_count_is_not():
    out = rs.rewrite(README_SNIPPET, [rs.Rule(r.name, r.pattern, r.replacement) for r in rs.README_RULES], FAKE)
    assert "tests-321%20passing" in out
    assert "pytest -q                          # 321 tests" in out
    assert "tests/               321 tests, including" in out
    assert "packs/           two Vertical Packs" in out
    assert "Two are included — dental clinic," in out
    assert "# the 11 scenarios, with a model talking" in out
    assert "# all 11 packaged scenarios, all two packs" in out
    assert "321 tests, 11 scenarios across\n  two packs and two languages" in out
    assert "— the two\n  packs are bundled" in out
    assert "16 tests, including the ArchUnit" in out, "the Java count is a different test suite"
    assert rs.rewrite(out, [rs.Rule(r.name, r.pattern, r.replacement) for r in rs.README_RULES], FAKE) == out


def test_the_report_table_headers_and_inventory_follow_the_facts():
    out = rs.rewrite(REPORT_SNIPPET, [rs.Rule(r.name, r.pattern, r.replacement) for r in rs.REPORT_RULES], FAKE)
    assert "Two packs are included:" in out
    assert "| dental_clinic | Hinglish | 6 | 3 | 8 |\n| clinic_pune | Marathinglish | 4 | 2 | 3 |\n" in out
    assert "| salon_spa |" not in out, "the table is rebuilt from the packs that ship"
    assert "the first five packs and 21 scenarios" in out, "history is never rewritten"
    assert "# 321 tests, about 6 s" in out and "# 11 scenarios reach" in out
    assert "## Appendix B. The packaged scenarios (11)" in out
    assert "## Appendix C. Test inventory (321 tests)" in out
    assert "| test_a.py | 300 | the turn controller |" in out
    assert rs.missing_inventory_rows(out, FAKE) == ["test_new.py"]


def test_the_facts_come_from_the_repository():
    f = rs.facts()
    assert f.pack_count >= 6 and f.scenarios >= 24 and f.languages >= 3      # the repository, not a constant
    assert f.tests > 400 and sum(f.tests_per_file.values()) == f.tests
    assert f.tests_per_file["test_readme_sync.py"] >= 4


def test_the_committed_readme_and_report_are_current():
    """What CI's `readme-check` enforces: run `make readme-sync` after adding tests, packs or scenarios."""
    assert rs.main(["--check"]) == 0
