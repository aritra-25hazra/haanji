"""Who may look at a business's calls.

Opt-in (HAANJI_AUTH=on): the public demo stays open, a deployment for a real
shop does not. The model is deliberately small and on-brand for the owner
of a clinic: no passwords, a one-time code on WhatsApp (the number is the
account), two roles (owner edits, staff reads), and each user sees only the
packs they were given. Tokens are HMAC-signed, stateless, and expire.

Nothing here is a vendor: the OTP goes through the same WhatsApp channel the
agent answers on; without a connected number, HAANJI_AUTH_DEV=1 returns the
code in the response so the flow can be exercised locally and in tests.
"""
from __future__ import annotations
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass, field

OTP_TTL_S = 300
OTP_MAX_ATTEMPTS = 5
TOKEN_TTL_S = 30 * 24 * 3600
ROLES = ("owner", "staff")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  phone   TEXT PRIMARY KEY,
  name    TEXT NOT NULL DEFAULT '',
  role    TEXT NOT NULL,
  packs   TEXT NOT NULL,               -- comma separated, or * for every pack
  created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS otps (
  phone    TEXT PRIMARY KEY,
  code     TEXT NOT NULL,
  expires  REAL NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass
class Principal:
    phone: str
    role: str
    packs: list[str] = field(default_factory=lambda: ["*"])
    name: str = ""

    def allows(self, pack: str | None) -> bool:
        return pack is None or "*" in self.packs or pack in self.packs

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"

    def as_dict(self) -> dict:
        return {"phone": self.phone, "role": self.role, "packs": self.packs, "name": self.name}


def normalise_phone(phone: str) -> str:
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


class AuthStore:
    def __init__(self, path: str, secret: str | None = None):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.secret = (secret or self._secret_from_file(path)).encode()

    @staticmethod
    def _secret_from_file(db_path: str) -> str:
        """A deployment without HAANJI_AUTH_SECRET gets one generated next to
        the database, so restarts keep every token valid."""
        path = db_path + ".secret"
        if os.path.exists(path):
            return open(path, encoding="utf-8").read().strip()
        value = secrets.token_hex(32)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(value)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return value

    # ------------------------------------------------------------------ users
    def upsert_user(self, phone: str, role: str, packs: list[str] | None = None, name: str = "") -> Principal:
        if role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        phone = normalise_phone(phone)
        packs = packs or ["*"]
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?)",
                              (phone, name, role, ",".join(packs),
                               dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
        return Principal(phone, role, packs, name)

    def user(self, phone: str) -> Principal | None:
        r = self.conn.execute("SELECT * FROM users WHERE phone=?", (normalise_phone(phone),)).fetchone()
        return Principal(r["phone"], r["role"], r["packs"].split(","), r["name"]) if r else None

    def users(self) -> list[Principal]:
        return [Principal(r["phone"], r["role"], r["packs"].split(","), r["name"])
                for r in self.conn.execute("SELECT * FROM users ORDER BY created")]

    def remove_user(self, phone: str) -> bool:
        with self.conn:
            cur = self.conn.execute("DELETE FROM users WHERE phone=?", (normalise_phone(phone),))
        return cur.rowcount > 0

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]

    # -------------------------------------------------------------------- otp
    def issue_otp(self, phone: str, now: float | None = None) -> str:
        code = f"{secrets.randbelow(10 ** 6):06d}"
        now = now or time.time()
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO otps VALUES (?,?,?,0)",
                              (normalise_phone(phone), hashlib.sha256(code.encode()).hexdigest(), now + OTP_TTL_S))
        return code

    def check_otp(self, phone: str, code: str, now: float | None = None) -> bool:
        phone = normalise_phone(phone)
        now = now or time.time()
        r = self.conn.execute("SELECT * FROM otps WHERE phone=?", (phone,)).fetchone()
        if r is None or r["expires"] < now or r["attempts"] >= OTP_MAX_ATTEMPTS:
            return False
        ok = hmac.compare_digest(r["code"], hashlib.sha256(str(code).strip().encode()).hexdigest())
        with self.conn:
            if ok:
                self.conn.execute("DELETE FROM otps WHERE phone=?", (phone,))
            else:
                self.conn.execute("UPDATE otps SET attempts=attempts+1 WHERE phone=?", (phone,))
        return ok

    # ----------------------------------------------------------------- tokens
    def token_for(self, p: Principal, now: float | None = None) -> str:
        body = json.dumps({"phone": p.phone, "role": p.role, "packs": p.packs, "name": p.name,
                           "exp": int((now or time.time()) + TOKEN_TTL_S)}, separators=(",", ":"))
        payload = base64.urlsafe_b64encode(body.encode()).rstrip(b"=")
        sig = hmac.new(self.secret, payload, hashlib.sha256).digest()
        return payload.decode() + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()

    def verify_token(self, token: str | None, now: float | None = None) -> Principal | None:
        if not token or "." not in token:
            return None
        payload, sig = token.rsplit(".", 1)
        try:
            want = base64.urlsafe_b64encode(hmac.new(self.secret, payload.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
            if not hmac.compare_digest(want, sig):
                return None
            body = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        except (ValueError, TypeError):
            return None
        if body.get("exp", 0) < (now or time.time()):
            return None
        return Principal(body["phone"], body["role"], list(body.get("packs", ["*"])), body.get("name", ""))
