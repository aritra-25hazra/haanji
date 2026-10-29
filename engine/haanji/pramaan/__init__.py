"""Pramaan Ledger — tamper-evident receipts for everything the agent does.

Each state-changing action produces a receipt that binds the action to the
caller's spoken confirmation, hashes it into a per-tenant chain and signs the
chain head with Ed25519. Editing or deleting any past receipt breaks every
later one, and anyone holding the public key can detect it.
"""
from .ledger import Ledger, LedgerError
from .receipt import GENESIS, ConfirmationProof, Receipt, canonical_json
from .verifier import ChainReport, verify_chain, verify_receipt

__all__ = ["ConfirmationProof", "Receipt", "canonical_json", "GENESIS",
           "Ledger", "LedgerError", "ChainReport", "verify_receipt", "verify_chain"]
