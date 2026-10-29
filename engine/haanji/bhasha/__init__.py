"""Bhasha Bridge — per-tenant Hinglish accuracy layer.

The problem: a general speech model mangles exactly the words a booking depends
on (service names, staff names, localities), and a model per business does not
scale.  The answer here is to bias and post-correct against a lexicon built
automatically from data the business already entered.
"""
from .bridge import BhashaBridge
from .lexicon import EntryType, LexEntry, TenantLexicon
from .phonetics import edit_distance, phonetic_key

__all__ = ["phonetic_key", "edit_distance", "LexEntry", "EntryType",
           "TenantLexicon", "BhashaBridge"]
