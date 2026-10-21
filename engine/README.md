# haanji-engine

The voice-agent engine behind [HaanJi](https://github.com/aritra-25hazra/haanji):
a receptionist for Indian small businesses that hears the business's own words
(Hinglish, Benglish, Marathinglish), answers before the caller finishes, and
can prove what was agreed.

Three mechanisms, each measured in the
[report](https://github.com/aritra-25hazra/haanji/blob/main/research/REPORT.md):

* **Bhasha Bridge** — a per-tenant phonetic index built from the catalogue a
  business supplies, used to bias the recogniser and to repair its output under
  a two-condition rule that cannot damage a correct transcript.
* **Speculative Turn Execution** — read-only tools predicted and run from
  partial transcripts while the caller is still speaking; a result is claimed
  only when the real turn asks for byte-identical arguments.
* **Pramaan Ledger** — every write sealed into an Ed25519-signed, hash-chained
  receipt bound to the caller's confirming words, with daily Merkle anchors;
  an unconfirmed write is refused, not logged.

```bash
pip install "haanji-engine[web]"
haanji demo            # one narrated call at real speed, mock providers
haanji selftest        # every packaged scenario reaches its expected outcome
haanji serve           # the demo server on http://localhost:8090
```

The wheel carries the six vertical packs (`HAANJI_PACKS_DIR` points at your
own). Providers are mocked by default; hosted recognition, synthesis,
telephony, WhatsApp and a hosted dialogue model are adapters switched on by
environment variables — see the
[repository README](https://github.com/aritra-25hazra/haanji#readme) and the
[documentation site](https://aritra-25hazra.github.io/haanji/).

Licence: Apache-2.0. Cite with the repository's `CITATION.cff`.
