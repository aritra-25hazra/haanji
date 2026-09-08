"""HaanJi voice-agent engine.

Three engineered contributions live here:

* ``haanji.bhasha``      - per-tenant phonetic lexicon biasing and Hinglish
                           post-correction, so one speech model serves every
                           business without per-business fine-tuning.
* ``haanji.speculation`` - Speculative Turn Execution: read-only tools are
                           predicted from partial transcripts and executed while
                           the caller is still speaking.
* ``haanji.pramaan``     - tamper-evident, Ed25519-signed receipts binding every
                           write action to the caller's spoken confirmation.

Everything runs offline with the mock adapters, which is what the demo and the
whole test suite use.
"""
__version__ = "0.3.0"
__all__ = ["__version__"]
