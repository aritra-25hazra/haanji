"""Personal data inside an immutable ledger: the PII vault.

A receipt must never change, and a customer may ask to be forgotten. Both
hold at once if the receipt stores the customer's name and number
*encrypted under a key that belongs to that customer*, kept outside the
chain. The ciphertext is what the hashes and signatures cover, so the chain
verifies forever; erasure deletes the key (crypto-shredding), after which
the fields are unreadable by anyone, including us. Lookups use a keyed
hash of the number, so the ledger can still be searched without holding it.
"""
from __future__ import annotations
import base64
import datetime as dt
import hashlib
import hmac
import os
import sqlite3
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

SCHEMA = """
CREATE TABLE IF NOT EXISTS customer_keys (
  subject   TEXT PRIMARY KEY,          -- keyed hash of the normalised phone number
  key       TEXT NOT NULL,
  created   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shredded (
  subject   TEXT PRIMARY KEY,
  at        TEXT NOT NULL
);
"""
PII_FIELDS = ("phone", "customer_name", "name")


def normalise_phone(phone: str | None) -> str:
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


class Vault:
    def __init__(self, path: str, secret: bytes | None = None):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.secret = secret or self._secret(path)

    @staticmethod
    def _secret(path: str) -> bytes:
        sp = path + ".secret"
        if os.path.exists(sp):
            return open(sp, "rb").read().strip()
        value = base64.urlsafe_b64encode(os.urandom(32))
        with open(sp, "wb") as fh:
            fh.write(value)
        try:
            os.chmod(sp, 0o600)
        except OSError:
            pass
        return value

    # ------------------------------------------------------------ subjects
    def subject(self, phone: str | None) -> str | None:
        p = normalise_phone(phone)
        if not p:
            return None
        return hmac.new(self.secret, p.encode(), hashlib.sha256).hexdigest()[:32]

    def _key(self, subject: str, create: bool) -> bytes | None:
        r = self.conn.execute("SELECT key FROM customer_keys WHERE subject=?", (subject,)).fetchone()
        if r:
            return r["key"].encode()
        if not create or self.conn.execute("SELECT 1 FROM shredded WHERE subject=?", (subject,)).fetchone():
            return None
        key = Fernet.generate_key()
        with self.conn:
            self.conn.execute("INSERT INTO customer_keys VALUES (?,?,?)",
                              (subject, key.decode(), dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
        return key

    # ------------------------------------------------------------- sealing
    def seal_args(self, args: dict[str, Any]) -> dict[str, Any]:
        """Replace personal fields with ciphertext under the customer's key.
        A customer who asked to be forgotten gets no new key: their fields
        are stored as 'erased'. Arguments without a phone are left alone."""
        phone = args.get("phone")
        subject = self.subject(phone)
        if subject is None:
            return dict(args)
        key = self._key(subject, create=True)
        out = {k: v for k, v in args.items() if k not in PII_FIELDS}
        out["subject"] = subject
        if key is None:
            out["pii"] = "erased"
            return out
        f = Fernet(key)
        for field in PII_FIELDS:
            if args.get(field) not in (None, ""):
                out[f"{field}_enc"] = f.encrypt(str(args[field]).encode()).decode()
        return out

    def open_args(self, args: dict[str, Any]) -> dict[str, Any]:
        """Decrypt what can still be decrypted; erased fields stay absent."""
        out = dict(args)
        subject = args.get("subject")
        key = self._key(subject, create=False) if subject else None
        for field in PII_FIELDS:
            token = args.get(f"{field}_enc")
            if not token:
                continue
            if key is None:
                out[field] = None
                continue
            try:
                out[field] = Fernet(key).decrypt(token.encode()).decode()
            except InvalidToken:
                out[field] = None
        return out

    # ------------------------------------------------------------- erasure
    def forget(self, phone: str) -> bool:
        """Crypto-shred: delete the customer's key. The receipts stay valid;
        their personal fields become unreadable."""
        subject = self.subject(phone)
        if subject is None:
            return False
        with self.conn:
            cur = self.conn.execute("DELETE FROM customer_keys WHERE subject=?", (subject,))
            self.conn.execute("INSERT OR REPLACE INTO shredded VALUES (?,?)",
                              (subject, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
        return cur.rowcount > 0

    def is_shredded(self, phone: str) -> bool:
        subject = self.subject(phone)
        return bool(subject and self.conn.execute("SELECT 1 FROM shredded WHERE subject=?", (subject,)).fetchone())

    def count(self) -> dict[str, int]:
        return {"keys": self.conn.execute("SELECT COUNT(*) c FROM customer_keys").fetchone()["c"],
                "shredded": self.conn.execute("SELECT COUNT(*) c FROM shredded").fetchone()["c"]}
