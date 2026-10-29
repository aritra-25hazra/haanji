"""Speculative Turn Execution — branch prediction for dialogue.

Read-only tools are predicted from partial transcripts and executed while the
caller is still speaking, so that the model's real tool call hits a warm cache.
Correctness never depends on the guess: only read-only tools may be speculated,
a cached result is used only on an exact argument match, entries expire and can
be claimed once, and any write clears the cache.
"""
from .cache import SpecStats, SpeculationCache
from .engine import SpeculationEngine
from .predictor import IntentPredictor, ToolGuess

__all__ = ["IntentPredictor", "ToolGuess", "SpeculationCache", "SpecStats", "SpeculationEngine"]
