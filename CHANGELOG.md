# Changelog

All notable changes to HaanJi. Dates are when the work reached `main`.

## 1.1.0 — unreleased (phase G, from the 2026-10-29 review)

A whole-project review found the engine understanding scripted callers and
mishearing real ones, and a set of security holes in front of a real shop.
This release fixes what it found, each with a test that reproduces the old
behaviour, and adds the operations a shop pays a receptionist for.

### Dialogue
* Hindi/Bengali/Marathi fractions and number words ("saade das" → 10:30,
  "paune gyarah" → 10:45, "dhai" → 14:30); numeric dates ("15 tarikh",
  "3 november", "do din baad"); an unclear day is asked about, never
  silently "tomorrow".
* A part-of-day request ("kal shaam ko", "tomorrow afternoon") gets slots in
  that part of the day; "nahi, shaam ko" looks again instead of repeating the
  offer; "nahi parso" changes the day instead of ending the call.
* A time the caller names is checked exactly before any details are asked,
  with alternatives when it is taken or out of hours.
* The named doctor is the one booked; a group ("mujhe aur meri wife ko") is
  booked together under one receipt; "pehla / doosra" pick an offered slot.
* Phone numbers are read in one breath, never glued across words; names are
  not grammar.
* A refusal (advice, promise, discount) is spoken in the pack's refusal line
  and the call goes on (`REFUSED` outcome, ledgered `refuse`); it no longer
  tells a discount question it has an emergency. "Dawai ki dukaan" is not a
  prescription request. Packs may add `guardrails.rules` and `disable`
  built-ins.
* Cancelling or moving a booking from the web page needs the booking's
  receipt code; a channel-vouched number (caller-id, WhatsApp sender) does
  not. Receipts record `identity`.

### Operations
* **Reminders** the evening before (per-pack hour, template or text); "1"
  confirms, "2" cancels through the ledger with the reminder as the question.
* **Deposits**: `deposit_inr` puts a payment link in every confirmation
  (Razorpay Payment Links, or a one-click mock page); paid deposits are sealed
  as `payment_received`.
* **Waitlist**: a full day's caller joins the waitlist; a cancellation offers
  the freed slot to the first waiting person on WhatsApp; "haan" books it.
* **Console API** (`docs/console-api.md`): bookings by range with cancel /
  no-show / completed sealed as staff actions, customers, per-pack settings,
  waitlist, payments, backup download, `POST /api/auth/logout`.
* **Backups**: consistent SQLite backups as one tar.gz, nightly to
  S3-compatible storage, restore on boot into an empty data directory,
  `haanji backup` / `restore`.
* **Audio in receipts**: the phone channel's confirmation proof carries the
  SHA-256 of the caller's reply audio; `HAANJI_CONFIRMATION_AUDIO_DIR` keeps
  the clip.
* Missed-call outreach is actually sent when a WhatsApp number is connected;
  WhatsApp sends report delivery and use approved templates when configured;
  an undelivered login code is a 503.

### Security
* Privacy erasure requires a whole ten-digit number and matches exactly (the
  1.0 endpoint could wipe a tenant); vault subjects are per tenant;
  `secure_delete` on the vault.
* "No `?pack=`" no longer means "any pack"; live sessions and events filter
  by the user's packs; takeover routes resolve the session's pack.
* `/api/ops`, the WhatsApp simulator, `/api/record`, `/api/study` are behind
  sign-in when it is on; `/metrics` takes `HAANJI_METRICS_TOKEN` or a staff
  token; `/api/status` no longer discloses the data directory.
* OTP: 3 codes per 15 minutes per number, a 15-minute lock after 10 wrong
  guesses across codes; tokens are revocable (logout, removal) and carry the
  user's current role; `?token=` is accepted only by the SSE route.
* Request bodies are capped (1 MB; 26 MB for recordings); the channel is an
  enum; `max_concurrent_calls` is enforced; idle sessions are collected.
* Twilio: the signed URL is rebuilt from the public URL behind the proxy,
  uvicorn trusts forwarded headers on Render, a one-time ticket authenticates
  the media socket; a public server refuses unsigned vendor webhooks.
* `LocalBackend.today` is live (IST), the past cannot be booked; demo
  customers are seeded only in demo mode; signing keys can be encrypted at
  rest (`HAANJI_LEDGER_KEY_SECRET`); receipt codes are indexed; web push runs
  off the event loop with a timeout; `print` became logging.

### Repository
* The Java control plane moved to `experimental/`; the compose stack is the
  engine, the console, Prometheus and Grafana, with the engine's data on a
  volume.
* `docs/operations.md`, `docs/console-api.md`; the WhatsApp, phone, auth,
  privacy and Pramaan docs describe the new knobs.

## 1.0.0 — 2026-10-21

The release that goes with the project report and the paper draft. Every
number in `research/REPORT.md` is reproducible from this tag.

### Engine
* **Merged-token repair.** A long, low-confidence token that the lexicon cannot
  explain as a whole is split where both halves are known words and one of
  them is a catalogue word ("subhahroot" → "subah root"), then repaired by the
  ordinary rule. Measured on the real-recogniser pilot (REPORT §4.9).
* **Calibrated confidence gate.** `haanji.bhasha.calibration` fits a
  per-recogniser threshold from (heard, truth) pairs by Youden's J, with the
  ROC and AUC recorded; the engine can load `research/calibration.json`. The
  measurement says Whisper's word probabilities are weakly informative and the
  default gate stays at 0.85 (REPORT §4.10).
* **Recogniser biasing in the pilot pipeline.** `research/collect/transcribe.py
  --bias` passes the pack vocabulary to Whisper as its initial prompt; this
  halves entity error before any repair (REPORT §4.11).
* **Rescheduling.** "Meri booking parso shift kar do": the booking is found by
  phone number, re-slotted through the ordinary confirmation flow and sealed as
  one receipt that names the previous booking; outcome `RESCHEDULED`.
* **Human takeover.** Staff take a live web, WhatsApp or phone call from the
  agent in the console, reply in their own words (spoken on the line, sent on
  WhatsApp or shown in the browser), and hand it back; every human turn is
  recorded as such.
* **Web push.** VAPID keys generated beside the data; owners subscribe from the
  console and are buzzed on a booking, a reschedule, a callback or a handoff.
* **Devanagari input.** A recogniser running in Hindi mode may send Hindi
  script; the engine transliterates before the pipeline.
* **Learned predictor harness.** `research/harness/predictor_fit.py` logs
  partials, fits a logistic predictor with leave-one-pack-out validation and
  benchmarks it against the hand-set weights (REPORT §5.4). The hand-set
  weights stay the default.

### Console
* Live panel with takeover and hand-back, a reply box for the human turn, a
  *Notifications on* button; installable (web-app manifest, service worker).

### Release engineering
* `CITATION.cff` and `.zenodo.json`; PyPI packaging with trusted publishing
  (`.github/workflows/publish.yml`); a documentation site built with MkDocs
  (`.github/workflows/pages.yml`); the paper in LaTeX (`research/paper-latex/`).

## 0.4.0 — 2026-10-15

The platform and the examiner's items.

* **Research.** Evaluation report with confidence intervals over five seeds;
  real-recogniser pipeline and the synthetic-speech pilot that found and fixed
  the open confidence gate; classic-key baselines with McNemar tests; per-rule
  ablation; noise learned from Whisper on the public Gram Vaani corpus; cost
  and load measurements; the IEEE-style paper draft; the viva kit.
* **Trust.** Daily signed Merkle anchors and a public transparency page;
  property-based tests of the ledger; a per-customer encrypted vault with
  crypto-shredding, access and erasure endpoints (DPDP).
* **Platform.** Opt-in sign-in with WhatsApp one-time codes and per-pack scope;
  live call feed over server-sent events; onboarding wizard; Prometheus
  metrics, per-turn spans and an ops page; iCalendar feeds and Google Calendar;
  a Twilio Media Streams bridge with Deepgram and ElevenLabs; the owner's
  evening digest; receipt links in every WhatsApp reply; CodeQL, secret
  scanning, dependency audits and an SBOM on every push; Codespaces.
* **Languages.** Marathinglish pack (Pune) beside Hinglish and Benglish.
* **Dialogue.** A hosted-model adapter (Claude) behind the same boundary as the
  deterministic policy, with the ledger's guarantee preserved by construction.
* **Demo pages** redesigned in the Signboard direction; WhatsApp channel taken
  live.

## 0.3.0 — 2026-10-07

The engine, the console and the Java core API compile and boot from a clean
checkout; the console is hosted on Vercel and the engine on Render.

## 0.1.0 – 0.2.0 — 2026-09

Bhasha Bridge, Speculative Turn Execution and the Pramaan Ledger as a Python
engine with mock providers, five vertical packs, the benchmark harness and the
first measured results.
