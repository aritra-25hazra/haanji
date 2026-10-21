# HaanJi: Tenant-Vocabulary Repair, Speculative Tool Execution and Verifiable Consent Receipts for a Hinglish Voice Receptionist

<p class="byline">Aritra Hazra, Prabhav Upadhayay, Anuj Uniyal — B.Tech IT (AI), Medi-Caps University · Draft for review, October 2026 · Code and data: github.com/aritra-25hazra/haanji</p>

<div class="abstract" markdown="1">
**Abstract** — Voice agents for small Indian businesses fail on three specific points: the catalogue words a booking turns on are exactly the words a general recogniser mangles; latency is felt at the turn, not on average; and "the AI booked it" is no record of consent. We present HaanJi, an open-source engine with one mechanism for each. *Bhasha Bridge* indexes a tenant's catalogue by an Indic-aware phonetic key and repairs recogniser output only when the recogniser was unsure *and* the key matches exactly. *Speculative Turn Execution* runs read-only tools from partial transcripts and claims a result only for byte-identical arguments. The *Pramaan Ledger* seals every write into an Ed25519-signed, hash-chained receipt that binds the action to the caller's confirmed words and refuses writes without one. On an ablation over 24 scripted calls in six vertical packs and three languages (five seeds), the bridge reduces catalogue entity error from 32.6% to 0.82% at 30% synthetic noise with no harmful correction, and lifts task success from 76.4% to 90.8%; against Soundex, Metaphone, Double Metaphone, NYSIIS and edit distance alone, with everything else fixed, the key is best on synthetic noise (every pairwise McNemar p < 0.001) and within a point of the classics on real recogniser output. Speculation lowers read-turn latency from 246 to 142 ms (p50) at a 41.9% hit rate without changing a transcript. The ledger detects 80/80 single-field mutations, deletion and re-hashed forgery, and accepts zero unconfirmed writes in every configuration. A pilot on synthetic Indian-English speech through Whisper exposed an open confidence gate and harmful corrections, fixed by three stated guards; on that data the bridge removes an eighth of the entity errors, biasing the recogniser with the pack vocabulary halves them before any repair, and calibrating the gate does not help, because the guards and not the gate carry the safety. Real recordings and a user study are the next step.
</div>

<div class="cols" markdown="1">

## I. Introduction

A neighbourhood clinic answers a fraction of its calls; the callers who get through speak Hinglish and name services, doctors and localities a general-purpose recogniser has never seen. The ingredients for an automated receptionist — streaming recognition, a language model, synthesis — are commodities. What is not is a system a business can *trust to take a booking*: one that hears its own vocabulary, answers without a pause, and can show afterwards what was agreed.

We make three contributions, each small, measured and tested, and one methodological one. (1) **Bhasha Bridge**: a per-tenant phonetic index with a key written for Indian-English phonology and a two-condition correction rule that cannot damage a transcript the recogniser got right. (2) **Speculative Turn Execution**: prediction and early execution of read-only tools from partial transcripts, with purity, argument identity, freshness and invalidation enforced by tests. (3) **Pramaan Ledger**: signed, hash-chained receipts that bind a write to the caller's confirmation and refuse writes without one, verifiable by anyone with the public key. (4) A reproducible harness — four-way ablation, a corruption model independent of the correction layer, classic-key baselines, significance tests — that regenerates every number from a clean checkout with no network.

## II. Related Work

Contextual biasing steers end-to-end recognisers towards phrases supplied at request time [Pundak 2018; Zhao 2019] but acts only before the fact and only if the recogniser honours the list; we bias *and* repair. Soundex, Metaphone and Double Metaphone [Russell 1918; Philips 1990, 2000] encode English phonology; Hinglish merges distinctions English keeps (v/w, s/sh, dental/retroflex) and keeps some English merges apart, so we state a small Indic rule set and test it rule by rule. Indian-accented and code-mixed speech is documented as hard for general models [Bali 2014; Javed 2023, 2024; Radford 2023]. Speculating on the likely branch and discarding the work if wrong is the oldest latency trick in architecture [Hennessy & Patterson 2017] and, recently, in decoding [Leviathan 2023; Chen 2023]; we apply it at the dialogue turn with the same correctness argument. Hash chains, Merkle trees and transparency logs [Haber & Stornetta 1991; Merkle 1987; Laurie 2013] with Ed25519 [Bernstein 2012] are standard; what we seal — the confirmation question, the reply, their timing and confidence — and the refusal of unconfirmed writes are not. Explicit confirmation before consequential actions is a long-standing design in spoken dialogue [Bohus & Rudnicky 2005; Skantze 2005].

## III. System

One pass through the turn controller is the whole hot path: partial transcripts feed the speculation engine; the final transcript is corrected by Bhasha Bridge, checked by the guardrails, then handed to the dialogue adapter (a deterministic policy by default; a hosted model behind the same boundary, which cannot write); tool calls claim speculative results or execute; writes are sealed by the ledger; the reply is synthesised, cancellable on barge-in. A *vertical pack* is one YAML file — catalogue, staff, hours, persona, refusals, lexicon seeds, knowledge, scenarios; six packs in three languages (Hinglish, Benglish, Marathinglish) share one engine. The system is deployed (engine, console, WhatsApp webhook, a Twilio media-stream bridge) and the demo runs with mock providers.

### A. Bhasha Bridge

The key applies an ordered rule list before encoding: long vowels shorten; v/w, s/sh/z, ch/chh, t/d/th/dh, k/kh/q/c, g/gh, b/bh/p, n/m, l/r merge; h and y drop; a word-initial vowel is bucketed (a dropped initial /h/); vowels after the first position are removed. A span is replaced only when recogniser confidence is below 0.85 *and* its key equals a lexicon key exactly with surface edit distance ≤ 2 (≤ 3 for phrases). Grammar words, the words of the booking dialogue itself, tokens of fewer than four letters and lexicon forms of fewer than four letters are never evidence; the last three guards came from the real-recogniser pilot (§V-D).

### B. Speculative Turn Execution

A deterministic predictor with a small logistic scorer proposes a read-only tool from each partial; the engine runs it at once. Only registry-declared read-only tools are speculated; a result is claimed only for byte-identical arguments (predictor and policy share one extractor); results expire after 4 s and are claimed once; any write invalidates everything; at most 2 in flight, 3 per turn. A test asserts the transcript is identical with speculation on and off.

### C. Pramaan Ledger

Payload hash = SHA-256 over canonical JSON of the action, its arguments, the confirmation proof (question, reply, timings, confidence), the excerpt, the pack version and the timestamp; chain hash = SHA-256(previous chain hash ‖ payload hash); Ed25519 signature over the chain hash; a signed Merkle root per day published outside the server. `append` raises on a missing proof inside the transaction. Personal fields are encrypted per customer so that erasure (crypto-shredding) leaves the chain valid. Property-based tests cover every mutation, interior deletion and reordering, and state what the chain alone cannot see (truncation), which the anchor catches.

## IV. Method

*Entity error rate* (EER) is the fraction of catalogue entities in what the caller said that the transcript gets wrong; *task success* is reaching the scenario's expected outcome; latency is engine-side in nominal milliseconds under a time-scaled simulation; every correction is classified beneficial, neutral or *harmful*. Noise comes from (i) hand-authored corruptions in the packs' 24 scenarios and (ii) a corruption model written independently of the lexicon that substitutes Indian-English confusions on content words, including words in no lexicon. Experiments: the four-way ablation (full / no speculation / no bridge / neither) on authored scenarios; a transcript-level experiment over 2,430 corrupted sentences per noise level built from every catalogue entity in eight frames; an end-to-end sweep under the same noise; six keyers swapped under identical rules with McNemar's test on paired per-sentence outcomes; a per-rule ablation; eleven ledger attacks; a concurrency ladder; a pilot through a real recogniser, repeated with the pack vocabulary as the recogniser's prompt; a calibration and a sweep of the confidence gate; and a learned speculation predictor against the hand-set one. Five seeds × three repetitions; intervals are 95% t-intervals over seeds.

## V. Results

### A. Correction

At 30% noise over 2,430 sentences and 3,303 entities, EER falls from 32.6% to 0.82% (97.5% relative) at 99.1% precision; harmful corrections are zero in every seed at every rate (McNemar off vs on: b = 936, c = 0, p < 0.001). End to end, task success rises from 76.4% to 90.8% at 30% noise and from 59.7% to 81.1% at 45%; the Benglish and Marathinglish packs gain as much as the Hinglish ones.

**Table I.** Entity error after correction at 30% noise by keyer (synthetic), and on the 300-utterance real-recogniser pilot.

| keyer | synthetic | pilot | harmful (pilot) |
|---|---|---|---|
| edit distance only | 1.45% | 31.1% | 6 |
| exact spelling | 32.18% | 33.3% | 0 |
| Soundex | 4.15% | 30.1% | 0 |
| Metaphone | 8.08% | 31.1% | 0 |
| NYSIIS | 3.24% | 32.0% | 0 |
| Double Metaphone | 6.78% | 30.1% | 0 |
| Bhasha (ours) | 0.88% | 29.2% | 0 |

Every classic key is worse than ours on synthetic noise (pairwise McNemar p < 0.001; against the edit-distance bound alone p = 0.007). On the pilot the keys are within a point of one another: where the recogniser paraphrases and merges tokens rather than substituting sounds, the key matters less than the safety rule. A per-rule ablation shows three rules carry the synthetic result (k/kh/q/c, v/w, initial h) and twelve are not exercised by the corruption model — a statement about the harness's coverage as much as the key.

### B. Speculation

Read-turn p50 falls from 246 to 142 ms (42.3%) and p90 from 310 to 238 ms, at a 41.9% hit rate; no outcome and no transcript changes. Write turns are never speculated: the booking turn's p90 is 194 ms with speculation and without it. With the bridge off the hit rate falls to 19.2%: the predictor derives arguments from the same mangled entities the policy does. A logistic predictor fitted to the harness's 156 partials (leave-one-pack-out precision 1.00, recall 0.25–1.00) is more precise and less eager: in a paired single run it lifts the hit rate from 41.9% to 44.4% and slows the median read turn from 116 to 160 ms, because the partials it declines are the ones where a hit saves most; for latency recall is what matters, and the hand-set weights stay.

### C. Ledger

80/80 single-field mutations across eight fields, a deleted receipt and a re-hashed forgery are detected; zero unconfirmed writes are accepted in any configuration, seed or attack. Property-based tests generate random receipts and mutations with the same result, and record that truncation is caught by the published daily root rather than by the chain.

### D. A real recogniser

Synthetic Indian-English speech (three OS voices) through faster-whisper, decoded as English with no hints: WER 89%, EER 33.8% → 30.1% after the guards and 29.2% with a merged-token rule. Whisper's word probabilities fell below the 0.85 gate for 80% of words, so the bridge's first condition was effectively off and it made 8 harmful corrections (six were *slot* → *Salt*, a fragment of the locality Salt Lake, one sound key away) until three guards were stated: words of the booking dialogue are never corrected, no single token under four letters is replaced, no lexicon form under four letters is evidence. The merged-token rule splits a long, unsure token the lexicon cannot explain whole where both halves are known words and one is a catalogue word ("subhahroot" → "subah root"); its first version split before the whole-token rule ran and raised synthetic EER from 0.80% to 1.18% with the harmful count still zero, a blind spot of that count (a neutral correction pre-empting a beneficial one) that the ordering condition closes. Calibrating the gate per recogniser — Youden's J on the ROC of word probability against alignment-labelled errors — gives thresholds of 0.64 (English), 0.65 (biased) and 0.73 (Hindi) at AUC 0.62–0.77, and applying them *lowers* the gain (29.2% → 31.1%); a sweep from 0.5 to no gate at all finds zero harmful corrections throughout, so on this recogniser the guards and the second condition carry the safety and the gate contributes nothing. Biasing is the lever: with the pack vocabulary as Whisper's initial prompt, WER falls to 68.5% and EER before any repair halves to 15.1%; the bridge then adds 6.1% relative at zero harm, and one correction (*meen* → Meena) invents an entity the harmful count cannot see but the entity error rate charges. All of these gains were evaluated on the 300 utterances that motivated them. A corruption model learned from Whisper's output on public rural Hindi telephone speech (Gram Vaani, 110 utterances, WER 80%, 26% of words dropped) and replayed over the benchmark corpus gives the honest range: the bridge removes 28–32% of entity errors under data-shaped noise at over 94% precision and no harmful corrections, against 97% under our own model, which substitutes and never drops.

### E. Concurrency and cost

One process answered 5 to 50 concurrent scripted callers with turn p50 under 7 ms, p95 under 187 ms and no errors at 2548 calls per minute; the expected-outcome rate fell from 97% to 70% because sixty callers filled one calendar and the fixed script did not take the offered alternative, which is the calendar working.

## VI. Threats to Validity

EER ignores date and number errors (task success does not). The corruption model was written by us; mitigated by corrupting words outside every lexicon, by counting harmful corrections, and now by a model learned from a real recogniser's output. Latencies are engine-side under simulated time; scripted callers do not adapt; six packs and 24 scenarios are a small authored sample; the guards, the merged-token rule, the calibrated gate and the biasing comparison were all evaluated on the same 300 pilot utterances; five seeds give honest but wide intervals, and overlapping intervals are read as "not separated".

## VII. Conclusion

A voice receptionist for Indian small businesses fails for three specific reasons, and each has a small, inspectable, measured mechanism here. The bridge removes most catalogue entity errors under heavy synthetic noise without harm and beats the classic keys; on a real recogniser's output it needed three stated rules to stay safe and then helped far less; biasing that recogniser with the tenant's vocabulary halves entity error before the bridge runs, which makes biasing the lever and the bridge the safety net behind it, and calibrating the bridge's gate was measured and found not to matter. The next work is recordings, not more synthetic noise. Speculation takes a large fraction off read-turn latency with identical transcripts. The ledger makes an unconfirmed booking impossible rather than unlikely, with or without a hosted model in the loop, and survives the right to be forgotten. Everything regenerates from a clean checkout.

## References

<div class="refs" markdown="1">
Bali, K. et al. (2014). "I am borrowing ya mixing?" EMNLP CodeSwitch. · Bernstein, D. J. et al. (2012). High-speed high-security signatures. J. Crypt. Eng. · Bohus, D., Rudnicky, A. (2005). Sorry, I didn't catch that! SIGdial. · Chen, C. et al. (2023). Accelerating LLM decoding with speculative sampling. arXiv:2302.01318. · Haber, S., Stornetta, W. S. (1991). How to time-stamp a digital document. J. Cryptology. · Hennessy, J., Patterson, D. (2017). Computer Architecture, 6e. · Javed, T. et al. (2023). Svarah. Interspeech. · Javed, T. et al. (2024). IndicVoices. ACL Findings. · Laurie, B. et al. (2013). Certificate Transparency. RFC 6962. · Leviathan, Y. et al. (2023). Fast inference via speculative decoding. ICML. · Merkle, R. (1987). A digital signature based on a conventional encryption function. CRYPTO. · Philips, L. (1990, 2000). Metaphone; Double Metaphone. · Pundak, G. et al. (2018). Deep context. SLT. · Radford, A. et al. (2023). Robust speech recognition via large-scale weak supervision. ICML. · Russell, R. C. (1918). US Patent 1,261,167. · Skantze, G. (2005). Exploring human error recovery strategies. Speech Comm. · Zhao, D. et al. (2019). Shallow-fusion end-to-end contextual biasing. Interspeech.
</div>

</div>
