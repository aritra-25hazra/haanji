"""Google Calendar: connect once, every booking lands on the owner's calendar.

Plain OAuth 2.0 over HTTP (no Google SDK): the authorisation URL, the code
exchange, the refresh, and one ``events.insert``. Credentials come from
HAANJI_GOOGLE_CLIENT_ID / HAANJI_GOOGLE_CLIENT_SECRET; the refresh token is
stored per tenant. Everything network-facing goes through one ``httpx``
client so tests can swap the transport.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import secrets
import sqlite3
import time
import urllib.parse
from typing import Any

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar}/events"
SCOPE = "https://www.googleapis.com/auth/calendar.events"

SCHEMA = """
CREATE TABLE IF NOT EXISTS google_links (
  tenant_id     TEXT PRIMARY KEY,
  refresh_token TEXT NOT NULL,
  access_token  TEXT NOT NULL DEFAULT '',
  expires_at    REAL NOT NULL DEFAULT 0,
  calendar_id   TEXT NOT NULL DEFAULT 'primary',
  email         TEXT NOT NULL DEFAULT '',
  connected_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS google_states (
  state     TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  created   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS google_events (
  booking_id TEXT PRIMARY KEY,
  tenant_id  TEXT NOT NULL,
  event_id   TEXT NOT NULL,
  created    TEXT NOT NULL
);
"""


class GoogleCalendar:
    def __init__(self, path: str, client_id: str | None = None, client_secret: str | None = None,
                 redirect_uri: str = "", transport: httpx.AsyncBaseTransport | None = None):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.client_id = client_id or os.environ.get("HAANJI_GOOGLE_CLIENT_ID") or ""
        self.client_secret = client_secret or os.environ.get("HAANJI_GOOGLE_CLIENT_SECRET") or ""
        self.redirect_uri = redirect_uri
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=20.0)

    # ------------------------------------------------------------- linking
    def connect_url(self, tenant_id: str) -> str:
        state = secrets.token_urlsafe(24)
        with self.conn:
            self.conn.execute("DELETE FROM google_states WHERE created < ?", (time.time() - 900,))
            self.conn.execute("INSERT INTO google_states VALUES (?,?,?)", (state, tenant_id, time.time()))
        q = {"client_id": self.client_id, "redirect_uri": self.redirect_uri, "response_type": "code",
             "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": state,
             "include_granted_scopes": "true"}
        return AUTH_URL + "?" + urllib.parse.urlencode(q)

    def tenant_for_state(self, state: str) -> str | None:
        r = self.conn.execute("SELECT tenant_id FROM google_states WHERE state=? AND created > ?",
                              (state, time.time() - 900)).fetchone()
        if r is None:
            return None
        with self.conn:
            self.conn.execute("DELETE FROM google_states WHERE state=?", (state,))
        return r["tenant_id"]

    async def finish(self, tenant_id: str, code: str) -> dict[str, Any]:
        async with self._client() as c:
            r = await c.post(TOKEN_URL, data={"code": code, "client_id": self.client_id, "client_secret": self.client_secret,
                                              "redirect_uri": self.redirect_uri, "grant_type": "authorization_code"})
        r.raise_for_status()
        tok = r.json()
        if not tok.get("refresh_token"):
            raise RuntimeError("Google returned no refresh token; disconnect the app in your Google account and connect again")
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO google_links VALUES (?,?,?,?,?,?,?)",
                              (tenant_id, tok["refresh_token"], tok.get("access_token", ""),
                               time.time() + float(tok.get("expires_in", 3600)) - 60, "primary", "",
                               dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
        return {"connected": True}

    def link(self, tenant_id: str) -> dict[str, Any] | None:
        r = self.conn.execute("SELECT * FROM google_links WHERE tenant_id=?", (tenant_id,)).fetchone()
        return dict(r) if r else None

    def disconnect(self, tenant_id: str) -> bool:
        with self.conn:
            cur = self.conn.execute("DELETE FROM google_links WHERE tenant_id=?", (tenant_id,))
        return cur.rowcount > 0

    def connected(self) -> list[str]:
        return [r["tenant_id"] for r in self.conn.execute("SELECT tenant_id FROM google_links ORDER BY tenant_id")]

    # ------------------------------------------------------------- pushing
    async def _access_token(self, tenant_id: str) -> str:
        link = self.link(tenant_id)
        if link is None:
            raise RuntimeError("not connected")
        if link["access_token"] and link["expires_at"] > time.time():
            return link["access_token"]
        async with self._client() as c:
            r = await c.post(TOKEN_URL, data={"refresh_token": link["refresh_token"], "client_id": self.client_id,
                                              "client_secret": self.client_secret, "grant_type": "refresh_token"})
        r.raise_for_status()
        tok = r.json()
        with self.conn:
            self.conn.execute("UPDATE google_links SET access_token=?, expires_at=? WHERE tenant_id=?",
                              (tok["access_token"], time.time() + float(tok.get("expires_in", 3600)) - 60, tenant_id))
        return tok["access_token"]

    async def push(self, tenant_id: str, booking_id: str, body: dict[str, Any]) -> str | None:
        """Create the event once per booking. Returns the Google event id."""
        done = self.conn.execute("SELECT event_id FROM google_events WHERE booking_id=?", (booking_id,)).fetchone()
        if done:
            return done["event_id"]
        link = self.link(tenant_id)
        if link is None:
            return None
        token = await self._access_token(tenant_id)
        async with self._client() as c:
            r = await c.post(EVENTS_URL.format(calendar=urllib.parse.quote(link["calendar_id"])),
                             headers={"Authorization": f"Bearer {token}"}, json=body)
        r.raise_for_status()
        event_id = r.json().get("id", "")
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO google_events VALUES (?,?,?,?)",
                              (booking_id, tenant_id, event_id, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
        return event_id
