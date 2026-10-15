Seeds: 5 · reps per seed: 3 · packs: 5 · scenarios: 21 · time scale: 90.0× · values are mean ± 95% CI over seeds

**Table 1 — Transcript-level correction (Bhasha Bridge alone)**

| noise rate | sentences | entities | EER off (%) | EER on (%) | reduction (%) | precision (%) | harmful |
|---|---|---|---|---|---|---|---|
| 15% | 2097 | 2862 | 16.7 ± 1.5 | 0.26 ± 0.14 | 98.5 ± 0.8 | 99.1 ± 0.7 | 0.0 |
| 30% | 2097 | 2862 | 32.4 ± 0.5 | 0.71 ± 0.17 | 97.8 ± 0.6 | 98.9 ± 0.3 | 0.0 |
| 45% | 2097 | 2862 | 48.5 ± 2.9 | 1.87 ± 0.19 | 96.1 ± 0.3 | 99.0 ± 0.1 | 0.0 |

**Table 2 — End-to-end calls under the same noise (Bhasha on vs off)**

| noise rate | calls | EER off (%) | EER on (%) | task success off (%) | task success on (%) | beneficial | neutral | harmful |
|---|---|---|---|---|---|---|---|---|
| 15% | 63 | 16.4 ± 8.3 | 0.0 ± 0.0 | 88.2 ± 5.9 | 96.5 ± 0.9 | 8.0 | 0.8 | 0.0 |
| 30% | 63 | 32.3 ± 8.0 | 0.0 ± 0.0 | 78.4 ± 8.7 | 92.7 ± 7.0 | 15.6 | 2.6 | 0.0 |
| 45% | 63 | 47.7 ± 2.9 | 0.0 ± 0.0 | 62.2 ± 4.5 | 84.4 ± 2.6 | 21.4 | 3.4 | 0.0 |

**Table 3 — Per pack at 30% noise**

| pack | language | calls | task success off (%) | task success on (%) | EER off (%) | EER on (%) |
|---|---|---|---|---|---|---|
| clinic_kolkata | benglish | 9 | 75.6 ± 15.1 | 88.9 ± 16.9 | 36.7 ± 9.3 | 0.0 ± 0.0 |
| coaching_institute | hinglish | 9 | 82.2 ± 15.7 | 91.1 ± 15.1 | 26.7 ± 34.6 | 0.0 ± 0.0 |
| dental_clinic | hinglish | 24 | 70.0 ± 17.3 | 90.0 ± 8.6 | 34.4 ± 17.8 | 0.0 ± 0.0 |
| diagnostic_lab | hinglish | 9 | 91.1 ± 6.2 | 97.8 ± 6.2 | 20.0 ± 22.7 | 0.0 ± 0.0 |
| salon_spa | hinglish | 12 | 85.0 ± 8.7 | 98.3 ± 4.6 | 31.1 ± 15.1 | 0.0 ± 0.0 |

**Table 4 — Ablation on the authored scenarios (clean transcripts)**

| configuration | task success (%) | EER (%) | read-turn p50 (ms) | read-turn p90 (ms) | write-turn p90 (ms) | all-tool p90 (ms) | spec. hit rate (%) | wasted | unconfirmed writes |
|---|---|---|---|---|---|---|---|---|---|
| full | 100.0 ± 0.0 | 0.0 ± 0.0 | 161 ± 22 | 270 ± 29 | 233 ± 33 | 251 ± 31 | 46.2 ± 0.0 | 42.0 | 0 |
| no_speculation | 100.0 ± 0.0 | 0.0 ± 0.0 | 286 ± 7 | 374 ± 13 | 228 ± 7 | 349 ± 10 | 0.0 ± 0.0 | 0.0 | 0 |
| no_bhasha | 66.7 ± 0.0 | 69.2 ± 0.0 | 194 ± 5 | 306 ± 16 | 226 ± 5 | 278 ± 18 | 21.7 ± 0.0 | 54.0 | 0 |
| baseline | 66.7 ± 0.0 | 69.2 ± 0.0 | 206 ± 3 | 332 ± 23 | 221 ± 18 | 306 ± 24 | 0.0 ± 0.0 | 0.0 | 0 |

**Table 5 — Pramaan Ledger under attack (deterministic)**

| attack | attempted | detected |
|---|---|---|
| mutate `action_args.time` | 10 | 10 |
| mutate `action_args.service` | 10 | 10 |
| mutate `action_args.phone` | 10 | 10 |
| mutate `confirmation.reply_text` | 10 | 10 |
| mutate `confirmation.asr_confidence` | 10 | 10 |
| mutate `transcript_excerpt` | 10 | 10 |
| mutate `occurred_at` | 10 | 10 |
| mutate `agent_config_version` | 10 | 10 |
| delete a receipt from the middle | 1 | 1 |
| forge a receipt and re-hash it | 1 | 1 |
| write without a confirmation proof | 1 | 1 |
