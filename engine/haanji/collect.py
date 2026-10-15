"""Real recogniser output, measured the same way as the synthetic kind.

The benchmark's corruption model is a model. This module is the other half of
the honesty argument: a fixed list of prompt sentences built from the packs,
a (heard, truth) pair format that any recogniser's output can be written in,
and the same entity-error measurement run over those pairs with the Bhasha
Bridge off and on. ``research/collect/`` holds the scripts that fill the
manifest (volunteers through ``/record``, or synthetic speech through the
operating system's voices) and transcribe it; this module is what they feed.
"""
from __future__ import annotations
import json
import random
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import nlu
from .bhasha.bridge import BhashaBridge
from .bhasha.lexicon import TenantLexicon
from .config import BhashaConfig
from .models import Token, Transcript
from .scenario import scenarios_of
from .vertical import Pack

_PUNCT = re.compile(r"[^\w\s'-]", re.UNICODE)
_SPACES = re.compile(r"\s+")


def normalise(text: str) -> str:
    """What every recogniser's output is reduced to before scoring: lower
    case, no punctuation, single spaces. Entities are matched as words."""
    return _SPACES.sub(" ", _PUNCT.sub(" ", text.lower())).strip()


# ----------------------------------------------------------------- prompts
TEMPLATES = [
    "{service} karwana hai kal",
    "{service} ka kitna charge hai",
    "kal subah {service} ke liye time chahiye",
    "{staff} se milna hai parso",
    "{staff} ke saath {service} book karna hai",
    "{place} wali branch mein {service} ka slot hai kya",
    "{place} mein aap log hain na",
]


def prompts_for(pack: Pack, limit: int = 40, seed: int = 11) -> list[dict[str, Any]]:
    """Sentences a volunteer reads aloud for one pack: every scenario line the
    pack ships, then entity-bearing frames over the catalogue, shuffled with a
    fixed seed so every volunteer sees the same order."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(text: str, kind: str) -> None:
        key = normalise(text)
        if key and key not in seen:
            seen.add(key)
            out.append({"pack": pack.pack_id, "truth": text.strip(), "kind": kind})

    for sc in scenarios_of(pack):
        for u in sc.utterances:
            add(u.truth, "scenario")
    services = pack.service_names
    staff = pack.staff or ["staff"]
    places = pack.places or ["branch"]
    frames: list[str] = []
    for i, service in enumerate(services):
        for t in TEMPLATES:
            frames.append(t.format(service=service, staff=staff[i % len(staff)],
                                   place=places[i % len(places)]))
    random.Random(seed).shuffle(frames)
    for f in frames:
        add(f, "catalogue")
    return out[:limit]


# -------------------------------------------------------------------- pairs
@dataclass
class Pair:
    """One utterance as a recogniser heard it, next to what was said."""
    pack: str
    truth: str
    heard: str
    confidences: list[float] = field(default_factory=list)   # per heard word, 0..1
    speaker: str = ""
    recogniser: str = ""
    id: str = ""

    def tokens(self, default_conf: float = 0.9) -> list[Token]:
        words = normalise(self.heard).split()
        confs = list(self.confidences) + [default_conf] * (len(words) - len(self.confidences))
        return [Token(w, max(0.0, min(1.0, float(c)))) for w, c in zip(words, confs)]


def load_pairs(path: str | Path) -> list[Pair]:
    pairs: list[Pair] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        pairs.append(Pair(pack=d["pack"], truth=d["truth"], heard=d.get("heard", ""),
                          confidences=[float(c) for c in d.get("confidences", [])],
                          speaker=d.get("speaker", ""), recogniser=d.get("recogniser", ""),
                          id=d.get("id", "")))
    return pairs


def entity_errors(truth: str, hypothesis: str, index: dict[str, str]) -> tuple[int, int]:
    gold = nlu.find_entities(normalise(truth), index)
    pred = nlu.find_entities(normalise(hypothesis), index)
    return len(gold), len(gold - pred) + len(pred - gold)


def word_error_rate(truth: str, hypothesis: str) -> float:
    """Plain WER, for the reader who wants the conventional number too."""
    a, b = normalise(truth).split(), normalise(hypothesis).split()
    if not a:
        return 0.0 if not b else 1.0
    prev = list(range(len(b) + 1))
    for i, wa in enumerate(a, 1):
        cur = [i]
        for j, wb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (wa != wb)))
        prev = cur
    return prev[-1] / len(a)


def real_pairs_experiment(packs: Iterable[Pack], pairs: list[Pair],
                          config: BhashaConfig | None = None) -> dict[str, Any]:
    """The transcript-level experiment of ``haanji.bench`` over recorded pairs.

    Returns the same quantities (entity error rate off and on, correction
    precision, harmful count) overall, per pack and per speaker, plus plain
    word error rate so the two instruments can be compared on the same data."""
    by_pack = {p.pack_id: p for p in packs}
    cfg = config or BhashaConfig(enabled=True)
    bridges: dict[str, BhashaBridge] = {}
    indexes: dict[str, dict[str, str]] = {}

    def tally() -> dict[str, Any]:
        return {"utterances": 0, "entities": 0, "err_off": 0, "err_on": 0,
                "beneficial": 0, "neutral": 0, "harmful": 0, "wer": [], "elapsed_ms": []}

    overall = tally()
    per_pack: dict[str, dict[str, Any]] = {}
    per_speaker: dict[str, dict[str, Any]] = {}
    examples: list[dict[str, Any]] = []
    for pair in pairs:
        pack = by_pack.get(pair.pack)
        if pack is None:
            continue
        if pair.pack not in bridges:
            lex = TenantLexicon.build(version=pack.version, **pack.lexicon_seed())
            bridges[pair.pack] = BhashaBridge(lex, cfg)
            indexes[pair.pack] = pack.entity_index()
        bridge, index = bridges[pair.pack], indexes[pair.pack]
        corrected = bridge.correct(Transcript(pair.tokens(), True))
        g, e_off = entity_errors(pair.truth, pair.heard, index)
        _, e_on = entity_errors(pair.truth, corrected.text, index)
        truth_padded = f" {normalise(pair.truth)} "
        gold = nlu.find_entities(normalise(pair.truth), index)
        quality = {"beneficial": 0, "neutral": 0, "harmful": 0}
        for c in corrected.corrections:
            if f" {c.from_token.lower()} " in truth_padded:
                quality["harmful"] += 1
            elif c.to_surface in gold:
                quality["beneficial"] += 1
            else:
                quality["neutral"] += 1
        for bucket in (overall, per_pack.setdefault(pair.pack, tally()),
                       per_speaker.setdefault(pair.speaker or "unknown", tally())):
            bucket["utterances"] += 1
            bucket["entities"] += g
            bucket["err_off"] += e_off
            bucket["err_on"] += e_on
            for k, v in quality.items():
                bucket[k] += v
            bucket["wer"].append(word_error_rate(pair.truth, pair.heard))
            bucket["elapsed_ms"].append(corrected.elapsed_ms)
        if corrected.corrections or e_off:
            examples.append({"id": pair.id, "pack": pair.pack, "speaker": pair.speaker,
                             "truth": pair.truth, "heard": pair.heard, "corrected": corrected.text,
                             "corrections": [{"from": c.from_token, "to": c.to_surface}
                                             for c in corrected.corrections],
                             "entity_errors_off": e_off, "entity_errors_on": e_on})

    def finish(t: dict[str, Any]) -> dict[str, Any]:
        n_corr = t["beneficial"] + t["neutral"] + t["harmful"]
        return {
            "utterances": t["utterances"], "entities": t["entities"],
            "entity_error_rate_off": round(t["err_off"] / t["entities"], 4) if t["entities"] else 0.0,
            "entity_error_rate_on": round(t["err_on"] / t["entities"], 4) if t["entities"] else 0.0,
            "relative_reduction_pct": round(100 * (t["err_off"] - t["err_on"]) / t["err_off"], 1)
                if t["err_off"] else 0.0,
            "corrections": {"beneficial": t["beneficial"], "neutral": t["neutral"], "harmful": t["harmful"]},
            "precision": round(t["beneficial"] / n_corr, 4) if n_corr else 0.0,
            "word_error_rate": round(statistics.fmean(t["wer"]), 4) if t["wer"] else 0.0,
            "median_correct_ms": round(statistics.median(t["elapsed_ms"]), 3) if t["elapsed_ms"] else 0.0,
        }

    return {"overall": finish(overall),
            "per_pack": {k: finish(v) for k, v in per_pack.items()},
            "per_speaker": {k: finish(v) for k, v in per_speaker.items()},
            "examples": examples}
