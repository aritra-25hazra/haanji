"""The per-tenant lexicon: what the business already told us, indexed by sound."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

from .phonetics import phonetic_key, phrase_key


class EntryType(str, Enum):
    SERVICE = "SERVICE"
    STAFF = "STAFF"
    PLACE = "PLACE"
    BRAND = "BRAND"
    PHRASE = "PHRASE"


TYPE_PRIOR = {
    EntryType.SERVICE: 1.25,   # getting the service wrong breaks the booking
    EntryType.STAFF: 1.10,
    EntryType.PLACE: 1.00,
    EntryType.BRAND: 0.95,
    EntryType.PHRASE: 0.85,
}


@dataclass
class LexEntry:
    surface: str
    entry_type: EntryType = EntryType.PHRASE
    variants: list[str] = field(default_factory=list)
    weight: float = 1.0

    @property
    def words(self) -> int:
        return len(self.surface.split())

    def forms(self) -> list[str]:
        """The canonical surface plus every spelling the tenant told us about."""
        return [self.surface, *self.variants]

    @staticmethod
    def key_of(form: str) -> str:
        return phrase_key(form) if len(form.split()) > 1 else phonetic_key(form)

    def keys(self) -> set[str]:
        return {k for k in (self.key_of(f) for f in self.forms()) if k}

    def forms_matching(self, key: str, n_words: int) -> list[str]:
        """Forms of this entry that are *n* words long and land on ``key``.

        A variant can be shorter than the canonical surface — callers say
        "cleaning" for "teeth cleaning" — so the length test belongs to the
        matched form, not to the entry."""
        return [f for f in self.forms()
                if len(f.split()) == n_words and self.key_of(f) == key]


class TenantLexicon:
    """Sound-indexed vocabulary for one tenant, plus the hint list for the ASR."""

    def __init__(self, entries: list[LexEntry] | None = None, version: int = 1):
        self.version = version
        self.entries: list[LexEntry] = []
        self.by_key: dict[str, list[LexEntry]] = {}
        for e in entries or []:
            self.add(e)

    # ---------------------------------------------------------------- building
    def add(self, entry: LexEntry) -> None:
        self.entries.append(entry)
        for k in entry.keys():
            self.by_key.setdefault(k, []).append(entry)

    TITLES = {"dr", "dr.", "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "shri", "smt", "prof", "prof."}

    @classmethod
    def build(cls, *, services: list[str] | None = None, staff: list[str] | None = None,
              places: list[str] | None = None, brands: list[str] | None = None,
              phrases: list[str] | None = None, variants: dict[str, list[str]] | None = None,
              version: int = 1) -> "TenantLexicon":
        """Build a lexicon from the data a tenant already entered during onboarding."""
        variants = variants or {}
        lex = cls(version=version)
        for group, etype in ((services, EntryType.SERVICE), (staff, EntryType.STAFF),
                             (places, EntryType.PLACE), (brands, EntryType.BRAND),
                             (phrases, EntryType.PHRASE)):
            for surface in group or []:
                lex.add(LexEntry(surface=surface, entry_type=etype,
                                 variants=variants.get(surface, []),
                                 weight=TYPE_PRIOR[etype]))
                # Callers rarely say the full form: "Dr Sheikh" is heard as
                # "Sheikh". Index the distinctive tokens of names and places too.
                if etype in (EntryType.STAFF, EntryType.PLACE) and len(surface.split()) > 1:
                    for part in surface.split():
                        if part.lower() in cls.TITLES or len(part) < 4:
                            continue
                        lex.add(LexEntry(surface=part, entry_type=etype,
                                         weight=TYPE_PRIOR[etype] * 0.9))
        return lex

    # ---------------------------------------------------------------- runtime
    def candidates(self, key: str) -> list[LexEntry]:
        return self.by_key.get(key, [])

    def hints(self, limit: int = 60) -> list[str]:
        """Top surfaces by weight, sent to the recogniser as biasing hints."""
        ranked = sorted(self.entries, key=lambda e: -e.weight)
        return [e.surface for e in ranked[:limit]]

    def reinforce(self, surface: str, delta: float) -> None:
        """Feedback: corrections that led to a booking gain weight, repairs lose it."""
        for e in self.entries:
            if e.surface == surface:
                e.weight = max(0.2, min(3.0, e.weight + delta))

    def __len__(self) -> int:
        return len(self.entries)
