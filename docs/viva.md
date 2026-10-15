# Viva — the questions, the answers, and where the evidence is

Each answer is three lines at most. The last line says where an examiner can
check it. Numbers are from `research/REPORT.md` (five seeds, 95 % CI);
single-run numbers in the README agree within those intervals.

## The problem and the claim

**1. What problem does this solve?** Small Indian businesses lose bookings because nobody answers the phone; the callers who get through speak Hinglish and name services, doctors and localities a general recogniser has never seen. HaanJi answers in that register, books, and can prove what was agreed. *Evidence: README §"What a call looks like"; REPORT §1.*

**2. What is new? Isn't this just an LLM with a phone?** Three mechanisms not found together in any product we could find: a per-tenant Indic phonetic index with a two-condition correction rule; speculative execution of read-only tools from partial transcripts with a byte-identical claim rule; and signed, hash-chained receipts that bind every write to the caller's confirmed words and refuse writes without one. An LLM is optional and sits behind the same boundary (§7). *Evidence: REPORT §1.2, §4–§6; docs/competitors.md.*

**3. Why not Google Dialogflow / Rasa / Vapi / Retell?** None does tenant-vocabulary repair with a safety condition, none speculates tool calls, none produces a verifiable record of consent; most are English-first and bill per minute of model time. The comparison table lists this feature by feature. *Evidence: docs/competitors.md.*

**4. Why a deterministic policy rather than an LLM for dialogue?** Reproducibility (a regression is a bug, not a sampling accident), auditability (the ledger audits decisions), and latency (microseconds). The Claude adapter exists for the phrasings the policy cannot anticipate, and even then it cannot write. *Evidence: REPORT §3.3, §7; `engine/haanji/adapters/claude.py`; test `test_a_confirmed_yes_goes_through_the_policy_and_the_ledger`.*

## Bhasha Bridge

**5. How does the phonetic key differ from Soundex or Metaphone?** It encodes Indian-English phonology: v/w, s/sh, dental–retroflex and aspirate merges, long-vowel shortening, a bucketed initial vowel for a dropped /h/. Soundex and Metaphone encode English phonology and both under- and over-merge for Hinglish. We measured all of them with the same lexicon and rule. *Evidence: REPORT §4.1, Table 8; `engine/haanji/bhasha/phonetics.py`.*

**6. Did you compare against baselines?** Yes: edit distance only, exact spelling, Soundex, Metaphone, NYSIIS, Double Metaphone, and ours, on synthetic noise and on the real-recogniser pilot, with McNemar's test on per-sentence outcomes. *Evidence: REPORT Tables 8–9; `research/baselines.json`.*

**7. Which rules matter?** The per-rule ablation removes each of the 16 normalisation rules in turn and reports the entity-error change at 30 % noise. *Evidence: REPORT Table 10; `research/harness/baselines.py`.*

**8. Why two conditions? Why not correct whenever the key matches?** Because a correction layer that overwrites a correct transcript is worse than none. Low recogniser confidence plus an exact key match plus a small edit distance together keep harmful corrections at zero on synthetic data; the pilot showed what happens when the confidence gate is open (§4.5). *Evidence: REPORT §4.1, §4.5; test `test_correction_never_damages_a_correct_transcript`.*

**9. Why entity error rate and not word error rate?** The agent books correctly if it gets the service, the doctor and the place right; it can survive a hundred wrong function words. WER is reported alongside on the pilot for comparison (89 %). *Evidence: REPORT §3.4, §4.5.*

**10. Your noise is synthetic. What about real recognisers?** We built the pipeline and ran a pilot: synthetic Indian-English speech through faster-whisper. It found a real weakness (confidence not calibrated; `slot`→`Salt`), which three stated guards fixed; on that data the bridge helps about a tenth, not 97 %. Volunteers' recordings go through the same pipeline. *Evidence: REPORT §4.5; `research/real_asr.json`, `real_asr_v0.json`; `research/collect/`.*

**11. Does it generalise beyond Hindi?** The Benglish pack (Kolkata) gains as much as the Hinglish ones from the same key rules, and a Marathinglish pack (Pune) was added afterwards with one phrase-table row and one YAML file; the policy's language is a phrase table and a vocabulary list, no forked code. *Evidence: REPORT Table 3; `packs/clinic_kolkata.yaml`, `packs/clinic_pune.yaml`; `engine/haanji/speak.py`; `engine/tests/test_marathi.py`.*

**12. Known failure of the key?** /b/ and /p/ merge, so *braces* and *prices* collide; the confidence condition keeps it from mattering, and a test documents it so it cannot be lost. *Evidence: REPORT §4.4; test `test_a_known_collision_is_documented_not_hidden`.*

## Speculation

**13. What is speculative turn execution?** Branch prediction for a conversation: a cheap predictor guesses the read-only tool the turn will need from the partial transcript and runs it while the caller is still talking; the real turn claims the result only if it asks for byte-identical arguments. *Evidence: REPORT §5.1.*

**14. How do you guarantee it never changes an answer?** Four properties with tests: only read-only tools are speculated (registry-enforced); claims require identical arguments (both sides share `nlu.py`); results expire in 4 s and are claimed once; any write invalidates everything. A test asserts the transcript is identical with speculation on and off. *Evidence: `engine/tests/test_speculation.py`; `test_the_result_is_identical_with_speculation_on_and_off`.*

**15. How much does it save?** Read-turn p50 from 256 to 142 ms (44 %), at a 46 % hit rate; write turns are never speculated, so the booking turn's p90 is unchanged (209 vs 213 ms), and we say so. *Evidence: REPORT Table 4, Figure 3.*

**16. What does a wrong guess cost?** Bounded work: at most 2 in flight, 3 per turn; about 42 wasted speculations per 63-call run. Never correctness. *Evidence: REPORT §5.2.*

## Pramaan Ledger

**17. What exactly is in a receipt?** The action and arguments, the agent's confirmation question, the caller's exact reply, their timings and offset, the recogniser's confidence in the reply, a redacted excerpt, the pack version, a timestamp; SHA-256 payload hash, chain hash over the previous one, Ed25519 signature; daily Merkle root. *Evidence: REPORT §6.1; `engine/haanji/pramaan/receipt.py`.*

**18. What is the security property, formally?** Any change to any sealed field, any deletion, and any re-signed forgery is detected by a verifier holding only the public key; and no write reaches the business without a confirmation proof. The threat model and proof sketch are written down; property-based tests generate random mutations. *Evidence: docs/pramaan-security.md; `engine/tests/test_pramaan_properties.py`; REPORT Table 5.*

**19. What if the tenant's private key leaks?** Past receipts stay verifiable (signatures were valid when made and daily roots were published); future forgeries are the risk, so keys rotate and the transparency log pins each day's root outside the server. *Evidence: docs/pramaan-security.md §key management; `/transparency`.*

**20. Why Ed25519 and not RSA/ECDSA?** Small keys and signatures, fast, deterministic (no nonce-reuse failure mode), widely verifiable in browsers (TweetNaCl). *Evidence: REPORT §2 (Bernstein et al. 2012); `engine/haanji/web/verifier.js`.*

**21. How does a customer verify without trusting you?** The verifier runs in their browser: it re-derives every hash and checks every signature from the export and the public key; the receipt link in their WhatsApp opens their own receipt. *Evidence: `/verify?code=…`; test `test_a_whatsapp_booking_reply_carries_the_customers_receipt_link`.*

**22. Immutable ledger versus the right to erasure (DPDP)?** Personal fields in receipts are encrypted with a per-customer key kept outside the chain; erasure deletes the key (crypto-shredding), so hashes and signatures still verify but the data is unreadable. *Evidence: docs/privacy-dpdp.md; `engine/haanji/pramaan/vault.py`; `/api/privacy/*`.*

## Evaluation and rigour

**23. How many runs? Are the differences significant?** Five seeds × three repetitions for the ablation; 2,097 sentences per noise level for the correction layer; McNemar's test on paired per-sentence outcomes (p < 0.001 for bridge off vs on and for ours vs every baseline at 30 %). *Evidence: REPORT §3.4, Table 8; `research/harness/stats.py`.*

**24. Confidence intervals overlap in some rows. So?** Then that row is "not separated by this experiment", and the report says so rather than claiming a win. *Evidence: REPORT §8 "Statistical".*

**25. Where is the real data?** Pilot on synthetic speech through a real recogniser (done); public Hindi telephone speech through Whisper with a corruption model learned from it (§4.8); volunteer recordings and the user study need people and are pending with their kits ready. *Evidence: REPORT §4.5–§4.6, §9.*

**26. How reproducible is this?** One clean checkout, no network, no key: `pytest` (≈300 tests), `selftest` (21 scenarios), `bench`, and the five-seed harness regenerate every table. CI runs it on every push. *Evidence: REPORT Appendix A; `.github/workflows/ci.yml`.*

**27. What are the threats to validity?** Construct (EER ignores date/number errors), internal (the corruption model was written by us), external (engine-side latency, scripted callers, five packs), statistical (few seeds). Each is listed with what was done about it. *Evidence: REPORT §8.*

**28. What did not work?** Listed: the open confidence gate on Whisper probabilities, `to do`→`thyroid profile` via an alias, merged tokens the n-gram matcher cannot split, the scripted callers who do not take an offered alternative under load. *Evidence: docs/failure-gallery.md; REPORT §4.5, §5.3.*

## Engineering

**29. How does it scale?** One process: 50 concurrent scripted callers, p50 6 ms, p95 186 ms, no errors, 2,500 calls/min; CPU per call measured. Vendors' round trips will dominate before the engine does. *Evidence: REPORT §5.3, Table 7; `research/load_test.json`.*

**30. What does a call cost?** The cost model's constants are in `insights.py` (telephony, STT, TTS per minute, infra per call); infra is now measured from CPU-seconds in the load test. About ₹3/call against ≈ ₹9 for a part-time receptionist at 50 calls/day. *Evidence: README "AI insights"; `research/load_test.json` → cost.*

**31. Is it deployed?** Engine on Render (Docker), console on Vercel, WhatsApp webhook live and signed, CI + CodeQL + secret scanning + SBOM on every push, Prometheus metrics, a transparency log on a GitHub branch. *Evidence: README badges; `/api/status`; `/metrics`.*

**32. Security of the demo?** Rate limiting per client, hardening headers, signed Meta and Twilio webhooks, opt-in sign-in with WhatsApp one-time codes and per-tenant scope, no secrets in the repo (gitleaks). *Evidence: `engine/tests/test_hardening.py`, `test_auth.py`, `test_whatsapp_webhook.py`.*

**33. How does a business get onboarded?** Five answers in the console build a complete pack — persona, guardrails for that kind of business, knowledge base, two generated scenarios — which run before saving. Pack Studio edits the YAML afterwards. *Evidence: `engine/haanji/onboard.py`; test `test_the_generated_scenarios_pass_on_the_generated_pack`.*

**34. What happens when the model or a vendor is down?** The dialogue adapter falls back to the deterministic policy for that turn; a failed receipt notification or calendar push never blocks the call; the WhatsApp webhook de-duplicates Meta's retries. *Evidence: test `test_a_vendor_failure_falls_back_to_the_policy`; `server.py` `_notify_customer`.*

**35. Guardrails — can the model talk its way past them?** No: guardrails run on the corrected transcript before the dialogue adapter sees it, and refusals/escalations are also described to the model. *Evidence: `engine/haanji/guardrails.py`; REPORT §3.3.*

**36. Barge-in on a real phone line?** The Twilio bridge cancels synthesis and clears Twilio's audio buffer when a partial transcript arrives while the agent is speaking. Tested with fake vendors over a WebSocket. *Evidence: `engine/tests/test_telephony.py::test_barge_in_clears_twilio_s_buffer`.*

**37. Accessibility and UI quality?** Every page passes axe (WCAG 2 AA) at desktop and 390 px with no horizontal overflow; icons are SVG, no emoji; one design system (Signboard) across demo and console. *Evidence: `engine/tests/visual_check.py`; `/design`.*

## Research framing

**38. Related work?** Contextual biasing (Pundak 2018, Zhao 2019), phonetic matching (Soundex, Metaphone), code-mixed Indian speech (Bali 2014, IndicVoices, Svarah), speculative execution and decoding (Hennessy & Patterson, Leviathan 2023), tamper-evident logs (Haber & Stornetta 1991, Merkle, Certificate Transparency), confirmation in dialogue (Bohus & Rudnicky 2005). *Evidence: REPORT §2 and references.*

**39. Could this be published?** The IEEE-format paper draft condenses the report; the contributions are measured, the baselines are present, the limitations are stated. The missing piece for a strong venue is the volunteer-recording study. *Evidence: `research/PAPER.md` / `PAPER.pdf`.*

**40. What would you do with six more months?** Real recordings and the user study; a learned predictor for speculation; a closed-vocabulary repair for dates and numbers; a PSTN deployment measured end to end; Marathi, Tamil and Telugu packs. *Evidence: REPORT §9.*

## Ethics, privacy, law

**41. Do callers know they are talking to a machine?** The greeting names the agent; a consent line can be switched on per deployment; the policy never claims to be human and hands off on request. *Evidence: docs/privacy-dpdp.md; `HAANJI_CONSENT_LINE`.*

**42. What personal data is stored and for how long?** Phone, name, the transcript, the booking; retention is configurable (`HAANJI_RETENTION_DAYS`), erasure is an endpoint and a console button, logs mask numbers to four digits. *Evidence: docs/privacy-dpdp.md; `/api/privacy/*`; live feed masking.*

**43. Bias and fairness?** The key rules are stated claims about Indian-English pronunciation, testable per rule; the Benglish pack is the check that Hindi is not privileged in the engine. Accent coverage on real speech is the open question (§9). *Evidence: REPORT §4.1, §8.*

## Project process

**44. Who did what?** Three authors; the repository history and co-author trailers show each change. *Evidence: `git log`.*

**45. How was it tested?** ≈300 unit, property and integration tests; 24 scenario tests in three languages; a visual/accessibility pass; a load test; a real-recogniser pilot. *Evidence: REPORT Appendix C.*

**46. Why Python for the engine and Java for the core API?** Python for the research iteration and the speech/ML ecosystem; Java (Spring) for the owner-facing API with ArchUnit rules; the ledger is ported to both and the property is tested end to end on the Python side. *Evidence: README "Honest notes".*

**47. What is the hardest bug you found?** The bridge's confidence gate was open on a real recogniser's probabilities and it corrected `slot` to `Salt` six times; the fix was two stated rules, and the finding changed the report's headline from 97 % to "about a tenth on real recogniser output". *Evidence: REPORT §4.5.*

**48. What is the single most important number?** Zero: unconfirmed writes accepted, in every configuration, every seed, every attack, and in production. *Evidence: REPORT Table 4 (last column), Table 5; `/metrics` `haanji_ledger_unconfirmed_refused_total`.*

**49. What would a competitor have to do to copy this?** Build the per-tenant phonetic index and prove it does no harm, make tool execution speculative without changing answers, and give customers a receipt they can verify without trusting the company. Each is small; together they are the product. *Evidence: this document.*

**50. Demo it in two minutes.** `/talk`: say "rut kanal kal subah", watch the repair paint over, the slot arrive before you finish, the stamp drop; open the receipt link; press *tamper* on `/verify`. *Evidence: docs/demo-script.md.*
