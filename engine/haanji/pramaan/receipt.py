"""Receipt structure and the exact bytes that get hashed and signed."""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any

GENESIS = b"\x00" * 32


def canonical_json(obj: Any) -> str:
    """Byte-stable JSON so that an honest re-serialisation is not read as tampering.

    (RFC 8785 in spirit: sorted keys, no insignificant whitespace, UTF-8.)
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass
class ConfirmationProof:
    """What the agent asked, what the caller answered, and when — the evidence."""
    prompt_text: str
    prompt_start_ms: int
    reply_text: str
    reply_start_ms: int
    asr_confidence: float
    audio_offset_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Receipt:
    tenant_id: str
    seq: int
    conversation_id: str
    action: str
    action_args: dict[str, Any]
    confirmation: dict[str, Any]
    transcript_excerpt: str
    agent_config_version: int
    occurred_at: str
    prev_hash: bytes
    payload_hash: bytes = b""
    chain_hash: bytes = b""
    signature: bytes = b""
    key_id: str = ""
    receipt_id: str = ""

    # ------------------------------------------------------------------ hashing
    def compute_payload_hash(self) -> bytes:
        h = hashlib.sha256()
        h.update(canonical_json(self.action_args).encode())
        h.update(canonical_json(self.confirmation).encode())
        h.update(self.transcript_excerpt.encode())
        h.update(self.occurred_at.encode())
        h.update(str(self.agent_config_version).encode())
        h.update(self.action.encode())
        return h.digest()

    def compute_chain_hash(self) -> bytes:
        return hashlib.sha256(self.prev_hash + self.payload_hash).digest()

    # ------------------------------------------------------------------ display
    def short_code(self) -> str:
        raw = self.chain_hash.hex().upper()
        return f"{raw[:4]}-{raw[4:8]}"

    def to_row(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id, "tenant_id": self.tenant_id, "seq": self.seq,
            "conversation_id": self.conversation_id, "action": self.action,
            "action_args": canonical_json(self.action_args),
            "confirmation": canonical_json(self.confirmation),
            "transcript_excerpt": self.transcript_excerpt,
            "agent_config_version": self.agent_config_version,
            "occurred_at": self.occurred_at,
            "prev_hash": self.prev_hash.hex(), "payload_hash": self.payload_hash.hex(),
            "chain_hash": self.chain_hash.hex(), "signature": self.signature.hex(),
            "key_id": self.key_id,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Receipt":
        r = cls(
            tenant_id=row["tenant_id"], seq=int(row["seq"]),
            conversation_id=row["conversation_id"], action=row["action"],
            action_args=json.loads(row["action_args"]),
            confirmation=json.loads(row["confirmation"]),
            transcript_excerpt=row["transcript_excerpt"],
            agent_config_version=int(row["agent_config_version"]),
            occurred_at=row["occurred_at"],
            prev_hash=bytes.fromhex(row["prev_hash"]),
        )
        r.payload_hash = bytes.fromhex(row["payload_hash"])
        r.chain_hash = bytes.fromhex(row["chain_hash"])
        r.signature = bytes.fromhex(row["signature"])
        r.key_id = row["key_id"]
        r.receipt_id = row.get("receipt_id", "")
        return r
