"""Command line entry point: ``haanji <command>``."""
from __future__ import annotations
import argparse
import asyncio
import datetime as dt
import json
import sqlite3
import sys

from . import bench as bench_mod
from . import demo as demo_mod
from .bhasha.lexicon import TenantLexicon
from .bhasha.phonetics import phonetic_key, phrase_key
from .clock import set_speed
from .pramaan.ledger import Ledger
from .pramaan.verifier import verify_chain
from .scenario import scenarios_of
from .tools.builtin import build_registry, open_backend
from .vertical import list_packs, load_pack


def cmd_packs(args) -> int:
    for pid in list_packs():
        pack = load_pack(pid)
        problems = pack.validate()
        state = "ok" if not problems else "; ".join(problems)
        print(f"{pid:22s} v{pack.version}  {len(pack.services):2d} services  "
              f"{len(pack.staff)} staff  {len(pack.knowledge):2d} kb  "
              f"{len(pack.scenarios)} scenarios  [{state}]")
    return 0


def cmd_lexicon(args) -> int:
    pack = load_pack(args.pack)
    lex = TenantLexicon.build(version=pack.version, **pack.lexicon_seed())
    print(f"{pack.display_name}: {len(lex)} entries, {len(lex.by_key)} phonetic buckets")
    for entry in sorted(lex.entries, key=lambda e: (e.entry_type.value, e.surface)):
        key = phrase_key(entry.surface) if entry.words > 1 else phonetic_key(entry.surface)
        variants = f"  <- {', '.join(entry.variants)}" if entry.variants else ""
        print(f"  {entry.entry_type.value:8s} {entry.surface:26s} key={key:14s} "
              f"w={entry.weight:.2f}{variants}")
    return 0


def cmd_scenarios(args) -> int:
    for pid in ([args.pack] if args.pack else list_packs()):
        pack = load_pack(pid)
        for sc in scenarios_of(pack):
            print(f"{pid:22s} {sc.name:26s} expect={sc.expect:14s} "
                  f"turns={len(sc.utterances)} corrupted={sc.corrupted_turns}")
    return 0


def cmd_demo(args) -> int:
    return demo_mod.main(args.pack, args.scenario, args.speed)


def cmd_call(args) -> int:
    return demo_mod.main(args.pack, args.scenario, args.speed)


def cmd_bench(args) -> int:
    return bench_mod.main(["--reps", str(args.reps), "--speed", str(args.speed)]
                          + (["--out", args.out] if args.out else []))


def cmd_verify(args) -> int:
    ledger = Ledger(sqlite3.connect(args.db))
    receipts = ledger.receipts(args.tenant)
    if not receipts:
        print(f"no receipts for tenant {args.tenant}")
        return 1
    report = verify_chain(receipts, ledger.public_key)
    print(f"tenant {args.tenant}: {report}")
    for r in receipts if args.verbose else []:
        print(f"  seq {r.seq:4d}  {r.short_code()}  {r.action:20s} {r.occurred_at}")
    return 0 if report.ok else 2


def cmd_serve(args) -> int:
    """Run the demo web server: web calls, WhatsApp simulator, insights,
    Pack Studio APIs and the public verifier — all on one port."""
    try:
        import uvicorn
    except ImportError:
        print("The web server needs the 'web' extra:  pip install -e \".[web]\"")
        return 1
    import os
    os.environ.setdefault("HAANJI_PACK", args.pack)
    os.environ.setdefault("HAANJI_VAR_DIR", args.var_dir)
    uvicorn.run("haanji.server:app", host=args.host, port=args.port,
                reload=args.reload, log_level="info")
    return 0


def cmd_selftest(args) -> int:
    """Run every packaged scenario and report which reach their expected outcome."""
    async def go() -> int:
        set_speed(args.speed)
        failures = 0
        total = 0
        wanted = [args.pack] if getattr(args, "pack", None) else list_packs()
        for pid in wanted:
            pack = load_pack(pid)
            for sc in scenarios_of(pack):
                backend, _ = open_backend(pack, "t_selftest", today=dt.date(2026, 9, 7))
                ledger = Ledger(sqlite3.connect(":memory:"))
                registry = build_registry("t_selftest", backend, pack, ledger)
                from .pipeline import run_scenario
                _, report = await run_scenario(sc, pack=pack, backend=backend,
                                               registry=registry, ledger=ledger,
                                               tenant_id="t_selftest")
                ok = report.outcome.value == sc.expect
                total += 1
                failures += not ok
                print(f"{'PASS' if ok else 'FAIL'}  {pid:20s} {sc.name:28s} "
                      f"{report.outcome.value}")
        print(f"\n{total - failures}/{total} scenarios reached the expected outcome")
        return 0 if not failures else 1
    return asyncio.run(go())


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="haanji", description="Haanji voice engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("packs", help="list and validate the vertical packs")
    p.set_defaults(func=cmd_packs)

    p = sub.add_parser("lexicon", help="show a tenant lexicon with phonetic keys")
    p.add_argument("--pack", default="dental_clinic")
    p.set_defaults(func=cmd_lexicon)

    p = sub.add_parser("scenarios", help="list packaged scenarios")
    p.add_argument("--pack", default=None)
    p.set_defaults(func=cmd_scenarios)

    p = sub.add_parser("demo", help="run one narrated call")
    p.add_argument("--pack", default="dental_clinic")
    p.add_argument("--scenario", default=None)
    p.add_argument("--speed", type=float, default=1.0,
                   help="simulated time scale; 1.0 runs the call at real speed")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("call", help="alias of demo")
    p.add_argument("--pack", default="dental_clinic")
    p.add_argument("--scenario", default=None)
    p.add_argument("--speed", type=float, default=1.0)
    p.set_defaults(func=cmd_call)

    p = sub.add_parser("bench", help="run the evaluation harness")
    p.add_argument("--reps", type=int, default=5)
    p.add_argument("--speed", type=float, default=40.0)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_bench)

    p = sub.add_parser("verify", help="verify a ledger database independently")
    p.add_argument("--db", required=True)
    p.add_argument("--tenant", required=True)
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("selftest", help="run every packaged scenario")
    p.add_argument("--speed", type=float, default=40.0)
    p.add_argument("--pack", default=None, help="limit to one pack")
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser("serve", help="run the demo web server (web call, WhatsApp, insights)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8090)
    p.add_argument("--pack", default="dental_clinic", help="default pack for new sessions")
    p.add_argument("--var-dir", default="var", help="where the demo databases live")
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
