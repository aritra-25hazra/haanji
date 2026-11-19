"""The clinic's token queue: one line per doctor (or counsellor), per day.

A booked patient gets a token when reception checks them in; a walk-in gets
one at the desk. Reception calls the next token, marks a no-show, and a TV
screen shows who is being seen. A caller can ask "mera number kab aayega" and
hears their token, how many are ahead and a rough wait.

Tokens are numbered per department per day and read like ``GP-07``. The wait
is an estimate and is always said as one ("lagbhag"): the average consult time
of the doctor's finished tokens today once there are three, otherwise the
duration of the doctor's first service in the pack.

The table lives in the tenant's backend database, so it works on SQLite and,
through haanji/db.py, on Postgres.
"""
from __future__ import annotations
import datetime as dt
import re
import uuid
from typing import Any, Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

SCHEMA = """
CREATE TABLE IF NOT EXISTS queue_tokens (
  token_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, day TEXT NOT NULL,
  staff TEXT NOT NULL, dept_code TEXT NOT NULL, number INTEGER NOT NULL,
  kind TEXT NOT NULL, booking_id TEXT, service TEXT, name TEXT, phone TEXT,
  status TEXT NOT NULL, created_at TEXT NOT NULL, called_at TEXT, done_at TEXT);
CREATE INDEX IF NOT EXISTS queue_day_ix ON queue_tokens (tenant_id, day, staff, status);
"""
STATUSES = ("waiting", "serving", "done", "no_show")
MIN_SAMPLES = 3                       # finished tokens before the day's own average is trusted


class QueueError(ValueError):
    pass


def _phone10(phone: str | None) -> str:
    digits = re.sub(r"\D", "", phone or "")
    return digits[-10:] if len(digits) >= 10 else digits


def _label(code: str, number: int) -> str:
    return f"{code}-{number:02d}"


class TokenQueue:
    def __init__(self, backend, pack, tenant_id: str):
        self.b, self.pack, self.tenant = backend, pack, tenant_id
        self.b.conn.executescript(SCHEMA)
        self.b.conn.commit()

    # ------------------------------------------------------------- helpers
    @property
    def day(self) -> str:
        return self.b.today.isoformat()

    def _now(self) -> str:
        return self.b.now().isoformat(timespec="seconds")

    def code_of(self, staff: str) -> str:
        dept = self.pack.department_of(staff)
        if dept:
            return dept.code
        letters = "".join(w[0] for w in staff.split() if w[:1].isalpha()).upper()
        return (letters[-2:] or "T")

    def dept_name(self, staff: str) -> str | None:
        dept = self.pack.department_of(staff)
        return dept.name if dept else None

    def _rows(self, where: str, args: tuple) -> list[dict[str, Any]]:
        rows = self.b.conn.execute(f"SELECT * FROM queue_tokens WHERE tenant_id=? AND {where}",
                                   (self.tenant, *args)).fetchall()
        return [dict(r) for r in rows]

    def _public(self, row: dict[str, Any]) -> dict[str, Any]:
        return {**row, "label": _label(row["dept_code"], row["number"]), "department": self.dept_name(row["staff"])}

    def _insert(self, *, staff: str, kind: str, booking_id: str | None, service: str | None,
                name: str | None, phone: str | None) -> dict[str, Any]:
        if staff not in self.pack.staff:
            raise QueueError(f"no such {self.pack.staff_role}: {staff}")
        code = self.code_of(staff)
        top = self.b.conn.execute("SELECT MAX(number) AS n FROM queue_tokens WHERE tenant_id=? AND day=? AND dept_code=?",
                                  (self.tenant, self.day, code)).fetchone()
        number = (top["n"] or 0) + 1
        row = {"token_id": uuid.uuid4().hex[:12], "tenant_id": self.tenant, "day": self.day, "staff": staff,
               "dept_code": code, "number": number, "kind": kind, "booking_id": booking_id, "service": service,
               "name": name, "phone": _phone10(phone) or None, "status": "waiting", "created_at": self._now(),
               "called_at": None, "done_at": None}
        self.b.conn.execute(
            "INSERT INTO queue_tokens (token_id,tenant_id,day,staff,dept_code,number,kind,booking_id,service,name,"
            "phone,status,created_at,called_at,done_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(row.values()))
        self.b.conn.commit()
        return self._public(row)

    # ----------------------------------------------------------- reception
    def check_in(self, booking_id: str) -> dict[str, Any]:
        """A booked patient has arrived: their token (the same one if they
        were already checked in)."""
        have = self._rows("booking_id=?", (booking_id,))
        if have:
            return self._public(have[0])
        bk = self.b.booking(self.tenant, booking_id)
        if bk is None or bk.status != "CONFIRMED":
            raise QueueError("no confirmed booking with that id")
        if bk.date != self.day:
            raise QueueError(f"that booking is for {bk.date}, not today")
        return self._insert(staff=bk.staff, kind="booked", booking_id=bk.booking_id, service=bk.service,
                            name=bk.customer_name, phone=bk.phone)

    def add_walkin(self, *, staff: str | None = None, service: str | None = None,
                   name: str | None = None, phone: str | None = None) -> dict[str, Any]:
        """A walk-in: to the named doctor, or to whichever doctor who does the
        service has the shortest line."""
        if not staff:
            svc = next((s for s in self.pack.services if service and s.name.lower() == service.lower()), None)
            if svc is None:
                raise QueueError("a walk-in needs a doctor or a service")
            staff = min(svc.staff or self.pack.staff, key=lambda p: len(self._rows(
                "day=? AND staff=? AND status IN ('waiting','serving')", (self.day, p))))
        return self._insert(staff=staff, kind="walkin", booking_id=None, service=service, name=name, phone=phone)

    def call_next(self, staff: str) -> dict[str, Any]:
        """The patient being seen is done; the next one in line is called."""
        now = self._now()
        for row in self._rows("day=? AND staff=? AND status='serving'", (self.day, staff)):
            self.b.conn.execute("UPDATE queue_tokens SET status='done', done_at=? WHERE token_id=?", (now, row["token_id"]))
        waiting = sorted(self._rows("day=? AND staff=? AND status='waiting'", (self.day, staff)),
                         key=lambda r: (r["created_at"], r["number"]))
        nxt = waiting[0] if waiting else None
        if nxt:
            self.b.conn.execute("UPDATE queue_tokens SET status='serving', called_at=? WHERE token_id=?",
                                (now, nxt["token_id"]))
            nxt = {**nxt, "status": "serving", "called_at": now}
        self.b.conn.commit()
        return {"staff": staff, "serving": self._public(nxt) if nxt else None}

    def mark(self, token_id: str, status: str) -> dict[str, Any]:
        if status not in STATUSES:
            raise QueueError(f"status must be one of {', '.join(STATUSES)}")
        rows = self._rows("token_id=?", (token_id,))
        if not rows:
            raise QueueError("no such token")
        done = self._now() if status in ("done", "no_show") else None
        self.b.conn.execute("UPDATE queue_tokens SET status=?, done_at=COALESCE(?, done_at) WHERE token_id=?",
                            (status, done, token_id))
        self.b.conn.commit()
        return self._public({**rows[0], "status": status})

    # ---------------------------------------------------------------- views
    def avg_minutes(self, staff: str) -> float:
        finished = [r for r in self._rows("day=? AND staff=? AND status='done'", (self.day, staff))
                    if r["called_at"] and r["done_at"]]
        if len(finished) >= MIN_SAMPLES:
            spans = [(dt.datetime.fromisoformat(r["done_at"]) - dt.datetime.fromisoformat(r["called_at"])).total_seconds()
                     for r in finished]
            return max(1.0, sum(spans) / len(spans) / 60)
        svc = next((s for s in self.pack.services if staff in s.staff), None)
        return float(svc.duration_min if svc else 15)

    def view(self) -> dict[str, Any]:
        """Reception's screen: every doctor's line, and today's booked patients
        who have not checked in yet."""
        tokens = self._rows("day=?", (self.day,))
        lines = []
        for person in self.pack.staff:
            mine = sorted((t for t in tokens if t["staff"] == person), key=lambda r: (r["created_at"], r["number"]))
            serving = next((t for t in mine if t["status"] == "serving"), None)
            lines.append({
                "staff": person, "department": self.dept_name(person), "code": self.code_of(person),
                "serving": self._public(serving) if serving else None,
                "waiting": [self._public(t) for t in mine if t["status"] == "waiting"],
                "done": sum(t["status"] == "done" for t in mine),
                "no_show": sum(t["status"] == "no_show" for t in mine),
                "avg_minutes": round(self.avg_minutes(person), 1)})
        checked = {t["booking_id"] for t in tokens if t["booking_id"]}
        due = [b.as_dict() for b in self.b.bookings_between(self.tenant, self.day, self.day)
               if b.booking_id not in checked]
        return {"day": self.day, "lines": lines, "to_check_in": due}

    def display(self) -> dict[str, Any]:
        """The waiting-room screen: tokens and doctors only, never a name or a number."""
        out = []
        for line in self.view()["lines"]:
            out.append({"staff": line["staff"], "department": line["department"],
                        "serving": line["serving"]["label"] if line["serving"] else None,
                        "next": [t["label"] for t in line["waiting"][:3]], "waiting": len(line["waiting"])})
        return {"day": self.day, "lines": out}

    def position(self, phone: str) -> dict[str, Any] | None:
        """Where a caller stands today: their token, how many are ahead and a
        rough wait; or, booked but not checked in, how long the doctor's line is."""
        p = _phone10(phone)
        if not p:
            return None
        mine = [t for t in self._rows("day=? AND phone=? AND status IN ('waiting','serving')", (self.day, p))]
        if mine:
            t = sorted(mine, key=lambda r: r["created_at"])[0]
            pub = self._public(t)
            if t["status"] == "serving":
                return {**pub, "token_kind": pub["kind"], "kind": "token", "ahead": 0, "wait_min": 0}
            line = self._rows("day=? AND staff=? AND status IN ('waiting','serving')", (self.day, t["staff"]))
            ahead = sum(1 for r in line if r["status"] == "serving" or
                        (r["status"] == "waiting" and (r["created_at"], r["number"]) < (t["created_at"], t["number"])))
            return {**pub, "token_kind": pub["kind"], "kind": "token", "ahead": ahead,
                    "wait_min": int(round(ahead * self.avg_minutes(t["staff"])))}
        booked = [b for b in self.b.bookings_between(self.tenant, self.day, self.day) if _phone10(b.phone) == p]
        if booked:
            b = sorted(booked, key=lambda x: x.time)[0]
            line = self._rows("day=? AND staff=? AND status IN ('waiting','serving')", (self.day, b.staff))
            return {"kind": "booking", "staff": b.staff, "department": self.dept_name(b.staff), "time": b.time,
                    "service": b.service, "in_line": len(line)}
        return None

    def ahead_of_booking(self, staff: str, date: str, time: str) -> int:
        """Appointments with the same doctor earlier that day (what a booking
        card can say before the patient arrives)."""
        return sum(1 for b in self.b.bookings_between(self.tenant, date, date)
                   if b.staff == staff and b.time < time)


def spoken_position(pos: dict[str, Any] | None) -> str:
    """The caller's answer, in the agent's Hinglish."""
    if pos is None:
        return ("Aaj aapke number par koi token ya booking nahi mili. Clinic pahunch kar reception par "
                "check-in kijiye, wahin token milta hai.")
    if pos["kind"] == "booking":
        line = f"abhi {pos['staff']} ki line mein {pos['in_line']} log hain" if pos["in_line"] else \
               f"abhi {pos['staff']} ki line khaali hai"
        return f"Aapki booking aaj {pos['time']} baje {pos['staff']} ke saath hai; {line}. Pahunch kar reception par token lijiye."
    if pos["status"] == "serving":
        return f"Aapka token {pos['label']} hai, aur ab aapki baari hai: {pos['staff']} ke paas jaiye."
    if pos["ahead"] == 0:
        return f"Aapka token {pos['label']} hai. Aap agle hain, {pos['staff']} thodi der mein bulayenge."
    return (f"Aapka token {pos['label']} hai. Aapse pehle {pos['ahead']} log hain, "
            f"lagbhag {pos['wait_min']} minute lagenge.")


# ------------------------------------------------------------------- the API
class CheckIn(BaseModel):
    booking_id: str = Field(max_length=64)


class WalkIn(BaseModel):
    staff: str | None = Field(default=None, max_length=80)
    service: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=20)


class NextIn(BaseModel):
    staff: str = Field(max_length=80)


class MarkIn(BaseModel):
    status: str = Field(max_length=16)


def make_router(*, queue_for: Callable[[str], TokenQueue], publish: Callable[..., Any], default_pack: str) -> APIRouter:
    """Reception's endpoints (staff sign-in, scoped to the pack in ?pack=)
    and the waiting-room display (public; no names, no numbers)."""
    r = APIRouter()

    def run(fn, *args, **kw):
        try:
            return fn(*args, **kw)
        except QueueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @r.get("/api/queue")
    async def queue_view(pack: str = default_pack):
        return run(queue_for(pack).view)

    @r.get("/api/queue/display")
    async def queue_display(pack: str = default_pack):
        return run(queue_for(pack).display)

    @r.post("/api/queue/checkin")
    async def queue_checkin(body: CheckIn, pack: str = default_pack):
        tok = run(queue_for(pack).check_in, body.booking_id)
        publish("queue", pack=pack, action="checkin", label=tok["label"], staff=tok["staff"])
        return tok

    @r.post("/api/queue/walkin")
    async def queue_walkin(body: WalkIn, pack: str = default_pack):
        tok = run(queue_for(pack).add_walkin, staff=body.staff, service=body.service, name=body.name, phone=body.phone)
        publish("queue", pack=pack, action="walkin", label=tok["label"], staff=tok["staff"])
        return tok

    @r.post("/api/queue/next")
    async def queue_next(body: NextIn, pack: str = default_pack):
        out = run(queue_for(pack).call_next, body.staff)
        publish("queue", pack=pack, action="next", staff=body.staff,
                label=out["serving"]["label"] if out["serving"] else None)
        return out

    @r.post("/api/queue/{token_id}/status")
    async def queue_mark(token_id: str, body: MarkIn, pack: str = default_pack):
        tok = run(queue_for(pack).mark, token_id, body.status)
        publish("queue", pack=pack, action=body.status, label=tok["label"], staff=tok["staff"])
        return tok

    return r
