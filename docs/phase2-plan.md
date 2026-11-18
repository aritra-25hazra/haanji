# Phase 2 plan

**Status (2026-11-18): all six items are built on the `phase2/platform` branch.** What was built is listed under each heading as **Built**; the plan text below it is kept as it was proposed.

The review brief asked for these six items as a plan first. Nothing below is
implemented on `phase1/demo-fixes`. Each item lists what exists today, what
would change, how it would be tested, and what it needs from the owner.
Order is the suggested build order: each step leaves `main` deployable.

## 1. Demo reset

**Built.** `POST /api/admin/demo-reset` (operator token on a public server), nightly at `HAANJI_DEMO_RESET_HOUR`; old files (or Postgres schemas) archived whole. Tests: test_demo_reset.py. (smallest; makes every later demo repeatable)

**Today.** The public demo writes to SQLite files on Render's disk. A
redeploy starts clean (`HAANJI_DEMO=1` seeds one returning caller); between
deploys, test calls pile up in the console.

**Change.**
- Add an owner-only `POST /api/admin/demo-reset`, refused when `HAANJI_AUTH=on`.
- It empties calls, WhatsApp threads, bookings, waitlist and payments for the
  demo tenant, and starts a new Pramaan chain. The old chain is anchored and
  kept, never rewritten.
- Re-seed the returning caller.
- Optionally, a nightly reset at 04:00 IST via the existing reminder loop.

**Tests.**
- Reset leaves zero calls and a valid new chain.
- The old chain still verifies.
- A reset is refused with auth on.

**Needs.** Nothing.

## 2. Digest consistency

**Built.** Today-only insights (bookings by today's receipts), the digest built from them under the dashboard's labels, `owner_language` setting. Tests: test_digest.py.

**Today.** `digest_text()` in server.py already reads `compute_insights(...)`,
the same function the dashboard uses, so the numbers come from one place. The
words still differ, though:

- the digest says "N bookings calendar pe" for `bookings_confirmed`, and
  "N calls booking bani" for the BOOKED outcome, two numbers that look alike;
- it quotes `calls_total` (all time) next to today's count;
- the date in its first line is taken from the server clock separately from
  the insights' IST day.

**Change.**
- The digest uses the dashboard's labels (labels.ts / hi/*.ts): Booked, Needs
  a callback, Missed calls recovered.
- It quotes only today's numbers, and in the owner's chosen language.
- It takes its day from the same IST `today` the insights use.

**Tests.** For a seeded store, every number in the digest equals the matching
dashboard tile, including just after midnight IST.

**Needs.** Nothing.

## 3. Sign-in for real shops (auth)

**Built.** Device sessions (list, end one), 14-day idle sign-out, weekly refresh, owner-only activity log; console Settings shows both. Not built: the OTP template itself (the owner approves it in Meta). Tests: test_auth_sessions.py.

**Today.**
- `auth.py` already has a WhatsApp OTP: 5-minute TTL, 5 attempts.
- Roles are owner and staff, with per-pack scopes; `PROTECTED` routes check them.
- The public demo runs with auth off, read-only.

**Gaps.**
- No session expiry or refresh beyond the token lifetime.
- No owner-visible list of active devices beyond "sign out everywhere".
- No audit log of who changed settings or cancelled a booking.
- OTP delivery depends on an approved WhatsApp template (`HAANJI_WA_TEMPLATE_OTP`).

**Change.**
- Token expiry with sliding refresh.
- An `audit` table recording who, what and when for every owner/staff write,
  shown in Settings.
- A console screen for the devices that are signed in.

**Tests.**
- An expired token gets 401.
- Every write route adds one audit row.
- Staff cannot read the audit log.

**Needs.** The owner approves an OTP template in Meta Business Manager.

## 4. Postgres instead of SQLite files

**Built.** `HAANJI_DATABASE_URL` (haanji/db.py), `haanji db-copy`, a CI job on Postgres; the suite passes on Postgres 18 locally. Tests: test_db.py.

**Today.**
- 13 modules open their own SQLite files under `HAANJI_VAR_DIR`: store,
  auth, settings, payments, push, gcal, backup, the ledger vault, and others.
- Render's free disk is ephemeral; `backup.py` copies the files to S3 nightly.

**Change.**
- One `db.py` with a connection factory that reads `DATABASE_URL`:
  `sqlite:///…` stays the default for local work and tests, and
  `postgresql://…` is for production.
- Port the modules one at a time behind that factory. The SQL is
  mostly portable; the exceptions are `INSERT OR REPLACE` (becomes
  `ON CONFLICT`) and `PRAGMA` (removed).
- The Pramaan ledger keeps its append-only rule: no UPDATE or DELETE grants
  on the receipts table.
- A one-off migration script copies the existing SQLite files.

**Tests.**
- The whole suite runs twice in CI, on SQLite and on a Postgres service
  container.
- The migration round-trips a seeded store, and the copied chain still
  verifies.

**Needs.** A managed Postgres. Several hosts have free tiers with limits
(Render's free Postgres expires); compare current terms. Paid plans cost money, so the owner chooses.

## 5. Telephony adapter (a real phone number)

**Built.** A provider-neutral bridge with Twilio and Exotel (AgentStream) wires and a G.711 codec. Not built: call transfer to the shop's line. Tests: test_telephony_exotel.py.

**Today.**
- `telephony/twilio.py` handles inbound calls with media streams; Deepgram is
  the speech recogniser and ElevenLabs the voice.
- A missed-call webhook exists.
- Twilio trial numbers cannot call Indian mobiles freely, and Indian numbers
  need KYC.

**Change.**
- A `TelephonyProvider` interface (answer, stream audio, hang up, transfer,
  missed-call), with Twilio as its first implementation and Exotel as the
  second.
- Exotel issues Indian numbers and supports passthru webhooks.
- `transfer` calls the shop's landline only inside the pack's hours, which is
  the same `_open_now` rule as the agent's emergency line.

**Tests.**
- A contract test runs against both adapters with recorded webhook payloads.
- A transfer outside hours becomes an urgent callback.

**Needs.**
- A provider account with KYC, and a number with a monthly rental plus
  per-minute charges (check the provider's current price before buying).
- STT and TTS keys.
- These all cost money; nothing is bought without the owner's yes.

## 6. Data rights (DPDP)

**Built.** `/my-data` (WhatsApp code, download, erasure request), owner approval in Settings, a hash-only log, S3 backups pruned past retention. Tests: test_data_rights.py.

**Today.**
- `/api/privacy/customer/{phone}` exports (GET) and erases (DELETE):
  - it shreds the receipt key;
  - it anonymises bookings;
  - it deletes calls and threads.
- Retention purges call records after `HAANJI_RETENTION_DAYS`.
- A consent line is spoken at the start of every call.

**Gaps.**
- The customer has to ask the owner; there is no self-service.
- There is no record that an erasure happened.
- Backups in S3 still hold the erased rows until they age out.

**Change.**
- A customer-facing request page: the customer enters their number and gets
  an OTP on WhatsApp. They can download their data, or ask for erasure; erasure
  needs the owner's approval in Settings.
- An erasure log, holding only a hash of the phone number.
- Backup retention capped at the same `HAANJI_RETENTION_DAYS`, so erased data
  leaves backups too.

**Tests.**
- Export contains every table that has the phone number.
- After erasure, the number is in no table and its receipts still verify as
  "erased".
- Backup pruning respects retention.

**Needs.** A privacy contact (name and email) for the policy page.
