"""Deposits: a payment link with every booking, when the owner wants one.

No-shows are the small clinic's quiet tax, and a ₹200–500 deposit is the
usual cure. The owner sets ``deposit_inr`` in the console; the engine then
issues a payment link for each new booking and sends it with the receipt.
Razorpay Payment Links are the provider (UPI, cards, net banking, one API);
without keys the engine mints a mock link on itself (``/pay/{id}``) that a
demo can "pay" with one click, through the identical code path.

A paid deposit is sealed in the Pramaan ledger as ``payment_received`` with
the provider's ids, so the receipt chain shows the money as well as the
promise."""
from __future__ import annotations
import datetime as dt
import hashlib
import hmac
import logging
import os
import sqlite3
import uuid
from typing import Any

log = logging.getLogger("haanji.payments")

SCHEMA = """
CREATE TABLE IF NOT EXISTS payments (
  payment_id   TEXT PRIMARY KEY,
  tenant_id    TEXT NOT NULL,
  booking_id   TEXT NOT NULL,
  phone        TEXT,
  amount_inr   INTEGER NOT NULL,
  status       TEXT NOT NULL,            -- CREATED | PAID | FAILED | EXPIRED
  provider     TEXT NOT NULL,            -- razorpay | mock
  provider_id  TEXT,                     -- the provider's link id
  link         TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  paid_at      TEXT,
  receipt_code TEXT
);
CREATE INDEX IF NOT EXISTS payments_tenant_ix ON payments (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS payments_booking_ix ON payments (booking_id);
"""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def configured() -> bool:
    return bool(os.environ.get("HAANJI_RAZORPAY_KEY_ID") and os.environ.get("HAANJI_RAZORPAY_KEY_SECRET"))


def verify_razorpay_signature(secret: str, raw: bytes, header: str | None) -> bool:
    """Razorpay signs webhook bodies: X-Razorpay-Signature = HMAC-SHA256(secret, body)."""
    if not header:
        return False
    want = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, header.strip())


class PaymentStore:
    def __init__(self, path: str, public_url: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.public_url = public_url.rstrip("/")

    # ------------------------------------------------------------- create
    async def create_link(self, tenant_id: str, booking: Any, amount_inr: int, *, business: str,
                          client=None) -> dict[str, Any]:
        """A payment link for one booking. Razorpay when configured, a mock
        link on this server otherwise. Never raises: a failed provider call
        is logged and the booking stands without a link."""
        pid = "pay_" + uuid.uuid4().hex[:12]
        provider, provider_id, link = "mock", None, f"{self.public_url}/pay/{pid}"
        if configured():
            try:
                provider, provider_id, link = await self._razorpay_link(pid, booking, amount_inr, business, client)
            except Exception as exc:                        # noqa: BLE001 - vendor boundary
                log.warning("razorpay link failed: %s", exc)
                return {}
        row = {"payment_id": pid, "tenant_id": tenant_id, "booking_id": booking.booking_id,
               "phone": booking.phone, "amount_inr": int(amount_inr), "status": "CREATED",
               "provider": provider, "provider_id": provider_id, "link": link,
               "created_at": _now(), "paid_at": None, "receipt_code": None}
        with self.conn:
            self.conn.execute("INSERT INTO payments VALUES (:payment_id,:tenant_id,:booking_id,:phone,:amount_inr,"
                              ":status,:provider,:provider_id,:link,:created_at,:paid_at,:receipt_code)", row)
        return row

    async def _razorpay_link(self, pid: str, booking: Any, amount_inr: int, business: str, client=None):
        import httpx
        body = {"amount": int(amount_inr) * 100, "currency": "INR", "accept_partial": False,
                "reference_id": pid, "description": f"{business}: {booking.service} deposit",
                "customer": {"contact": f"+91{booking.phone}" if booking.phone else None,
                             "name": booking.customer_name or "Customer"},
                "notify": {"sms": False, "email": False},
                "notes": {"booking_id": booking.booking_id, "tenant": booking.tenant_id},
                "callback_url": f"{self.public_url}/pay/{pid}/done", "callback_method": "get"}
        auth = (os.environ["HAANJI_RAZORPAY_KEY_ID"], os.environ["HAANJI_RAZORPAY_KEY_SECRET"])
        own = client is None
        client = client or httpx.AsyncClient(timeout=15)
        try:
            r = await client.post("https://api.razorpay.com/v1/payment_links", json=body, auth=auth)
            r.raise_for_status()
            data = r.json()
            return "razorpay", data["id"], data["short_url"]
        finally:
            if own:
                await client.aclose()

    # --------------------------------------------------------------- read
    def get(self, payment_id: str) -> dict[str, Any] | None:
        r = self.conn.execute("SELECT * FROM payments WHERE payment_id=?", (payment_id,)).fetchone()
        return dict(r) if r else None

    def for_booking(self, booking_id: str) -> dict[str, Any] | None:
        r = self.conn.execute("SELECT * FROM payments WHERE booking_id=? ORDER BY created_at DESC LIMIT 1",
                              (booking_id,)).fetchone()
        return dict(r) if r else None

    def list(self, tenant_id: str, limit: int = 200) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM payments WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?", (tenant_id, limit))]

    # ------------------------------------------------------------- settle
    def mark(self, payment_id: str, status: str, *, receipt_code: str | None = None) -> dict[str, Any] | None:
        row = self.get(payment_id)
        if row is None:
            return None
        if row["status"] == "PAID":
            return row                                       # idempotent: webhooks are retried
        with self.conn:
            self.conn.execute("UPDATE payments SET status=?, paid_at=?, receipt_code=COALESCE(?, receipt_code)"
                              " WHERE payment_id=?",
                              (status, _now() if status == "PAID" else None, receipt_code, payment_id))
        return self.get(payment_id)

    @staticmethod
    def from_webhook(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        """(our payment id, provider payment id, status) from a Razorpay
        payment_link.* event; (None, None, None) for anything else."""
        event = payload.get("event", "")
        if not event.startswith("payment_link."):
            return None, None, None
        entity = ((payload.get("payload") or {}).get("payment_link") or {}).get("entity") or {}
        pay = ((payload.get("payload") or {}).get("payment") or {}).get("entity") or {}
        status = {"payment_link.paid": "PAID", "payment_link.expired": "EXPIRED",
                  "payment_link.cancelled": "FAILED"}.get(event)
        return entity.get("reference_id"), pay.get("id") or entity.get("id"), status

    def summary(self, tenant_id: str) -> dict[str, int]:
        rows = self.conn.execute("SELECT status, COUNT(*) c, COALESCE(SUM(amount_inr),0) s FROM payments"
                                 " WHERE tenant_id=? GROUP BY status", (tenant_id,)).fetchall()
        out = {"created": 0, "paid": 0, "paid_inr": 0}
        for r in rows:
            if r["status"] == "PAID":
                out["paid"] = r["c"]
                out["paid_inr"] = r["s"]
            elif r["status"] == "CREATED":
                out["created"] = r["c"]
        return out
