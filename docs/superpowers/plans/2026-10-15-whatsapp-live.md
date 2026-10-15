# WhatsApp Live (B1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A real WhatsApp number answered by HaanJi on the Render engine, with signed deliveries, redelivery dedup, a visible connection status, and an owner's guide.

**Architecture:** Harden `channels/whatsapp.py` and the two `/wa/webhook` routes in `server.py`; expose the connection in `api/status`; secrets via `render.yaml` `sync: false`; tests drive every contract with Meta-shaped payloads and a monkeypatched `send_text`.

**Tech Stack:** FastAPI, `hmac`/`hashlib`, pytest + TestClient.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-10-15-whatsapp-live-design.md`.
- Branch `whatsapp-live`; git via `/Library/Developer/CommandLineTools/usr/bin/git`; `$PY` = the scratchpad venv python; run pytest from `engine/`.
- No secret values anywhere in the repo. No emoji in UI text.

---

### Task 1: Tests, then the channel and the webhook

**Files:**
- Create: `engine/tests/test_whatsapp_webhook.py`
- Modify: `engine/haanji/channels/whatsapp.py`, `engine/haanji/server.py`

- [ ] **Step 1: Write the failing tests** — the file in the branch (see commit). Key shapes: `meta_payload(msg_id, sender, text)` builds Meta's `entry[].changes[].value.messages[]`; `sign(secret, body)` returns `sha256=<hex>`; `sent` fixture monkeypatches `whatsapp.send_text` and clears `server._wa_seen`.
- [ ] **Step 2: Run** `cd engine && $PY -m pytest tests/test_whatsapp_webhook.py -q` → failures (no `verify_signature`, `_wa_seen`, `handled`, 3-tuples).
- [ ] **Step 3: Implement** `whatsapp.py`: `extract_incoming` yields `(id, from, text)`; `verify_signature`; `status()`; `send_text` logs failures. `server.py`: `_wa_seen = deque(maxlen=500)`; `wa_verify(request)` reads `request.query_params`, checks `hub.mode`; `wa_webhook(request)` reads the raw body, verifies when `HAANJI_WA_APP_SECRET` is set, dedups, picks `HAANJI_WA_PACK`, returns `{"ok": True, "handled": n}`; `status()` adds `"whatsapp": wa_status()`.
- [ ] **Step 4: Run** the file, then the whole suite → `192 passed` (183 + 9).
- [ ] **Step 5: Commit** `feat(engine): make the WhatsApp webhook production-safe`.

### Task 2: Surface it — Render, simulator chip, console chip, guide

**Files:**
- Modify: `render.yaml`, `engine/haanji/web/whatsapp.html`, `console/src/types.ts`, `console/src/pages/Dashboard.tsx`
- Create: `docs/whatsapp-setup.md`

- [ ] **Step 1:** `render.yaml` — five `HAANJI_WA_*` keys with `sync: false` and a comment pointing at the guide.
- [ ] **Step 2:** `whatsapp.html` — after `status()`, if `s.whatsapp.configured`, insert a chip in the sidebar head: *Asli number juda hai · <number>*.
- [ ] **Step 3:** console — `Status.whatsapp?: { configured: boolean; number: string | null }`; the dashboard `Page` gets `actions` with an `ok` chip *Asli WhatsApp juda hai* when configured.
- [ ] **Step 4:** `docs/whatsapp-setup.md` in Hinglish: the owner's steps from the spec, with exact URLs and field names, a test, troubleshooting (403 = verify token or signature; no reply = token expired or recipient not registered), and the permanent-token section.
- [ ] **Step 5:** `npm run build`, `pytest -q`, `test_web.py` rule tests (no emoji in the chip), commit `docs(whatsapp): the owner's guide, and the connection shown where it matters`.

### Task 3: Ship

- [ ] Merge to main, push (Render redeploys the engine), `vercel deploy --prod` for the console, verify `curl https://haanji-engine.onrender.com/api/status | grep whatsapp` and `GET /wa/webhook?hub.mode=subscribe&hub.verify_token=wrong&hub.challenge=1` → 403.
