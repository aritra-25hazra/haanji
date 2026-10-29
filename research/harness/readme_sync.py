#!/usr/bin/env python3
"""Keep the counts quoted in README.md and research/REPORT.md equal to what the
repository actually contains: how many tests pytest collects, how many packs
ship, how many scenarios they carry, how many languages they speak.

    python research/harness/readme_sync.py            # rewrite both files
    python research/harness/readme_sync.py --check    # exit 1 when anything is stale

Every rewrite is a named rule over a specific phrase ("N tests" beside the
pytest line, the test badge, "six packs and three languages", the §3.2 pack
table, the Appendix C inventory), so a historical number in the report's prose
("the first five packs and 21 scenarios" of an evaluation already run) is never
touched. A rule that finds nothing to match any more is reported, because the
sentence it guarded has probably been rewritten by hand.
"""
from __future__ import annotations
import argparse
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from haanji.vertical import list_packs, load_pack     # noqa: E402

README = ROOT / "README.md"
REPORT = ROOT / "research" / "REPORT.md"
WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
         9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}
LANGUAGE_LABEL = {"hinglish": "Hinglish", "benglish": "Benglish", "marathinglish": "Marathinglish"}


def word(n: int) -> str:
    return WORDS.get(n, str(n))


# ------------------------------------------------------------------ facts
@dataclass
class Facts:
    tests: int
    tests_per_file: dict[str, int]
    packs: list[dict]                 # id, language, services, staff, scenarios
    scenarios: int
    languages: int

    @property
    def pack_count(self) -> int:
        return len(self.packs)


def count_tests() -> tuple[int, dict[str, int]]:
    """What ``pytest --collect-only -q`` reports from engine/, per file and in total."""
    try:
        import hypothesis  # noqa: F401  - the dev extra: without it two test modules skip and the count is short
    except ImportError:
        raise SystemExit("readme_sync: the test count needs the dev extras (hypothesis is missing): "
                         "pip install -e '.[dev]' and re-run")
    if sys.version_info < (3, 11):
        raise SystemExit(f"readme_sync: the engine needs Python 3.11+, this is {sys.version.split()[0]}")
    proc = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                          cwd=ROOT / "engine", capture_output=True, text=True)
    per_file: Counter[str] = Counter()
    for line in proc.stdout.splitlines():
        if "::" in line:
            per_file[Path(line.split("::")[0]).name] += 1
    m = re.search(r"(\d+) tests? collected", proc.stdout)
    if not m:
        raise SystemExit(f"could not read the test count from pytest:\n{proc.stdout[-800:]}\n{proc.stderr[-800:]}")
    return int(m.group(1)), dict(per_file)


def facts() -> Facts:
    total, per_file = count_tests()
    packs = []
    for pid in list_packs():
        p = load_pack(pid)
        packs.append({"id": pid, "language": LANGUAGE_LABEL.get(p.language, p.language.capitalize()),
                      "services": len(p.services), "staff": len(p.staff), "scenarios": len(p.scenarios)})
    return Facts(tests=total, tests_per_file=per_file, packs=packs,
                 scenarios=sum(p["scenarios"] for p in packs),
                 languages=len({p["language"] for p in packs}))


# ------------------------------------------------------------------ rules
@dataclass
class Rule:
    name: str
    pattern: re.Pattern
    replacement: Callable[[re.Match, Facts], str]
    matches: int = field(default=0)

    def apply(self, text: str, f: Facts) -> str:
        def sub(m: re.Match) -> str:
            self.matches += 1
            return self.replacement(m, f)
        return self.pattern.sub(sub, text)


def _rx(p: str) -> re.Pattern:
    return re.compile(p, re.MULTILINE)


README_RULES: list[Rule] = [
    Rule("test badge", _rx(r"tests-\d+%20passing"), lambda m, f: f"tests-{f.tests}%20passing"),
    Rule("pytest line", _rx(r"(pytest -q\s+# )\d+ tests"), lambda m, f: f"{m.group(1)}{f.tests} tests"),
    Rule("tests/ in the layout", _rx(r"(tests/\s+)\d+ tests, including"),
         lambda m, f: f"{m.group(1)}{f.tests} tests, including"),
    Rule("honest notes", _rx(r"(executed here\.\*\* )\d+ tests, \d+ scenarios across(\s+)\w+ packs and \w+ languages"),
         lambda m, f: f"{m.group(1)}{f.tests} tests, {f.scenarios} scenarios across{m.group(2)}"
                      f"{word(f.pack_count)} packs and {word(f.languages)} languages"),
    Rule("selftest line", _rx(r"(# all )\d+( packaged scenarios, all )\w+( packs)"),
         lambda m, f: f"{m.group(1)}{f.scenarios}{m.group(2)}{word(f.pack_count)}{m.group(3)}"),
    Rule("packs/ in the layout", _rx(r"(packs/\s+)\w+( Vertical Packs)"),
         lambda m, f: f"{m.group(1)}{word(f.pack_count)}{m.group(2)}"),
    Rule("packs are included", _rx(r"\b\w+( are included — dental clinic)"),
         lambda m, f: f"{word(f.pack_count).capitalize()}{m.group(1)}"),
    Rule("packs are bundled", _rx(r"(— the )\w+(\s+packs are bundled)"),
         lambda m, f: f"{m.group(1)}{word(f.pack_count)}{m.group(2)}"),
    Rule("selftest with a model", _rx(r"(# the )\d+( scenarios, with a model talking)"),
         lambda m, f: f"{m.group(1)}{f.scenarios}{m.group(2)}"),
]


def _pack_table_rows(m: re.Match, f: Facts) -> str:
    """The §3.2 table: its own header (group 1) followed by one row per pack that ships."""
    rows = "\n".join(f"| {p['id']} | {p['language']} | {p['services']} | {p['staff']} | {p['scenarios']} |"
                     for p in f.packs)
    return m.group(1) + rows + "\n"


def _inventory_row(m: re.Match, f: Facts) -> str:
    name, count, rest = m.group(1), m.group(2), m.group(3)
    actual = f.tests_per_file.get(name)
    return m.group(0) if actual is None else f"| {name} | {actual} | {rest} |"


REPORT_RULES: list[Rule] = [
    Rule("§3.2 packs are included", _rx(r"\b\w+( packs are included:)"),
         lambda m, f: f"{word(f.pack_count).capitalize()}{m.group(1)}"),
    # Anchored to the table's own header and to whole rows: other tables in the
    # report have rows that start the same way ("| harmful | 0 | 0 | 0 | ...").
    Rule("§3.2 pack table", _rx(r"(^\| pack \| language \| services \| staff \| scenarios \|\n\|---\|---\|---\|---\|---\|\n)"
                                r"(?:\| [a-z_]+ \| [A-Za-z]+ \| \d+ \| \d+ \| \d+ \|\n)+"),
         _pack_table_rows),
    Rule("Appendix A pytest line", _rx(r"(pytest -q\s+# )\d+ tests, about"),
         lambda m, f: f"{m.group(1)}{f.tests} tests, about"),
    Rule("Appendix A selftest line", _rx(r"(selftest\s+# )\d+ scenarios reach"),
         lambda m, f: f"{m.group(1)}{f.scenarios} scenarios reach"),
    Rule("Appendix B header", _rx(r"(## Appendix B\. The packaged scenarios \()\d+\)"),
         lambda m, f: f"{m.group(1)}{f.scenarios})"),
    Rule("Appendix C header", _rx(r"(## Appendix C\. Test inventory \()\d+ tests\)"),
         lambda m, f: f"{m.group(1)}{f.tests} tests)"),
    Rule("Appendix C rows", _rx(r"^\| (test_\w+\.py) \| (\d+) \| (.*) \|$"), _inventory_row),
]


# ------------------------------------------------------------------ driver
def rewrite(text: str, rules: list[Rule], f: Facts) -> str:
    for rule in rules:
        text = rule.apply(text, f)
    return text


def missing_inventory_rows(report_text: str, f: Facts) -> list[str]:
    listed = set(re.findall(r"^\| (test_\w+\.py) \|", report_text, re.MULTILINE))
    return sorted(name for name in f.tests_per_file if name not in listed)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 instead of writing when anything is stale")
    args = ap.parse_args(argv)
    f = facts()
    print(f"repository: {f.tests} tests, {f.pack_count} packs, {f.scenarios} scenarios, {f.languages} languages")
    stale: list[str] = []
    for path, rules in ((README, README_RULES), (REPORT, REPORT_RULES)):
        before = path.read_text(encoding="utf-8")
        after = rewrite(before, rules, f)
        for rule in rules:
            if rule.matches == 0:
                print(f"  note: {path.name}: rule '{rule.name}' matched nothing (sentence rewritten by hand?)")
        if after != before:
            stale.append(path.name)
            if not args.check:
                path.write_text(after, encoding="utf-8")
                print(f"  rewrote {path.relative_to(ROOT)}")
        else:
            print(f"  {path.relative_to(ROOT)} is current")
    for name in missing_inventory_rows(REPORT.read_text(encoding="utf-8"), f):
        print(f"  note: {name} ({f.tests_per_file[name]} tests) has no row in REPORT Appendix C")
    if args.check and stale:
        print(f"stale: {', '.join(stale)} — run `make readme-sync`")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
