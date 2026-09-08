"""Predicting the next tool from a partial transcript.

Deliberately cheap: deterministic triggers with high precision, plus a tiny
logistic model over bag-of-cue features. Asking a language model to predict
would cost more time than the speculation can possibly save, which would
defeat the point.

The arguments a guess carries are produced by :mod:`haanji.nlu`, the same
module the dialogue policy uses. Sharing the extractor is what lets a
speculative result be claimed by the real turn: the claim requires the
arguments to be identical, and identical arguments are only reachable when
both sides normalise the caller's words the same way.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any

from .. import nlu
from ..models import ConversationContext


@dataclass
class ToolGuess:
    tool: str
    confidence: float
    args: dict[str, Any] = field(default_factory=dict)

    def key_args(self) -> dict[str, Any]:
        return dict(sorted(self.args.items()))


class IntentPredictor:
    """Rules first, then a small scorer for anything the rules missed."""

    # Coefficients fitted offline on the harness scenario packs and kept in
    # source so the behaviour stays inspectable and reproducible.
    WEIGHTS = {
        "date": 1.6, "time": 1.5, "booking": 1.9, "question": -1.2,
        "identity": -0.4, "cancel": -1.8, "len": 0.12, "has_service": 0.7,
    }
    BIAS = -2.4

    def __init__(self, services: list[str] | None = None):
        self.services = services or []

    def predict(self, partial: str, ctx: ConversationContext) -> list[ToolGuess]:
        w = nlu.words(partial)
        guesses: list[ToolGuess] = []

        has_date = bool(w & nlu.DATE_WORDS)
        has_time = bool(w & nlu.TIME_WORDS)
        has_book = bool(w & nlu.BOOKING_VERBS)
        has_q = bool(w & nlu.QUESTION_WORDS)
        has_id = bool(w & nlu.IDENTITY_WORDS)
        has_cancel = bool(w & nlu.CANCEL_WORDS)
        service = nlu.match_service(partial, self.services) or ctx.service

        # --- rule 1: the caller is heading for a slot question
        if (has_date or has_time) and has_book and not has_cancel:
            guesses.append(ToolGuess("check_availability", 0.82, {
                "service": service or "__default__",
                "date": nlu.normalise_date(partial, ctx.date),
            }))
        # --- rule 2: a price / timing / policy question
        if has_q and not has_book:
            guesses.append(ToolGuess("search_knowledge", 0.70, {"query": partial.strip()}))
        # --- rule 3: a returning caller identifying themselves
        if has_id and ctx.customer_phone:
            guesses.append(ToolGuess("lookup_customer", 0.65, {"phone": ctx.customer_phone}))

        # --- scorer, for availability turns the rules did not catch
        if not any(g.tool == "check_availability" for g in guesses):
            z = (self.BIAS
                 + self.WEIGHTS["date"] * has_date
                 + self.WEIGHTS["time"] * has_time
                 + self.WEIGHTS["booking"] * has_book
                 + self.WEIGHTS["question"] * has_q
                 + self.WEIGHTS["identity"] * has_id
                 + self.WEIGHTS["cancel"] * has_cancel
                 + self.WEIGHTS["len"] * min(len(w), 12)
                 + self.WEIGHTS["has_service"] * bool(service))
            p = 1 / (1 + math.exp(-z))
            if p >= 0.60:
                guesses.append(ToolGuess("check_availability", round(p, 3), {
                    "service": service or "__default__",
                    "date": nlu.normalise_date(partial, ctx.date),
                }))

        best: dict[str, ToolGuess] = {}
        for g in guesses:
            if g.tool not in best or g.confidence > best[g.tool].confidence:
                best[g.tool] = g
        return sorted(best.values(), key=lambda g: -g.confidence)[:2]
