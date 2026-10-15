"""Name -> dialogue adapter. The one place the configuration string is read."""
from __future__ import annotations

from .mock import MockLLM


def make_llm(name: str, policy, pack, registry, **kw):
    """``mock`` is the deterministic policy; ``claude`` is the hosted model with
    the policy underneath it for confirmations and for the day the API is down."""
    key = (name or "mock").lower()
    if key == "mock":
        return MockLLM(policy)
    if key == "claude":
        from .claude import ClaudeLLM          # lazy: the SDK is an optional extra
        return ClaudeLLM(policy, pack, registry, **kw)
    raise ValueError(f"unknown LLM provider {name!r}; expected 'mock' or 'claude'")
