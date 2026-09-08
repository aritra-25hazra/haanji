"""Scenarios: scripted callers used by the demo, the tests and the benchmark.

Each turn carries both what the recogniser produced (``heard``) and what the
caller actually said (``truth``). Keeping the pair is what makes an honest
measurement possible: the Entity Error Rate is computed against ``truth``, so
the harness can tell a genuine repair from a lucky guess.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .vertical import Pack, ScenarioSpec


@dataclass
class Utterance:
    heard: str
    truth: str = ""
    low_conf: list[str] = field(default_factory=list)
    barge_in: bool = False

    def __post_init__(self) -> None:
        if not self.truth:
            self.truth = self.heard

    @property
    def corrupted(self) -> bool:
        return self.heard != self.truth


@dataclass
class Scenario:
    name: str
    pack_id: str
    utterances: list[Utterance]
    expect: str = "BOOKED"
    note: str = ""

    @property
    def corrupted_turns(self) -> int:
        return sum(1 for u in self.utterances if u.corrupted)


def scenarios_of(pack: Pack) -> list[Scenario]:
    out: list[Scenario] = []
    for spec in pack.scenarios:
        out.append(from_spec(pack.pack_id, spec))
    return out


def from_spec(pack_id: str, spec: ScenarioSpec) -> Scenario:
    utterances = [Utterance(heard=t["heard"], truth=t.get("truth", ""),
                            low_conf=list(t.get("low_conf", [])),
                            barge_in=bool(t.get("barge_in", False)))
                  for t in spec.turns]
    return Scenario(spec.name, pack_id, utterances, spec.expect, spec.note)
