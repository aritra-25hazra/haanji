# WhatsApp live (B1) — design

**Date:** 2026-10-15
**Scope:** make the existing Meta WhatsApp Cloud API path production-safe on the
Render engine, surface the connection in the UI, and give the owner a
step-by-step to connect a real number. No new service; the simulator and the
real webhook keep sharing `_wa_turn`.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Transport | Meta WhatsApp Cloud API, as already wired | Free, direct, the code exists; Twilio's sandbox is not a real number. |
| Authentication of deliveries | Verify `X-Hub-Signature-256` (HMAC-SHA256 of the raw body with the app secret) when `HAANJI_WA_APP_SECRET` is set; 403 otherwise. Unset = development mode, accepted. | Without it anyone who finds the URL can inject messages into tenants' threads. |
| Redelivery | Remember the last 500 message ids; a repeat is acknowledged (200) but not handled again. | Meta retries deliveries it did not get a 200 for in time. |
| Verification handshake | `GET /wa/webhook` echoes `hub.challenge` only when `hub.mode=subscribe` and `hub.verify_token` matches `HAANJI_WA_VERIFY_TOKEN`. | Meta's contract. The current handler reads `**params`, which FastAPI does not populate — it must read `request.query_params`. |
| Which pack answers | `HAANJI_WA_PACK`, default the engine's default pack | One number, one business for the demo; a per-number map is a later step. |
| Secrets | `render.yaml` lists the five `HAANJI_WA_*` keys with `sync: false`; values live only in the Render dashboard. | Never in the repo. |
| Visibility | `api/status` gains `whatsapp: {configured, number}`; the simulator header and the console dashboard show *Asli number juda hai* when configured. | So a visitor and the owner can tell the demo from the real thing. |

## Contracts

`channels/whatsapp.py`
- `extract_incoming(payload) -> Iterator[(message_id, sender, text)]` — text messages only; `statuses`-only deliveries yield nothing.
- `verify_signature(secret: str, raw: bytes, header: str | None) -> bool` — constant-time.
- `status() -> {"configured": bool, "number": str | None}` — `number` is `HAANJI_WA_DISPLAY_NUMBER` if set, else the phone-number id's last four digits.
- `send_text(to, text)` — unchanged contract; failures are logged, never raised into the webhook.

`server.py`
- `GET /wa/webhook` → 200 challenge | 403.
- `POST /wa/webhook` → always 200 `{"ok": true, "handled": n}` for a valid delivery (even n = 0); 403 for a bad or missing signature when a secret is set.
- `GET /api/status` → adds `whatsapp`.

Environment: `HAANJI_WA_TOKEN`, `HAANJI_WA_PHONE_ID`, `HAANJI_WA_VERIFY_TOKEN`, `HAANJI_WA_APP_SECRET`, `HAANJI_WA_PACK`, `HAANJI_WA_DISPLAY_NUMBER` (optional).

## Owner's steps (in `docs/whatsapp-setup.md`, Hinglish)

Meta app → WhatsApp product → test number → add own phone as recipient →
temporary token → Render dashboard env (4 values) → webhook URL
`https://haanji-engine.onrender.com/wa/webhook` + verify token → subscribe to
`messages` → send "hi" from the phone → see the reply and the thread in the
console. Then: permanent token via a System User, and what the test number can
and cannot do (5 recipients, 24-hour reply window).

## Tests (`engine/tests/test_whatsapp_webhook.py`)

Verification handshake (right token, wrong token, wrong mode); signed
delivery answered and recorded in the thread; bad and missing signature
rejected when a secret is set; unsigned accepted when none is set; redelivery
handled once; statuses-only delivery ignored; pack from the environment;
status reports the connection; `extract_incoming` yields ids.

## Non-goals

Media messages, templates for messages outside the 24-hour window, per-number
tenant routing, delivery receipts.
