"""Append-only, signed ledger. Backed by SQLite here; the production
implementation in ``core-api`` is the same construction over PostgreSQL."""
from __future__ import annotations
import datetime as dt
import sqlite3
import uuid
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

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
    """One ledger instance serves every tenant in the database it is given.

    ``key_secret`` (HAANJI_LEDGER_KEY_SECRET in a deployment) encrypts the
    tenants' private signing keys at rest, so a copy of the database file
    alone cannot re-sign the chain. Without it the keys are stored in the
    clear, which is what the demo does and the schema comment admits."""

    def __init__(self, conn: sqlite3.Connection, key_secret: str | bytes | None = None):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(receipts)")}
        if "short_code" not in cols:
            # by_code() used to recompute every receipt's code on each lookup
            # (O(N) on a public endpoint). The code is now a column with an index.
            self.conn.execute("ALTER TABLE receipts ADD COLUMN short_code TEXT")
            for r in self.conn.execute("SELECT receipt_id, chain_hash FROM receipts").fetchall():
                code = bytes.fromhex(r["chain_hash"]).hex().upper()[:8]
                self.conn.execute("UPDATE receipts SET short_code=? WHERE receipt_id=?", (code, r["receipt_id"]))
        self.conn.execute("CREATE INDEX IF NOT EXISTS receipts_code_ix ON receipts (tenant_id, short_code)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS receipts_day_ix ON receipts (tenant_id, occurred_at)")
        self.conn.commit()
        self._fernet = None
        if key_secret:
            import base64
            import hashlib

            from cryptography.fernet import Fernet
            raw = key_secret.encode() if isinstance(key_secret, str) else key_secret
            self._fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw).digest()))

    def _wrap(self, private_hex: str) -> str:
        return "enc:" + self._fernet.encrypt(private_hex.encode()).decode() if self._fernet else private_hex

    def _unwrap(self, stored: str) -> str:
        if stored.startswith("enc:"):
            if self._fernet is None:
                raise LedgerError("the signing key is encrypted and HAANJI_LEDGER_KEY_SECRET is not set")
            return self._fernet.decrypt(stored[4:].encode()).decode()
        return stored

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
             self._wrap(priv.private_bytes(serialization.Encoding.Raw,
                                           serialization.PrivateFormat.Raw,
                                           serialization.NoEncryption()).hex()),
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
        return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(self._unwrap(row["private_key"])))

    # ----------------------------------------------------------------- append
    def append(self, *, tenant_id: str, conversation_id: str, action: str,
               action_args: dict[str, Any], confirmation: ConfirmationProof | None,
               transcript_excerpt: str, agent_config_version: int = 1,
               require_confirmation: bool = True) -> Receipt:
        """Seal one action. Refuses a write action that has no confirmation proof."""
        if require_confirmation and confirmation is None:
            from ..telemetry import TELEMETRY
            TELEMETRY.inc("ledger_unconfirmed_refused_total", pack=tenant_id)
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
        row["short_code"] = r.short_code().replace("-", "")
        self.conn.execute(
            "INSERT INTO receipts (receipt_id,tenant_id,seq,conversation_id,action,action_args,"
            "confirmation,transcript_excerpt,agent_config_version,occurred_at,prev_hash,"
            "payload_hash,chain_hash,signature,key_id,short_code) VALUES (:receipt_id,:tenant_id,:seq,"
            ":conversation_id,:action,:action_args,:confirmation,:transcript_excerpt,"
            ":agent_config_version,:occurred_at,:prev_hash,:payload_hash,:chain_hash,"
            ":signature,:key_id,:short_code)", row)
        self.conn.commit()
        return r

    # ------------------------------------------------------------------- read
    def receipts(self, tenant_id: str) -> list[Receipt]:
        rows = self.conn.execute(
            "SELECT * FROM receipts WHERE tenant_id=? ORDER BY seq", (tenant_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d.pop("short_code", None)
            out.append(Receipt.from_row(d))
        return out

    def by_code(self, tenant_id: str, code: str) -> Receipt | None:
        key = code.replace("-", "").upper()
        row = self.conn.execute("SELECT * FROM receipts WHERE tenant_id=? AND short_code=? LIMIT 1",
                                (tenant_id, key)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d.pop("short_code", None)
        return Receipt.from_row(d)

    def write_action_count(self, tenant_id: str) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) c FROM receipts WHERE tenant_id=?", (tenant_id,)).fetchone()["c"]

    # ----------------------------------------------------------------- anchors
    def anchors(self, tenant_id: str) -> list[dict]:
        """Every day that has been sealed, oldest first."""
        rows = self.conn.execute(
            "SELECT tenant_id, day, first_seq, last_seq, merkle_root, signature FROM daily_anchors "
            "WHERE tenant_id=? ORDER BY day", (tenant_id,)).fetchall()
        return [dict(r) for r in rows]

    def days_with_receipts(self, tenant_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT substr(occurred_at, 1, 10) d FROM receipts WHERE tenant_id=? ORDER BY d",
            (tenant_id,)).fetchall()
        return [r["d"] for r in rows]

    def anchor_day(self, tenant_id: str, day: str | None = None) -> str:
        """Publish a signed Merkle root over one day of receipts."""
        import hashlib
        day = day or dt.date.today().isoformat()
        rows = [Receipt.from_row({k: v for k, v in dict(r).items() if k != "short_code"}) for r in self.conn.execute(
            "SELECT * FROM receipts WHERE tenant_id=? AND occurred_at >= ? AND occurred_at < ? ORDER BY seq",
            (tenant_id, day, day + "T99")).fetchall()]
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
