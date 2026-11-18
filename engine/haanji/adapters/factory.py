"""Name -> dialogue adapter. The one place the configuration string is read."""
from __future__ import annotations

from .mock import MockLLM


def make_llm(name: str, policy, pack, registry, **kw):
    """``mock`` is the deterministic policy; ``claude`` and ``gemini`` are hosted
    models with the policy underneath them for confirmations and for the day
    the API is down."""
    key = (name or "mock").lower()
    if key == "mock":
        return MockLLM(policy)
    if key == "claude":
        from .claude import ClaudeLLM  # lazy: the SDK is an optional extra
        return ClaudeLLM(policy, pack, registry, **kw)
    if key == "gemini":
        from .gemini import GeminiLLM  # plain httpx; no SDK
        return GeminiLLM(policy, pack, registry, **kw)
    raise ValueError(f"unknown LLM provider {name!r}; expected 'mock', 'claude' or 'gemini'")
