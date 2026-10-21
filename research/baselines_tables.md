**Table 8 — Keyers on synthetic noise (transcript level, 2,430 sentences per rate)**

| keyer | EER on @15% | EER on @30% | EER on @45% | precision @30% | harmful @30% | McNemar vs ours @30% |
|---|---|---|---|---|---|---|
| edit distance only | 0.48% | 1.45% | 2.54% | 94.2% | 0 | b=32, c=13, p = 0.007 |
| exact spelling | 17.47% | 32.18% | 50.65% | 100.0% | 0 | b=936, c=0, p < 0.001 |
| Soundex | 2.48% | 4.15% | 7.72% | 98.5% | 0 | b=118, c=13, p < 0.001 |
| Metaphone | 3.88% | 8.08% | 13.99% | 98.6% | 0 | b=234, c=0, p < 0.001 |
| NYSIIS | 1.51% | 3.24% | 6.81% | 99.2% | 0 | b=90, c=13, p < 0.001 |
| Double Metaphone | 2.91% | 6.78% | 10.63% | 98.6% | 0 | b=193, c=0, p < 0.001 |
| Bhasha (ours) | 0.36% | 0.88% | 2.06% | 99.2% | 0 | — |

Entity error with no correction at 30%: 32.2% (identical for every keyer). Bridge off vs ours: b=938, c=0, p < 0.001.

**Table 9 — Keyers on the real-recogniser pilot (300 utterances, faster-whisper small)**

| keyer | EER off | EER on | reduction | precision | beneficial | neutral | harmful |
|---|---|---|---|---|---|---|---|
| edit distance only | 33.8% | 31.1% | 8.1% | 42.0% | 34 | 41 | 6 |
| exact spelling | 33.8% | 33.3% | 1.4% | 50.0% | 1 | 1 | 0 |
| Soundex | 33.8% | 30.1% | 10.8% | 66.7% | 14 | 7 | 0 |
| Metaphone | 33.8% | 31.1% | 8.1% | 63.2% | 12 | 7 | 0 |
| NYSIIS | 33.8% | 32.0% | 5.4% | 76.9% | 10 | 3 | 0 |
| Double Metaphone | 33.8% | 30.1% | 10.8% | 66.7% | 14 | 7 | 0 |
| Bhasha (ours) | 33.8% | 29.2% | 13.5% | 60.9% | 14 | 9 | 0 |

**Table 10 — Per-rule ablation of the Bhasha key (30% noise; higher delta = the rule matters more)**

| # | rule | EER on without it | Δ vs full (points) | precision | harmful |
|---|---|---|---|---|---|
| 8 | k/kh/q/c merge | 3.51% | +2.63 | 99.0% | 0 |
| 4 | v/w merge | 2.48% | +1.60 | 98.6% | 0 |
| 15 | h/y dropped | 1.21% | +0.33 | 99.2% | 0 |
| 0 | long a shortens (aa→a) | 0.88% | +0.00 | 99.2% | 0 |
| 1 | ee/ie/ii/iy→i | 0.88% | +0.00 | 99.2% | 0 |
| 2 | oo/uu→u | 0.88% | +0.00 | 99.2% | 0 |
| 3 | ph→f | 0.88% | +0.00 | 99.2% | 0 |
| 5 | s/sh/z merge | 0.88% | +0.00 | 99.2% | 0 |
| 7 | t/d/th/dh collapse | 0.88% | +0.00 | 99.2% | 0 |
| 9 | surviving c→k | 0.88% | +0.00 | 99.2% | 0 |
| 10 | g/gh/j-cluster merge | 0.88% | +0.00 | 99.2% | 0 |
| 11 | b/bh/p merge | 0.88% | +0.00 | 99.2% | 0 |
| 12 | j | 0.88% | +0.00 | 99.2% | 0 |
| 13 | n/m merge | 0.88% | +0.00 | 99.2% | 0 |
| 14 | l/r merge | 0.88% | +0.00 | 99.2% | 0 |
| 6 | ch/chh merge | 0.45% | -0.43 | 99.2% | 0 |
