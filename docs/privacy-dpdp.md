# Privacy and the DPDP Act, 2023

India's Digital Personal Data Protection Act, 2023 applies to a business
that records who called and what they booked. This is how HaanJi meets each
obligation in code, and where the one real tension — an immutable ledger
versus the right to be forgotten — is resolved.

| DPDP obligation | what HaanJi does | where |
|---|---|---|
| **Notice and consent** (s. 5–6) | The greeting names the agent; `HAANJI_CONSENT_LINE` adds a spoken notice to every call ("…AI receptionist, call record ho rahi hai"); the booking itself is confirmed by an explicit yes that is sealed with the receipt | `server._new_session`; the confirmation proof in every receipt |
| **Purpose limitation** (s. 4) | Data is used to answer, book and prove bookings; nothing is shared with a model vendor unless the owner switches the Claude adapter on, and then only the transcript of that turn | `adapters/claude.py`; `render.yaml` (`HAANJI_PROVIDER_LLM=mock`) |
| **Data minimisation** | No audio is stored by the call path (the browser and Twilio streams are transcribed, not kept); phone numbers are masked to four digits in the live feed; the recording page is a separate opt-in with its own notice | `telephony/`, `/record`, `_mask()` |
| **Storage limitation** (s. 8(7)) | `HAANJI_RETENTION_DAYS` purges call records, WhatsApp messages and missed-call rows older than N days every evening; bookings and receipts, the business's own records, are kept | `server.purge_old_records` |
| **Right of access** (s. 11) | `GET /api/privacy/customer/{phone}` lists every booking, lead, call, message count and receipt held for a number | `server.customer_record` |
| **Right to erasure** (s. 12) | `DELETE /api/privacy/customer/{phone}`: shreds the customer's key, anonymises bookings, deletes calls, messages, leads and the customer row; the console has a button | `server.erase_customer`; console → Dashboard → Privacy |
| **Security safeguards** (s. 8(5)) | Receipts' personal fields encrypted per customer; signed webhooks; rate limiting; hardening headers; secrets never in the repository (scanned); opt-in sign-in with per-tenant scope | `pramaan/vault.py`, `test_hardening.py`, `test_auth.py` |
| **Breach notification** (s. 8(6)) | Out of the code's scope; the owner's contact in the pack persona is the grievance channel; the transparency log shows if receipts were altered | `/transparency` |
| **Children** (s. 9) | Not applicable: a receptionist books on behalf of adults; no age data is collected | — |

## The tension, and the mechanism

A receipt must never change (that is the whole point of the Pramaan Ledger),
and a customer may ask to be forgotten. Both hold if the personal fields in a
receipt are stored **encrypted under a key that belongs to that customer** and
kept outside the chain:

* `book_appointment` seals `{"service", "date", "time", "staff", "subject", "phone_enc", "customer_name_enc"}` — the hashes and the signature cover the ciphertext.
* `subject` is a keyed hash of the number, so receipts can be found for a customer without storing the number.
* Erasure deletes the key (**crypto-shredding**). The chain still verifies — not one byte of any receipt changed — but the name and number are unreadable by anyone, including the operator. The verifier page shows "(mita diya gaya)".
* A forgotten customer who books again gets no new key: the receipt records `pii: erased`.

What stays after erasure, and why: the receipt's non-personal facts (a root
canal was booked for 09:30 and confirmed with "haan") are the business's
record of a transaction, which the Act lets it keep for its legitimate
purpose; the person is no longer identifiable from it.

## For the owner (Hinglish)

- Console → Dashboard → **Privacy**: customer ka number daalo → "Kya rakha hai" se list, "Mita do" se sab hata do (receipt rahegi, par naam-number nahi khulega).
- Render → Environment: `HAANJI_RETENTION_DAYS=180` (kitne din call records rakhne hain), `HAANJI_CONSENT_LINE="Yeh call HaanJi AI receptionist utha raha hai aur record ho rahi hai."`
- Kisi vendor (Claude, Deepgram, ElevenLabs) ko data tabhi jaata hai jab aap uski key daalte ho.

## What 1.1 fixed

* **Erasure is exact.** `DELETE /api/privacy/customer/{phone}` requires a whole
  ten-digit number (else `400`) and matches the stored number exactly, in the
  forms it may have been stored (`98…`, `098…`, `9198…`). The 1.0 endpoint
  matched with `LIKE '%…'`, so a request with no digits erased every customer
  of the tenant.
* **Per tenant.** The vault's subject is a keyed hash of *tenant and number*;
  forgetting a customer at one shop leaves their receipts at another shop
  readable. Older receipts (unscoped subject) are still found and shredded.
* **Secure delete.** The vault's SQLite file runs with `secure_delete=ON`, so a
  shredded key is overwritten in the file, not merely unlinked.
* **Consent audio.** A phone confirmation's audio clip is kept only when
  `HAANJI_CONFIRMATION_AUDIO_DIR` is set; by default only its hash exists.
* **Defaults that protect by default (1.1.1).** Call records and WhatsApp
  messages are purged after 180 days unless `HAANJI_RETENTION_DAYS` says
  otherwise (0 keeps everything; bookings and receipts always stay), and the
  public deployment speaks a consent line at the start of every call. The 1.0
  defaults were "keep forever" and "say nothing" unless configured.
