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
CREATE TABLE IF NOT EXISTS waitlist (
  entry_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, phone TEXT NOT NULL, name TEXT,
  service TEXT, date TEXT NOT NULL, period TEXT, status TEXT NOT NULL DEFAULT 'WAITING',
  created_at TEXT NOT NULL, offered_at TEXT, offered_slot TEXT);
CREATE INDEX IF NOT EXISTS waitlist_day_ix ON waitlist (tenant_id, date, status);
"""
# Columns added after 1.0.0; a database made by 1.0.0 gets them on open.
MIGRATIONS = [
    ("bookings", "reminder_sent_at", "TEXT"),
    ("bookings", "paid", "INTEGER NOT NULL DEFAULT 0"),
    ("bookings", "payment_id", "TEXT"),
    ("bookings", "notes", "TEXT"),
]
BOOKING_STATUSES = ("CONFIRMED", "CANCELLED", "NO_SHOW", "COMPLETED")

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
    party: list[dict[str, str]] | None = None     # where a group is seen, when asked for one

    def spoken(self) -> str:
        from ..speak import spoken_time
        return spoken_time(self.time)

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"date": self.date, "time": self.time, "staff": self.staff, "spoken": self.spoken()}
        if self.party:
            d["party"] = self.party
        return d


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
    created_at: str | None = None
    reminder_sent_at: str | None = None
    paid: bool = False
    payment_id: str | None = None
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"booking_id": self.booking_id, "service": self.service, "staff": self.staff,
                "date": self.date, "time": self.time, "duration_min": self.duration_min,
                "customer_name": self.customer_name,
                "phone": self.phone, "status": self.status, "receipt_code": self.receipt_code,
                "created_at": self.created_at, "reminder_sent_at": self.reminder_sent_at,
                "paid": bool(self.paid), "payment_id": self.payment_id, "notes": self.notes}

    @classmethod
    def from_row(cls, row) -> "Booking":
        keys = row.keys() if hasattr(row, "keys") else row
        return cls(row["booking_id"], row["tenant_id"], row["service"], row["staff"], row["date"], row["time"],
                   row["duration_min"], row["customer_name"], row["phone"], row["status"], row["receipt_code"],
                   row["created_at"] if "created_at" in keys else None,
                   row["reminder_sent_at"] if "reminder_sent_at" in keys else None,
                   bool(row["paid"]) if "paid" in keys and row["paid"] is not None else False,
                   row["payment_id"] if "payment_id" in keys else None,
                   row["notes"] if "notes" in keys else None)


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
PERIODS = {"morning": (0, 12 * 60), "afternoon": (12 * 60, 16 * 60), "evening": (16 * 60, 24 * 60)}


class LocalBackend:
    """Business data plus the rules that protect it."""

    def __init__(self, conn: sqlite3.Connection, *, today: dt.date | None = None,
                 now: dt.datetime | None = None):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        for table, column, decl in MIGRATIONS:
            cols = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        self.conn.commit()
        # ``today`` used to be read once at construction, so a server that ran
        # past midnight resolved "kal" to the wrong day. It is a property now;
        # tests pin it (and optionally the clock) for reproducibility.
        self._today: dt.date | None = today
        self._now: dt.datetime | None = now
        self.calls: dict[str, int] = {}

    @property
    def today(self) -> dt.date:
        if self._now is not None:
            return self._now.date()
        return self._today or dt.datetime.now(IST).date()

    @today.setter
    def today(self, value: dt.date | None) -> None:
        self._today = value

    def now_minutes(self, day: dt.date) -> int:
        """Minutes past midnight if ``day`` is today, else -1. With a pinned
        ``today`` but no pinned clock there is no "now" to compare against,
        so nothing is treated as past (keeps the tests deterministic)."""
        if day != self.today:
            return -1
        if self._now is not None:
            return self._now.hour * 60 + self._now.minute
        if self._today is not None:
            return -1
        now = dt.datetime.now(IST)
        return now.hour * 60 + now.minute

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
                           *, limit: int = 3, staff: str | None = None,
                           period: str | None = None, at: str | None = None,
                           party: int = 1) -> dict[str, Any]:
        """Free slots for a service on a day.

        ``period`` keeps only morning / afternoon / evening starts (the caller
        said "shaam ko"); ``at`` asks about one exact time and, when it is
        taken, returns the nearest free alternatives; ``party`` asks for
        room for several people at once: a different staff member each at the
        same time, or back-to-back slots with one staff member."""
        await CLOCK.sleep_ms(NOMINAL_MS["availability"])
        self.calls["availability"] = self.calls.get("availability", 0) + 1
        iso = self.resolve_date(date_token)
        day = dt.date.fromisoformat(iso)
        svc = self.service(tenant_id, service) if service and service != "__default__" else None
        duration = svc["duration_min"] if svc else 30
        wanted_staff = [staff] if staff else (
            [s for s in (svc["staff"] or "").split(",") if s] if svc else self.staff_names(tenant_id))
        wanted_staff = wanted_staff or self.staff_names(tenant_id)
        party = max(1, int(party or 1))

        hrow = self.conn.execute("SELECT * FROM hours WHERE tenant_id=? AND weekday=?",
                                 (tenant_id, day.weekday())).fetchone()
        base = {"date": iso, "service": svc["name"] if svc else service, "duration_min": duration,
                "period": period, "requested": at, "party": party}
        if hrow is None:
            return {**base, "closed": True, "slots": []}
        if day < self.today:
            return {**base, "closed": False, "past": True, "slots": []}

        occupied: dict[str, list[tuple[int, int]]] = {}
        for row in self.conn.execute(
            "SELECT staff, time, duration_min FROM bookings"
            " WHERE tenant_id=? AND date=? AND status='CONFIRMED'",
            (tenant_id, iso),
        ):
            start = _mins(row["time"])
            occupied.setdefault(row["staff"], []).append(
                (start, start + int(row["duration_min"] or 30)))
        now_min = self.now_minutes(day)
        lo, hi = PERIODS.get(period or "", (0, 24 * 60))
        step = max(15, duration)

        def free_at(start: int) -> list[str]:
            if hrow["break_start"] is not None and hrow["break_start"] <= start < hrow["break_end"]:
                return []
            if start < hrow["open_min"] or start > hrow["close_min"] - duration:
                return []
            end = start + duration
            return [p for p in wanted_staff
                    if not any(booked_start < end and start < booked_end
                               for booked_start, booked_end in occupied.get(p, []))]

        def party_plan(start: int) -> list[dict[str, str]] | None:
            """Where ``party`` people can be seen: together, or in a row."""
            if party == 1:
                return None
            people = free_at(start)
            if len(people) >= party:
                return [{"time": _hhmm(start), "staff": p} for p in people[:party]]
            for person in people:
                run = [{"time": _hhmm(start), "staff": person}]
                nxt = start + step
                while len(run) < party and person in free_at(nxt):
                    run.append({"time": _hhmm(nxt), "staff": person})
                    nxt += step
                if len(run) == party:
                    return run
            return None

        def slot_for(start: int) -> Slot | None:
            if start <= now_min + 30:
                return None                    # never offer a slot in the past
            people = free_at(start)
            if not people:
                return None
            plan = party_plan(start)
            if party > 1 and plan is None:
                return None
            s = Slot(iso, _hhmm(start), people[0])
            s.party = plan
            return s

        starts = list(range(hrow["open_min"], hrow["close_min"] - duration + 1, step))
        slots: list[Slot] = []
        if at:
            want = _mins(at)
            exact = slot_for(want) if want in starts or free_at(want) else None
            if exact is not None:
                slots = [exact]
            else:
                # nearest alternatives either side, within the day
                cands = sorted((abs(st - want), st) for st in starts)
                for _, st in cands:
                    s = slot_for(st)
                    if s is not None:
                        slots.append(s)
                    if len(slots) >= 2:
                        break
                return {**base, "closed": False, "slots": [], "at_free": False,
                        "alternatives": [s.as_dict() for s in slots]}
            return {**base, "closed": False, "slots": [s.as_dict() for s in slots], "at_free": True}

        for start in starts:
            if not (lo <= start < hi):
                continue
            s = slot_for(start)
            if s is None:
                continue
            slots.append(s)
            if len(slots) >= limit:
                break
        return {**base, "closed": False, "slots": [s.as_dict() for s in slots]}

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
        if day < self.today or _mins(time) <= self.now_minutes(day):
            raise BackendError("that time has already passed")
        start, end = _mins(time), _mins(time) + duration
        # SQLite stores clock times as text, so compare the occupied intervals
        # as minutes in Python rather than relying on lexical time ordering.
        for row in self.conn.execute(
            "SELECT time, duration_min FROM bookings"
            " WHERE tenant_id=? AND staff=? AND date=? AND status='CONFIRMED'",
            (tenant_id, staff, iso),
        ):
            booked_start = _mins(row["time"])
            booked_end = booked_start + int(row["duration_min"] or 30)
            if booked_start < end and start < booked_end:
                raise BackendError("that slot overlaps another booking")
        booking = Booking(str(uuid.uuid4()), tenant_id, svc["name"] if svc else service,
                          staff, iso, time, duration, customer_name, phone,
                          "CONFIRMED", receipt_code)
        try:
            booking.created_at = dt.datetime.now(dt.timezone.utc).isoformat()
            self.conn.execute(
                "INSERT INTO bookings (booking_id, tenant_id, service, staff, date, time, duration_min,"
                " customer_name, phone, status, receipt_code, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (booking.booking_id, tenant_id, booking.service, staff, iso, time, duration,
                 customer_name, phone, "CONFIRMED", receipt_code, booking.created_at))
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
        return Booking.from_row(row)

    def booking(self, tenant_id: str, booking_id: str) -> Booking | None:
        row = self.conn.execute("SELECT * FROM bookings WHERE tenant_id=? AND booking_id=?",
                                (tenant_id, booking_id)).fetchone()
        return Booking.from_row(row) if row else None

    def bookings_between(self, tenant_id: str, start: str, end: str, status: str | None = "CONFIRMED") -> list[Booking]:
        """Bookings with ``start <= date <= end`` (ISO dates), oldest first.
        ``status`` None or 'ALL' returns every status."""
        if status in (None, "ALL"):
            rows = self.conn.execute("SELECT * FROM bookings WHERE tenant_id=? AND date BETWEEN ? AND ?"
                                     " ORDER BY date, time", (tenant_id, start, end))
        else:
            rows = self.conn.execute("SELECT * FROM bookings WHERE tenant_id=? AND date BETWEEN ? AND ? AND status=?"
                                     " ORDER BY date, time", (tenant_id, start, end, status))
        return [Booking.from_row(r) for r in rows]

    def set_status(self, tenant_id: str, booking_id: str, status: str) -> bool:
        """Attendance from the console: NO_SHOW / COMPLETED, or back to CONFIRMED."""
        if status not in BOOKING_STATUSES:
            raise BackendError(f"status must be one of {', '.join(BOOKING_STATUSES)}")
        cur = self.conn.execute("UPDATE bookings SET status=? WHERE tenant_id=? AND booking_id=? AND status != 'CANCELLED'",
                                (status, tenant_id, booking_id))
        self.conn.commit()
        return cur.rowcount > 0

    def mark_reminded(self, tenant_id: str, booking_id: str, when: str | None = None) -> None:
        self.conn.execute("UPDATE bookings SET reminder_sent_at=? WHERE tenant_id=? AND booking_id=?",
                          (when or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), tenant_id, booking_id))
        self.conn.commit()

    def mark_paid(self, tenant_id: str, booking_id: str, payment_id: str | None, paid: bool = True) -> None:
        self.conn.execute("UPDATE bookings SET paid=?, payment_id=COALESCE(?, payment_id) WHERE tenant_id=? AND booking_id=?",
                          (1 if paid else 0, payment_id, tenant_id, booking_id))
        self.conn.commit()

    def due_reminders(self, tenant_id: str, date: str) -> list[Booking]:
        rows = self.conn.execute("SELECT * FROM bookings WHERE tenant_id=? AND date=? AND status='CONFIRMED'"
                                 " AND reminder_sent_at IS NULL AND phone IS NOT NULL ORDER BY time", (tenant_id, date))
        return [Booking.from_row(r) for r in rows]

    # -------------------------------------------------------------- customers
    def customers(self, tenant_id: str, q: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        """One row per number, with what the bookings table says about them."""
        rows = self.conn.execute(
            "SELECT c.phone, c.name, c.last_service, c.last_visit, c.visits,"
            " (SELECT COUNT(*) FROM bookings b WHERE b.tenant_id=c.tenant_id AND b.phone=c.phone AND b.status='CONFIRMED') AS bookings,"
            " (SELECT COUNT(*) FROM bookings b WHERE b.tenant_id=c.tenant_id AND b.phone=c.phone AND b.status='NO_SHOW') AS no_shows"
            " FROM customers c WHERE c.tenant_id=? ORDER BY c.last_visit DESC LIMIT ?", (tenant_id, limit)).fetchall()
        out = [dict(r) for r in rows]
        if q:
            needle = q.strip().lower()
            out = [r for r in out if needle in (r["name"] or "").lower() or needle in (r["phone"] or "")]
        return out

    # --------------------------------------------------------------- waitlist
    def add_waitlist(self, *, tenant_id: str, phone: str, name: str | None, service: str | None,
                     date: str, period: str | None = None) -> str:
        """Remember that this caller wanted this day and found no slot."""
        iso = self.resolve_date(date)
        dup = self.conn.execute("SELECT entry_id FROM waitlist WHERE tenant_id=? AND phone=? AND date=? AND status='WAITING'",
                                (tenant_id, phone, iso)).fetchone()
        if dup:
            return dup["entry_id"]
        entry_id = str(uuid.uuid4())
        self.conn.execute("INSERT INTO waitlist (entry_id, tenant_id, phone, name, service, date, period, status, created_at)"
                          " VALUES (?,?,?,?,?,?,?,'WAITING',?)",
                          (entry_id, tenant_id, phone, name, service, iso, period,
                           dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
        self.conn.commit()
        return entry_id

    def waitlist(self, tenant_id: str, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self.conn.execute("SELECT * FROM waitlist WHERE tenant_id=? AND status=? ORDER BY date, created_at",
                                     (tenant_id, status))
        else:
            rows = self.conn.execute("SELECT * FROM waitlist WHERE tenant_id=? ORDER BY date, created_at", (tenant_id,))
        return [dict(r) for r in rows]

    def next_waiting(self, tenant_id: str, date: str, service: str | None = None) -> dict[str, Any] | None:
        """Who should hear about a slot that just freed up on ``date``."""
        rows = self.conn.execute("SELECT * FROM waitlist WHERE tenant_id=? AND date=? AND status='WAITING'"
                                 " ORDER BY created_at", (tenant_id, date)).fetchall()
        for r in rows:
            if service is None or not r["service"] or r["service"] == service:
                return dict(r)
        return dict(rows[0]) if rows else None

    def waitlist_mark(self, tenant_id: str, entry_id: str, status: str, offered_slot: str | None = None) -> bool:
        cur = self.conn.execute("UPDATE waitlist SET status=?, offered_at=CASE WHEN ?='OFFERED' THEN ? ELSE offered_at END,"
                                " offered_slot=COALESCE(?, offered_slot) WHERE tenant_id=? AND entry_id=?",
                                (status, status, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                 offered_slot, tenant_id, entry_id))
        self.conn.commit()
        return cur.rowcount > 0

    def waitlist_remove(self, tenant_id: str, entry_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM waitlist WHERE tenant_id=? AND entry_id=?", (tenant_id, entry_id))
        self.conn.commit()
        return cur.rowcount > 0

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
        return [Booking.from_row(r) for r in rows]
