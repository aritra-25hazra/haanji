# Changelog

All notable changes to HaanJi. Dates are when the work reached `main`.

## Unreleased

### Phase 1 review (branch phase1/demo-fixes)
* **English by default, Hindi on a switch.** Every console screen and engine
  page reads English first; EN / हिं switches to the Hinglish the product
  always used (remembered per browser, `?lang=hi` in a link). The agent still
  speaks the shop's language. A test checks every string has its Hindi.
* **Help assistant.** A "Help" button on every console page and the landing
  page answers questions about HaanJi and the console: Claude or Gemini (the
  person picks) when their keys are set, a built-in FAQ otherwise. Short
  history, capped replies, a per-client rate limit and a daily cap.
* **A front door and How it works.** The console's `/` says what HaanJi does,
  the three ideas with the benchmark's numbers (copied from
  research/results.json by a script, with a test) and plans without prices;
  `/how` walks one call and shows the measured table, and runs the shop's
  scenarios on the live engine.
* **Sample mode with no dead ends**, consistent sample data, India's time
  everywhere, the agent's behaviour fixes (says it is an AI, keeps details,
  reads back the number, no transfer promised after hours) and the owner
  screens (plain outcome names, filters, a customer drawer, a week grid).

### For the shop that is deciding, the owner, and the caller
* **Landing page for a buyer.** "Customer ki call se aapke calendar tak" walks
  one real booking through three real screens (the WhatsApp chat, the
  customer's receipt, the owner's day); then who it is for (10 packs, 7
  languages), the engine's numbers with their conditions stated (simulated
  recognition noise, not live calls), privacy as the code enforces it, how to
  start, and six questions answered from what the code does. "Free pilot
  maango" opens WhatsApp with the number in `HAANJI_SALES_WHATSAPP` and is
  hidden when it is unset. Eyebrow labels gone; the phone nav keeps Demo and
  the ask.
* **/verify for the customer.** A confirmation link now opens "Aapki booking
  ka सबूत" with the receipt first, the day as "Somvaar, 16 Nov 2026", the time
  as "10:30 subah" and the confirmation time in IST (it showed UTC); the
  ledger tools fold below.
* **Console for the owner.** Five daily tabs and an "Engine" menu; "Inhe wapas
  call karo"; a first-run checklist; React Bits where motion carries state
  (live feed, receipt codes, sign-in, onboarding steps), loaded lazily.
* Accessibility: axe finds no serious or critical issue on 15 pages at 1440
  and 390 px; contrast, small targets (24 px checkboxes, links) and line
  lengths fixed; `.webp`/`.png` served with their media types.
* **Premium pass.** Skeletons shaped like the page instead of "Loading…";
  Calls and Customers become labelled cards on a phone; outcomes, table
  headers and the engine's errors read in Hinglish; "Sample din dekho" shows
  an empty shop a full day, watermarked SAMPLE; text selection, caret,
  scrollbar and tabular numbers themed; the current tab scrolls into view.
* **Fonts from this server.** The four families (latin, latin-ext for ₹,
  devanagari; 186 kB in all, each file fetched only when a page needs it) are
  self-hosted with their OFL notices, cached for a year; no visitor IP goes
  to Google Fonts.
* **Brand and pages.** Favicon on every page, a 1200×630 share image with
  Open Graph and Twitter tags, and `/privacy`, which reads the retention days
  and consent line from the server it runs on.
* **Tests no longer fail at the weekend.** Server tests booked "kal" and
  "parso" on the live clock, and the packs close on Sunday: 17 failed on a
  Saturday. On Friday to Sunday the tests' today is now the Thursday before
  (`wall_today()` in the backend; `@pytest.mark.real_today` opts out).

### Public demo
* **Strangers no longer see whole phone numbers.** With sign-in off on a public
  server, calls, bookings, customers, the waitlist and payments show only the
  last four digits; the calendar feed's secret URL and the per-number privacy
  record answer 403; the WhatsApp simulator stops listing other people's
  threads. Real WhatsApp numbers reach the demo once it is connected, which is
  why this matters now.
* **The landing page quoted the 1.0 benchmark** (31.6% → 1.1%, 239 → 137 ms,
  45.5%) and called itself v0.4.0. It now shows `research/results.json`
  (30.8% → 0.96%, 270 → 172 ms, 46.3%) and v1.1.0, and `readme_sync.py --check`
  fails CI if either drifts again.
* Console: "Calls kaise khatam huin" said "1 calls" with no calls; empty charts
  and a "100% SLO" on zero turns are now a plain empty line. Pack Studio opens
  the pack chosen in the header instead of repeating the Packs table. UI copy
  lost its slogans, a joke, and most em dashes.

### Talk page
* **A 3D counter** above the engine cards (three.js 0.170.0, vendored, loaded
  only when WebGL2 is available): the shop's own signboard hangs over a painted
  counter; Bhasha repairs are sign plates that turn round from what was heard
  to what was read; speculation is a race between the caller's sentence and
  the tool's answer to the "sawaal" line; each receipt is a slip a rubber
  stamp comes down on, chained to the last. Toon-shaded in the Signboard
  palette, framed by projecting its corners, paused off-screen, still under
  reduced motion, switchable off (remembered), aria-hidden: the cards remain
  the record.
* **"Ye boliye"**: the pack's own booking scenario as one-tap lines, said word
  by word as partial transcripts so speculation can hit exactly as it does
  from the microphone.
* Fixed: a deposit link was appended to an element that did not exist, which
  threw and skipped the end-of-call handling; on phones the collapsed engine
  sheet covered the end of the transcript; small text in the bubbles is now
  AA contrast and the transcript is keyboard-scrollable (axe: no violations).

## 1.1.0 — 2026-10-29 (phase G, from the review of the same day)

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
