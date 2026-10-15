# Claude dialogue adapter (B2) — design

**Date:** 2026-10-15
**Scope:** a real language model behind the engine's dialogue boundary, without
giving up any of the three guarantees; the seam that makes it swappable; an
ablation that measures what it costs and what it changes.

## What exists, honestly

`adapters/__init__.py` declares `LLMAdapter.respond(system, history, tools)`
and `adapters/mock.py` has `MockLLM`, but `pipeline.py` never calls either —
it calls `DialoguePolicy.plan()` and `.after_tools()` directly. The README's
"replace one adapter class" is therefore a promise, not a seam. B2 builds the
seam first, with `MockLLM` as the default so every existing test stays green,
then adds `ClaudeLLM`.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Seam | `CallSession` owns `self.llm`; both phases of a turn go through `await self.llm.respond(system, [{"content", "context", "results"?}], tools)`. Mock delegates to the policy. | One boundary, one protocol; the pipeline stops knowing the policy's method names. |
| Confirmation | **Never the model's call.** A `requires_confirmation` tool requested while no confirmation is pending is intercepted: the adapter fills the context from the model's arguments and returns the pack's own read-back question; `ctx.pending_confirmation` is set. While a confirmation is pending, the adapter delegates the whole turn to the deterministic policy, which already handles yes/no/change and produces the tool call with `needs_confirmation=True` — the ledger then has its proof. | The write path is identical with or without the model; the ledger's guarantee does not depend on prompt quality. |
| Guardrails | Unchanged — checked before the adapter runs; refusals and escalations are also described in the system prompt. | Belt and braces. |
| Speculation | Unchanged. Its predictor derives arguments through `nlu.py`; the model's arguments will often differ, so the hit rate will fall. | Measured and reported, not hidden. |
| Failure | Any adapter failure (auth, network, rate limit, bad response) falls back to the deterministic policy for that turn and counts `fallbacks`. | A call never dies because a vendor did. |
| Model | `claude-opus-4-8` by default (`HAANJI_LLM_MODEL`), `output_config.effort="low"` (`HAANJI_LLM_EFFORT`), adaptive thinking, `max_tokens=1024`, 20 s timeout, one retry. | Skill default; a receptionist's turns are short. |
| SDK | Official `anthropic` package, optional extra `[llm]`, imported lazily inside the adapter. | The engine core still imports no vendor SDK; the README wording becomes "outside its adapters". |
| Prompt | Built from the pack: persona, language, catalogue with durations and prices, staff, hours, refusals and escalations, knowledge Q&A; stable text with `cache_control` so it caches. | The model knows exactly what the deterministic policy knows. |
| Tools | The registry's schemas converted to Anthropic's `input_schema` form (the `x-haanji` block dropped, confirmation tools' descriptions say the engine will ask the caller first), plus a pseudo-tool `end_call` the model calls to end the conversation. | The policy's decisions are already tool calls; the model speaks the same language. |
| Conversation | Messages rebuilt each turn from `ctx.turns` (caller → user, agent → assistant, leading agent greeting folded into the system prompt), ending with the current caller text; after tools, the previous assistant content plus `tool_result` blocks keyed by `tool_use_id`. | Stateless per turn except for the ids of the tool calls in flight. |
| Secrets | `ANTHROPIC_API_KEY` from the environment or `engine/.env` (gitignored; a tiny loader in `config.py`); on Render as `sync: false`. | Never in the repo or in chat. |

## Contracts

`adapters/prompt.py` (vendor-neutral)
- `build_system_prompt(pack) -> str`
- `tool_schemas(registry) -> list[dict]` — the registry's schemas as-is.

`adapters/mock.py`
- `MockLLM.respond(system, history, tools)` — `history[-1]` carries `content`, `context`, and optionally `results`; with results → `policy.after_tools`, else `policy.plan`.

`adapters/claude.py`
- `ClaudeLLM(policy, pack, registry, *, client=None, model=None, effort=None, timeout=20.0)`; attributes `calls`, `fallbacks`, `usage {"input", "output"}`; `name = "claude"`.
- `build_tools(registry) -> list[dict]` (Anthropic format + `end_call`).
- `respond(...)` as above.

`adapters/factory.py`
- `make_llm(name, policy, pack, registry, **kw)` — `"mock"` | `"claude"`; anything else `ValueError`.

`policy.py`
- `DialoguePolicy.ask_confirmation(ctx, action, args) -> LLMTurn` — public: sets `ctx.pending_confirmation` and returns the read-back question (the existing book template; the cancel question for cancels).

`pipeline.py`
- `CallSession(..., llm=None)`; `self.llm = llm or make_llm(config.llm, …)`; `_complete_turn` calls `respond` for both phases.

`cli.py`
- `selftest --llm {mock,claude}` sets `HAANJI_PROVIDER_LLM` before the config is built.

`research/harness/llm_ablation.py`
- Runs every pack's scenarios under `mock` and `claude`, writes
  `research/llm_ablation.json` (`{provider: {scenarios: [{pack, name, expect, outcome, passed, turns}], passed, total, speculation: {started, hits}, latency_p50_ms, llm_calls, fallbacks, tokens}}`) and prints a Markdown table. The `claude` half is skipped with a note when no key is configured.

## Tests (`engine/tests/test_claude_adapter.py`, no network)

A fake client scripted with content blocks. A text reply becomes `say`; a
read-only tool call round-trips with matching `tool_use_id`; a write becomes
the read-back question and sets `pending_confirmation` without calling the
tool; a confirmed yes runs the policy, books, and leaves a receipt while the
fake client is not called; `end_call` ends the call; an exploding client falls
back to the policy and counts a fallback; the system prompt and tools describe
the pack; the factory maps names; `CallSession` uses `MockLLM` by default.

## Non-goals

Streaming replies; speculation on model-derived arguments; model-written
read-backs; per-tenant model choice; TTS/STT vendors.
