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
import logging
import os
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass, field

from . import db, totp

log = logging.getLogger("haanji.auth")

OTP_TTL_S = 300
OTP_MAX_ATTEMPTS = 5
OTP_ISSUE_LIMIT = 3            # codes per phone per OTP_ISSUE_WINDOW_S
OTP_ISSUE_WINDOW_S = 15 * 60
OTP_LOCK_FAILURES = 10         # wrong guesses across codes before the number is locked
OTP_LOCK_S = 15 * 60
TOKEN_TTL_S = 30 * 24 * 3600
IDLE_TTL_S = 14 * 24 * 3600
LOGIN_MAX_FAILURES = 10        # wrong passwords per email in LOGIN_WINDOW_S before a lock
LOGIN_WINDOW_S = 15 * 60
LOGIN_LOCK_S = 15 * 60
MIN_PASSWORD = 10             # for a new or reset password; existing ones still sign in
_SCRYPT = (2 ** 14, 8, 1)      # n, r, p    # a device unused this long is signed out
TOUCH_EVERY_S = 300            # last_seen is written at most this often
REFRESH_AFTER_S = 7 * 24 * 3600
ROLES = ("owner", "staff")


class OtpThrottled(RuntimeError):
    """Too many codes asked for, or too many wrong guesses: wait."""

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
CREATE TABLE IF NOT EXISTS otp_history (
  phone    TEXT PRIMARY KEY,
  issued   TEXT NOT NULL DEFAULT '',   -- comma-separated issue times inside the window
  failures INTEGER NOT NULL DEFAULT 0, -- wrong guesses since the last success
  locked_until REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS revoked (
  phone      TEXT PRIMARY KEY,
  revoked_at REAL NOT NULL             -- tokens issued before this instant are dead
);
CREATE TABLE IF NOT EXISTS sessions (  -- one row per signed-in device
  sid        TEXT PRIMARY KEY,
  phone      TEXT NOT NULL,
  created    REAL NOT NULL,
  last_seen  REAL NOT NULL,
  agent      TEXT NOT NULL DEFAULT '',
  revoked    REAL
);
CREATE INDEX IF NOT EXISTS sessions_phone_ix ON sessions (phone);
CREATE TABLE IF NOT EXISTS credentials ( -- email + password sign-in, beside the WhatsApp code
  email    TEXT PRIMARY KEY,
  phone    TEXT NOT NULL,              -- the user it signs in as
  pw_hash  TEXT NOT NULL,              -- scrypt$n$r$p$salt$hash; the password itself is never kept
  created  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_history (
  email        TEXT PRIMARY KEY,
  failures     INTEGER NOT NULL DEFAULT 0,
  window_start REAL NOT NULL DEFAULT 0,
  locked_until REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS twofactor ( -- an authenticator app as a second step at sign-in
  phone     TEXT PRIMARY KEY,
  secret    TEXT NOT NULL,             -- AES-GCM under a key derived from the token secret
  enabled   INTEGER NOT NULL DEFAULT 0,
  last_step INTEGER NOT NULL DEFAULT -1, -- the last code's time step: a code is never accepted twice
  backup    TEXT NOT NULL DEFAULT '',  -- comma-separated sha256 of unused recovery codes
  created   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_meta ( -- the token-signing secret when HAANJI_AUTH_SECRET is not set
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (     -- who changed what, for the owner
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  at     REAL NOT NULL,
  phone  TEXT NOT NULL,
  role   TEXT NOT NULL,
  method TEXT NOT NULL,
  path   TEXT NOT NULL,
  pack   TEXT,
  status INTEGER NOT NULL
);
"""


@dataclass
class Principal:
    phone: str
    role: str
    packs: list[str] = field(default_factory=lambda: ["*"])
    name: str = ""

    def allows(self, pack: str | None) -> bool:
        """A request whose pack cannot be determined is allowed only to
        users who may see every pack. "No pack" used to mean "any pack",
        which let a staff member scoped to one shop read another's calls."""
        if "*" in self.packs:
            return True
        return pack is not None and pack in self.packs

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
        self.conn = db.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.secret_source = "env" if secret else "database"
        self.secret = (secret or self._stored_secret(path)).encode()

    def _stored_secret(self, db_path: str) -> str:
        """Without HAANJI_AUTH_SECRET the signing secret is kept in the auth
        database itself. It used to be a file beside the database, which on a
        host with a throwaway disk (Render) and the records in Postgres was
        lost at every deploy, signing every user out. A file left by an older
        version is adopted once. HAANJI_AUTH_SECRET in the environment is
        still the better place: whoever reads the database cannot then also
        mint tokens."""
        row = self.conn.execute("SELECT value FROM auth_meta WHERE key='token_secret'").fetchone()
        if row:
            return row["value"] if hasattr(row, "keys") else row[0]
        legacy = db_path + ".secret"
        value = open(legacy, encoding="utf-8").read().strip() if os.path.exists(legacy) else secrets.token_hex(32)
        with self.conn:
            self.conn.execute("INSERT INTO auth_meta (key, value) VALUES ('token_secret', ?)", (value,))
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

    def remove_user(self, phone: str, now: float | None = None) -> bool:
        phone = normalise_phone(phone)
        with self.conn:
            self.conn.execute("DELETE FROM credentials WHERE phone=?", (phone,))
            # Removing and adding a user back is how the owner resets a staff
            # member's two-step sign-in when their phone and recovery codes are lost.
            self.conn.execute("DELETE FROM twofactor WHERE phone=?", (phone,))
            cur = self.conn.execute("DELETE FROM users WHERE phone=?", (phone,))
            if cur.rowcount:
                self.revoke(phone, now)
        return cur.rowcount > 0

    def revoke(self, phone: str, now: float | None = None) -> None:
        """Every token this number holds stops working (sign-out everywhere,
        a demotion, a lost phone)."""
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO revoked VALUES (?,?)",
                              (normalise_phone(phone), now or time.time()))

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]

    # --------------------------------------------------------------- password
    @staticmethod
    def _hash(password: str, salt: bytes | None = None) -> str:
        n, r, p = _SCRYPT
        salt = salt or secrets.token_bytes(16)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
        return "$".join(["scrypt", str(n), str(r), str(p), base64.b64encode(salt).decode(), base64.b64encode(digest).decode()])

    @staticmethod
    def _matches(password: str, stored: str) -> bool:
        try:
            _, n, r, p, salt, digest = stored.split("$")
            got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=32)
            return hmac.compare_digest(got, base64.b64decode(digest))
        except (ValueError, TypeError):
            return False

    @staticmethod
    def password_problem(email: str, password: str) -> str | None:
        """Why a new password is refused, or None."""
        email = email.strip().lower()
        if "@" not in email or len(email) > 200:
            return "a valid email address"
        if len(password) < MIN_PASSWORD:
            return f"a password of at least {MIN_PASSWORD} characters"
        if password.strip().lower() in (email, email.split("@")[0]):
            return "a password that is not the email address"
        return None

    def set_password(self, phone: str, email: str, password: str) -> None:
        """Email + password for an existing user. Only a salted scrypt hash is kept."""
        email = email.strip().lower()
        problem = self.password_problem(email, password)
        if problem:
            raise ValueError(problem)
        phone = normalise_phone(phone)
        if self.user(phone) is None:
            raise ValueError("no such user")
        with self.conn:
            self.conn.execute("DELETE FROM credentials WHERE phone=? AND email<>?", (phone, email))
            self.conn.execute("INSERT OR REPLACE INTO credentials (email, phone, pw_hash, created) VALUES (?,?,?,?)",
                              (email, phone, self._hash(password),
                               dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))

    def has_password(self, email: str, password: str) -> bool:
        """Whether this email's stored password is this one (no lockout bookkeeping)."""
        r = self.conn.execute("SELECT pw_hash FROM credentials WHERE email=?", (email.strip().lower(),)).fetchone()
        return bool(r) and self._matches(password, r["pw_hash"])

    def seed_password(self, phone: str, email: str, password: str) -> bool:
        """The operator's password from the environment (HAANJI_OWNER_PASSWORD),
        applied only when it is new to this database: on the first boot, or
        after the operator changed it. A password set since then (a reset by
        email) is kept: the server restarts often, and re-applying the
        environment's password at every boot undid every reset. A salted
        scrypt hash of the last applied value is kept to tell. True when the
        password was set."""
        email = email.strip().lower()
        key = "env_password:" + email
        row = self.conn.execute("SELECT value FROM auth_meta WHERE key=?", (key,)).fetchone()
        seen = row is not None and self._matches(password, row["value"])
        if seen and self.phone_for_email(email) is not None:
            return False
        applied = False
        if row is not None or not self.has_password(email, password):
            self.set_password(phone, email, password)
            applied = True
        with self.conn:
            self.conn.execute("INSERT INTO auth_meta (key, value) VALUES (?, ?)"
                              " ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, self._hash(password)))
        return applied

    def phone_for_email(self, email: str) -> str | None:
        """The user an email belongs to (set with an email login), if any."""
        r = self.conn.execute("SELECT phone FROM credentials WHERE email=?", (email.strip().lower(),)).fetchone()
        return r["phone"] if r else None

    def email_of(self, phone: str) -> str | None:
        r = self.conn.execute("SELECT email FROM credentials WHERE phone=?", (normalise_phone(phone),)).fetchone()
        return r["email"] if r else None

    def check_password(self, email: str, password: str, now: float | None = None) -> Principal | None:
        """The user, if the email and password match and the email is not
        locked. Ten wrong passwords in fifteen minutes lock it for fifteen.
        An unknown email costs the same hash, so timing does not reveal it."""
        email = email.strip().lower()
        now = now or time.time()
        h = self.conn.execute("SELECT * FROM login_history WHERE email=?", (email,)).fetchone()
        if h and float(h["locked_until"]) > now:
            raise OtpThrottled("too many wrong passwords; try again in 15 minutes")
        r = self.conn.execute("SELECT * FROM credentials WHERE email=?", (email,)).fetchone()
        ok = self._matches(password, r["pw_hash"] if r else self._hash("not-a-password"))
        if ok and r is not None:
            with self.conn:
                self.conn.execute("DELETE FROM login_history WHERE email=?", (email,))
            return self.user(r["phone"])
        start = float(h["window_start"]) if h and now - float(h["window_start"]) < LOGIN_WINDOW_S else now
        failures = (int(h["failures"]) if h and start == float(h["window_start"]) else 0) + 1
        locked = now + LOGIN_LOCK_S if failures >= LOGIN_MAX_FAILURES else 0
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO login_history (email, failures, window_start, locked_until) VALUES (?,?,?,?)",
                              (email, failures, start, locked))
        return None

    def unlock_login(self, email: str) -> None:
        """Clear the wrong-password lock: the owner of the email proved it
        with a reset code."""
        with self.conn:
            self.conn.execute("DELETE FROM login_history WHERE email=?", (email.strip().lower(),))

    # -------------------------------------------------------------------- otp
    def _history(self, phone: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM otp_history WHERE phone=?", (phone,)).fetchone()

    def otp_locked_until(self, phone: str, now: float | None = None) -> float:
        """0 when the number may ask for / try a code now, else the lock's end."""
        h = self._history(normalise_phone(phone))
        now = now or time.time()
        return float(h["locked_until"]) if h and h["locked_until"] > now else 0.0

    def issue_otp(self, phone: str, now: float | None = None) -> str:
        """A fresh code for a WhatsApp number (see issue_code)."""
        return self.issue_code(normalise_phone(phone), now)

    def check_otp(self, phone: str, code: str, now: float | None = None) -> bool:
        return self.check_code(normalise_phone(phone), code, now)

    def issue_code(self, key: str, now: float | None = None) -> str:
        """A fresh one-time code for a key: a phone number, or a purpose and an
        email ("login:a@b.in", "reset:a@b.in"). At most OTP_ISSUE_LIMIT codes
        per window per key, and none while the key is locked for wrong
        guesses: re-issuing used to reset the attempt counter, which made the
        five-try limit meaningless. Only a hash of the code is kept."""
        phone = key
        now = now or time.time()
        h = self._history(phone)
        if h and h["locked_until"] > now:
            raise OtpThrottled("too many wrong codes; try again later")
        issued = [float(x) for x in (h["issued"] if h else "").split(",") if x]
        issued = [t for t in issued if now - t < OTP_ISSUE_WINDOW_S]
        if len(issued) >= OTP_ISSUE_LIMIT:
            raise OtpThrottled("too many codes requested; wait a few minutes")
        issued.append(now)
        code = f"{secrets.randbelow(10 ** 6):06d}"
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO otps VALUES (?,?,?,0)",
                              (phone, hashlib.sha256(code.encode()).hexdigest(), now + OTP_TTL_S))
            self.conn.execute("INSERT INTO otp_history (phone, issued, failures, locked_until) VALUES (?,?,?,?)"
                              " ON CONFLICT(phone) DO UPDATE SET issued=excluded.issued",
                              (phone, ",".join(f"{t:.3f}" for t in issued), h["failures"] if h else 0,
                               h["locked_until"] if h else 0))
        return code

    def check_code(self, key: str, code: str, now: float | None = None) -> bool:
        phone = key
        now = now or time.time()
        h = self._history(phone)
        if h and h["locked_until"] > now:
            return False
        r = self.conn.execute("SELECT * FROM otps WHERE phone=?", (phone,)).fetchone()
        usable = r is not None and r["expires"] >= now and r["attempts"] < OTP_MAX_ATTEMPTS
        ok = usable and hmac.compare_digest(r["code"], hashlib.sha256(str(code).strip().encode()).hexdigest())
        with self.conn:
            if ok:
                self.conn.execute("DELETE FROM otps WHERE phone=?", (phone,))
                self.conn.execute("UPDATE otp_history SET failures=0 WHERE phone=?", (phone,))
            else:
                # Every wrong guess counts against the number, including guesses
                # at an exhausted or expired code: that is what makes the lock real.
                if r is not None:
                    self.conn.execute("UPDATE otps SET attempts=attempts+1 WHERE phone=?", (phone,))
                failures = (h["failures"] if h else 0) + 1
                locked = now + OTP_LOCK_S if failures >= OTP_LOCK_FAILURES else (h["locked_until"] if h else 0)
                self.conn.execute("INSERT INTO otp_history (phone, issued, failures, locked_until) VALUES (?,?,?,?)"
                                  " ON CONFLICT(phone) DO UPDATE SET failures=excluded.failures,"
                                  " locked_until=excluded.locked_until",
                                  (phone, h["issued"] if h else "", failures, locked))
        return ok

    # ----------------------------------------------------------------- tokens
    def token_for(self, p: Principal, now: float | None = None, *, agent: str = "", sid: str | None = None) -> str:
        """A signed token for one device. A new sign-in opens a session row
        (the owner's list of devices); a refresh keeps the same one."""
        now = now or time.time()
        if sid is None:
            sid = secrets.token_hex(8)
            with self.conn:
                self.conn.execute("INSERT INTO sessions (sid, phone, created, last_seen, agent) VALUES (?,?,?,?,?)",
                                  (sid, p.phone, now, now, agent[:160]))
        body = json.dumps({"phone": p.phone, "role": p.role, "packs": p.packs, "name": p.name, "sid": sid,
                           # iat to the millisecond: a whole second let a token minted just
                           # after a revoke (a reset, then signing in at once) count as revoked.
                           "iat": round(now, 3), "exp": int(now + TOKEN_TTL_S)}, separators=(",", ":"))
        payload = base64.urlsafe_b64encode(body.encode()).rstrip(b"=")
        sig = hmac.new(self.secret, payload, hashlib.sha256).digest()
        return payload.decode() + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()

    def verify_token(self, token: str | None, now: float | None = None) -> Principal | None:
        claims = self.claims(token, now)
        if claims is None:
            return None
        current = self.user(claims["phone"]) if claims.get("phone") else None
        if current is not None:
            return current
        return Principal(claims["phone"], claims["role"], list(claims.get("packs", ["*"])), claims.get("name", ""))

    def claims(self, token: str | None, now: float | None = None) -> dict | None:
        """The token's body when it is genuine, unexpired, not revoked, and
        its device session is open and was used in the last IDLE_TTL_S."""
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
        rev = self.conn.execute("SELECT revoked_at FROM revoked WHERE phone=?", (body.get("phone"),)).fetchone()
        if rev and float(body.get("iat", 0)) <= float(rev["revoked_at"]):
            return None                            # signed out everywhere, or removed
        sid = body.get("sid")
        if sid:                                    # tokens from before sessions carry none
            t = now or time.time()
            row = self.conn.execute("SELECT * FROM sessions WHERE sid=? AND phone=?", (sid, body.get("phone"))).fetchone()
            if row is None or row["revoked"] is not None or t - float(row["last_seen"]) > IDLE_TTL_S:
                return None
            if t - float(row["last_seen"]) > TOUCH_EVERY_S:
                with self.conn:
                    self.conn.execute("UPDATE sessions SET last_seen=? WHERE sid=?", (t, sid))
        # verify_token gives a user still on the books their *current* role
        # and packs, so a demotion takes effect without waiting for expiry.
        return body

    def refresh(self, token: str | None, now: float | None = None) -> str | None:
        """A fresh 30 days for a device that is still in use: same session,
        new expiry. Only for a token older than REFRESH_AFTER_S."""
        claims = self.claims(token, now)
        now = now or time.time()
        if claims is None or not claims.get("sid"):
            return None
        if now - float(claims.get("iat", now)) < REFRESH_AFTER_S:
            return token
        p = self.verify_token(token, now)
        return self.token_for(p, now, sid=claims["sid"]) if p else None

    # --------------------------------------------------------------- devices
    def sessions_of(self, phone: str, now: float | None = None) -> list[dict]:
        t = now or time.time()
        rows = self.conn.execute("SELECT * FROM sessions WHERE phone=? AND revoked IS NULL ORDER BY last_seen DESC",
                                 (normalise_phone(phone),))
        return [{"sid": r["sid"], "created": r["created"], "last_seen": r["last_seen"], "agent": r["agent"]}
                for r in rows if t - float(r["last_seen"]) <= IDLE_TTL_S]

    def end_session(self, phone: str, sid: str, now: float | None = None) -> bool:
        with self.conn:
            cur = self.conn.execute("UPDATE sessions SET revoked=? WHERE sid=? AND phone=? AND revoked IS NULL",
                                    (now or time.time(), sid, normalise_phone(phone)))
        return cur.rowcount > 0

    # ----------------------------------------------------------------- audit
    def record(self, who: "Principal", method: str, path: str, pack: str | None, status: int,
               now: float | None = None) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO audit (at, phone, role, method, path, pack, status) VALUES (?,?,?,?,?,?,?)",
                              (now or time.time(), who.phone, who.role, method, path[:200], pack, status))

    def audit(self, limit: int = 200) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ two-step
    TWOFA_LOCK_FAILURES = 10
    TICKET_TTL_S = 300

    def _aead(self):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"haanji-2fa", info=b"totp-secret").derive(self.secret)
        return AESGCM(key)

    def _seal(self, plain: str) -> str:
        nonce = secrets.token_bytes(12)
        return base64.b64encode(nonce + self._aead().encrypt(nonce, plain.encode(), b"totp")).decode()

    def _open(self, sealed: str) -> str | None:
        """The app's secret, or None when it cannot be read: the auth secret
        it was sealed with has changed. Recovery codes (hashes, not sealed)
        still work then; the app has to be set up again."""
        from cryptography.exceptions import InvalidTag
        try:
            raw = base64.b64decode(sealed)
            return self._aead().decrypt(raw[:12], raw[12:], b"totp").decode()
        except (InvalidTag, ValueError):
            log.warning("a two-step secret cannot be read: HAANJI_AUTH_SECRET changed since it was set up")
            return None

    def twofa_enabled(self, phone: str) -> bool:
        r = self.conn.execute("SELECT enabled FROM twofactor WHERE phone=?", (normalise_phone(phone),)).fetchone()
        return bool(r and r["enabled"])

    def twofa_begin(self, phone: str) -> str:
        """A new secret, stored but not yet on: it turns on only once a code
        from the app has been checked (twofa_enable)."""
        phone = normalise_phone(phone)
        if self.twofa_enabled(phone):
            raise ValueError("two-step sign-in is already on; turn it off first")
        secret = totp.new_secret()
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO twofactor (phone, secret, enabled, last_step, backup, created)"
                              " VALUES (?,?,0,-1,'',?)", (phone, self._seal(secret), time.time()))
        return secret

    def twofa_enable(self, phone: str, code: str, now: float | None = None) -> list[str]:
        """Turn two-step on with a first code from the app. Returns eight
        one-time recovery codes, shown once; only their hashes are kept."""
        phone = normalise_phone(phone)
        r = self.conn.execute("SELECT * FROM twofactor WHERE phone=?", (phone,)).fetchone()
        if r is None or r["enabled"]:
            raise ValueError("start the setup first")
        secret = self._open(r["secret"])
        step = totp.verify(secret, code, now) if secret else None
        if step is None:
            raise ValueError("that code is not right; check the time on the phone and try the next one")
        backup = [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(8)]
        with self.conn:
            self.conn.execute("UPDATE twofactor SET enabled=1, last_step=?, backup=? WHERE phone=?",
                              (step, ",".join(self._backup_hash(b) for b in backup), phone))
        return backup

    def twofa_check(self, phone: str, code: str, now: float | None = None) -> bool:
        """A code from the app (never the same one twice) or an unused recovery
        code. Ten wrong codes lock two-step for fifteen minutes."""
        phone = normalise_phone(phone)
        now = now or time.time()
        key = "2fa:" + phone
        h = self._history(key)
        if h and h["locked_until"] > now:
            return False
        r = self.conn.execute("SELECT * FROM twofactor WHERE phone=? AND enabled=1", (phone,)).fetchone()
        if r is None:
            return False
        ok = False
        secret = self._open(r["secret"])
        step = totp.verify(secret, code, now, last_step=int(r["last_step"])) if secret else None
        with self.conn:
            if step is not None:
                self.conn.execute("UPDATE twofactor SET last_step=? WHERE phone=?", (step, phone))
                ok = True
            else:
                digest = self._backup_hash(code)
                left = [x for x in r["backup"].split(",") if x]
                if digest in left:
                    left.remove(digest)
                    self.conn.execute("UPDATE twofactor SET backup=? WHERE phone=?", (",".join(left), phone))
                    ok = True
            failures = 0 if ok else (h["failures"] if h else 0) + 1
            locked = now + OTP_LOCK_S if failures >= self.TWOFA_LOCK_FAILURES else 0
            self.conn.execute("INSERT INTO otp_history (phone, issued, failures, locked_until) VALUES (?,?,?,?)"
                              " ON CONFLICT(phone) DO UPDATE SET failures=excluded.failures, locked_until=excluded.locked_until",
                              (key, "", failures, locked))
        return ok

    @staticmethod
    def _backup_hash(code: str) -> str:
        """Recovery codes match however they are typed: "ab12-cd34",
        "AB12 CD34" and "ab12cd34" are the same code."""
        return hashlib.sha256(re.sub(r"[^0-9a-f]", "", (code or "").lower()).encode()).hexdigest()

    def twofa_backup_left(self, phone: str) -> int:
        r = self.conn.execute("SELECT backup FROM twofactor WHERE phone=? AND enabled=1", (normalise_phone(phone),)).fetchone()
        return len([x for x in r["backup"].split(",") if x]) if r else 0

    def twofa_disable(self, phone: str, code: str, now: float | None = None) -> bool:
        if not self.twofa_check(phone, code, now):
            return False
        with self.conn:
            self.conn.execute("DELETE FROM twofactor WHERE phone=?", (normalise_phone(phone),))
        return True

    def twofa_reset(self, phone: str) -> bool:
        """Turn two-step off without a code (the operator's way back in)."""
        with self.conn:
            cur = self.conn.execute("DELETE FROM twofactor WHERE phone=?", (normalise_phone(phone),))
        return cur.rowcount > 0

    def twofa_ticket(self, phone: str, now: float | None = None) -> str:
        """Proof that the first step (password, code or Google) passed, good
        for five minutes and once: the second step trades it for a token."""
        body = json.dumps({"phone": normalise_phone(phone), "exp": (now or time.time()) + self.TICKET_TTL_S,
                           "n": secrets.token_hex(8)}, separators=(",", ":"))
        payload = base64.urlsafe_b64encode(body.encode()).rstrip(b"=").decode()
        sig = hmac.new(self.secret, b"2fa|" + payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{sig}"

    def twofa_redeem(self, ticket: str, now: float | None = None, *, consume: bool = True) -> str | None:
        """The phone a ticket was issued for, once, while it is fresh. With
        consume=False it is only checked, so a mistyped code can be retried
        (wrong codes are limited by twofa_check's lock)."""
        payload, _, sig = (ticket or "").partition(".")
        want = hmac.new(self.secret, b"2fa|" + payload.encode(), hashlib.sha256).hexdigest()
        if not payload or not hmac.compare_digest(want, sig):
            return None
        try:
            body = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        except (ValueError, TypeError):
            return None
        now = now or time.time()
        if float(body.get("exp", 0)) < now:
            return None
        used = "ticket:" + str(body.get("n"))
        with self.conn:
            if self.conn.execute("SELECT 1 FROM otps WHERE phone=?", (used,)).fetchone():
                return None
            if consume:
                self.conn.execute("INSERT INTO otps (phone, code, expires, attempts) VALUES (?,?,?,0)",
                                  (used, "used", float(body["exp"])))
        return body.get("phone")

