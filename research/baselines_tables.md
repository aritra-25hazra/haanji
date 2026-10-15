**Table 8 — Keyers on synthetic noise (transcript level, 2,097 sentences per rate)**

| keyer | EER on @15% | EER on @30% | EER on @45% | precision @30% | harmful @30% | McNemar vs ours @30% |
|---|---|---|---|---|---|---|
| edit distance only | 0.56% | 1.68% | 2.94% | 93.9% | 0 | b=32, c=7, p < 0.001 |
| exact spelling | 17.30% | 32.01% | 50.35% | 100.0% | 0 | b=807, c=0, p < 0.001 |
| Soundex | 2.48% | 3.98% | 7.09% | 98.5% | 0 | b=97, c=7, p < 0.001 |
| Metaphone | 3.77% | 8.04% | 14.29% | 98.5% | 0 | b=203, c=0, p < 0.001 |
| NYSIIS | 1.64% | 3.46% | 7.09% | 99.2% | 0 | b=82, c=7, p < 0.001 |
| Double Metaphone | 2.80% | 6.99% | 10.97% | 98.5% | 0 | b=175, c=0, p < 0.001 |
| Bhasha (ours) | 0.14% | 0.80% | 2.10% | 99.1% | 0 | — |

Entity error with no correction at 30%: 32.1% (identical for every keyer). Bridge off vs ours: b=809, c=0, p < 0.001.

**Table 9 — Keyers on the real-recogniser pilot (300 utterances, faster-whisper small)**

| keyer | EER off | EER on | reduction | precision | beneficial | neutral | harmful |
|---|---|---|---|---|---|---|---|
| edit distance only | 33.8% | 32.4% | 4.1% | 42.1% | 32 | 38 | 6 |
| exact spelling | 33.8% | 33.3% | 1.4% | 100.0% | 1 | 0 | 0 |
| Soundex | 33.8% | 30.6% | 9.5% | 68.4% | 13 | 6 | 0 |
| Metaphone | 33.8% | 31.5% | 6.8% | 64.7% | 11 | 6 | 0 |
| NYSIIS | 33.8% | 32.4% | 4.1% | 81.8% | 9 | 2 | 0 |
| Double Metaphone | 33.8% | 31.1% | 8.1% | 66.7% | 12 | 6 | 0 |
| Bhasha (ours) | 33.8% | 30.1% | 10.8% | 60.0% | 12 | 8 | 0 |

**Table 10 — Per-rule ablation of the Bhasha key (30% noise; higher delta = the rule matters more)**

| # | rule | EER on without it | Δ vs full (points) | precision | harmful |
|---|---|---|---|---|---|
| 8 | k/kh/q/c merge | 2.97% | +2.17 | 99.0% | 0 |
| 4 | v/w merge | 2.52% | +1.72 | 98.5% | 0 |
| 15 | h/y dropped | 1.19% | +0.39 | 99.0% | 0 |
| 0 | long a shortens (aa→a) | 0.80% | +0.00 | 99.1% | 0 |
| 1 | ee/ie/ii/iy→i | 0.80% | +0.00 | 99.1% | 0 |
| 2 | oo/uu→u | 0.80% | +0.00 | 99.1% | 0 |
| 3 | ph→f | 0.80% | +0.00 | 99.1% | 0 |
| 5 | s/sh/z merge | 0.80% | +0.00 | 99.1% | 0 |
| 7 | t/d/th/dh collapse | 0.80% | +0.00 | 99.1% | 0 |
| 9 | surviving c→k | 0.80% | +0.00 | 99.1% | 0 |
| 10 | g/gh/j-cluster merge | 0.80% | +0.00 | 99.1% | 0 |
| 11 | b/bh/p merge | 0.80% | +0.00 | 99.1% | 0 |
| 12 | j | 0.80% | +0.00 | 99.1% | 0 |
| 13 | n/m merge | 0.80% | +0.00 | 99.1% | 0 |
| 14 | l/r merge | 0.80% | +0.00 | 99.1% | 0 |
| 6 | ch/chh merge | 0.52% | -0.28 | 99.1% | 0 |
