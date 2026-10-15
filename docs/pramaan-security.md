# Pramaan Ledger — threat model and the property it enforces

This is the formal statement behind "every write is sealed and nobody can
change it afterwards", with what it assumes, what it does not cover, and
where the tests are.

## Objects

* **Receipt** `r = (seq, action, args, confirmation, excerpt, version, occurred_at)`.
* **Payload hash** `P(r) = SHA-256(canon(args) ‖ canon(confirmation) ‖ excerpt ‖ occurred_at ‖ version ‖ action)`, where `canon` is canonical JSON (sorted keys, no whitespace, UTF-8; RFC 8785 in spirit).
* **Chain hash** `C(r_i) = SHA-256(C(r_{i-1}) ‖ P(r_i))`, with `C(r_0) = 0^256` (genesis).
* **Signature** `S(r_i) = Ed25519_sign(sk_tenant, C(r_i))`.
* **Daily anchor** `A(d) = Ed25519_sign(sk_tenant, MerkleRoot({C(r_i) : day(r_i) = d}) ‖ d)`, published to a place the server does not control (the repository's `transparency` branch).
* **Verifier** `V(receipts, pk)`: recomputes every `P`, every `C` from genesis, checks every `S` against `pk`, and reports the first sequence number at which any of them fails.

## Property 1 — tamper evidence

For any sequence of receipts `R = r_1..r_n` sealed by the ledger and any `R' ≠ R` obtained by (a) changing any sealed field of any receipt, (b) removing any receipt other than the first or the last, (c) reordering receipts (swapping sequence numbers), or (d) inserting a receipt not signed by `sk_tenant`: `V(R', pk)` reports failure, and for (a)–(c) it names a sequence number at or before the first difference. **Truncation and prefix removal** — cutting the chain's tail, or exporting it from a later sequence number — are *not* detectable by the chain alone (a shorter chain is internally valid); it is detected by comparing the day's Merkle root with the published anchor, which pins the whole receipt set of each day. The property test `test_truncation_is_invisible_to_the_chain_and_visible_to_the_anchor` states this exactly, so the limitation cannot be quietly lost.

*Why.* (a) changes `P(r_i)`, so the stored `C(r_i)` no longer equals `SHA-256(C(r_{i-1}) ‖ P(r_i))`; the attacker can recompute `C` and every later `C`, but cannot produce `S` for the new values without `sk`. (b) and (c) break the `prev_hash` link at the gap. (d) fails the signature check. The argument rests on SHA-256 collision resistance and Ed25519 existential unforgeability under chosen-message attack (EUF-CMA); both are standard assumptions.

*Evidence.* `engine/tests/test_pramaan.py` (field mutations, deletion, forged re-hash); `engine/tests/test_pramaan_properties.py` (Hypothesis generates random receipts and random mutations: every mutation of every field, every deletion, every swap is detected); the benchmark's 80/80 mutation table (REPORT Table 5); the browser verifier is an independent implementation of `V` (`engine/haanji/web/verifier.js`).

## Property 2 — no write without a confirmation proof

`Ledger.append` raises `LedgerError` when `confirmation is None`, inside the backend transaction, so the booking it would have sealed is rolled back; the counter `haanji_ledger_unconfirmed_refused_total` increments and `ops/alerts.yml` pages on it. The dialogue policy produces a write only with `needs_confirmation=True` after an affirmative reply to a read-back; the hosted-model adapter cannot produce one at all (a model's write request becomes the read-back question; the yes is handled by the policy). The property is enforced below every decision-maker.

*Evidence.* `test_the_ledger_refuses_an_unconfirmed_write`, `test_a_confirmed_yes_goes_through_the_policy_and_the_ledger`, the ablation's "unconfirmed writes" column (0 in every configuration and seed), `test_the_ledger_counts_a_refused_unconfirmed_write`.

## Property 3 — the proof is bound to the caller's words

The `confirmation` object sealed in `P(r)` contains the agent's question text, the caller's reply text, both start times, their offset and the recogniser's confidence. A receipt therefore asserts "this question was asked at t1, this answer began at t2 with confidence c, and this action followed". It does not assert that the recognition was correct: a mis-recognised "haan" is sealed as the text the engine acted on, with its confidence — which is exactly what a dispute needs to see.

## Threat model

| attacker | capability | outcome |
|---|---|---|
| Business owner / staff with database access | edit, delete, reorder rows | detected by any verifier with `pk` (Property 1); the daily anchor on the transparency branch shows the day's root changed |
| The platform operator (us) | everything above plus the server code | cannot forge past receipts without `sk`; can forge *new* receipts, which is why `sk` must be held in an HSM/KMS in production and why anchors are published outside the server; a published root pins each day |
| Attacker with `sk` (key leak) | sign arbitrary new receipts | past days remain pinned by published anchors; rotate keys (`ensure_key` creates a new `key_id`; receipts carry `key_id`; old `pk` stays valid for old receipts) |
| Customer | disputes a booking | reads their receipt at `/verify?code=…`: the question, their answer, the time; verification runs in their browser |
| Network attacker | tampers with the export in transit | hashes and signatures fail; the verifier page is served over TLS |
| Recogniser error | "nahi" heard as "haan" | sealed as heard with confidence; not prevented by the ledger (that is Bhasha Bridge's job and the read-back's); the receipt makes it auditable |

## Out of scope

Availability (a deleted database loses receipts; anchors prove loss, not content), confidentiality of receipt contents at rest (see docs/privacy-dpdp.md for the PII vault), and correctness of the dialogue itself.

## Key management in production

Per-tenant Ed25519 keys; the demo stores the private key in SQLite (the schema says so), production stores it in a KMS and the ledger calls out to sign. Rotation: a new `key_id` per period; receipts record the `key_id` that signed them; the export carries every public key ever used. Revocation: a compromised key's later receipts are distrusted from the first anchor that disagrees with the transparency branch.

## Why these primitives

SHA-256: universal, hardware-accelerated, no known practical collision. Ed25519: 64-byte signatures, deterministic (no nonce reuse), fast to verify in a browser (TweetNaCl). Merkle roots: a day's receipts pinned by one 32-byte value that fits in a git commit, which is where ours go.
