#!/usr/bin/env python3
"""Write console/src/packs.json: what the console's sample mode knows about
every pack (business, services with prices and staff, hours, lexicon), read
from packs/*.yaml exactly as the engine reads them. The sample shop is built
from this file, so a sample booking can only use a service and a person the
pack really has.

    python research/harness/console_packs.py            # rewrite the file
    python research/harness/console_packs.py --check    # exit 1 when it is stale
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from haanji.bhasha.lexicon import TenantLexicon       # noqa: E402
from haanji.vertical import PACK_DIR, list_packs, load_pack     # noqa: E402

PRODUCT_DIR = Path(PACK_DIR) / "product"

OUT = ROOT / "console" / "src" / "packs.json"


def pack_record(pid: str, product: bool = False) -> dict:
    p = load_pack(str(PRODUCT_DIR / f"{pid}.yaml") if product else pid)
    lex = TenantLexicon.build(version=p.version, **p.lexicon_seed())
    return {
        "pack_id": pid, "display_name": p.display_name, "version": p.version, "language": p.language,
        "business_name": p.persona.business_name, "agent_name": p.persona.agent_name, "greeting": p.persona.greeting,
        "staff": list(p.staff), "staff_role": p.staff_role,
        "services": [{"name": s.name, "price_inr": s.price_inr, "duration_min": s.duration_min,
                      "staff": list(s.staff) or list(p.staff), "aliases": list(s.aliases)} for s in p.services],
        # weekday as Python counts it (Monday 0): [open, close] or [open, close, break_from, break_to]
        "hours": {str(d): list(v) for d, v in sorted(p.hours.items())},
        "knowledge": [{"q": q, "a": a} for q, a, _tags in p.knowledge],
        "refusal_line": p.guardrails.refusal_line, "escalation_line": p.guardrails.escalation_line,
        "after_hours_line": p.guardrails.after_hours_line, "emergency_contact": p.guardrails.emergency_contact,
        "closing": p.persona.closing,
        "scenarios": len(p.scenarios), "issues": p.validate(),
        # the product ships the packs in packs/product/; the others are the research corpus
        "product": product,
        "departments": [{"name": d.name, "code": d.code, "staff": list(d.staff)} for d in p.departments],
        "lexicon": [{"surface": e.surface, "entry_type": e.entry_type.value, "variants": list(e.variants),
                     "keys": sorted(e.keys()), "weight": round(e.weight, 2)} for e in lex.entries],
    }


def render() -> str:
    return json.dumps({"generated_from": "packs/product/*.yaml and packs/*.yaml by research/harness/console_packs.py",
                       "packs": [pack_record(pid, product=True) for pid in list_packs(str(PRODUCT_DIR))] +
                                [pack_record(pid) for pid in list_packs()]},
                      ensure_ascii=False, indent=1) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 instead of writing when the file is stale")
    args = ap.parse_args(argv)
    text = render()
    current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    if text == current:
        print(f"{OUT.relative_to(ROOT)} is current")
        return 0
    if args.check:
        print(f"stale: {OUT.relative_to(ROOT)} — run `python research/harness/console_packs.py`")
        return 1
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
