# Indic STT comparison

Generated 2026-10-29T08:48:09+00:00 over `research/collect/data/synthetic`. haanji.collect.real_pairs_experiment: WER, entity error rate with the bridge off and on, correction precision and harmful corrections, over the same (heard, truth) pairs.

| engine | pairs | confidence | WER (%) | EER off (%) | EER on (%) | reduction (%) | precision (%) | beneficial | neutral | harmful |
|---|---|---|---|---|---|---|---|---|---|---|
| whisper — faster-whisper small, English decoding, no hints | 300 | vendor | 88.7 | 33.8 | 29.2 | 13.5 | 60.9 | 14 | 9 | 0 |
| whisper_biased — faster-whisper small, pack vocabulary as the prompt | 300 | vendor | 68.5 | 15.1 | 14.2 | 6.1 | 42.9 | 3 | 4 | 0 |
| sarvam — Sarvam Saarika, hi-IN (Devanagari, romanised) | — | — | — | — | — | — | — | — | — | — |
| bhashini — Bhashini / ULCA ASR, hi (Devanagari, romanised) | — | — | — | — | — | — | — | — | — | — |
| deepgram — Deepgram nova-2, hi-Latn | — | — | — | — | — | — | — | — | — | — |
| google — Google Speech-to-Text v1, hi-IN (Devanagari, romanised) | — | — | — | — | — | — | — | — | — | — |

Not run:

* `sarvam` — not run: key needed (SARVAM_API_KEY)
* `bhashini` — not run: key needed (BHASHINI_USER_ID, BHASHINI_API_KEY)
* `deepgram` — not run: key needed (HAANJI_DEEPGRAM_KEY)
* `google` — not run: key needed (GOOGLE_APPLICATION_CREDENTIALS)
