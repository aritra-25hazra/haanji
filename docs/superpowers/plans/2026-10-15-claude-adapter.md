# Claude Dialogue Adapter (B2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a real model behind the dialogue boundary — swappable, failure-tolerant, and unable to write without the caller's confirmed yes — and measure it against the deterministic policy on the 21 packaged scenarios.

**Architecture:** `adapters/prompt.py` (vendor-neutral prompt + schemas), `adapters/claude.py` (the adapter, SDK imported lazily), `adapters/factory.py` (name → adapter); `CallSession` gains the `llm` seam and routes both turn phases through `respond`; `DialoguePolicy.ask_confirmation` becomes public so the adapter can reuse the read-back; `cli selftest --llm`; `research/harness/llm_ablation.py`.

**Tech Stack:** Python 3.11, `anthropic` SDK (optional extra), pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-10-15-claude-adapter-design.md`.
- Branch `claude-adapter`; git via `/Library/Developer/CommandLineTools/usr/bin/git`; `$PY` = scratchpad venv python; pytest from `engine/`.
- Tests must pass with no network and without `ANTHROPIC_API_KEY`.
- The existing 192 tests must keep passing after the seam lands — that is the proof the default path is unchanged.

---

### Task 1: Tests, then prompt + mock seam + policy read-back + factory

**Files:** create `engine/tests/test_claude_adapter.py`, `engine/haanji/adapters/prompt.py`, `engine/haanji/adapters/factory.py`; modify `engine/haanji/adapters/mock.py`, `engine/haanji/policy.py`.

- [ ] Write the tests (the file on the branch), run → red (`ModuleNotFoundError: haanji.adapters.claude`).
- [ ] `prompt.py`: `build_system_prompt(pack)` and `tool_schemas(registry)`.
- [ ] `mock.py`: `MockLLM.respond` honours `results`.
- [ ] `policy.py`: `ask_confirmation(ctx, action, args)` public; `_ask_confirmation` unchanged for the book path.
- [ ] `factory.py`: `make_llm`.

### Task 2: The Claude adapter

**Files:** create `engine/haanji/adapters/claude.py`.

- [ ] `build_tools(registry)`; `ClaudeLLM` with lazy client, `respond`, confirmation gate, `end_call`, fallback, usage; run the adapter tests → green.

### Task 3: The seam in the pipeline, CLI flag, `.env`, extras

**Files:** modify `engine/haanji/pipeline.py`, `engine/haanji/cli.py`, `engine/haanji/config.py`, `engine/pyproject.toml`, `engine/Dockerfile`, `render.yaml`, `README.md`.

- [ ] `CallSession.__init__(…, llm=None)`; `self.llm`; `_complete_turn` uses `await self.llm.respond(...)` for both phases; `MAX_TOOL_ROUNDS` loop unchanged.
- [ ] `cli.py`: `selftest --llm`; `demo --llm` too (same mechanism).
- [ ] `config.py`: load `engine/.env` at import (setdefault only).
- [ ] `pyproject.toml`: `llm = ["anthropic>=0.50"]`; Dockerfile `.[live,web,llm]`; `render.yaml`: `ANTHROPIC_API_KEY` (`sync: false`), `HAANJI_PROVIDER_LLM` (`mock`), `HAANJI_LLM_MODEL` (`claude-opus-4-8`), `HAANJI_LLM_EFFORT` (`low`).
- [ ] README: the SDK sentence; a short "A real model" subsection under the platform section.
- [ ] Full suite → `201 passed` (192 + 9). Commit.

### Task 4: Ablation harness

**Files:** create `research/harness/llm_ablation.py`, `research/harness/README.md`.

- [ ] Run the `mock` half now; the `claude` half when `engine/.env` exists; write `research/llm_ablation.json`; print the table. Commit.

### Task 5: Ship

- [ ] Merge, push (Render rebuilds with the `llm` extra installed; `HAANJI_PROVIDER_LLM` stays `mock` until the owner flips it), verify `api/status` still fine and the 21 scenarios pass on the mock path in CI.
