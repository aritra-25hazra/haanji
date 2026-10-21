Seeds: 5 · reps per seed: 3 · packs: 6 · scenarios: 24 · time scale: 90.0× · values are mean ± 95% CI over seeds

**Table 1 — Transcript-level correction (Bhasha Bridge alone)**

| noise rate | sentences | entities | EER off (%) | EER on (%) | reduction (%) | precision (%) | harmful |
|---|---|---|---|---|---|---|---|
| 15% | 2430 | 3303 | 16.8 ± 1.7 | 0.37 ± 0.14 | 97.8 ± 0.9 | 99.2 ± 0.6 | 0.0 |
| 30% | 2430 | 3303 | 32.6 ± 0.7 | 0.82 ± 0.13 | 97.5 ± 0.4 | 99.1 ± 0.3 | 0.0 |
| 45% | 2430 | 3303 | 48.7 ± 2.9 | 1.93 ± 0.17 | 96.0 ± 0.4 | 99.1 ± 0.1 | 0.0 |

**Table 2 — End-to-end calls under the same noise (Bhasha on vs off)**

| noise rate | calls | EER off (%) | EER on (%) | task success off (%) | task success on (%) | beneficial | neutral | harmful |
|---|---|---|---|---|---|---|---|---|
| 15% | 72 | 16.9 ± 6.6 | 0.0 ± 0.0 | 87.5 ± 4.4 | 95.8 ± 1.7 | 9.2 | 0.8 | 0.0 |
| 30% | 72 | 33.8 ± 9.2 | 0.0 ± 0.0 | 76.4 ± 9.4 | 90.8 ± 7.1 | 18.2 | 2.8 | 0.0 |
| 45% | 72 | 50.2 ± 3.7 | 0.0 ± 0.0 | 59.7 ± 5.2 | 81.1 ± 3.4 | 25.4 | 3.4 | 0.0 |

**Table 3 — Per pack at 30% noise**

| pack | language | calls | task success off (%) | task success on (%) | EER off (%) | EER on (%) |
|---|---|---|---|---|---|---|
| clinic_kolkata | benglish | 9 | 75.6 ± 15.1 | 88.9 ± 16.9 | 36.7 ± 9.3 | 0.0 ± 0.0 |
| clinic_pune | marathinglish | 9 | 62.2 ± 15.8 | 77.8 ± 13.8 | 43.3 ± 23.6 | 0.0 ± 0.0 |
| coaching_institute | hinglish | 9 | 82.2 ± 15.7 | 91.1 ± 15.1 | 26.7 ± 34.6 | 0.0 ± 0.0 |
| dental_clinic | hinglish | 24 | 70.0 ± 17.3 | 90.0 ± 8.6 | 34.4 ± 17.8 | 0.0 ± 0.0 |
| diagnostic_lab | hinglish | 9 | 91.1 ± 6.2 | 97.8 ± 6.2 | 20.0 ± 22.7 | 0.0 ± 0.0 |
| salon_spa | hinglish | 12 | 85.0 ± 8.7 | 98.3 ± 4.6 | 31.1 ± 15.1 | 0.0 ± 0.0 |

**Table 4 — Ablation on the authored scenarios (clean transcripts)**

| configuration | task success (%) | EER (%) | read-turn p50 (ms) | read-turn p90 (ms) | write-turn p90 (ms) | all-tool p90 (ms) | spec. hit rate (%) | wasted | unconfirmed writes |
|---|---|---|---|---|---|---|---|---|---|
| full | 100.0 ± 0.0 | 0.0 ± 0.0 | 142 ± 15 | 238 ± 26 | 194 ± 55 | 220 ± 20 | 41.9 ± 0.0 | 54.0 | 0 |
| no_speculation | 100.0 ± 0.0 | 0.0 ± 0.0 | 246 ± 8 | 310 ± 11 | 194 ± 22 | 297 ± 5 | 0.0 ± 0.0 | 0.0 | 0 |
| no_bhasha | 66.7 ± 0.0 | 66.7 ± 0.0 | 167 ± 7 | 260 ± 30 | 164 ± 43 | 224 ± 26 | 19.2 ± 0.0 | 63.0 | 0 |
| baseline | 66.7 ± 0.0 | 66.7 ± 0.0 | 180 ± 12 | 275 ± 12 | 163 ± 40 | 249 ± 22 | 0.0 ± 0.0 | 0.0 | 0 |

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
