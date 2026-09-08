"""Durable demo-server state: finished calls, WhatsApp threads, missed calls.

One SQLite file per installation. This is deliberately separate from the
business backend (bookings, customers) and from the ledger — those model the
tenant's world; this models the channels through which callers reached it.
"""
from __future__ import annotations
import datetime as dt
import json
import sqlite3
import uuid
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
  call_id      TEXT PRIMARY KEY,
  tenant_id    TEXT NOT NULL,
  channel      TEXT NOT NULL,             -- WEB | WHATSAPP | PHONE
  phone        TEXT,
  started_at   TEXT NOT NULL,
  ended_at     TEXT,
  outcome      TEXT,
  corrections  INTEGER NOT NULL DEFAULT 0,
  spec_started INTEGER NOT NULL DEFAULT 0,
  spec_hits    INTEGER NOT NULL DEFAULT 0,
  latency_p50  REAL,
  turns_json   TEXT NOT NULL DEFAULT '[]',
  receipts_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS calls_tenant_ix ON calls (tenant_id, started_at DESC);

CREATE TABLE IF NOT EXISTS missed_calls (
  missed_id   TEXT PRIMARY KEY,
  tenant_id   TEXT NOT NULL,
  phone       TEXT NOT NULL,
  at          TEXT NOT NULL,
  outreach_sent INTEGER NOT NULL DEFAULT 0,
  recovered   INTEGER NOT NULL DEFAULT 0,
  booking_code TEXT
);

CREATE TABLE IF NOT EXISTS wa_messages (
  msg_id     TEXT PRIMARY KEY,
  tenant_id  TEXT NOT NULL,
  phone      TEXT NOT NULL,
  direction  TEXT NOT NULL,               -- in | out
  text       TEXT NOT NULL,
  at         TEXT NOT NULL,
  meta_json  TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS wa_thread_ix ON wa_messages (tenant_id, phone, at);
"""


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


class DemoStore:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ------------------------------------------------------------------ calls
    def record_call(self, report, *, channel: str, phone: str | None) -> None:
        lat = sorted(report.latencies)
        p50 = lat[len(lat) // 2] if lat else None
        turns = [{"seq": t.seq, "heard": t.heard, "corrected": t.corrected, "said": t.said,
                  "tools": t.tools, "speculation_hits": t.speculation_hits,
                  "corrections": [{"from_token": c.from_token, "to_surface": c.to_surface,
                                   "asr_confidence": c.asr_confidence, "ngram": c.ngram}
                                  for c in t.corrections],
                  "guard": t.guard, "latency_ms": t.latency_ms,
                  "interrupted": t.interrupted}
                 for t in report.turns]
        self.conn.execute(
            "INSERT OR REPLACE INTO calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (report.conversation_id, report.tenant_id, channel, phone, _now(), _now(),
             report.outcome.value, report.corrections,
             report.speculation.get("started", 0), report.speculation.get("hits", 0),
             p50, json.dumps(turns, ensure_ascii=False),
             json.dumps(report.receipts)))
        self.conn.commit()

    def calls(self, tenant_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM calls WHERE tenant_id=? ORDER BY started_at DESC LIMIT ?",
            (tenant_id, limit))
        return [dict(r) for r in rows]

    def call(self, tenant_id: str, call_id: str) -> dict[str, Any] | None:
        r = self.conn.execute("SELECT * FROM calls WHERE tenant_id=? AND call_id=?",
                              (tenant_id, call_id)).fetchone()
        return dict(r) if r else None

    # ----------------------------------------------------------- missed calls
    def record_missed(self, tenant_id: str, phone: str) -> str:
        mid = str(uuid.uuid4())
        self.conn.execute("INSERT INTO missed_calls VALUES (?,?,?,?,1,0,NULL)",
                          (mid, tenant_id, phone, _now()))
        self.conn.commit()
        return mid

    def mark_recovered(self, tenant_id: str, phone: str, booking_code: str) -> None:
        self.conn.execute(
            "UPDATE missed_calls SET recovered=1, booking_code=? WHERE tenant_id=? AND phone=?"
            " AND recovered=0", (booking_code, tenant_id, phone))
        self.conn.commit()

    def missed_summary(self, tenant_id: str) -> dict[str, int]:
        row = self.conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(recovered),0) AS recovered"
            " FROM missed_calls WHERE tenant_id=?", (tenant_id,)).fetchone()
        return {"total": row["total"], "recovered": row["recovered"]}

    def has_open_missed(self, tenant_id: str, phone: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM missed_calls WHERE tenant_id=? AND phone=? AND recovered=0 LIMIT 1",
            (tenant_id, phone)).fetchone()
        return bool(row)

    # -------------------------------------------------------------- whatsapp
    def add_wa(self, tenant_id: str, phone: str, direction: str, text: str,
               meta: dict | None = None) -> None:
        self.conn.execute("INSERT INTO wa_messages VALUES (?,?,?,?,?,?,?)",
                          (str(uuid.uuid4()), tenant_id, phone, direction, text, _now(),
                           json.dumps(meta or {}, ensure_ascii=False)))
        self.conn.commit()

    def wa_thread(self, tenant_id: str, phone: str, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM wa_messages WHERE tenant_id=? AND phone=? ORDER BY at, msg_id LIMIT ?",
            (tenant_id, phone, limit))
        return [dict(r) for r in rows]

    def wa_threads(self, tenant_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT phone, MAX(at) AS last_at, COUNT(*) AS messages FROM wa_messages"
            " WHERE tenant_id=? GROUP BY phone ORDER BY last_at DESC", (tenant_id,))
        return [dict(r) for r in rows]
