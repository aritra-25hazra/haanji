"""A narrated call, for a live demonstration.

Runs one real conversation through the real engine and prints what each
contribution did while it happened, then attacks the ledger the call just
wrote so the audience can watch the tamper be caught.
"""
from __future__ import annotations
import asyncio
import copy
import datetime as dt
import sqlite3

from .clock import CLOCK, set_speed
from .config import EngineConfig
from .pipeline import CallSession
from .pramaan.ledger import Ledger
from .pramaan.verifier import verify_chain
from .scenario import scenarios_of
from .tools.builtin import build_registry, open_backend
from .vertical import load_pack

RULE = "=" * 78
TENANT = "t_demo"


def _wrap(prefix: str, text: str, width: int = 74) -> str:
    words, lines, cur = text.split(), [], prefix
    pad = " " * len(prefix)
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = pad + w
        else:
            cur = f"{cur}{'' if cur.endswith(' ') or cur == prefix else ' '}{w}"
    lines.append(cur)
    return "\n".join(lines)


async def run(pack_id: str = "dental_clinic", scenario_name: str | None = None,
              speed: float = 1.0, today: dt.date | None = None) -> None:
    set_speed(speed)
    pack = load_pack(pack_id)
    scenarios = scenarios_of(pack)
    scenario = next((s for s in scenarios if s.name == scenario_name), scenarios[0])

    backend, _ = open_backend(pack, TENANT, today=today or dt.date(2026, 9, 7))
    ledger = Ledger(sqlite3.connect(":memory:"))
    registry = build_registry(TENANT, backend, pack, ledger)
    session = CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry,
                          ledger=ledger, config=EngineConfig())

    print(RULE)
    print(f"HAANJI — live call   pack: {pack.display_name}   scenario: {scenario.name}")
    print(f"tenant vocabulary: {len(session.lexicon)} entries, "
          f"{len(session.bhasha.hints())} biasing hints sent to the recogniser")
    if scenario.note:
        print(_wrap("note: ", scenario.note))
    print(RULE)

    await session.open()
    print(_wrap("AGENT  ", session.ctx.last_agent_utterance))

    for utt in scenario.utterances:
        print()
        record = await session.handle_utterance(utt)
        print(_wrap("HEARD  ", record.heard))
        if record.corrections:
            for c in record.corrections:
                print(f"       ~ Bhasha Bridge: {c.from_token!r} -> {c.to_surface!r} "
                      f"(recogniser confidence {c.asr_confidence:.2f})")
            print(_wrap("CALLER ", record.corrected))
        if record.guard:
            print(f"       ! guardrail fired: {record.guard}")
        for tool in record.tools:
            mark = "  [speculated, already computed]" if tool in record.speculation_hits else ""
            print(f"       > tool {tool}{mark}")
        print(_wrap("AGENT  ", record.said))
        print(f"       . turn latency {record.latency_ms:.0f} ms")
        if session.ctx.flags.get("ended"):
            break

    report = session.finish()
    spec = report.speculation
    print(f"\n{RULE}\nCALL SUMMARY")
    print(f"  outcome            {report.outcome.value}")
    print(f"  corrections made   {report.corrections}")
    print(f"  speculations       {spec['started']} started, {spec['hits']} used, "
          f"{spec['wasted']} discarded, "
          f"{spec['saved_ms'] * CLOCK.speed:.0f} ms of tool time saved")
    print(f"  receipts sealed    {', '.join(report.receipts) or 'none'}")
    print(f"  turn latency       p50 "
          f"{report.metrics.summary('turn_latency_ms').get('p50', 0)} ms, "
          f"p90 {report.metrics.summary('turn_latency_ms').get('p90', 0)} ms")

    receipts = ledger.receipts(TENANT)
    if not receipts:
        print(RULE)
        return
    key_id = ledger.ensure_key(TENANT)
    public = ledger.public_key(key_id)
    print(f"\n{RULE}\nPRAMAAN LEDGER — what was sealed, and what happens if it is edited")
    r = receipts[-1]
    print(f"  receipt {r.short_code()}   action {r.action}   seq {r.seq}")
    print(_wrap("  caller was asked : ", r.confirmation.get('prompt_text', '')))
    print(_wrap("  caller replied   : ", r.confirmation.get('reply_text', '')))
    print(f"  reply began {r.confirmation.get('audio_offset_ms', 0)} ms after the question, "
          f"recognised at confidence {r.confirmation.get('asr_confidence', 0)}")
    print(f"  chain hash       : {r.chain_hash.hex()[:48]}...")
    clean = verify_chain(receipts, lambda _k: public)
    print(f"  verifier says    : {clean}")

    tampered = copy.deepcopy(receipts)
    victim = tampered[-1]
    victim.action_args = dict(victim.action_args)
    original = victim.action_args.get("time")
    victim.action_args["time"] = "18:00"
    broken = verify_chain(tampered, lambda _k: public)
    print(f"\n  someone edits the booking time {original!r} -> '18:00' in the database")
    print(f"  verifier says    : {broken}")
    print(RULE)


def main(pack_id: str = "dental_clinic", scenario: str | None = None,
         speed: float = 1.0) -> int:
    asyncio.run(run(pack_id, scenario, speed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
