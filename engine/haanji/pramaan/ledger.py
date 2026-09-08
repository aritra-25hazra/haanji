"""Append-only, signed ledger. Backed by SQLite here; the production
implementation in ``core-api`` is the same construction over PostgreSQL."""
from __future__ import annotations
import datetime as dt
import sqlite3
import uuid
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)

from .receipt import GENESIS, ConfirmationProof, Receipt

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenant_keys (
  key_id      TEXT PRIMARY KEY,
  tenant_id   TEXT NOT NULL,
  public_key  TEXT NOT NULL,
  private_key TEXT NOT NULL,          -- sealed store in production; here for the demo
  created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS receipts (
  receipt_id           TEXT PRIMARY KEY,
  tenant_id            TEXT NOT NULL,
  seq                  INTEGER NOT NULL,
  conversation_id      TEXT,
  action               TEXT NOT NULL,
  action_args          TEXT NOT NULL,
  confirmation         TEXT NOT NULL,
  transcript_excerpt   TEXT NOT NULL,
  agent_config_version INTEGER NOT NULL,
  occurred_at          TEXT NOT NULL,
  prev_hash            TEXT NOT NULL,
  payload_hash         TEXT NOT NULL,
  chain_hash           TEXT NOT NULL,
  signature            TEXT NOT NULL,
  key_id               TEXT NOT NULL,
  UNIQUE (tenant_id, seq)
);
CREATE TABLE IF NOT EXISTS daily_anchors (
  tenant_id  TEXT NOT NULL,
  day        TEXT NOT NULL,
  first_seq  INTEGER NOT NULL,
  last_seq   INTEGER NOT NULL,
  merkle_root TEXT NOT NULL,
  signature  TEXT NOT NULL,
  PRIMARY KEY (tenant_id, day)
);
"""


class LedgerError(RuntimeError):
    pass


class Ledger:
    """One ledger instance serves every tenant in the database it is given."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ------------------------------------------------------------------- keys
    def ensure_key(self, tenant_id: str) -> str:
        row = self.conn.execute(
            "SELECT key_id FROM tenant_keys WHERE tenant_id=? ORDER BY created_at DESC LIMIT 1",
            (tenant_id,)).fetchone()
        if row:
            return row["key_id"]
        priv = Ed25519PrivateKey.generate()
        key_id = f"k_{uuid.uuid4().hex[:12]}"
        self.conn.execute(
            "INSERT INTO tenant_keys (key_id, tenant_id, public_key, private_key, created_at)"
            " VALUES (?,?,?,?,?)",
            (key_id, tenant_id,
             priv.public_key().public_bytes(serialization.Encoding.Raw,
                                            serialization.PublicFormat.Raw).hex(),
             priv.private_bytes(serialization.Encoding.Raw,
                                serialization.PrivateFormat.Raw,
                                serialization.NoEncryption()).hex(),
             dt.datetime.now(dt.timezone.utc).isoformat()))
        self.conn.commit()
        return key_id

    def public_key(self, key_id: str) -> Ed25519PublicKey:
        row = self.conn.execute("SELECT public_key FROM tenant_keys WHERE key_id=?",
                                (key_id,)).fetchone()
        if not row:
            raise LedgerError(f"unknown key_id {key_id}")
        return Ed25519PublicKey.from_public_bytes(bytes.fromhex(row["public_key"]))

    def _private_key(self, key_id: str) -> Ed25519PrivateKey:
        row = self.conn.execute("SELECT private_key FROM tenant_keys WHERE key_id=?",
                                (key_id,)).fetchone()
        return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(row["private_key"]))

    # ----------------------------------------------------------------- append
    def append(self, *, tenant_id: str, conversation_id: str, action: str,
               action_args: dict[str, Any], confirmation: ConfirmationProof | None,
               transcript_excerpt: str, agent_config_version: int = 1,
               require_confirmation: bool = True) -> Receipt:
        """Seal one action. Refuses a write action that has no confirmation proof."""
        if require_confirmation and confirmation is None:
            raise LedgerError(
                f"action '{action}' has no confirmation proof; the ledger refuses "
                f"to record an unconfirmed write")
        key_id = self.ensure_key(tenant_id)
        cur = self.conn.execute(
            "SELECT seq, chain_hash FROM receipts WHERE tenant_id=? ORDER BY seq DESC LIMIT 1",
            (tenant_id,)).fetchone()
        seq = (cur["seq"] + 1) if cur else 1
        prev = bytes.fromhex(cur["chain_hash"]) if cur else GENESIS

        r = Receipt(
            tenant_id=tenant_id, seq=seq, conversation_id=conversation_id, action=action,
            action_args=action_args,
            confirmation=confirmation.to_dict() if confirmation else {},
            transcript_excerpt=transcript_excerpt,
            agent_config_version=agent_config_version,
            occurred_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds"),
            prev_hash=prev,
        )
        r.payload_hash = r.compute_payload_hash()
        r.chain_hash = r.compute_chain_hash()
        r.signature = self._private_key(key_id).sign(r.chain_hash)
        r.key_id = key_id
        r.receipt_id = str(uuid.uuid4())

        row = r.to_row()
        self.conn.execute(
            "INSERT INTO receipts (receipt_id,tenant_id,seq,conversation_id,action,action_args,"
            "confirmation,transcript_excerpt,agent_config_version,occurred_at,prev_hash,"
            "payload_hash,chain_hash,signature,key_id) VALUES (:receipt_id,:tenant_id,:seq,"
            ":conversation_id,:action,:action_args,:confirmation,:transcript_excerpt,"
            ":agent_config_version,:occurred_at,:prev_hash,:payload_hash,:chain_hash,"
            ":signature,:key_id)", row)
        self.conn.commit()
        return r

    # ------------------------------------------------------------------- read
    def receipts(self, tenant_id: str) -> list[Receipt]:
        rows = self.conn.execute(
            "SELECT * FROM receipts WHERE tenant_id=? ORDER BY seq", (tenant_id,)).fetchall()
        return [Receipt.from_row(dict(r)) for r in rows]

    def by_code(self, tenant_id: str, code: str) -> Receipt | None:
        for r in self.receipts(tenant_id):
            if r.short_code() == code.upper():
                return r
        return None

    def write_action_count(self, tenant_id: str) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) c FROM receipts WHERE tenant_id=?", (tenant_id,)).fetchone()["c"]

    # ----------------------------------------------------------------- anchors
    def anchor_day(self, tenant_id: str, day: str | None = None) -> str:
        """Publish a signed Merkle root over one day of receipts."""
        import hashlib
        day = day or dt.date.today().isoformat()
        rows = [r for r in self.receipts(tenant_id) if r.occurred_at.startswith(day)]
        if not rows:
            raise LedgerError("no receipts for that day")
        layer = [r.chain_hash for r in rows]
        while len(layer) > 1:
            nxt = []
            for i in range(0, len(layer), 2):
                a = layer[i]
                b = layer[i + 1] if i + 1 < len(layer) else a
                nxt.append(hashlib.sha256(a + b).digest())
            layer = nxt
        root = layer[0]
        key_id = self.ensure_key(tenant_id)
        sig = self._private_key(key_id).sign(root + day.encode())
        self.conn.execute(
            "INSERT OR REPLACE INTO daily_anchors (tenant_id,day,first_seq,last_seq,"
            "merkle_root,signature) VALUES (?,?,?,?,?,?)",
            (tenant_id, day, rows[0].seq, rows[-1].seq, root.hex(), sig.hex()))
        self.conn.commit()
        return root.hex()
