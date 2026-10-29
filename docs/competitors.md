# How HaanJi compares

Feature-by-feature against the products an examiner will name. "Yes" means
documented and generally available in 2026; "partial" means possible with
custom work; "—" means not offered. Where we are unsure we say so.

| capability | HaanJi | Vapi | Retell AI | Bland AI | Google CCAI / Dialogflow CX | Exotel bots | Haptik |
|---|---|---|---|---|---|---|---|
| Hinglish / Benglish out of the box (Latin-script code-mixed) | **yes** (packs, phrase tables) | partial (model-dependent) | partial | partial | partial (hi-IN, not code-mixed) | partial | yes (text) |
| Tenant vocabulary repair after recognition, with a do-no-harm rule | **yes** (Bhasha Bridge, two conditions, measured harmful = 0) | — (biasing hints only) | — | — | partial (speech adaptation hints) | — | — |
| Indic-aware phonetic key, compared against Soundex/Metaphone | **yes** (Table 8) | — | — | — | — | — | — |
| Tools run speculatively on partial transcripts, byte-identical claim | **yes** (Table 4) | — | — | — | — | — | — |
| Deterministic, auditable dialogue policy; LLM optional and write-safe | **yes** | — (LLM-driven) | — | — | partial (flows) | partial | partial |
| Signed, hash-chained receipt per booking with the caller's words | **yes** (Pramaan) | — | — | — | — | — | — |
| Customer-verifiable record (browser verifier, public key, transparency log) | **yes** | — | — | — | — | — | — |
| Refuses a write without a confirmation proof (enforced below the policy) | **yes** | — | — | — | — | — | — |
| Real phone number (PSTN) | yes (Twilio bridge; Exotel adapter point) | yes | yes | yes | yes | yes | partial |
| WhatsApp channel with the same policy | yes (Meta Cloud API, signed) | partial | partial | — | yes | yes | yes |
| Owner console: live feed, insights, receipts, onboarding wizard | yes | partial | partial | partial | yes (Google tooling) | partial | yes |
| Google Calendar / iCalendar feed of bookings | yes | via functions | via functions | via functions | via integrations | partial | partial |
| Self-hostable, open source, runs offline with mocks | **yes** (Apache-2.0) | — | — | — | — | — | — |
| Reproducible evaluation with baselines and CIs | **yes** | — | — | — | — | — | — |
| Day-before reminder with reply handling (1 = confirm, 2 = cancel, through the same ledger) | **yes** (1.1) | via functions | via functions | — | partial (flows) | yes | yes |
| Deposit link with every booking; payment sealed in the receipt chain | **yes** (1.1, Razorpay / mock) | via functions | via functions | — | via integrations | — | partial |
| Waitlist: a cancellation offers the freed slot to the first caller waiting | **yes** (1.1) | — | — | — | partial | — | — |
| Caller identity before changing a booking (caller-id / sender, or the receipt code on the web) | **yes** (1.1, recorded in the receipt) | partial | partial | partial | partial | partial | partial |
| Price model | ≈ ₹3/call measured (vendor minutes + ₹0.0002 infra) | per-minute + model | per-minute | per-minute | per-request/minute | per-minute | per-conversation |

What the others do better today: production telephony at scale, many
languages via large models, vendor SLAs, and polished voices. What none of
them does: the three mechanisms in the first block, which are what this
project is about. The honest framing for a viva: HaanJi is a research-grade
engine with a product-grade surface, not a competitor's replacement.

Sources: public documentation and pricing pages of each product as of
October 2026; where a cell says "partial" the capability depends on model
choice or custom integration rather than a documented feature.
