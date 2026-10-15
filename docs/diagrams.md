# Diagrams

The system as examiners expect to see it: context, containers, a booking turn,
the data, the data flow, the classes that matter, and the deployment. All
Mermaid, so they render on GitHub and in the PDF report.

## C4 — context

```mermaid
flowchart LR
  caller([Caller\nHinglish / Benglish\nphone or WhatsApp or browser]) -->|speech / text| haanji[[HaanJi\nvoice receptionist]]
  owner([Business owner\nclinic, salon, lab, institute]) -->|console| haanji
  haanji -->|bookings, receipts| cal[(Owner's calendar\nGoogle / iCal)]
  haanji -->|receipt link, digest, OTP| wa[Meta WhatsApp Cloud API]
  haanji -->|audio in/out| tel[Twilio Media Streams]
  haanji -->|transcripts| stt[Deepgram]
  haanji -->|speech| tts[ElevenLabs]
  haanji -.->|optional dialogue| llm[Claude]
  anyone([Anyone with the receipt]) -->|verify| haanji
```

## C4 — containers

```mermaid
flowchart TB
  subgraph browser[Browser]
    talk[/talk — call page\nWeb Speech partials/]
    console[Owner console — React\nlive feed, insights, packs, ops]
    verify[/verify — client-side verifier\nTweetNaCl/]
  end
  subgraph engine[Engine — Python 3.11, FastAPI, one process]
    api[HTTP + SSE + WebSocket API]
    pipe[CallSession pipeline]
    bridge[Bhasha Bridge]
    spec[Speculation engine]
    policy[Dialogue policy / Claude adapter]
    guard[Guardrails]
    tools[Tool registry]
    ledger[(Pramaan ledger\nSQLite, Ed25519)]
    backend[(Tenant backend\nbookings, services, leads)]
    store[(Demo store\ncalls, WhatsApp threads)]
    tele[Telephony bridge]
  end
  packs[(Vertical packs\nYAML)]
  core[Core API — Java/Spring\nPostgres, Redis, ledger port]
  talk --> api
  console --> api
  verify --> api
  api --> pipe
  pipe --> bridge --> guard --> policy --> tools
  pipe --> spec --> tools
  tools --> backend
  tools --> ledger
  pipe --> store
  tele --> pipe
  packs --> pipe
  console -. optional .-> core
```

## Sequence — one booking turn (speculation, correction, confirmation, receipt)

```mermaid
sequenceDiagram
  autonumber
  participant C as Caller
  participant S as STT
  participant P as CallSession
  participant B as Bhasha Bridge
  participant X as Speculation
  participant D as Policy
  participant T as Tools
  participant L as Pramaan Ledger
  C->>S: "kal subah rut kanal ka…"
  S-->>P: partial "kal subah rut"
  P->>X: on_partial
  X->>T: check_availability(root canal, tomorrow) [read-only, early]
  S-->>P: final "kal subah rut kanal ka time milega"
  P->>B: correct(final, confidences)
  B-->>P: "root canal" (conf 0.32, key RTKNL = RTKNL, edit 2)
  P->>D: plan(corrected text, context)
  D-->>P: tool_call check_availability(root canal, 2026-09-08)
  P->>X: claim(args byte-identical?)
  X-->>P: cached result (hit)
  D-->>P: "Kal subah saade 9 baje khaali hai… chalega?"
  C->>S: "haan confirm kar do"
  S-->>P: final
  P->>D: plan (pending confirmation + affirmative)
  D-->>P: book_appointment(..., needs_confirmation)
  P->>T: book_appointment(args, proof{question, reply, timings, confidence})
  T->>L: append(receipt)
  L-->>T: receipt 2504-7863 (hash-chained, signed)
  T-->>P: booked
  P-->>C: "Ho gaya. Confirmation code 2504-7863."
```

## ER — the data

```mermaid
erDiagram
  TENANT ||--o{ SERVICE : offers
  TENANT ||--o{ STAFF : employs
  TENANT ||--o{ BOOKING : holds
  TENANT ||--o{ LEAD : captures
  TENANT ||--o{ RECEIPT : seals
  TENANT ||--o{ DAILY_ANCHOR : publishes
  TENANT ||--|| KEY : signs_with
  CALL ||--o{ TURN : contains
  CALL ||--o{ RECEIPT : produces
  BOOKING ||--o| RECEIPT : proven_by
  RECEIPT ||--|| RECEIPT : prev_hash
  USER }o--o{ TENANT : scoped_to
  SERVICE { string name  int duration_min  int price_inr  string staff }
  BOOKING { string booking_id  string service  string date  string time  string staff  string customer_name  string phone  string status  string receipt_code }
  RECEIPT { int seq  string action  json action_args  json confirmation  string transcript_excerpt  bytes prev_hash  bytes payload_hash  bytes chain_hash  bytes signature }
  DAILY_ANCHOR { string day  int first_seq  int last_seq  bytes merkle_root  bytes signature }
  CALL { string call_id  string channel  string phone  string outcome  int corrections  int spec_hits  real latency_p50 }
  USER { string phone  string role  string packs }
```

## DFD — level 0 and level 1

```mermaid
flowchart LR
  subgraph L0[Level 0]
    c0([Caller]) -->|speech| s0((HaanJi))
    s0 -->|reply, receipt code| c0
    o0([Owner]) -->|pack, settings| s0
    s0 -->|insights, digest, calendar| o0
  end
```

```mermaid
flowchart LR
  subgraph L1[Level 1 — one turn]
    a[(1.0 recognise)] --> b[(2.0 correct\nBhasha Bridge)]
    a -. partials .-> x[(3.0 speculate)]
    b --> g[(4.0 guard)]
    g --> d[(5.0 decide\npolicy / model)]
    d --> t[(6.0 execute tools)]
    x --> t
    t -->|write| l[(7.0 seal receipt)]
    d --> s[(8.0 speak)]
    D1[(lexicon)] --> b
    D2[(backend)] <--> t
    D3[(ledger)] <--> l
    D4[(call store)] <-- s
  end
```

## Class diagram — the engine's core

```mermaid
classDiagram
  class CallSession {
    +open(phone)
    +handle_utterance(utt)
    +handle_partial_text(text)
    +handle_text_turn(text, confidence)
    +finish() CallReport
    -_complete_turn()
    -_run_tools()
  }
  class BhashaBridge { +correct(Transcript) CorrectedTranscript  +hints() }
  class TenantLexicon { +build(**seed)  +candidates(key)  +reinforce() }
  class SpeculationEngine { +on_partial(text, ctx)  +claim(tool, args)  +on_write() }
  class IntentPredictor { +predict(partial, ctx) ToolGuess }
  class DialoguePolicy { +plan(text, ctx) LLMTurn  +after_tools()  +ask_confirmation() }
  class LLMAdapter { <<protocol>> +respond(system, history, tools) LLMTurn }
  class MockLLM
  class ClaudeLLM
  class Guard { +check(text) Verdict }
  class ToolRegistry { +register(Tool)  +execute(name, args)  +is_read_only() }
  class Ledger { +append(...) Receipt  +receipts()  +anchor_day() }
  class Receipt { +compute_payload_hash()  +compute_chain_hash() }
  CallSession --> BhashaBridge
  CallSession --> SpeculationEngine
  CallSession --> LLMAdapter
  CallSession --> Guard
  CallSession --> ToolRegistry
  BhashaBridge --> TenantLexicon
  SpeculationEngine --> IntentPredictor
  LLMAdapter <|.. MockLLM
  LLMAdapter <|.. ClaudeLLM
  MockLLM --> DialoguePolicy
  ClaudeLLM --> DialoguePolicy
  ToolRegistry --> Ledger
  Ledger --> Receipt
```

## Deployment

```mermaid
flowchart LR
  dev[Developer / Codespaces] -->|git push main| gh[GitHub]
  gh -->|CI, CodeQL, gitleaks, SBOM| gh
  gh -->|auto deploy| render[Render — engine container\nhaanji-engine.onrender.com]
  gh -->|vercel deploy --prod| vercel[Vercel — console\nhaanji-kappa.vercel.app]
  vercel -->|/engine/* rewrite| render
  gh -->|daily workflow| tb[(transparency branch\nsigned daily roots)]
  render -->|anchors| tb
  meta[Meta WhatsApp] -->|signed webhook| render
  twilio[Twilio] -->|voice webhook + media stream| render
  render --> dg[Deepgram]
  render --> el[ElevenLabs]
  render --> gcal[Google Calendar]
  prom[Prometheus] -->|/metrics| render
  prom --> graf[Grafana]
```
