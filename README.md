# HaanJi

**An AI voice receptionist for Indian small businesses.** It answers the phone in
Hinglish, books the appointment, and can prove afterwards exactly what the caller
agreed to.

Most small clinics, salons and labs in India lose bookings for one boring reason:
nobody picks up. The front desk is with a patient, it is lunch time, it is Sunday.
The caller does not leave a voicemail — they call the next place. HaanJi answers
every one of those calls, in the language the caller actually speaks, and writes
the booking straight into the business's calendar.

Three things in here are not in any product we could find, and each one is
implemented, measured and testable rather than described:

| | What it is | What it is worth |
|---|---|---|
| **Bhasha Bridge** | A per-tenant phonetic index built from the business's own catalogue, used both to bias the recogniser and to repair its output — but only when the recogniser was unsure *and* the sound key matches exactly. | Entity error rate **31.6% → 1.1%** at 30% recognition noise, with **zero** harmful corrections over 2,940 sentences. |
| **Speculative Turn Execution** | Branch prediction for dialogue. Read-only tools are predicted from partial transcripts and executed while the caller is still speaking; the result is used only if the real turn asks for byte-identical arguments. | Median latency on read turns **239 ms → 137 ms**, a 42.6% reduction, with a 45.5% prediction hit rate. |
| **Pramaan Ledger** | Every write is sealed into an Ed25519-signed, hash-chained receipt that binds the action to the caller's recorded confirmation. Daily Merkle anchors; an independent verifier. | **80/80** single-field tampering attempts detected; deletion and forgery detected; **0** unconfirmed writes accepted. |

Every number above was produced by `python -m haanji.bench` on this repository and
is written to [`research/results.json`](research/results.json). Nothing in this
README is an estimate.

---

## Try it in one minute

```bash
cd code/engine
pip install -e ".[dev]"

python -m haanji.cli demo          # one narrated call, at real speaking speed
python -m haanji.cli selftest      # all 21 packaged scenarios, all five verticals
pytest -q                          # 161 tests
python -m haanji.bench             # regenerates research/results.json
```

No API keys, no network, no database. The mock providers stream partial
transcripts with per-word confidences at a realistic speaking rate, which is
exactly the signal the speculation engine consumes, so the demo exercises the
real code path rather than a simulation of it.

`make demo`, `make test`, `make bench` do the same from the repository root.

### Try it in a browser

```bash
pip install -e ".[web]"
python -m haanji.cli serve         # http://localhost:8090
```

One process, still no keys, gives you the whole platform:

| Page | What it shows |
|---|---|
| `/talk` | **Talk to HaanJi** — speak into your mic (Chrome/Edge), watch partial transcripts drive speculation live, interrupt it mid-sentence |
| `/whatsapp` | **WhatsApp simulator** — the same brain over text, plus a *missed call* button that triggers the recovery flow |
| `/verify` | **Public Pramaan verifier** — re-checks every hash and signature *in your browser*; a tamper button proves it isn't decorative |
| `/` | Landing page linking everything, plus `/api/insights` — outcomes, peak hours, recovered revenue, and a costed ₹/call comparison |

The React console (`cd console && npm run dev`) proxies to this server: the
dashboard shows live insights, the calls list shows live conversations, and
**Pack Studio** edits a Vertical Pack in the browser, validates it, and runs its
scenarios before saving.

### In VS Code

Open this folder in VS Code and everything is pre-wired: **Run and Debug** has
configurations for the demo call, the server, selftest and the benchmark;
**Terminal → Run Task** has install/test/serve tasks for both engine and
console (`.vscode/`). How three of us work on this repo from three machines at
three different hours is written down in [CONTRIBUTING.md](CONTRIBUTING.md).

---

## What a call looks like

```
AGENT  Haanji, Smile Care Dental. Main aapki kya madad karun?

HEARD  haan ji mujhe rut kanal karwana tha
       ~ Bhasha Bridge: 'rut kanal' -> 'root canal' (recogniser confidence 0.32)
CALLER haan ji mujhe root canal karwana tha
AGENT  Theek hai. Kis din ka time dekhun?                      . 22 ms

HEARD  kal subah ka time mil jayega
       > tool check_availability  [speculated, already computed]
AGENT  Kal subah saade 9 baje khaali hai, Dr Sheikh ke saath.
       Ya phir subah saade 10 baje. Chalega?                   . 31 ms
...
HEARD  haan confirm kar do
       > tool book_appointment
AGENT  Ho gaya. Kal subah saade 9 baje, Dr Sheikh ke saath.
       Confirmation code 2504-7863.                            . 301 ms

PRAMAAN LEDGER
  receipt 2504-7863   action book_appointment   seq 1
  caller was asked : Ek baar dohra deta hoon — root canal, kal subah saade 9
                     baje Dr Sheikh ke saath, Vijay Sharma naam se. Confirm kar dun?
  caller replied   : haan confirm kar do
  verifier says    : VALID — 1 receipts, chain intact

  someone edits the booking time '09:30' -> '18:00' in the database
  verifier says    : BROKEN at seq 1: payload hash does not match the stored content
```

---

## Repository layout

```
code/
├── engine/          Python 3.11 voice engine — the runnable centrepiece
│   ├── haanji/
│   │   ├── bhasha/          phonetics, tenant lexicon, the correction bridge
│   │   ├── speculation/     predictor, claim-once cache, speculation engine
│   │   ├── pramaan/         receipts, ledger, independent verifier
│   │   ├── adapters/        STT / LLM / TTS boundaries + offline mock providers
│   │   ├── backend/         the business system the agent acts on (SQLite)
│   │   ├── tools/           the eight actions, with purity and confirmation flags
│   │   ├── channels/        WhatsApp (Meta Cloud API) + telephony webhook adapters
│   │   ├── web/             Talk · WhatsApp sim · public verifier (vanilla JS)
│   │   ├── policy.py        the deterministic dialogue policy
│   │   ├── pipeline.py      the turn controller — where the three ideas meet
│   │   ├── guardrails.py    what the agent must never do
│   │   ├── server.py        FastAPI demo server — every channel on one port
│   │   ├── insights.py      outcome/revenue/cost analytics behind /api/insights
│   │   ├── bench.py         the evaluation harness that produces every number
│   │   └── cli.py           demo · selftest · bench · verify · serve · packs
│   └── tests/               161 tests, including the safety properties
├── core-api/        Java 21 / Spring Boot 3 control plane
│   ├── domain repo service web security config pramaan packs
│   ├── db/migration/        Flyway: schema, ledger, knowledge + lexicon
│   └── test/                unit tests plus ArchUnit architecture rules
├── console/         React 18 + TypeScript operator console (Vite) + Pack Studio
├── packs/           five Vertical Packs — the commercial moat, as YAML
├── research/        results.json, regenerated by the harness
└── ops/             Prometheus scrape config and the four real alerts
```

---

## The three contributions, in more detail

### Bhasha Bridge — the business's own words, indexed by sound

A general recogniser has never heard of *Bhawarkuan*, or of Dr Sheikh, and it
mangles *root canal* into *rut kanal* on a bad line. But the business already
told us its services, its staff and its neighbourhood during onboarding. Bhasha
Bridge turns that into a phonetic index using rules chosen for Indian English —
v/w merge, s/sh merge, aspirates weaken, long vowels shorten, word-initial
vowels bucket together because a weak /h/ is dropped by speakers and recognisers
alike.

The index is used twice: as biasing hints sent into the recogniser, and as a
post-correction pass over its output. The correction is where the care is. A
token is only replaced when **two independent conditions** hold:

1. the recogniser was **not confident** about it (below 0.85), and
2. its phonetic key matches a lexicon form **exactly**, within a small edit
   distance of that form.

Either condition alone produces false corrections, and a layer that damages a
good transcript is worse than no layer at all. Personal names the caller has just
introduced are never touched — "mera naam Wijay hai" stays *Wijay*, even though
*Vijay Nagar* is in the lexicon.

Measured over 2,940 independently corrupted sentences at three noise levels:

| noise | entity error, off | entity error, on | reduction | precision | harmful |
|---|---|---|---|---|---|
| 15% | 18.1% | 0.42% | 97.7% | 99.6% | 0 |
| 30% | 31.6% | 1.14% | 96.4% | 99.4% | 0 |
| 45% | 48.7% | 2.03% | 95.8% | 99.5% | 0 |

Median cost: **0.19 ms** per utterance.

The corruption model in `haanji/corrupt.py` is written independently of the
lexicon and corrupts words that appear in no lexicon at all, so the harness can
catch the layer doing damage. It never has.

### Speculative Turn Execution — branch prediction for a conversation

By the time a caller has said "kal subah root canal ka…", it is nearly certain
the next thing needed is the availability for root canal tomorrow. A CPU in this
position starts executing the likely branch. So does HaanJi: partial transcripts
drive a cheap predictor, and read-only tools begin running while the caller is
still talking.

The speed is easy. Correctness is the work, and rests on four properties, each
with a test that fails loudly if it is weakened:

* **Purity** — only tools declared `read_only` are ever speculated. Enforced in
  the tool registry, not trusted to the predictor.
* **Argument identity** — a speculative result is claimed only when the real
  turn asks for byte-identical arguments. Both sides derive arguments through
  the same `haanji/nlu.py`, which makes the identity structural rather than
  lucky.
* **Freshness** — results expire after 4 s and can be claimed exactly once.
* **Invalidation** — any write voids everything computed against the old world.

There is also a budget: at most 2 in flight and 3 per turn, so a wrong guess
costs bounded work and never costs correctness. `test_the_result_is_identical_
with_speculation_on_and_off` asserts the strong form of this — the transcript of
the call must be identical whether speculation is on or off, because it is a
latency optimisation and nothing else.

Measured: **239 ms → 137 ms** median on read turns (42.6% lower), 45.5% hit rate
over 110 speculations, 213 ms saved per hit. Write turns are never speculated, so
the overall tail is unchanged — reported honestly rather than averaged away.

### Pramaan Ledger — proof, not logs

"The AI booked it" is not an answer when a customer disputes an appointment. Every
write in HaanJi produces a receipt containing the action, its arguments, the exact
sentence the agent asked, the exact words the caller replied, how long after the
question the reply began, and the recogniser's confidence in it. The receipt is
hash-chained to its predecessor and signed with the tenant's Ed25519 key; days are
anchored with a signed Merkle root.

Two consequences that a log file cannot give you:

* **The ledger refuses an unconfirmed write.** `book_appointment` without a
  confirmation proof raises, the surrounding transaction rolls back, and no
  booking exists. The engine cannot book something the caller did not agree to,
  even if the dialogue policy has a bug.
* **Anyone can check it.** `/api/v1/receipts/export` returns the receipts and the
  public key and nothing else; `haanji verify` re-derives every hash and checks
  every signature without trusting the platform.

Measured: 80 of 80 single-field mutations detected across eight different fields;
receipt deletion detected; a forged receipt re-hashed by an attacker still fails
the signature; 0 unconfirmed writes accepted.

### Vertical Packs — why this is a product and not a demo

A pack is one YAML file that describes a *kind* of business: catalogue, hours,
staff, persona, refusals, escalations, seed vocabulary, knowledge base, and the
scenarios the pack must pass before it ships. Five are included — dental clinic,
salon and spa, diagnostic lab, coaching institute, and a dental clinic in
Kolkata that speaks **Benglish** (Bengali-English).

The Kolkata pack is the proof of the whole claim. Supporting a second language
took a phrase table in `speak.py` and one YAML file — surface forms, vocabulary,
scenarios. Zero engine code was forked: the same extractor resolves "porshu
bikel char te" the way it resolves "parso shaam char baje", and the agent
replies "Aapnar naam ta bolben?". Nothing in the engine knows what a dentist is,
and now nothing in it knows what Hindi is either. Onboarding a business is
filling in a pack; supporting a new industry — or a new city — is writing one.

---

## The platform around the engine (v0.4)

The engine answers a call. A business needs the rest of the loop, and each piece
below is running code behind `haanji serve`, not a slide:

* **Talk to HaanJi** — a browser call at `/talk`: your microphone, live partial
  transcripts, barge-in, and the speculation/repair badges lighting up as they
  happen. The demo is the product.
* **WhatsApp channel** — the identical pipeline over text (`NullTTS`, same
  policy, same guardrails, same receipts). A real Meta Cloud API adapter ships
  in `channels/whatsapp.py`; the simulator at `/whatsapp` runs it keyless.
* **Missed-call recovery** — the Indian classic: caller gives a missed call, the
  platform messages them back on WhatsApp and finishes the booking in chat.
  Recovered bookings are counted separately in insights, because "revenue that
  would have been lost" is the number a shop owner buys.
* **Returning-caller memory** — "Vijay ji, wapas swagat hai! Pichhli baar root
  canal karaya tha." The greeting, the pre-filled phone number, and the shorter
  question path all come from the store, per tenant.
* **AI insights** — `/api/insights` turns the call log into sentences an owner
  acts on: outcomes, peak hours, top services, recovered revenue, and a costed
  comparison (about **₹3.2/call** for AI versus **₹9.2/call** for a
  ₹12,000/month receptionist at 50 calls/day — every constant is in
  `insights.py`, argue with the constants, not the arithmetic).
* **Pack Studio** — the console page where a pack is edited as YAML, validated,
  and its scenarios run against the live engine *before* saving. Selling a
  vertical becomes a form, not a deployment.
* **Public verifier** — `/verify` re-derives every SHA-256 and checks every
  Ed25519 signature client-side (Web Crypto + vendored TweetNaCl). The page has
  a *tamper* button; press it and watch the chain break. A trust claim you can
  only check on our server would not be a trust claim.

---

## Architecture

```
   PSTN / WhatsApp / Web            React console
          │                               │
   ┌──────▼───────┐               ┌───────▼────────┐
   │ Voice engine │◄──── tools ───┤   Core API     │
   │  (Python)    │               │ (Spring Boot)  │
   │              │               │                │
   │ Bhasha       │               │ bookings       │
   │ Speculation  │               │ Pramaan ledger │
   │ Guardrails   │               │ packs, tenants │
   └──────────────┘               └───────┬────────┘
                                          │
                            PostgreSQL 16 + pgvector, Redis 7
```

The engine is stateless and horizontally scaled — a call is the expensive, bursty
part of this system. Everything durable lives behind the Core API, which is why a
call can survive an engine process dying.

Tenant isolation is enforced twice: the request's tenant comes only from the
signed token, and it is pushed into the database session so PostgreSQL row level
security applies as well. A repository method that forgets its tenant filter
returns nothing rather than returning somebody else's data.

---

## Running the whole system

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Engine demo server (talk · whatsapp · verify · insights) | http://localhost:8090 |
| Console | http://localhost:5173 |
| Core API + OpenAPI | http://localhost:8080/swagger-ui.html |
| Grafana | http://localhost:3000 (admin / haanji) |
| Prometheus | http://localhost:9090 |

The console runs standalone too (`cd console && npm install && npm run dev`); with
no token present it renders the sample dataset captured from the engine's demo run,
which is how the interface was designed and reviewed.

---

## Honest notes

A project report should say what was verified and what was not.

* **The Python engine is fully executed here.** 161 tests, 21 scenarios across
  five verticals and two languages, and the entire benchmark run on this
  machine. Every number in this README comes from that run.
* **The React console builds here.** `npm run build` type-checks the whole
  TypeScript source under `strict` and emits a production bundle.
* **The Java Core API is compiled only as far as this sandbox allows.** The build
  environment has no route to Maven Central, so `mvn verify` could not run. Every
  Java file was put through `javac` and reports **no syntax errors** — the only
  diagnostics are the missing third-party packages themselves. The build is wired
  into CI (`.github/workflows/ci.yml`) and runs on any machine with normal network
  access. The Java ledger is a direct port of the Python one, and the property it
  enforces — no write without a proof — is tested end to end on the Python side.
* **The browser call uses the browser's own recogniser.** `/talk` feeds Web
  Speech API partials and finals into the same pipeline the mock providers
  exercise; per-word confidence is not exposed by browsers, so the engine
  estimates it from its lexicon on that path. Chrome/Edge required for the mic;
  the type-a-line fallback works everywhere.
* **Providers are mocked by default.** Swapping in a hosted recogniser or model
  means replacing one adapter class; the engine imports no vendor SDK anywhere.
  The latency figures are therefore engine-side: they measure what HaanJi adds
  and what speculation removes, not what a particular vendor charges in
  round-trip time.
* **A known collision is recorded rather than hidden.** /b/ and /p/ merge for many
  speakers, so *braces* and *prices* land in one phonetic bucket and the edit
  distance does not separate them either. The confidence condition is what keeps
  this from mattering in practice. `test_a_known_collision_is_documented_not_hidden`
  exists so the limitation cannot be quietly lost.
* **The corruption model is a model.** It reproduces the substitutions Indian
  English recognisers actually make, but it is not a recording of real callers.
  Collecting that corpus is the next piece of work, and the harness is built to
  take it: swap the generator for real (heard, truth) pairs and every table in
  this README recomputes.

---

## Team

Aritra Hazra · Prabhav Upadhayay · Anuj Uniyal
B.Tech Information Technology (Artificial Intelligence), Medi-Caps University

## Licence

Apache-2.0. The engine, the packs and the verifier are open source on purpose: a
tamper-evidence claim nobody can inspect is not a claim.
