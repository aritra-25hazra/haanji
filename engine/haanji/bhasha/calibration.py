"""Calibrating the confidence gate to the recogniser in front of it.

The two-condition rule's first condition — "the recogniser was not sure" —
assumes the recogniser's confidence means something. The pilot showed it
does not, for Whisper, at the threshold the mock recogniser was tuned to
(0.85). This module learns the threshold from (heard, truth) pairs: every
heard token is labelled right or wrong by alignment, and the threshold is
the one that best separates them (Youden's J on the ROC curve), per
recogniser. The bridge reads it through ``BhashaConfig.conf_high``.
"""
from __future__ import annotations
import difflib
import json
import re
from pathlib import Path
from typing import Any, Iterable

_WORD = re.compile(r"[^\w\s']")


def _norm(text: str) -> list[str]:
    return _WORD.sub(" ", text.lower()).split()


def labelled_tokens(pairs: Iterable[Any]) -> list[tuple[float, bool]]:
    """(confidence, was_wrong) for every heard token with a confidence."""
    out: list[tuple[float, bool]] = []
    for p in pairs:
        heard, truth = _norm(p.heard), _norm(p.truth)
        confs = list(p.confidences)
        if len(confs) != len(heard):
            continue                                 # cannot align confidences to words
        sm = difflib.SequenceMatcher(a=truth, b=heard, autojunk=False)
        wrong = [True] * len(heard)
        for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for j in range(j1, j2):
                    wrong[j] = False
        out.extend(zip(confs, wrong))
    return out


def roc(points: list[tuple[float, bool]]) -> list[dict[str, float]]:
    """TPR/FPR of the rule 'treat as unsure when confidence < t', for every candidate t."""
    wrong_n = sum(1 for _, w in points if w)
    right_n = len(points) - wrong_n
    if not wrong_n or not right_n:
        return []
    thresholds = sorted({round(c, 2) for c, _ in points} | {0.0, 1.01})
    out = []
    for t in thresholds:
        tp = sum(1 for c, w in points if w and c < t)          # wrong token, gate open: good
        fp = sum(1 for c, w in points if (not w) and c < t)    # right token, gate open: a correction could do harm
        out.append({"threshold": t, "tpr": tp / wrong_n, "fpr": fp / right_n, "j": tp / wrong_n - fp / right_n})
    return out


def fit_threshold(pairs: Iterable[Any], floor: float = 0.3, ceiling: float = 0.99) -> dict[str, Any]:
    """The threshold that maximises Youden's J, with the curve it came from."""
    pts = labelled_tokens(pairs)
    curve = roc(pts)
    if not curve:
        return {"threshold": 0.85, "tokens": len(pts), "reason": "no labelled tokens", "curve": []}
    usable = [c for c in curve if floor <= c["threshold"] <= ceiling] or curve
    best = max(usable, key=lambda c: c["j"])
    wrong_n = sum(1 for _, w in pts if w)
    return {"threshold": best["threshold"], "tpr": round(best["tpr"], 3), "fpr": round(best["fpr"], 3),
            "youden_j": round(best["j"], 3), "tokens": len(pts), "wrong_tokens": wrong_n,
            "wrong_rate": round(wrong_n / len(pts), 3), "auc": round(_auc(curve), 3),
            "curve": [{k: round(v, 3) for k, v in c.items()} for c in curve]}


def _auc(curve: list[dict[str, float]]) -> float:
    pts = sorted((c["fpr"], c["tpr"]) for c in curve)
    area = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        area += (x1 - x0) * (y0 + y1) / 2
    return area


class Calibration:
    """Per-recogniser thresholds, loaded from research/calibration.json."""

    def __init__(self, table: dict[str, float] | None = None, default: float = 0.85):
        self.table = dict(table or {})
        self.default = default

    @classmethod
    def load(cls, path: str | Path, default: float = 0.85) -> "Calibration":
        p = Path(path)
        if not p.exists():
            return cls({}, default)
        d = json.loads(p.read_text(encoding="utf-8"))
        return cls({k: v["threshold"] for k, v in d.get("recognisers", {}).items()}, default)

    def threshold_for(self, recogniser: str | None) -> float:
        """Longest-prefix match: 'faster-whisper:small:en:biased' finds 'faster-whisper:small:en'."""
        if not recogniser:
            return self.default
        best = None
        for name, t in self.table.items():
            if recogniser.startswith(name) and (best is None or len(name) > len(best[0])):
                best = (name, t)
        return best[1] if best else self.default
