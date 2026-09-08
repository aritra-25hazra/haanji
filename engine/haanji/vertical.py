"""Vertical Packs: a business type expressed as data, not as code.

A pack carries everything that makes the agent competent at one kind of
business — the service catalogue, working hours, who does what, the persona,
the refusal rules, the seed vocabulary for Bhasha Bridge, the knowledge base,
and the scenarios the pack must still pass before it ships. Onboarding a new
tenant is filling in a pack; supporting a new industry is writing one. No part
of the engine knows what a dentist is.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Any

import yaml

WEEKDAY_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
PACK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "packs")


class PackError(ValueError):
    pass


@dataclass
class ServiceSpec:
    name: str
    duration_min: int = 30
    price_inr: int | None = None
    staff: list[str] = field(default_factory=list)
    prep_note: str | None = None
    aliases: list[str] = field(default_factory=list)


@dataclass
class Persona:
    agent_name: str = "Haanji"
    business_name: str = "the business"
    greeting: str = "Haanji, kaise madad karun?"
    closing: str = "Dhanyavaad, aapka din shubh ho."
    style: str = "warm, brief, Hinglish"


@dataclass
class Guardrails:
    refuse_topics: list[str] = field(default_factory=list)
    escalate_on: list[str] = field(default_factory=list)
    never_quote_outside_catalogue: bool = True
    max_discount_pct: int = 0
    refusal_line: str = "Iska sahi jawab hamari team hi de payegi, main aapko unse jodta hoon."
    escalation_line: str = "Yeh urgent lag raha hai — main abhi aapko humare staff se joddta hoon."


@dataclass
class ScenarioSpec:
    name: str
    turns: list[dict[str, Any]]
    expect: str = "BOOKED"
    note: str = ""


@dataclass
class Pack:
    pack_id: str
    display_name: str
    version: int = 1
    language: str = "hinglish"
    persona: Persona = field(default_factory=Persona)
    guardrails: Guardrails = field(default_factory=Guardrails)
    staff: list[str] = field(default_factory=list)
    staff_role: str = "staff"
    services: list[ServiceSpec] = field(default_factory=list)
    hours: dict[int, list[str]] = field(default_factory=dict)
    places: list[str] = field(default_factory=list)
    brands: list[str] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)
    variants: dict[str, list[str]] = field(default_factory=dict)
    knowledge: list[tuple[str, str, list[str]]] = field(default_factory=list)
    scenarios: list[ScenarioSpec] = field(default_factory=list)

    # ------------------------------------------------------------------ views
    @property
    def service_names(self) -> list[str]:
        return [s.name for s in self.services]

    def lexicon_seed(self) -> dict[str, Any]:
        """Exactly what :meth:`TenantLexicon.build` needs."""
        return {"services": self.service_names, "staff": self.staff, "places": self.places,
                "brands": self.brands, "phrases": self.phrases,
                "variants": {**self.variants,
                             **{s.name: s.aliases for s in self.services if s.aliases}}}

    def service_aliases(self) -> dict[str, str]:
        """Every spoken form of a service mapped to its catalogue name.

        The dialogue policy and the speculation predictor both resolve
        services through this map, so they cannot disagree about what the
        caller asked for."""
        out: dict[str, str] = {}
        for s in self.services:
            out[s.name.lower()] = s.name
            for alias in s.aliases:
                out[alias.lower()] = s.name
        return out

    def entity_index(self) -> dict[str, str]:
        """Alias map over services, staff and places, used by the evaluation
        harness to decide which entities a sentence actually contains."""
        out = self.service_aliases()
        for person in self.staff:
            out[person.lower()] = person
            for part in person.split():
                if len(part) >= 4 and part.lower() not in {"doctor"}:
                    out[part.lower()] = person
        for place in self.places:
            out[place.lower()] = place
        for canonical, forms in self.variants.items():
            for f in forms:
                out[f.lower()] = canonical
        return out

    def price_of(self, service: str) -> int | None:
        for s in self.services:
            if s.name.lower() == service.lower():
                return s.price_inr
        return None

    def validate(self) -> list[str]:
        """Checks a pack author is expected to fix before shipping."""
        problems: list[str] = []
        if not self.services:
            problems.append("pack defines no services")
        if not self.staff:
            problems.append("pack defines no staff")
        if not self.hours:
            problems.append("pack defines no working hours")
        known = set(self.staff)
        for s in self.services:
            for person in s.staff:
                if person not in known:
                    problems.append(f"service '{s.name}' names unknown staff '{person}'")
            if s.duration_min <= 0:
                problems.append(f"service '{s.name}' has a non-positive duration")
        for sc in self.scenarios:
            if not sc.turns:
                problems.append(f"scenario '{sc.name}' has no turns")
        return problems


# --------------------------------------------------------------------- loading
def _expand_days(spec: str) -> list[int]:
    out: list[int] = []
    for part in str(spec).replace(" ", "").split(","):
        if "-" in part:
            a, b = part.split("-")
            i, j = WEEKDAY_INDEX[a[:3].lower()], WEEKDAY_INDEX[b[:3].lower()]
            out.extend(range(i, j + 1) if i <= j else list(range(i, 7)) + list(range(0, j + 1)))
        elif part:
            out.append(WEEKDAY_INDEX[part[:3].lower()])
    return out


def from_dict(data: dict[str, Any]) -> Pack:
    try:
        pack = Pack(pack_id=data["pack"], display_name=data.get("display_name", data["pack"]),
                    version=int(data.get("version", 1)),
                    language=data.get("language", "hinglish"))
    except KeyError as exc:
        raise PackError(f"pack is missing required field {exc}") from exc

    p = data.get("persona") or {}
    pack.persona = Persona(
        agent_name=p.get("agent_name", "Haanji"),
        business_name=p.get("business_name", pack.display_name),
        greeting=p.get("greeting", Persona.greeting),
        closing=p.get("closing", Persona.closing),
        style=p.get("style", Persona.style))

    g = data.get("guardrails") or {}
    pack.guardrails = Guardrails(
        refuse_topics=list(g.get("refuse", [])),
        escalate_on=list(g.get("escalate_on", [])),
        never_quote_outside_catalogue=bool(g.get("never_quote_outside_catalogue", True)),
        max_discount_pct=int(g.get("max_discount_pct", 0)),
        refusal_line=g.get("refusal_line", Guardrails.refusal_line),
        escalation_line=g.get("escalation_line", Guardrails.escalation_line))

    pack.staff = list(data.get("staff", []))
    pack.staff_role = data.get("staff_role", "staff")
    for s in data.get("services", []):
        pack.services.append(ServiceSpec(
            name=s["name"], duration_min=int(s.get("duration_min", 30)),
            price_inr=s.get("price_inr"), staff=list(s.get("staff", [])),
            prep_note=s.get("prep_note"), aliases=list(s.get("aliases", []))))
    for days, spec in (data.get("hours") or {}).items():
        if not spec:
            continue
        for wd in _expand_days(days):
            pack.hours[wd] = list(spec)

    lex = data.get("lexicon") or {}
    pack.places = list(lex.get("places", []))
    pack.brands = list(lex.get("brands", []))
    pack.phrases = list(lex.get("phrases", []))
    pack.variants = {k: list(v) for k, v in (lex.get("variants") or {}).items()}

    for k in data.get("knowledge", []):
        pack.knowledge.append((k["q"], k["a"], list(k.get("tags", []))))
    for sc in data.get("scenarios", []):
        pack.scenarios.append(ScenarioSpec(name=sc["name"], turns=list(sc.get("turns", [])),
                                           expect=sc.get("expect", "BOOKED"),
                                           note=sc.get("note", "")))
    return pack


def load_pack(path_or_id: str) -> Pack:
    path = path_or_id
    if not os.path.exists(path):
        path = os.path.join(PACK_DIR, f"{path_or_id}.yaml")
    if not os.path.exists(path):
        raise PackError(f"no pack at {path_or_id}")
    with open(path, "r", encoding="utf-8") as fh:
        return from_dict(yaml.safe_load(fh))


def list_packs(directory: str | None = None) -> list[str]:
    directory = directory or PACK_DIR
    if not os.path.isdir(directory):
        return []
    return sorted(f[:-5] for f in os.listdir(directory) if f.endswith(".yaml"))
