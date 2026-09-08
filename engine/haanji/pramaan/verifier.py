"""Independent verification.

Deliberately small and dependency-light: anybody can read this file, check what
it does, and run it against a database dump without trusting the platform.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidSignature

from .receipt import GENESIS, Receipt


@dataclass
class ChainReport:
    ok: bool
    checked: int
    first_broken_seq: int | None = None
    reason: str | None = None
    missing_seqs: list[int] = field(default_factory=list)

    def __str__(self) -> str:
        if self.ok:
            return f"VALID — {self.checked} receipts, chain intact"
        return (f"BROKEN at seq {self.first_broken_seq}: {self.reason}"
                + (f"; missing sequence numbers {self.missing_seqs}" if self.missing_seqs else ""))


def verify_receipt(receipt: Receipt, public_key) -> tuple[bool, str | None]:
    """Recompute the hashes and check the signature of a single receipt."""
    if receipt.compute_payload_hash() != receipt.payload_hash:
        return False, "payload hash does not match the stored content"
    if receipt.compute_chain_hash() != receipt.chain_hash:
        return False, "chain hash does not match prev_hash + payload_hash"
    try:
        public_key.verify(receipt.signature, receipt.chain_hash)
    except InvalidSignature:
        return False, "signature does not verify against the tenant public key"
    return True, None


def verify_chain(receipts: list[Receipt], public_key_for) -> ChainReport:
    """Walk a tenant's chain from the genesis block, checking links and gaps."""
    if not receipts:
        return ChainReport(True, 0)
    ordered = sorted(receipts, key=lambda r: r.seq)
    missing = [s for s in range(ordered[0].seq, ordered[-1].seq + 1)
               if s not in {r.seq for r in ordered}]
    prev = GENESIS if ordered[0].seq == 1 else ordered[0].prev_hash
    for i, r in enumerate(ordered):
        if r.prev_hash != prev:
            return ChainReport(False, i, r.seq,
                               "prev_hash does not match the previous receipt's chain hash",
                               missing)
        ok, reason = verify_receipt(r, public_key_for(r.key_id))
        if not ok:
            return ChainReport(False, i, r.seq, reason, missing)
        prev = r.chain_hash
    if missing:
        return ChainReport(False, len(ordered), missing[0],
                           "sequence gap — a receipt was deleted", missing)
    return ChainReport(True, len(ordered))
