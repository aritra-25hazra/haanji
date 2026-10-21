# HaanJi

*Haan ji* is how a receptionist in India picks up the phone. HaanJi is an
open-source voice receptionist for the clinics, salons, laboratories and
coaching institutes that lose bookings because nobody answers: it hears the
business's own words in Hinglish, Benglish or Marathinglish, answers before
the caller finishes, and can prove what was agreed.

<div class="grid cards" markdown>

-   **Bhasha Bridge**

    A per-tenant phonetic index built from the catalogue a business supplies,
    used to bias the recogniser and to repair its output under a two-condition
    rule that cannot damage a correct transcript. [Report §4](research/REPORT.md#4-bhasha-bridge)

-   **Speculative Turn Execution**

    Read-only tools are predicted from partial transcripts and run while the
    caller is still speaking; a result is claimed only on byte-identical
    arguments. [Report §5](research/REPORT.md#5-speculative-turn-execution)

-   **Pramaan Ledger**

    Every write is sealed into an Ed25519-signed, hash-chained receipt bound
    to the caller's confirming words; an unconfirmed write is refused, not
    logged. [Report §6](research/REPORT.md#6-pramaan-ledger)

</div>

## Try it

```bash
git clone https://github.com/aritra-25hazra/haanji && cd haanji/engine
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,web]"
haanji demo          # one narrated call at real speed
haanji serve         # http://localhost:8090 — talk to it in the browser
```

Or `pip install "haanji-engine[web]"` for the engine alone, with the six
vertical packs bundled.

## Where things are

| You want to | Read |
|---|---|
| Put it on a WhatsApp number | [WhatsApp](whatsapp-setup.md) |
| Put it on a phone number | [A phone number](phone-setup.md) |
| Sign the owner console in | [Console sign-in](console-auth.md) |
| Know what the ledger guarantees | [Pramaan ledger, formally](pramaan-security.md) |
| Know what is stored and for how long | [Privacy and the DPDP Act](privacy-dpdp.md) |
| See every number and how it was measured | [The report](research/REPORT.md) |
| Prepare for a viva | [Viva](viva.md) |

The source, the packs, the harness and the data are at
[github.com/aritra-25hazra/haanji](https://github.com/aritra-25hazra/haanji).
Cite it with the repository's `CITATION.cff`.
