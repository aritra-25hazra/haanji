"""The evaluation harness.

Everything the report claims about this system is produced here, by running
the same engine four times over the same calls with one contribution switched
off at a time. Nothing is hand-entered: ``python -m haanji.bench`` regenerates
``research/results.json`` from scratch on any machine, with no network and no
API key.

Measured quantities
-------------------
Entity Error Rate
    Fraction of catalogue entities (services, staff, localities) that the
    transcript gets wrong, measured against what the caller actually said.
    Text-level word error rate is the wrong instrument here: the agent only
    has to get the *entities* right to make the correct booking.
Turn latency
    Wall-clock from the end of the caller's speech to the agent's reply,
    reported in nominal milliseconds.
Tamper detection
    Fraction of single-field mutations of a sealed receipt that the
    independent verifier catches.
Unconfirmed writes
    Number of write actions the ledger allowed without a confirmation proof.
    The design target is zero, and the harness tries to make it non-zero.
"""
from __future__ import annotations
import argparse
import asyncio
import copy
import dataclasses
import datetime as dt
import json
import os
import sqlite3
import random
import statistics
import zlib
import time
from typing import Any

from . import nlu
from .backend.local import LocalBackend
from .corrupt import corrupt
from .clock import CLOCK, set_speed
from .config import (BhashaConfig, EngineConfig, LedgerConfig, SpeculationConfig)
from .metrics import Metrics, percentile
from .pipeline import CallReport, run_scenario
from .pramaan.ledger import Ledger, LedgerError
from .pramaan.receipt import ConfirmationProof, Receipt
from .pramaan.verifier import verify_chain, verify_receipt
from .scenario import Scenario, Utterance, scenarios_of
from .tools.builtin import build_registry, open_backend
from .vertical import Pack, list_packs, load_pack

TODAY = dt.date(2026, 9, 7)          # a Monday, so every pack's week looks the same
TENANT = "t_bench"

CONFIGS: dict[str, dict[str, bool]] = {
    "full":            {"bhasha": True,  "speculation": True},
    "no_speculation":  {"bhasha": True,  "speculation": False},
    "no_bhasha":       {"bhasha": False, "speculation": True},
    "baseline":        {"bhasha": False, "speculation": False},
}


def make_config(bhasha: bool, speculation: bool) -> EngineConfig:
    return EngineConfig(
        bhasha=BhashaConfig(enabled=bhasha),
        speculation=SpeculationConfig(enabled=speculation),
        ledger=LedgerConfig(enabled=True, require_confirmation=True))


# ------------------------------------------------------------------ entity ER
def entity_errors(truth: str, hypothesis: str, index: dict[str, str]) -> tuple[int, int]:
    gold = nlu.find_entities(truth, index)
    pred = nlu.find_entities(hypothesis, index)
    return len(gold), len(gold - pred) + len(pred - gold)


def score_transcripts(report: CallReport, scenario: Scenario, index: dict[str, str],
                      use_corrected: bool) -> tuple[int, int]:
    gold_total = err_total = 0
    for record, utt in zip(report.turns, scenario.utterances):
        hypothesis = record.corrected if use_corrected else record.heard
        g, e = entity_errors(utt.truth, hypothesis, index)
        gold_total += g
        err_total += e
    return gold_total, err_total


def score_corrections(report: CallReport, index: dict[str, str]) -> dict[str, int]:
    """Was each repair an improvement, a no-op, or damage?

    A repair is *harmful* when the recogniser had in fact heard the span
    correctly and the layer overwrote it. That is the failure mode this
    design exists to avoid, so the harness counts it explicitly rather than
    reporting only the wins."""
    tally = {"beneficial": 0, "neutral": 0, "harmful": 0}
    for record in report.turns:
        truth = f" {record.truth.lower()} "
        gold = nlu.find_entities(record.truth, index)
        for c in record.corrections:
            heard_was_right = f" {c.from_token.lower()} " in truth
            if heard_was_right:
                tally["harmful"] += 1
            elif c.to_surface in gold:
                tally["beneficial"] += 1
            else:
                tally["neutral"] += 1
    return tally


def noisy(scenario: Scenario, rate: float, rng: random.Random) -> Scenario:
    """Rebuild a scenario with independently generated recognition errors."""
    utterances = []
    for u in scenario.utterances:
        heard, low = corrupt(u.truth, rate, rng)
        utterances.append(Utterance(heard=heard, truth=u.truth, low_conf=low))
    return Scenario(scenario.name, scenario.pack_id, utterances, scenario.expect, scenario.note)


# ----------------------------------------------------------------- one config
async def run_config(name: str, packs: list[Pack], reps: int,
                     noise: float | None = None) -> dict[str, Any]:
    flags = CONFIGS[name]
    cfg = make_config(flags["bhasha"], flags["speculation"])
    metrics = Metrics()
    gold_total = err_total = 0
    correct_outcomes = calls = 0
    quality = {"beneficial": 0, "neutral": 0, "harmful": 0}
    latencies: list[float] = []
    tool_latencies: list[float] = []
    read_latencies: list[float] = []
    spec_started = spec_hits = spec_wasted = 0
    spec_saved = 0.0
    per_pack: dict[str, dict[str, Any]] = {}
    unconfirmed_writes = 0

    for pack in packs:
        index = pack.entity_index()
        pack_gold = pack_err = pack_ok = pack_calls = 0
        for rep in range(reps):
            rng = random.Random(9000 + rep * 31 + zlib.crc32(pack.pack_id.encode()) % 1000)
            for base in scenarios_of(pack):
                scenario = base if noise is None else noisy(base, noise, rng)
                backend, _ = open_backend(pack, TENANT, today=TODAY)
                ledger = Ledger(sqlite3.connect(":memory:"))
                registry = build_registry(TENANT, backend, pack, ledger)
                _, report = await run_scenario(
                    scenario, pack=pack, backend=backend, registry=registry, ledger=ledger,
                    config=cfg, tenant_id=TENANT, metrics=metrics, seed=100 + rep)
                g, e = score_transcripts(report, scenario, index, flags["bhasha"])
                gold_total += g
                err_total += e
                pack_gold += g
                pack_err += e
                ok = report.outcome.value == scenario.expect
                correct_outcomes += ok
                pack_ok += ok
                calls += 1
                pack_calls += 1
                latencies.extend(report.latencies)
                tool_latencies.extend(report.tool_latencies)
                read_latencies.extend(report.read_latencies)
                for k, v in score_corrections(report, index).items():
                    quality[k] += v
                spec_started += report.speculation["started"]
                spec_hits += report.speculation["hits"]
                spec_wasted += report.speculation["wasted"]
                spec_saved += report.speculation["saved_ms"]
                # A write that reached the business without a sealed receipt
                # is the failure this contribution exists to prevent.
                for booking in backend.bookings(TENANT):
                    if booking.status == "CONFIRMED" and booking.customer_name != "walk-in" \
                            and not booking.receipt_code:
                        unconfirmed_writes += 1
        per_pack[pack.pack_id] = {
            "calls": pack_calls,
            "outcome_accuracy": round(pack_ok / pack_calls, 3) if pack_calls else 0.0,
            "entity_error_rate": round(pack_err / pack_gold, 4) if pack_gold else 0.0,
        }

    return {
        "config": name,
        "noise": noise,
        "bhasha": flags["bhasha"],
        "speculation": flags["speculation"],
        "calls": calls,
        "turns": len(latencies),
        "outcome_accuracy": round(correct_outcomes / calls, 4) if calls else 0.0,
        "entity_error_rate": round(err_total / gold_total, 4) if gold_total else 0.0,
        "entities_evaluated": gold_total,
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 1) if latencies else 0.0,
            "p50": round(percentile(latencies, 0.50), 1),
            "p90": round(percentile(latencies, 0.90), 1),
            "p95": round(percentile(latencies, 0.95), 1),
            "max": round(max(latencies), 1) if latencies else 0.0,
        },
        "tool_turn_latency_ms": {
            "n": len(tool_latencies),
            "mean": round(statistics.fmean(tool_latencies), 1) if tool_latencies else 0.0,
            "p50": round(percentile(tool_latencies, 0.50), 1),
            "p90": round(percentile(tool_latencies, 0.90), 1),
            "p95": round(percentile(tool_latencies, 0.95), 1),
        },
        "read_turn_latency_ms": {
            "n": len(read_latencies),
            "mean": round(statistics.fmean(read_latencies), 1) if read_latencies else 0.0,
            "p50": round(percentile(read_latencies, 0.50), 1),
            "p90": round(percentile(read_latencies, 0.90), 1),
            "p95": round(percentile(read_latencies, 0.95), 1),
        },
        "correction_quality": quality,
        "speculation": {
            "started": spec_started, "hits": spec_hits, "wasted": spec_wasted,
            "hit_rate": round(spec_hits / spec_started, 3) if spec_started else 0.0,
            "saved_ms_total": round(spec_saved * CLOCK.speed, 1),
            "saved_ms_per_hit": round(spec_saved * CLOCK.speed / spec_hits, 1) if spec_hits else 0.0,
        },
        "unconfirmed_writes": unconfirmed_writes,
        "per_pack": per_pack,
        "metrics": metrics.as_dict(),
    }


# ------------------------------------------------- transcript-level experiment
TEMPLATES = [
    "{service} karwana hai kal",
    "{service} ka kitna charge hai",
    "kal subah {service} ke liye time chahiye",
    "{staff} se milna hai parso",
    "{staff} ke saath {service} book karna hai",
    "{place} wali branch mein {service} ka slot hai kya",
    "{place} mein aap log hain na",
    "{service} aur {service2} dono karwane hain",
]


def corpus_of(pack: Pack) -> list[str]:
    """Entity-bearing sentences built from the tenant's own catalogue.

    The point of this corpus is volume and coverage: every service, every
    member of staff and every locality the tenant registered appears in
    several sentence frames, so the measurement is not dominated by whichever
    handful of phrases the scenario author happened to write."""
    services = pack.service_names
    staff = pack.staff or ["staff"]
    places = pack.places or ["branch"]
    out: list[str] = []
    for i, service in enumerate(services):
        service2 = services[(i + 1) % len(services)]
        for template in TEMPLATES:
            out.append(template.format(service=service, service2=service2,
                                       staff=staff[i % len(staff)],
                                       place=places[i % len(places)]))
    for person in staff:
        out.append(f"{person} kal available hain kya")
    for place in places:
        out.append(f"{place} wali branch ka number chahiye")
    return sorted(set(out))


def transcript_experiment(packs: list[Pack], rates: list[float],
                          trials: int = 12) -> dict[str, Any]:
    """Measure the correction layer alone, with no dialogue in the way."""
    from .bhasha.bridge import BhashaBridge
    from .bhasha.lexicon import TenantLexicon
    from .config import BhashaConfig
    from .models import Token, Transcript

    results: dict[str, Any] = {}
    for rate in rates:
        gold_off = err_off = gold_on = err_on = 0
        beneficial = neutral = harmful = 0
        sentences = 0
        elapsed: list[float] = []
        for pack in packs:
            index = pack.entity_index()
            lexicon = TenantLexicon.build(version=pack.version, **pack.lexicon_seed())
            bridge = BhashaBridge(lexicon, BhashaConfig(enabled=True))
            rng = random.Random(4242 + int(rate * 100))
            for truth in corpus_of(pack):
                for _ in range(trials):
                    heard, low = corrupt(truth, rate, rng)
                    sentences += 1
                    low_set = {w.lower() for w in low}
                    tokens = [Token(w, 0.42 if w.lower() in low_set else 0.94)
                              for w in heard.split()]
                    corrected = bridge.correct(Transcript(tokens, True))
                    elapsed.append(corrected.elapsed_ms)
                    g, e = entity_errors(truth, heard, index)
                    gold_off += g
                    err_off += e
                    g2, e2 = entity_errors(truth, corrected.text, index)
                    gold_on += g2
                    err_on += e2
                    truth_padded = f" {truth.lower()} "
                    gold_entities = nlu.find_entities(truth, index)
                    for c in corrected.corrections:
                        if f" {c.from_token.lower()} " in truth_padded:
                            harmful += 1
                        elif c.to_surface in gold_entities:
                            beneficial += 1
                        else:
                            neutral += 1
        results[f"{rate:.2f}"] = {
            "sentences": sentences,
            "entities": gold_off,
            "entity_error_rate_off": round(err_off / gold_off, 4) if gold_off else 0.0,
            "entity_error_rate_on": round(err_on / gold_on, 4) if gold_on else 0.0,
            "relative_reduction_pct": round(100 * (err_off - err_on) / err_off, 1)
                if err_off else 0.0,
            "corrections": {"beneficial": beneficial, "neutral": neutral, "harmful": harmful},
            "precision": round(beneficial / (beneficial + neutral + harmful), 4)
                if (beneficial + neutral + harmful) else 0.0,
            "median_correct_ms": round(statistics.median(elapsed), 3) if elapsed else 0.0,
        }
    return results


# ------------------------------------------------------------------- ledger
MUTATIONS = [
    ("action_args.time", lambda r: r.action_args.__setitem__("time", "18:00")),
    ("action_args.service", lambda r: r.action_args.__setitem__("service", "dental implant")),
    ("action_args.phone", lambda r: r.action_args.__setitem__("phone", "9000000000")),
    ("confirmation.reply_text", lambda r: r.confirmation.__setitem__("reply_text", "haan")),
    ("confirmation.asr_confidence",
     lambda r: r.confirmation.__setitem__("asr_confidence", 0.99)),
    ("transcript_excerpt", lambda r: setattr(r, "transcript_excerpt", "caller: haan")),
    ("occurred_at", lambda r: setattr(r, "occurred_at", "2020-01-01T00:00:00+00:00")),
    ("agent_config_version", lambda r: setattr(r, "agent_config_version", 99)),
]


def ledger_experiment(pack: Pack, trials: int = 40) -> dict[str, Any]:
    """Seal a chain of real bookings, then attack it."""
    conn = sqlite3.connect(":memory:")
    ledger = Ledger(conn)
    proof = ConfirmationProof(
        prompt_text="Ek baar dohra deta hoon - root canal, kal subah 9:30 baje. Confirm kar dun?",
        prompt_start_ms=1000, reply_text="haan confirm kar do", reply_start_ms=4200,
        asr_confidence=0.94, audio_offset_ms=3200)
    receipts: list[Receipt] = []
    for i in range(trials):
        receipts.append(ledger.append(
            tenant_id=TENANT, conversation_id=f"c{i}", action="book_appointment",
            action_args={"service": "root canal", "date": "2026-09-08", "time": "09:30",
                         "staff": "Dr Sheikh", "phone": "9876543210", "seq": i},
            confirmation=proof, transcript_excerpt="caller: haan confirm kar do",
            agent_config_version=pack.version))
    key_id = ledger.ensure_key(TENANT)
    public = ledger.public_key(key_id)

    clean = verify_chain(receipts, lambda _kid: public)
    detected = attempted = 0
    per_field: dict[str, dict[str, int]] = {}
    for name, mutate in MUTATIONS:
        for i in range(0, len(receipts), 4):
            tampered = copy.deepcopy(receipts)
            target = tampered[i]
            target.action_args = dict(target.action_args)
            target.confirmation = dict(target.confirmation)
            mutate(target)
            report = verify_chain(tampered, lambda _kid: public)
            attempted += 1
            hit = not report.ok
            detected += hit
            slot = per_field.setdefault(name, {"attempted": 0, "detected": 0})
            slot["attempted"] += 1
            slot["detected"] += hit

    # Attack 2: delete a receipt from the middle of the chain.
    dropped = receipts[:10] + receipts[11:]
    drop_report = verify_chain(dropped, lambda _kid: public)
    # Attack 3: re-sign a forged receipt with a key that is not the tenant's.
    forged = copy.deepcopy(receipts[0])
    forged.action_args = dict(forged.action_args) | {"time": "18:00"}
    forged.payload_hash = forged.compute_payload_hash()
    forged.chain_hash = forged.compute_chain_hash()
    forged_ok, forged_reason = verify_receipt(forged, public)
    # Attack 4: a write with no confirmation proof at all.
    try:
        ledger.append(tenant_id=TENANT, conversation_id="c_evil", action="book_appointment",
                      action_args={"service": "root canal"}, confirmation=None,
                      transcript_excerpt="", agent_config_version=1)
        unconfirmed_accepted = 1
    except LedgerError:
        unconfirmed_accepted = 0

    anchor = ledger.anchor_day(TENANT)
    return {
        "chain_length": len(receipts),
        "clean_chain_valid": clean.ok,
        "mutations_attempted": attempted,
        "mutations_detected": detected,
        "detection_rate": round(detected / attempted, 4) if attempted else 0.0,
        "per_field": {k: {**v, "rate": round(v["detected"] / v["attempted"], 3)}
                      for k, v in per_field.items()},
        "deletion_detected": not drop_report.ok,
        "deletion_reason": drop_report.reason,
        "forged_signature_rejected": not forged_ok,
        "forged_reason": forged_reason,
        "unconfirmed_writes_accepted": unconfirmed_accepted,
        "daily_anchor": anchor[:32] + "...",
    }


# ------------------------------------------------------------------- driver
NOISE_RATES = [0.15, 0.30, 0.45]


async def main_async(reps: int, speed: float, out: str) -> dict[str, Any]:
    set_speed(speed)
    packs = [load_pack(p) for p in list_packs()]
    started = time.time()

    print("authored scenarios (the corruptions shipped in the packs)")
    authored: dict[str, Any] = {}
    for name in CONFIGS:
        t0 = time.time()
        authored[name] = await run_config(name, packs, reps)
        authored[name]["wall_seconds"] = round(time.time() - t0, 1)
        print(f"  {name:16s} {authored[name]['calls']:4d} calls  "
              f"{authored[name]['wall_seconds']:6.1f}s")

    print("transcript-level correction experiment")
    transcripts = transcript_experiment(packs, NOISE_RATES, trials=max(6, reps * 3))
    for rate, r in transcripts.items():
        print(f"  rate {rate}   {r['sentences']:5d} sentences  EER "
              f"{r['entity_error_rate_off']*100:5.1f}% -> {r['entity_error_rate_on']*100:5.2f}%"
              f"   precision {r['precision']*100:5.1f}%  harmful {r['corrections']['harmful']}")

    print("end-to-end calls under the same synthetic noise")
    sweep: dict[str, Any] = {}
    for rate in NOISE_RATES:
        sweep[f"{rate:.2f}"] = {}
        for name in ("full", "no_bhasha"):
            sweep[f"{rate:.2f}"][name] = await run_config(name, packs, reps, noise=rate)
        a, b = sweep[f"{rate:.2f}"]["full"], sweep[f"{rate:.2f}"]["no_bhasha"]
        print(f"  rate {rate:.2f}   EER {b['entity_error_rate']*100:5.1f}% -> "
              f"{a['entity_error_rate']*100:5.1f}%   task success "
              f"{b['outcome_accuracy']*100:5.1f}% -> {a['outcome_accuracy']*100:5.1f}%")

    full, no_spec = authored["full"], authored["no_speculation"]
    mid = sweep[f"{NOISE_RATES[1]:.2f}"]
    mid_tx = transcripts[f"{NOISE_RATES[1]:.2f}"]
    mid_full, mid_off = mid["full"], mid["no_bhasha"]
    p90_off = no_spec["read_turn_latency_ms"]["p90"]
    p90_on = full["read_turn_latency_ms"]["p90"]
    p50_off = no_spec["read_turn_latency_ms"]["p50"]
    p50_on = full["read_turn_latency_ms"]["p50"]

    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "reps": reps, "time_scale": speed,
        "packs": [p.pack_id for p in packs],
        "scenarios": sum(len(p.scenarios) for p in packs),
        "authored": authored,
        "transcripts": transcripts,
        "noise_sweep": sweep,
        "ledger": ledger_experiment(packs[0]),
        "headline": {
            "noise_rate": NOISE_RATES[1],
            "sentences_scored": mid_tx["sentences"],
            "entities_scored": mid_tx["entities"],
            "entity_error_rate_without_bhasha": mid_tx["entity_error_rate_off"],
            "entity_error_rate_with_bhasha": mid_tx["entity_error_rate_on"],
            "entity_error_reduction_pct": mid_tx["relative_reduction_pct"],
            "correction_precision": mid_tx["precision"],
            "harmful_corrections_transcript": mid_tx["corrections"]["harmful"],
            "bhasha_median_ms": mid_tx["median_correct_ms"],
            "task_success_without_bhasha": mid_off["outcome_accuracy"],
            "task_success_with_bhasha": mid_full["outcome_accuracy"],
            "harmful_corrections": mid_full["correction_quality"]["harmful"],
            "beneficial_corrections": mid_full["correction_quality"]["beneficial"],
            "neutral_corrections": mid_full["correction_quality"]["neutral"],
            "read_turn_p50_without_speculation": p50_off,
            "read_turn_p50_with_speculation": p50_on,
            "read_turn_p50_reduction_pct": round(100 * (p50_off - p50_on) / p50_off, 1)
                if p50_off else 0.0,
            "read_turn_p90_without_speculation": p90_off,
            "read_turn_p90_with_speculation": p90_on,
            "read_turn_p90_reduction_pct": round(100 * (p90_off - p90_on) / p90_off, 1)
                if p90_off else 0.0,
            "write_turn_p90_with_speculation": full["tool_turn_latency_ms"]["p90"],
            "speculation_hit_rate": full["speculation"]["hit_rate"],
            "speculations_started": full["speculation"]["started"],
            "wasted_speculations": full["speculation"]["wasted"],
            "saved_ms_per_hit": full["speculation"]["saved_ms_per_hit"],
            "outcome_accuracy_clean": full["outcome_accuracy"],
            "total_wall_seconds": round(time.time() - started, 1),
        },
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return payload


def print_report(p: dict[str, Any]) -> None:
    h = p["headline"]
    line = "-" * 82
    print(f"\n{line}\nHaanji engine — measured results")
    print(f"{p['scenarios']} scenarios x {p['reps']} repetitions over "
          f"{len(p['packs'])} vertical packs; latencies in nominal milliseconds\n{line}")

    print("A. Authored scenarios — ablation over the two runtime contributions")
    print(f"   {'config':17s}{'calls':>7s}{'task ok':>9s}{'EER':>8s}"
          f"{'read p50':>10s}{'read p90':>10s}{'any p90':>9s}{'spec hit':>10s}{'wasted':>8s}")
    for name, r in p["authored"].items():
        print(f"   {name:17s}{r['calls']:>7d}{r['outcome_accuracy']*100:>8.1f}%"
              f"{r['entity_error_rate']*100:>7.1f}%"
              f"{r['read_turn_latency_ms']['p50']:>10.0f}"
              f"{r['read_turn_latency_ms']['p90']:>10.0f}"
              f"{r['tool_turn_latency_ms']['p90']:>9.0f}"
              f"{r['speculation']['hit_rate']*100:>9.1f}%"
              f"{r['speculation']['wasted']:>8d}")

    print(f"\nB. Transcript-level correction, independently generated noise")
    print(f"   {'rate':>6s}{'sentences':>11s}{'entities':>10s}{'EER off':>10s}{'EER on':>9s}"
          f"{'reduction':>11s}{'precision':>11s}{'harmful':>9s}")
    for rate, r in p["transcripts"].items():
        print(f"   {rate:>6s}{r['sentences']:>11d}{r['entities']:>10d}"
              f"{r['entity_error_rate_off']*100:>9.1f}%{r['entity_error_rate_on']*100:>8.2f}%"
              f"{r['relative_reduction_pct']:>10.1f}%{r['precision']*100:>10.1f}%"
              f"{r['corrections']['harmful']:>9d}")

    print(f"\nC. End-to-end calls under the same noise")
    print(f"   {'rate':>6s}{'EER off':>10s}{'EER on':>9s}{'task off':>10s}"
          f"{'task on':>9s}{'good':>7s}{'neutral':>9s}{'harmful':>9s}")
    for rate, block in p["noise_sweep"].items():
        on, off = block["full"], block["no_bhasha"]
        q = on["correction_quality"]
        print(f"   {rate:>6s}{off['entity_error_rate']*100:>9.1f}%"
              f"{on['entity_error_rate']*100:>8.1f}%"
              f"{off['outcome_accuracy']*100:>9.1f}%{on['outcome_accuracy']*100:>8.1f}%"
              f"{q['beneficial']:>7d}{q['neutral']:>9d}{q['harmful']:>9d}")

    led = p["ledger"]
    print(f"\nD. Pramaan Ledger")
    print(f"   single-field mutations detected : {led['mutations_detected']}/"
          f"{led['mutations_attempted']} ({led['detection_rate']*100:.1f}%)")
    print(f"   receipt deleted from the chain  : "
          f"{'detected' if led['deletion_detected'] else 'MISSED'} — {led['deletion_reason']}")
    print(f"   forged receipt re-hashed        : "
          f"{'rejected' if led['forged_signature_rejected'] else 'ACCEPTED'}")
    print(f"   unconfirmed writes accepted     : {led['unconfirmed_writes_accepted']}")

    print(f"\n{line}\nHeadline")
    print(f"  Bhasha Bridge   at {h['noise_rate']:.0%} noise over {h['sentences_scored']} "
          f"sentences the entity error rate falls "
          f"{h['entity_error_rate_without_bhasha']*100:.1f}% -> "
          f"{h['entity_error_rate_with_bhasha']*100:.2f}% "
          f"({h['entity_error_reduction_pct']:.1f}% relative), precision "
          f"{h['correction_precision']*100:.1f}%, "
          f"{h['harmful_corrections_transcript']} harmful, "
          f"{h['bhasha_median_ms']:.2f} ms median")
    print(f"                  end to end, task success rises "
          f"{h['task_success_without_bhasha']*100:.1f}% -> "
          f"{h['task_success_with_bhasha']*100:.1f}%")
    print(f"  Speculation     read-turn p50 {h['read_turn_p50_without_speculation']:.0f} -> "
          f"{h['read_turn_p50_with_speculation']:.0f} ms "
          f"({h['read_turn_p50_reduction_pct']:.1f}% lower), p90 "
          f"{h['read_turn_p90_without_speculation']:.0f} -> "
          f"{h['read_turn_p90_with_speculation']:.0f} ms "
          f"({h['read_turn_p90_reduction_pct']:.1f}% lower)")
    print(f"                  hit rate {h['speculation_hit_rate']*100:.1f}% over "
          f"{h['speculations_started']} speculations, "
          f"{h['saved_ms_per_hit']:.0f} ms saved per hit; write turns are never "
          f"speculated, so the all-tool p90 stays at "
          f"{h['write_turn_p90_with_speculation']:.0f} ms")
    print(f"  Pramaan Ledger  {led['detection_rate']*100:.0f}% of tampering detected, "
          f"{led['unconfirmed_writes_accepted']} unconfirmed writes accepted")
    print(f"  Clean scenarios {h['outcome_accuracy_clean']*100:.1f}% of calls reach the "
          f"expected outcome\n{line}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Haanji evaluation harness")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--speed", type=float, default=40.0,
                    help="simulated time scale; latencies are reported in nominal ms")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "research", "results.json"))
    args = ap.parse_args(argv)
    payload = asyncio.run(main_async(args.reps, args.speed, args.out))
    print_report(payload)
    print(f"written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
