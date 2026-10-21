#!/usr/bin/env python3
"""Fit the speculation predictor's scorer from logged partials, and measure it.

The predictor in haanji/speculation/predictor.py has rules plus a small
logistic scorer whose weights were set by hand. This script replays every
packaged scenario word by word (what the recogniser's partials look like),
logs the scorer's features for each partial together with whether the real
turn then called check_availability, fits logistic regression by gradient
descent (no NumPy), reports held-out accuracy by leave-one-pack-out, and
runs the benchmark's "full" configuration with the fitted weights to see
what happens to the speculation hit rate and the wasted count. Nothing is
changed in the engine unless the numbers are better.

    python research/harness/predictor_fit.py
"""
from __future__ import annotations
import asyncio
import datetime as dt
import json
import math
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from haanji import bench, nlu                                   # noqa: E402
from haanji.clock import set_speed                              # noqa: E402
from haanji.config import EngineConfig                          # noqa: E402
from haanji.models import ConversationContext                   # noqa: E402
from haanji.pipeline import CallSession                         # noqa: E402
from haanji.pramaan.ledger import Ledger                        # noqa: E402
from haanji.scenario import scenarios_of                        # noqa: E402
from haanji.speculation.predictor import IntentPredictor        # noqa: E402
from haanji.tools.builtin import build_registry, open_backend   # noqa: E402
from haanji.vertical import list_packs, load_pack               # noqa: E402

OUT = ROOT / "research" / "predictor_fit.json"
FEATURES = ["date", "time", "booking", "question", "identity", "cancel", "len", "has_service"]


def features(partial: str, ctx: ConversationContext, services) -> dict[str, float]:
    w = nlu.words(partial)
    return {"date": float(bool(w & nlu.DATE_WORDS)), "time": float(bool(w & nlu.TIME_WORDS)),
            "booking": float(bool(w & nlu.BOOKING_VERBS)), "question": float(bool(w & nlu.QUESTION_WORDS)),
            "identity": float(bool(w & nlu.IDENTITY_WORDS)), "cancel": float(bool(w & nlu.CANCEL_WORDS)),
            "len": float(min(len(w), 12)), "has_service": float(bool(nlu.match_service(partial, services) or ctx.service))}


async def log_pack(pid: str) -> list[dict]:
    """Replay a pack's scenarios; one row per partial (prefix of each caller line)."""
    pack = load_pack(pid)
    rows = []
    for sc in scenarios_of(pack):
        backend, _ = open_backend(pack, "t_fit", today=dt.date(2026, 9, 7))
        registry = build_registry("t_fit", backend, pack, Ledger(sqlite3.connect(":memory:")))
        s = CallSession(tenant_id="t_fit", pack=pack, backend=backend, registry=registry, config=EngineConfig())
        await s.open()
        for u in sc.utterances:
            words = u.truth.split()
            snapshot = [features(" ".join(words[:k]), s.ctx, pack.service_aliases()) for k in range(3, len(words) + 1)]
            rec = await s.handle_text_turn(u.truth)
            label = float("check_availability" in rec.tools)
            for k, f in enumerate(snapshot):
                rows.append({"pack": pid, "scenario": sc.name, "k": k + 3, **f, "y": label})
    return rows


def fit(rows: list[dict], l2: float = 0.01, epochs: int = 400, lr: float = 0.05) -> tuple[dict[str, float], float]:
    w = {k: 0.0 for k in FEATURES}
    b = 0.0
    for _ in range(epochs):
        gw = {k: 0.0 for k in FEATURES}
        gb = 0.0
        for r in rows:
            z = b + sum(w[k] * r[k] for k in FEATURES)
            p = 1 / (1 + math.exp(-max(min(z, 30), -30)))
            err = p - r["y"]
            for k in FEATURES:
                gw[k] += err * r[k]
            gb += err
        n = len(rows)
        for k in FEATURES:
            w[k] -= lr * (gw[k] / n + l2 * w[k])
        b -= lr * gb / n
    return w, b


def accuracy(rows, w, b, thr=0.6) -> dict:
    tp = fp = fn = tn = 0
    for r in rows:
        z = b + sum(w[k] * r[k] for k in FEATURES)
        p = 1 / (1 + math.exp(-max(min(z, 30), -30)))
        pred = p >= thr
        if pred and r["y"]: tp += 1
        elif pred: fp += 1
        elif r["y"]: fn += 1
        else: tn += 1
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(prec, 3), "recall": round(rec, 3), "accuracy": round((tp + tn) / max(len(rows), 1), 3), "n": len(rows)}


async def bench_with(weights: dict[str, float], bias: float) -> dict:
    old_w, old_b = IntentPredictor.WEIGHTS, IntentPredictor.BIAS
    IntentPredictor.WEIGHTS, IntentPredictor.BIAS = weights, bias
    try:
        packs = [load_pack(p) for p in list_packs()]
        r = await bench.run_config("full", packs, reps=3, seed=0)
        return {"hit_rate": r["speculation"]["hit_rate"], "started": r["speculation"]["started"],
                "wasted": r["speculation"]["wasted"], "read_p50": r["read_turn_latency_ms"]["p50"],
                "outcome_accuracy": r["outcome_accuracy"]}
    finally:
        IntentPredictor.WEIGHTS, IntentPredictor.BIAS = old_w, old_b


def main() -> int:
    set_speed(200.0)
    rows = []
    for pid in list_packs():
        rows += asyncio.run(log_pack(pid))
    pos = sum(r["y"] for r in rows)
    print(f"{len(rows)} partials logged from {len(list_packs())} packs; {pos:.0f} positive ({pos/len(rows):.0%})")
    # leave-one-pack-out
    cv = []
    for pid in list_packs():
        train = [r for r in rows if r["pack"] != pid]
        test = [r for r in rows if r["pack"] == pid]
        if not test:
            continue
        w, b = fit(train)
        cv.append({"held_out": pid, **accuracy(test, w, b)})
        print(f"  held out {pid:20s} precision {cv[-1]['precision']:.2f} recall {cv[-1]['recall']:.2f}")
    hand = {"precision": None}
    hand = accuracy(rows, IntentPredictor.WEIGHTS, IntentPredictor.BIAS)
    w, b = fit(rows)
    fitted = accuracy(rows, w, b)
    print(f"hand-set weights on all partials: {hand}\nfitted weights on all partials:   {fitted}")
    print("benchmark with hand-set weights…")
    bh = asyncio.run(bench_with(IntentPredictor.WEIGHTS, IntentPredictor.BIAS))
    print("benchmark with fitted weights…")
    bf = asyncio.run(bench_with(w, b))
    print(f"  hand-set: hit {bh['hit_rate']:.1%} started {bh['started']} wasted {bh['wasted']} read p50 {bh['read_p50']}")
    print(f"  fitted:   hit {bf['hit_rate']:.1%} started {bf['started']} wasted {bf['wasted']} read p50 {bf['read_p50']}")
    OUT.write_text(json.dumps({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                               "partials": len(rows), "positives": pos, "cross_validation": cv,
                               "hand_weights": {"weights": IntentPredictor.WEIGHTS, "bias": IntentPredictor.BIAS, **hand},
                               "fitted": {"weights": {k: round(v, 3) for k, v in w.items()}, "bias": round(b, 3), **fitted},
                               "bench": {"hand": bh, "fitted": bf}}, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
