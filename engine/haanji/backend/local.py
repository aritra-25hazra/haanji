"""A complete, self-contained booking backend on SQLite.

Everything the agent can do to a business is implemented here: read the
service catalogue, compute free slots against real working hours and existing
bookings, hold a slot, book it, cancel it, look a customer up, capture a lead
and search the knowledge base. It enforces its own invariants — no double
booking, no booking outside working hours, no booking in the past — because a
voice agent that trusts the model to respect them will eventually double-book
somebody.
"""
from __future__ import annotations
import datetime as dt
import sqlite3
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..clock import CLOCK

SCHEMA = """
CREATE TABLE IF NOT EXISTS services (
  tenant_id TEXT NOT NULL, name TEXT NOT NULL, duration_min INTEGER NOT NULL,
  price_inr INTEGER, staff TEXT, prep_note TEXT,
  PRIMARY KEY (tenant_id, name));
CREATE TABLE IF NOT EXISTS staff (
  tenant_id TEXT NOT NULL, name TEXT NOT NULL, role TEXT,
  PRIMARY KEY (tenant_id, name));
CREATE TABLE IF NOT EXISTS hours (
  tenant_id TEXT NOT NULL, weekday INTEGER NOT NULL,
  open_min INTEGER NOT NULL, close_min INTEGER NOT NULL,
  break_start INTEGER, break_end INTEGER,
  PRIMARY KEY (tenant_id, weekday));
CREATE TABLE IF NOT EXISTS bookings (
  booking_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, service TEXT NOT NULL,
  staff TEXT, date TEXT NOT NULL, time TEXT NOT NULL, duration_min INTEGER NOT NULL,
  customer_name TEXT, phone TEXT, status TEXT NOT NULL DEFAULT 'CONFIRMED',
  receipt_code TEXT, created_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS ux_slot
  ON bookings (tenant_id, staff, date, time) WHERE status = 'CONFIRMED';
CREATE TABLE IF NOT EXISTS customers (
  tenant_id TEXT NOT NULL, phone TEXT NOT NULL, name TEXT,
  last_service TEXT, last_visit TEXT, visits INTEGER DEFAULT 0,
  PRIMARY KEY (tenant_id, phone));
CREATE TABLE IF NOT EXISTS knowledge (
  tenant_id TEXT NOT NULL, qid TEXT NOT NULL, question TEXT NOT NULL,
  answer TEXT NOT NULL, tags TEXT, PRIMARY KEY (tenant_id, qid));
CREATE TABLE IF NOT EXISTS leads (
  lead_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT, phone TEXT,
  intent TEXT, note TEXT, created_at TEXT NOT NULL);
"""

# Nominal latencies of the systems this backend stands in for. The demo and
# the benchmark sleep for these (divided by the time scale) so that measured
# speculation savings correspond to something a real deployment would see.
NOMINAL_MS = {
    "availability": 180.0,     # calendar read across staff
    "knowledge": 120.0,        # vector search over the tenant's documents
    "customer": 90.0,          # CRM lookup
    "book": 260.0,             # write plus confirmation SMS enqueue
    "cancel": 210.0,
    "lead": 110.0,
}


class BackendError(RuntimeError):
    pass


@dataclass
class Slot:
    date: str
    time: str
    staff: str

    def spoken(self) -> str:
        from ..speak import spoken_time
        return spoken_time(self.time)


@dataclass
class Booking:
    booking_id: str
    tenant_id: str
    service: str
    staff: str
    date: str
    time: str
    duration_min: int
    customer_name: str | None = None
    phone: str | None = None
    status: str = "CONFIRMED"
    receipt_code: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"booking_id": self.booking_id, "service": self.service, "staff": self.staff,
                "date": self.date, "time": self.time, "customer_name": self.customer_name,
                "phone": self.phone, "status": self.status, "receipt_code": self.receipt_code}


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


class LocalBackend:
    """Business data plus the rules that protect it."""

    def __init__(self, conn: sqlite3.Connection, *, today: dt.date | None = None):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.today = today or dt.date.today()
        self.calls: dict[str, int] = {}

    # ------------------------------------------------------------------ setup
    def load_pack(self, tenant_id: str, pack) -> None:
        """Populate the tenant from a vertical pack."""
        c = self.conn
        for s in pack.services:
            c.execute("INSERT OR REPLACE INTO services VALUES (?,?,?,?,?,?)",
                      (tenant_id, s.name, s.duration_min, s.price_inr,
                       ",".join(s.staff), s.prep_note))
        for person in pack.staff:
            c.execute("INSERT OR REPLACE INTO staff VALUES (?,?,?)",
                      (tenant_id, person, pack.staff_role))
        for weekday, spec in pack.hours.items():
            c.execute("INSERT OR REPLACE INTO hours VALUES (?,?,?,?,?,?)",
                      (tenant_id, weekday, _mins(spec[0]), _mins(spec[1]),
                       _mins(spec[2]) if len(spec) > 2 else None,
                       _mins(spec[3]) if len(spec) > 3 else None))
        for i, (q, a, tags) in enumerate(pack.knowledge):
            c.execute("INSERT OR REPLACE INTO knowledge VALUES (?,?,?,?,?)",
                      (tenant_id, f"q{i:03d}", q, a, ",".join(tags)))
        c.commit()

    def seed_customer(self, tenant_id: str, phone: str, name: str,
                      last_service: str | None = None, visits: int = 1) -> None:
        self.conn.execute("INSERT OR REPLACE INTO customers VALUES (?,?,?,?,?,?)",
                          (tenant_id, phone, name, last_service,
                           (self.today - dt.timedelta(days=90)).isoformat(), visits))
        self.conn.commit()

    def prefill(self, tenant_id: str, date: str, times: list[str], staff: str,
                service: str = "checkup") -> None:
        """Make the calendar realistic: some slots are already taken."""
        for t in times:
            self.book(tenant_id=tenant_id, service=service, staff=staff, date=date,
                      time=t, customer_name="walk-in", phone=None, duration_min=30)

    # ------------------------------------------------------------- catalogue
    def services(self, tenant_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM services WHERE tenant_id=?", (tenant_id,))
        return [dict(r) for r in rows]

    def service_names(self, tenant_id: str) -> list[str]:
        return [s["name"] for s in self.services(tenant_id)]

    def staff_names(self, tenant_id: str) -> list[str]:
        rows = self.conn.execute("SELECT name FROM staff WHERE tenant_id=?", (tenant_id,))
        return [r["name"] for r in rows]

    def service(self, tenant_id: str, name: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM services WHERE tenant_id=? AND name=?",
                                (tenant_id, name)).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------ date logic
    def resolve_date(self, token: str) -> str:
        """Turn 'tomorrow' / 'monday' / an ISO date into an ISO date."""
        if not token:
            return (self.today + dt.timedelta(days=1)).isoformat()
        t = token.lower()
        if t == "today":
            return self.today.isoformat()
        if t == "tomorrow":
            return (self.today + dt.timedelta(days=1)).isoformat()
        if t == "day_after_tomorrow":
            return (self.today + dt.timedelta(days=2)).isoformat()
        names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        if t in names:
            delta = (names.index(t) - self.today.weekday()) % 7 or 7
            return (self.today + dt.timedelta(days=delta)).isoformat()
        try:
            return dt.date.fromisoformat(token).isoformat()
        except ValueError:
            return (self.today + dt.timedelta(days=1)).isoformat()

    # ---------------------------------------------------------- availability
    async def availability(self, tenant_id: str, service: str | None, date_token: str,
                           *, limit: int = 3, staff: str | None = None) -> dict[str, Any]:
        await CLOCK.sleep_ms(NOMINAL_MS["availability"])
        self.calls["availability"] = self.calls.get("availability", 0) + 1
        iso = self.resolve_date(date_token)
        day = dt.date.fromisoformat(iso)
        svc = self.service(tenant_id, service) if service and service != "__default__" else None
        duration = svc["duration_min"] if svc else 30
        wanted_staff = [staff] if staff else (
            [s for s in (svc["staff"] or "").split(",") if s] if svc else self.staff_names(tenant_id))
        wanted_staff = wanted_staff or self.staff_names(tenant_id)

        hrow = self.conn.execute("SELECT * FROM hours WHERE tenant_id=? AND weekday=?",
                                 (tenant_id, day.weekday())).fetchone()
        if hrow is None:
            return {"date": iso, "closed": True, "slots": [],
                    "service": svc["name"] if svc else service}

        taken = {(r["staff"], r["time"]) for r in self.conn.execute(
            "SELECT staff, time FROM bookings WHERE tenant_id=? AND date=? AND status='CONFIRMED'",
            (tenant_id, iso))}
        now_min = (dt.datetime.now().hour * 60 + dt.datetime.now().minute) if day == self.today else -1

        slots: list[Slot] = []
        step = max(15, duration)
        for start in range(hrow["open_min"], hrow["close_min"] - duration + 1, step):
            if hrow["break_start"] is not None and hrow["break_start"] <= start < hrow["break_end"]:
                continue
            if start <= now_min + 30:
                continue                       # never offer a slot in the past
            for person in wanted_staff:
                if (person, _hhmm(start)) in taken:
                    continue
                slots.append(Slot(iso, _hhmm(start), person))
                break
            if len(slots) >= limit:
                break
        return {"date": iso, "closed": False, "service": svc["name"] if svc else service,
                "duration_min": duration,
                "slots": [{"date": s.date, "time": s.time, "staff": s.staff,
                           "spoken": s.spoken()} for s in slots]}

    # ------------------------------------------------------------- knowledge
    async def search_knowledge(self, tenant_id: str, query: str, *, limit: int = 2) -> dict[str, Any]:
        await CLOCK.sleep_ms(NOMINAL_MS["knowledge"])
        self.calls["knowledge"] = self.calls.get("knowledge", 0) + 1
        q = set(query.lower().split())
        rows = self.conn.execute("SELECT * FROM knowledge WHERE tenant_id=?", (tenant_id,))
        scored = []
        for r in rows:
            hay = f"{r['question']} {r['tags']}".lower()
            score = sum(1 for w in q if len(w) > 2 and w in hay)
            if score:
                scored.append((score, dict(r)))
        scored.sort(key=lambda p: -p[0])
        return {"query": query, "hits": [h for _, h in scored[:limit]]}

    # -------------------------------------------------------------- customer
    async def lookup_customer(self, tenant_id: str, phone: str) -> dict[str, Any]:
        await CLOCK.sleep_ms(NOMINAL_MS["customer"])
        self.calls["customer"] = self.calls.get("customer", 0) + 1
        row = self.conn.execute("SELECT * FROM customers WHERE tenant_id=? AND phone=?",
                                (tenant_id, phone)).fetchone()
        return {"found": bool(row), "customer": dict(row) if row else None}

    # ---------------------------------------------------------------- writes
    def book(self, *, tenant_id: str, service: str, date: str, time: str,
             staff: str | None = None, customer_name: str | None = None,
             phone: str | None = None, duration_min: int | None = None,
             receipt_code: str | None = None) -> Booking:
        """Synchronous so it can be wrapped in one transaction with the ledger."""
        iso = self.resolve_date(date)
        svc = self.service(tenant_id, service)
        duration = duration_min or (svc["duration_min"] if svc else 30)
        if staff is None:
            options = [s for s in ((svc["staff"] or "").split(",") if svc else []) if s]
            staff = (options or self.staff_names(tenant_id) or ["staff"])[0]
        day = dt.date.fromisoformat(iso)
        hrow = self.conn.execute("SELECT * FROM hours WHERE tenant_id=? AND weekday=?",
                                 (tenant_id, day.weekday())).fetchone()
        if hrow is None:
            raise BackendError("business is closed on that day")
        if not (hrow["open_min"] <= _mins(time) <= hrow["close_min"] - duration):
            raise BackendError("that time is outside working hours")
        booking = Booking(str(uuid.uuid4()), tenant_id, svc["name"] if svc else service,
                          staff, iso, time, duration, customer_name, phone,
                          "CONFIRMED", receipt_code)
        try:
            self.conn.execute(
                "INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (booking.booking_id, tenant_id, booking.service, staff, iso, time, duration,
                 customer_name, phone, "CONFIRMED", receipt_code,
                 dt.datetime.now(dt.timezone.utc).isoformat()))
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            raise BackendError("that slot was taken a moment ago") from exc
        if phone:
            self.conn.execute(
                "INSERT INTO customers (tenant_id, phone, name, last_service, last_visit, visits)"
                " VALUES (?,?,?,?,?,1) ON CONFLICT(tenant_id, phone) DO UPDATE SET"
                " name=COALESCE(excluded.name, customers.name), last_service=excluded.last_service,"
                " last_visit=excluded.last_visit, visits=customers.visits+1",
                (tenant_id, phone, customer_name, booking.service, iso))
            self.conn.commit()
        return booking

    def cancel(self, tenant_id: str, booking_id: str) -> bool:
        cur = self.conn.execute(
            "UPDATE bookings SET status='CANCELLED' WHERE tenant_id=? AND booking_id=?"
            " AND status='CONFIRMED'", (tenant_id, booking_id))
        self.conn.commit()
        return cur.rowcount > 0

    def find_booking(self, tenant_id: str, phone: str) -> Booking | None:
        row = self.conn.execute(
            "SELECT * FROM bookings WHERE tenant_id=? AND phone=? AND status='CONFIRMED'"
            " ORDER BY date, time LIMIT 1", (tenant_id, phone)).fetchone()
        if not row:
            return None
        return Booking(row["booking_id"], row["tenant_id"], row["service"], row["staff"],
                       row["date"], row["time"], row["duration_min"], row["customer_name"],
                       row["phone"], row["status"], row["receipt_code"])

    def capture_lead(self, *, tenant_id: str, name: str | None, phone: str | None,
                     intent: str, note: str = "") -> str:
        lead_id = str(uuid.uuid4())
        self.conn.execute("INSERT INTO leads VALUES (?,?,?,?,?,?,?)",
                          (lead_id, tenant_id, name, phone, intent, note,
                           dt.datetime.now(dt.timezone.utc).isoformat()))
        self.conn.commit()
        return lead_id

    def bookings(self, tenant_id: str) -> list[Booking]:
        rows = self.conn.execute("SELECT * FROM bookings WHERE tenant_id=? ORDER BY date, time",
                                 (tenant_id,))
        return [Booking(r["booking_id"], r["tenant_id"], r["service"], r["staff"], r["date"],
                        r["time"], r["duration_min"], r["customer_name"], r["phone"],
                        r["status"], r["receipt_code"]) for r in rows]
