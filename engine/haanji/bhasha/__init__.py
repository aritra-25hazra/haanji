"""Bhasha Bridge — per-tenant Hinglish accuracy layer.

The problem: a general speech model mangles exactly the words a booking depends
on (service names, staff names, localities), and a model per business does not
scale.  The answer here is to bias and post-correct against a lexicon built
automatically from data the business already entered.
"""
from .phonetics import phonetic_key, edit_distance
from .lexicon import LexEntry, EntryType, TenantLexicon
from .bridge import BhashaBridge

__all__ = ["phonetic_key", "edit_distance", "LexEntry", "EntryType",
           "TenantLexicon", "BhashaBridge"]
