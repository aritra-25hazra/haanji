"""The HaanJi demo server: every channel on one port.

    haanji serve                       # then open http://localhost:8090

Serves the browser call page (/talk), the WhatsApp simulator (/whatsapp), the
public receipt verifier (/verify), and the JSON APIs the operator console and
Pack Studio use. Speech stays in the browser (its recogniser sends partial and
final transcripts here), so the whole thing runs with no API keys — while the
engine underneath is the same code the telephone path exercises.
"""
from __future__ import annotations
import asyncio
import base64
import csv
import datetime as dt
import hmac
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid
import zipfile
import logging
import secrets
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from typing import Literal

from . import __version__
from .adapters.mock import NullTTS
from .backend.local import LocalBackend
from .channels import whatsapp as wa_channel
from . import collect as collect_mod
from . import onboard as onboard_mod
from .auth import AuthStore, OtpThrottled, Principal, normalise_phone
from .config import EngineConfig
from .telemetry import TELEMETRY, TOOL_BUCKETS_MS
from .devanagari import transliterate
from . import calendar as cal_mod
from .gcal import GoogleCalendar
from .telephony import twilio as twilio_mod
from .pramaan.vault import Vault, normalise_phone as _norm_phone
from .push import PushStore
from . import admin as admin_mod
from . import backup as backup_mod
from . import reminders as rem_mod
from .payments import PaymentStore
from .settings import SettingsStore
from .metrics import percentile
from .bhasha.phonetics import phrase_key
from .bhasha.lexicon import LexEntry, TenantLexicon
from .insights import compute as compute_insights
from .pipeline import CallSession, TurnRecord
from .models import Speaker, Turn
from .pramaan.ledger import Ledger
from .store import DemoStore
from .tools.builtin import build_registry
from .vertical import PACK_DIR, PackError, from_dict, list_packs, load_pack

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
VAR_DIR = os.path.abspath(os.environ.get("HAANJI_VAR_DIR", "var"))
DEFAULT_PACK = os.environ.get("HAANJI_PACK", "dental_clinic")
# Where this server is reachable from a customer's phone: the receipt link in a
# WhatsApp message has to be absolute. Render sets RENDER_EXTERNAL_URL itself.
PUBLIC_URL = (os.environ.get("HAANJI_PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL")
              or "http://localhost:8090").rstrip("/")
OWNER_PHONE = os.environ.get("HAANJI_OWNER_PHONE") or None
log = logging.getLogger("haanji.server")
ENGINE_CFG = EngineConfig()
# A server with a public address is a deployment: vendor webhooks must be
# signed there, and a missing secret is a misconfiguration, not a dev shortcut.
IS_PUBLIC = bool(os.environ.get("HAANJI_PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL"))
DEMO_DATA = os.environ.get("HAANJI_DEMO", "").lower() in ("1", "true", "on", "yes")
MAX_BODY_BYTES = int(os.environ.get("HAANJI_MAX_BODY_BYTES", str(1024 * 1024)))
MAX_RECORD_BYTES = 26 * 1024 * 1024
DIGEST_HOUR = int(os.environ.get("HAANJI_DIGEST_HOUR", "20"))          # IST
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SESSION_IDLE_S = 1800

os.makedirs(VAR_DIR, exist_ok=True)
backup_mod.restore_on_boot(VAR_DIR)                # HAANJI_RESTORE_FROM, only into an empty data dir

from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """The evening scheduler (daily anchors, the owner's digest) runs for the
    life of the process; HAANJI_SCHEDULER=0 keeps it off, e.g. in tests."""
    seed_owner()
    tasks: list[asyncio.Task] = []
    if os.environ.get("HAANJI_SCHEDULER", "1") != "0":
        tasks.append(asyncio.ensure_future(_evening_loop()))
        tasks.append(asyncio.ensure_future(_gc_loop()))
        tasks.append(asyncio.ensure_future(_reminder_loop()))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()


app = FastAPI(title="HaanJi demo server", version=__version__, lifespan=_lifespan)
# Same-origin in production, because the console is served through a rewrite;
# the regex is overridable so the engine can also be called directly.
CORS_ORIGIN_REGEX = os.environ.get(
    "HAANJI_CORS_ORIGIN_REGEX", r"http://(localhost|127\.0\.0\.1)(:\d+)?")
app.add_middleware(CORSMiddleware, allow_origin_regex=CORS_ORIGIN_REGEX,
                   allow_methods=["*"], allow_headers=["*"])


# ───────────────────────────────────────────────────────────── hardening
# A public demo gets hammered. Writes are rate limited per client (token
# bucket, in memory, generous), and every response carries the headers a
# scanner expects. The WhatsApp webhook is exempt: it is signed, and Meta
# retries in bursts.
RATE_LIMIT_PER_MIN = int(os.environ.get("HAANJI_RATE_LIMIT_PER_MIN", "120"))
RATE_LIMIT_GET_PER_MIN = int(os.environ.get("HAANJI_RATE_LIMIT_GET_PER_MIN", "600"))
RATE_LIMIT_EXEMPT = ("/wa/webhook", "/api/status", "/telephony/", "/payments/")
# X-Forwarded-For is only meaningful behind a proxy we trust; it is then the
# *last* hop that the proxy appended, never the first value a client can set.
TRUST_PROXY = os.environ.get("HAANJI_TRUST_PROXY", "1").lower() in ("1", "true", "on", "yes")
_buckets: dict[str, tuple[float, float]] = {}      # client -> (tokens, last refill)


def _client_of(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for") if TRUST_PROXY else None
    if fwd:
        return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "?"


def rate_limited(client: str, now: float | None = None, limit: int | None = None) -> bool:
    """One bucket per client: ``limit`` tokens (RATE_LIMIT_PER_MIN by default),
    refilled continuously."""
    limit = RATE_LIMIT_PER_MIN if limit is None else limit
    if limit <= 0:
        return False
    now = time.monotonic() if now is None else now
    tokens, last = _buckets.get(client, (float(limit), now))
    tokens = min(float(limit), tokens + (now - last) * limit / 60.0)
    if tokens < 1.0:
        _buckets[client] = (tokens, now)
        return True
    _buckets[client] = (tokens - 1.0, now)
    if len(_buckets) > 10000:                        # never grow without bound
        for key in list(_buckets)[:5000]:
            _buckets.pop(key, None)
    return False


def body_limit_for(path: str) -> int:
    # Nothing on this server needs a large body except a volunteer's recording.
    return MAX_RECORD_BYTES if path == "/api/record" else MAX_BODY_BYTES


class BodyLimitMiddleware:
    """Caps a request body by the bytes actually received. The Content-Length
    check below is a cheap early refusal, but a chunked request carries no
    length header, so the count has to happen on the way in."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = body_limit_for(scope.get("path", ""))
        seen = 0

        async def limited_receive():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    # An HTTPException, not a custom one: FastAPI turns any other
                    # error raised while it parses a body into a generic 400.
                    raise HTTPException(413, "request body too large")
            return message

        await self.app(scope, limited_receive, send)


app.add_middleware(BodyLimitMiddleware)


@app.middleware("http")
async def hardening(request: Request, call_next):
    path = request.url.path
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        if not path.startswith(RATE_LIMIT_EXEMPT) and rate_limited(_client_of(request)):
            TELEMETRY.inc("http_rate_limited_total")
            return JSONResponse({"detail": "too many requests; try again in a minute"}, status_code=429,
                                headers={"Retry-After": "60"})
        try:
            length = int(request.headers.get("content-length") or 0)
        except ValueError:
            length = 0
        if length > body_limit_for(path):
            return JSONResponse({"detail": "request body too large"}, status_code=413)
    if demo_locked(request.method, path):
        TELEMETRY.inc("demo_readonly_refused_total")
        return JSONResponse({"detail": "the public demo is read-only: set HAANJI_AUTH=on for a real shop "
                                       "(or HAANJI_DEMO_WRITES=1 for a private demo)"}, status_code=403)
    elif request.method == "GET" and not path.startswith(RATE_LIMIT_EXEMPT) and \
            rate_limited("GET " + _client_of(request), limit=RATE_LIMIT_GET_PER_MIN):
        TELEMETRY.inc("http_rate_limited_total")
        return JSONResponse({"detail": "too many requests; try again in a minute"}, status_code=429,
                            headers={"Retry-After": "60"})
    if AUTH_ENABLED and request.method != "OPTIONS":
        need = required_role(request)
        if need:
            who = principal_of(request)
            if who is None:
                TELEMETRY.inc("auth_denied_total", status="401")
                return JSONResponse({"detail": "sign in first"}, status_code=401,
                                    headers={"WWW-Authenticate": "Bearer"})
            if ROLE_RANK.get(who.role, 0) < ROLE_RANK[need]:
                TELEMETRY.inc("auth_denied_total", status="403")
                return JSONResponse({"detail": f"{need} role needed"}, status_code=403)
            pack = _pack_in(request)
            if pack is not SCOPED and not who.allows(pack):
                TELEMETRY.inc("auth_denied_total", status="403")
                return JSONResponse({"detail": "not your pack"}, status_code=403)
            request.state.user = who
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "microphone=(self), camera=(), geolocation=()")
    if request.headers.get("x-forwarded-proto", request.url.scheme) == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

store = DemoStore(os.path.join(VAR_DIR, "store.sqlite"))

gcal = GoogleCalendar(os.path.join(VAR_DIR, "gcal.sqlite"), redirect_uri=f"{PUBLIC_URL}/api/google/callback")
# Personal data in receipts is encrypted per customer (docs/privacy-dpdp.md).
vault = Vault(os.path.join(VAR_DIR, "vault.sqlite"))
# With HAANJI_LEDGER_KEY_SECRET set, tenants' signing keys are encrypted at rest.
LEDGER_KEY_SECRET = os.environ.get("HAANJI_LEDGER_KEY_SECRET") or None
settings = SettingsStore(os.path.join(VAR_DIR, "settings.sqlite"))
payments = PaymentStore(os.path.join(VAR_DIR, "payments.sqlite"), PUBLIC_URL)
push = PushStore(os.path.join(VAR_DIR, "push.sqlite"), os.path.join(VAR_DIR, "vapid.json"),
                 contact=os.environ.get("HAANJI_PUSH_CONTACT") or "mailto:owner@haanji.local")
CONSENT_LINE = os.environ.get("HAANJI_CONSENT_LINE") or ""
# Storage limitation (DPDP): call records and messages older than this are
# purged every evening; bookings and receipts (the business's records) stay.
# 0 keeps everything. The 1.0 default was 0, which meant nothing was ever
# purged unless the owner knew to configure it.
RETENTION_DAYS = int(os.environ.get("HAANJI_RETENTION_DAYS", "180"))

# ─────────────────────────────────────────────────────────────── auth
AUTH_ENABLED = os.environ.get("HAANJI_AUTH", "off").lower() in ("on", "1", "true", "yes")
AUTH_DEV = os.environ.get("HAANJI_AUTH_DEV", "0").lower() in ("1", "true", "yes", "on")
# A public server with sign-in off is a demo for strangers: the console's
# destructive operations (settings, cancelling bookings, users, pack saves,
# erasure, backups) are refused there. HAANJI_DEMO_WRITES=1 re-opens them for
# a private demo behind someone's own firewall.
DEMO_WRITES = os.environ.get("HAANJI_DEMO_WRITES", "").lower() in ("1", "true", "yes", "on")
DEMO_READONLY = IS_PUBLIC and not AUTH_ENABLED and not DEMO_WRITES
DEMO_LOCKED: list[tuple[str, re.Pattern]] = [
    ("PUT", re.compile(r"^/api/settings$")),
    ("POST", re.compile(r"^/api/bookings/[^/]+/(cancel|status)$")),
    ("DELETE", re.compile(r"^/api/waitlist/[^/]+$")),
    ("GET|POST|DELETE", re.compile(r"^/api/auth/users(/.*)?$")),
    ("GET", re.compile(r"^/api/admin/backup$")),
    ("POST", re.compile(r"^/api/(digest/send|push/test|anchors/seal)$")),
    ("DELETE", re.compile(r"^/api/privacy/customer/.*$")),
    ("PUT", re.compile(r"^/api/packs/[^/]+$")),
    ("DELETE", re.compile(r"^/api/google/disconnect$")),
]


def demo_locked(method: str, path: str) -> bool:
    return DEMO_READONLY and any(method in m.split("|") and rx.match(path) for m, rx in DEMO_LOCKED)
auth = AuthStore(os.path.join(VAR_DIR, "auth.sqlite"), os.environ.get("HAANJI_AUTH_SECRET") or None)
# (method regex, path regex, minimum role). Everything else is public: the
# demo pages, callers' sessions, the verifier's export, the webhooks.
PROTECTED: list[tuple[str, re.Pattern, str]] = [
    ("GET", re.compile(r"^/api/(insights|conversations(/.*)?|lexicon|wa/threads(/.*)?|events(/recent)?|digest|ops)$"), "staff"),
    ("GET", re.compile(r"^/api/packs/[^/]+$"), "staff"),
    ("GET", re.compile(r"^/api/(record/(manifest|export)|study/(responses|export))$"), "owner"),
    ("GET", re.compile(r"^/api/record/prompts$"), "staff"),
    # The WhatsApp *simulator* drives the real tenant's thread store; the
    # research pages write to disk. Both are demo/research surfaces that a
    # real shop keeps behind sign-in.
    ("POST", re.compile(r"^/api/(wa/incoming|record|study)$"), "staff"),
    ("POST", re.compile(r"^/api/(packs/(draft|validate|[^/]+/selftest)|anchors/seal|digest/send)$"), "owner"),
    ("PUT", re.compile(r"^/api/packs/[^/]+$"), "owner"),
    ("GET|POST|DELETE", re.compile(r"^/api/auth/users(/.*)?$"), "owner"),
    # the operator console (docs/console-api.md)
    ("GET", re.compile(r"^/api/(bookings|customers|settings|waitlist|payments)$"), "staff"),
    ("POST", re.compile(r"^/api/bookings/[^/]+/(cancel|status)$"), "staff"),
    ("DELETE", re.compile(r"^/api/waitlist/[^/]+$"), "staff"),
    ("PUT", re.compile(r"^/api/settings$"), "owner"),
    ("GET", re.compile(r"^/api/admin/backup$"), "owner"),
]
ROLE_RANK = {"staff": 1, "owner": 2}
SCOPED = object()        # "the handler filters by the user's own packs"


def seed_owner() -> None:
    """A fresh deployment with auth on and no users makes HAANJI_OWNER_PHONE
    the owner of every pack, so nobody is locked out of their own console."""
    if AUTH_ENABLED and OWNER_PHONE and auth.count() == 0:
        auth.upsert_user(OWNER_PHONE, "owner", ["*"], name="Owner")


def _pack_in(request: Request):
    """Which pack a request is about, for the scope check. Routes that list
    across packs return SCOPED and filter in the handler; everything else
    defaults to DEFAULT_PACK, exactly as the handlers do — "no pack" is never
    "any pack"."""
    path = request.url.path
    q = request.query_params.get("pack")
    if q:
        return q
    m = re.match(r"^/api/packs/([^/]+)", path)
    if m and m.group(1) not in ("draft", "validate"):
        return m.group(1)
    m = re.match(r"^/api/sessions/([^/]+)/(takeover|handback|human-reply)$", path)
    if m:
        holder = _sessions.get(m.group(1))
        return holder.rt.pack_id if holder else DEFAULT_PACK
    if path in ("/api/sessions/live", "/api/events", "/api/events/recent") or path.startswith("/api/auth/"):
        return SCOPED
    return DEFAULT_PACK


def _allowed_packs(request: Request) -> set[str] | None:
    """None = every pack; otherwise the signed-in user's own packs."""
    who: Principal | None = getattr(request.state, "user", None)
    if who is None or "*" in who.packs:
        return None
    return set(who.packs)


def required_role(request: Request) -> str | None:
    for methods, pattern, role in PROTECTED:
        if request.method in methods.split("|") and pattern.match(request.url.path):
            return role
    return None


def principal_of(request: Request) -> Principal | None:
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else None
    if token is None and request.url.path == "/api/events":
        token = request.query_params.get("token")       # EventSource cannot send headers
    return auth.verify_token(token)


# ─────────────────────────────────────────────────────────── tenant runtimes
@dataclass
class TenantRuntime:
    pack_id: str
    pack: Any
    backend: LocalBackend
    ledger: Ledger
    registry: Any


_runtimes: dict[str, TenantRuntime] = {}

DEMO_CUSTOMERS = {
    "dental_clinic": ("9876543210", "Vijay Sharma", "root canal"),
    "clinic_kolkata": ("9830012345", "Rohan Sen", "teeth cleaning"),
}


def runtime(pack_id: str) -> TenantRuntime:
    if pack_id in _runtimes:
        return _runtimes[pack_id]
    if pack_id not in list_packs():
        raise HTTPException(404, f"no pack '{pack_id}'")
    pack = load_pack(pack_id)
    conn = sqlite3.connect(os.path.join(VAR_DIR, f"backend-{pack_id}.sqlite"),
                           check_same_thread=False)
    backend = LocalBackend(conn)
    backend.load_pack(pack_id, pack)
    demo = DEMO_CUSTOMERS.get(pack_id)
    if demo and (DEMO_DATA or not AUTH_ENABLED):
        # "Vijay ji, wapas swagat hai" is for the public demo; a real shop's
        # customer table starts empty.
        backend.seed_customer(pack_id, *demo[:2], last_service=demo[2])
    ledger = Ledger(sqlite3.connect(os.path.join(VAR_DIR, f"ledger-{pack_id}.sqlite"),
                                    check_same_thread=False), key_secret=LEDGER_KEY_SECRET)
    registry = build_registry(pack_id, backend, pack, ledger, vault=vault)
    _runtimes[pack_id] = TenantRuntime(pack_id, pack, backend, ledger, registry)
    return _runtimes[pack_id]


# ─────────────────────────────────────────────────────────────────── sessions
@dataclass
class Holder:
    session: CallSession
    rt: TenantRuntime
    channel: str
    phone: str | None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_used: float = field(default_factory=time.monotonic)
    receipts_seen: int = 0
    human: bool = False                       # a person at the console has taken the call
    speak: Any = None                         # telephony: how to say something on this call
    finished: bool = False                    # _finish ran (a DELETE after end_call must not run it twice)


_sessions: dict[str, Holder] = {}
_wa_sessions: dict[tuple[str, str], str] = {}      # (pack, phone) -> session id


# ─────────────────────────────────────────────────────────── live event bus
# Every call publishes what it is doing; the console's live panel subscribes
# over server-sent events, and keeps a ring buffer for clients that cannot
# hold a stream open (a proxy that buffers, a phone on a bad link).
_subscribers: set[asyncio.Queue] = set()
_recent: deque[dict[str, Any]] = deque(maxlen=200)
_event_seq = 0
KEEPALIVE_S = 15.0


def publish(kind: str, **data: Any) -> dict[str, Any]:
    global _event_seq
    _event_seq += 1
    event = {"seq": _event_seq, "kind": kind, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **data}
    _recent.append(event)
    TELEMETRY.inc("events_published_total", kind=kind)
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:                   # a slow reader loses events, never blocks a call
            pass
    return event


def _sse(event: dict[str, Any]) -> str:
    return f"id: {event['seq']}\nevent: {event['kind']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _event_stream(pack: str | None, queue: asyncio.Queue):
    _subscribers.add(queue)
    try:
        yield ": connected\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_S)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"              # keeps proxies from closing an idle stream
                continue
            if pack and event.get("pack") not in (None, pack):
                continue
            yield _sse(event)
    finally:
        _subscribers.discard(queue)


def _visible(event: dict[str, Any], pack: str | None, allowed: set[str] | None) -> bool:
    if pack and event.get("pack") not in (None, pack):
        return False
    return allowed is None or event.get("pack") is None or event.get("pack") in allowed


async def _scoped_stream(pack: str | None, allowed: set[str] | None, queue: asyncio.Queue):
    async for chunk in _event_stream(None, queue):
        if chunk.startswith(":"):
            yield chunk
            continue
        try:
            event = json.loads(chunk.split("\ndata: ", 1)[1].rstrip("\n"))
        except (IndexError, ValueError):
            continue
        if _visible(event, pack, allowed):
            yield chunk


@app.get("/api/events")
async def events(request: Request, pack: str | None = None):
    allowed = _allowed_packs(request)
    if pack and allowed is not None and pack not in allowed:
        raise HTTPException(403, "not your pack")
    return StreamingResponse(_scoped_stream(pack, allowed, asyncio.Queue(maxsize=256)), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/events/recent")
async def events_recent(request: Request, pack: str | None = None, since: int = 0, limit: int = 50):
    allowed = _allowed_packs(request)
    if pack and allowed is not None and pack not in allowed:
        raise HTTPException(403, "not your pack")
    rows = [e for e in _recent if e["seq"] > since and _visible(e, pack, allowed)]
    return {"events": rows[-limit:], "latest": _event_seq, "live_sessions": len(_sessions)}


def _mask(phone: str | None) -> str | None:
    """A live feed is seen by everyone in the shop; show the last four digits."""
    return f"…{phone[-4:]}" if phone and len(phone) >= 4 else phone


def holder_sid(holder: Holder) -> str | None:
    for sid, h in _sessions.items():
        if h is holder:
            return sid
    return None


def _gc() -> None:
    cutoff = time.monotonic() - SESSION_IDLE_S
    for sid in [k for k, h in _sessions.items() if h.last_used < cutoff]:
        holder = _sessions.pop(sid)
        _wa_sessions.pop((holder.rt.pack_id, holder.phone or ""), None)


async def _gc_loop() -> None:
    while True:
        await asyncio.sleep(60)
        _gc()


async def _new_session(pack_id: str, channel: str, phone: str | None, *, verified: bool = False) -> tuple[str, Holder]:
    """Open a call. ``verified`` is whether the channel proved the caller's
    number (PSTN caller-id, the WhatsApp sender). A number typed into the
    web page is not verified, and the policy asks for the receipt code
    before it cancels or moves a booking for that number."""
    _gc()
    if ENGINE_CFG.max_concurrent_calls > 0 and len(_sessions) >= ENGINE_CFG.max_concurrent_calls:
        TELEMETRY.inc("sessions_refused_total")
        raise HTTPException(429, "the desk is busy; please try again in a minute")
    rt = runtime(pack_id)
    session = CallSession(tenant_id=pack_id, pack=rt.pack, backend=rt.backend,
                          registry=rt.registry, ledger=rt.ledger, tts=NullTTS())
    await session.open(phone=phone, verified=verified)
    if CONSENT_LINE:                                   # notice at the start of every call
        session.ctx.last_agent_utterance = f"{session.ctx.last_agent_utterance} {CONSENT_LINE}".strip()
        if session.ctx.turns:
            session.ctx.turns[-1].text = session.ctx.last_agent_utterance
    sid = uuid.uuid4().hex[:16]
    holder = Holder(session, rt, channel, phone)
    _sessions[sid] = holder
    publish("session.started", sid=sid, pack=pack_id, channel=channel, phone=_mask(phone),
            greeting=session.ctx.last_agent_utterance)
    return sid, holder


def _turn_payload(record, holder: Holder) -> dict[str, Any]:
    session = holder.session
    new_receipts = session.receipts[holder.receipts_seen:]
    holder.receipts_seen = len(session.receipts)
    pack_id = holder.rt.pack_id
    TELEMETRY.inc("turns_total", pack=pack_id)
    TELEMETRY.observe("turn_latency_ms", record.latency_ms, pack=pack_id)
    if record.corrections:
        TELEMETRY.inc("bhasha_corrections_total", len(record.corrections), pack=pack_id)
    if record.guard:
        TELEMETRY.inc("guardrail_total", pack=pack_id, rule=record.guard)
    if new_receipts:
        TELEMETRY.inc("ledger_receipts_total", len(new_receipts), pack=pack_id)
    for sp in record.spans:
        if sp["name"].startswith("tool:"):
            TELEMETRY.observe("tool_ms", sp["ms"], buckets=TOOL_BUCKETS_MS, tool=sp["name"][5:],
                              speculated=str(sp.get("speculated", False)).lower())
    if record.speculation_hits:
        TELEMETRY.inc("speculation_hits_total", len(record.speculation_hits), pack=pack_id)
    publish("turn", sid=holder_sid(holder), pack=pack_id, channel=holder.channel,
            heard=record.heard, corrected=record.corrected, reply=record.said,
            corrections=[{"from_token": c.from_token, "to_surface": c.to_surface} for c in record.corrections],
            tools=record.tools, speculation_hits=record.speculation_hits, receipts=new_receipts,
            guard=record.guard, latency_ms=round(record.latency_ms, 1), spans=record.spans,
            outcome=_provisional_outcome(session))
    return {
        "spans": record.spans,
        "reply": record.said,
        "heard": record.heard,
        "corrected": record.corrected,
        "corrections": [{"from_token": c.from_token, "to_surface": c.to_surface,
                         "asr_confidence": c.asr_confidence,
                         "key": phrase_key(c.from_token), "to_key": phrase_key(c.to_surface)}
                        for c in record.corrections],
        "tools": record.tools,
        "speculation_hits": record.speculation_hits,
        "guard": record.guard,
        "latency_ms": round(record.latency_ms, 1),
        "receipts": new_receipts,
        "end_call": bool(session.ctx.flags.get("ended")),
        "outcome": _provisional_outcome(session),
    }


def _provisional_outcome(session: CallSession) -> str | None:
    """What finish() will say if the call ended now: a question answered is
    an FAQ call, which the context only learns at the end."""
    if session.ctx.outcome:
        return session.ctx.outcome.value
    if session.ctx.flags.get("ended") and session.ctx.answered_questions:
        return "FAQ_ANSWERED"
    return None


def receipt_link(pack_id: str, code: str) -> str:
    """The customer's own proof: the public verifier, opened on their receipt."""
    return f"{PUBLIC_URL}/verify?code={code}&pack={pack_id}"


def receipt_note(pack_id: str, codes: list[str]) -> str:
    links = "\n".join(receipt_link(pack_id, c) for c in codes)
    return f"Aapki booking ki receipt (kabhi bhi verify kar sakte hain):\n{links}"


async def _push_calendar(holder: Holder, codes: list[str]) -> None:
    """Every sealed booking goes to the owner's Google Calendar, if connected."""
    pack_id = holder.rt.pack_id
    if not codes or gcal.link(pack_id) is None:
        return
    try:
        for b in holder.rt.backend.bookings(pack_id):
            if b.receipt_code in codes and b.status == "CONFIRMED":
                await gcal.push(pack_id, b.booking_id, cal_mod.google_event(b, holder.rt.pack.persona.business_name, PUBLIC_URL))
    except Exception as exc:                          # noqa: BLE001 - a mirror, not the booking
        log.warning(f"google calendar push failed: {exc}")


async def _payment_links(holder: Holder, codes: list[str]) -> list[dict[str, Any]]:
    """With a deposit configured, every booking just sealed gets a payment
    link (Razorpay, or this server's mock). Returns the links made."""
    rt = holder.rt
    deposit = int(settings.get(rt.pack_id).get("deposit_inr") or 0)
    if deposit <= 0 or not codes:
        return []
    made = []
    for b in rt.backend.bookings(rt.pack_id):
        if b.receipt_code in codes and b.status == "CONFIRMED" and not b.payment_id:
            link = await payments.create_link(rt.pack_id, b, deposit, business=rt.pack.persona.business_name)
            if link:
                rt.backend.mark_paid(rt.pack_id, b.booking_id, link["payment_id"], False)
                made.append(link)
    return made


def payment_note(links: list[dict[str, Any]]) -> str:
    if not links:
        return ""
    amount = links[0]["amount_inr"]
    return f"Slot pakka rakhne ke liye ₹{amount:,} ka deposit yahan de dijiye:\n" + "\n".join(l["link"] for l in links)


async def _notify_customer(holder: Holder, codes: list[str], links: list[dict[str, Any]] | None = None) -> None:
    """A web or phone caller who gave a number gets the receipt link (and the
    deposit link) on WhatsApp, if a real number is connected. Never blocks."""
    if codes and holder.phone and holder.channel != "WHATSAPP" and wa_channel.configured():
        try:
            text = receipt_note(holder.rt.pack_id, codes)
            if links:
                text += "\n\n" + payment_note(links)
            await wa_channel.send_template(holder.phone, "receipt", [codes[-1]], fallback_text=text)
        except Exception as exc:                      # noqa: BLE001 - a courtesy, not the call
            log.warning(f"receipt notification failed: {exc}")


async def offer_waitlist(rt: TenantRuntime, date: str, service: str | None) -> dict[str, Any] | None:
    """A slot on ``date`` just freed up: the first person waiting for that day
    hears about it on WhatsApp, and their thread is primed so that "haan"
    books it through the ordinary read-back and receipt."""
    if not settings.get(rt.pack_id).get("waitlist_on", True):
        return None
    entry = rt.backend.next_waiting(rt.pack_id, date, service)
    if entry is None:
        return None
    avail = await rt.backend.availability(rt.pack_id, entry.get("service") or service, date,
                                          period=entry.get("period") or None, limit=1)
    slot = (avail.get("slots") or [None])[0]
    if slot is None:
        return None
    business = rt.pack.persona.business_name
    from .speak import spoken_date, spoken_time
    when = f"{spoken_date(slot['date'], rt.backend.today, rt.backend.resolve_date, rt.pack.language)} {spoken_time(slot['time'], rt.pack.language)}"
    svc = entry.get("service") or service or "appointment"
    text = (f"Namaste{(' ' + entry['name'].split()[0] + ' ji') if entry.get('name') else ''}! {business} se: "
            f"{svc} ka ek slot khaali hua hai — {when}, {slot['staff']} ke saath. "
            f"Chahiye to 'haan' likh dijiye, main book kar dunga.")
    phone = entry["phone"]
    key = (rt.pack_id, phone)
    if key in _wa_sessions:
        _sessions.pop(_wa_sessions.pop(key), None)
    sid, holder = await _new_session(rt.pack_id, "WHATSAPP", phone, verified=True)
    _wa_sessions[key] = sid
    ctx = holder.session.ctx
    ctx.service, ctx.date, ctx.time, ctx.staff = svc, slot["date"], slot["time"], slot["staff"]
    ctx.customer_name = ctx.customer_name or entry.get("name")
    ctx.flags["time_checked"] = True
    ctx.last_agent_utterance = text
    if ctx.turns:
        ctx.turns[-1].text = text
    rt.backend.waitlist_mark(rt.pack_id, entry["entry_id"], "OFFERED", f"{slot['date']} {slot['time']}")
    store.add_wa(rt.pack_id, phone, "out", text, meta={"waitlist_offer": entry["entry_id"]})
    delivered = None
    if wa_channel.configured():
        delivered = await wa_channel.send_template(phone, "outreach", [business], fallback_text=text)
    publish("waitlist.offered", pack=rt.pack_id, phone=_mask(phone), slot=f"{slot['date']} {slot['time']}")
    TELEMETRY.inc("waitlist_offers_total", pack=rt.pack_id)
    return {"entry_id": entry["entry_id"], "phone": phone, "slot": slot, "delivered": delivered, "text": text}


async def _after_turn(holder: Holder, record, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """What a booking or a cancellation sets in motion beyond the reply:
    deposit links, the owner's calendar, the customer's WhatsApp, the next
    person on the waitlist. Returns the payment links, for the channel to
    show. Never raises into the call."""
    links: list[dict[str, Any]] = []
    try:
        if payload["receipts"]:
            links = await _payment_links(holder, payload["receipts"])
            asyncio.ensure_future(_notify_customer(holder, payload["receipts"], links))
            asyncio.ensure_future(_push_calendar(holder, payload["receipts"]))
        if any(t in ("cancel_appointment", "reschedule_appointment") for t in record.tools):
            phone = holder.session.ctx.customer_phone or holder.phone
            freed = [b for b in holder.rt.backend.bookings(holder.rt.pack_id)
                     if b.status == "CANCELLED" and (not phone or b.phone == phone)]
            if freed:
                last = freed[-1]
                asyncio.ensure_future(offer_waitlist(holder.rt, last.date, last.service))
    except Exception as exc:                          # noqa: BLE001
        log.warning("after-turn work failed: %s", exc)
    return links


def _finish(sid: str, holder: Holder) -> None:
    if holder.finished:
        return
    holder.finished = True
    report = holder.session.finish()
    store.record_call(report, channel=holder.channel, phone=holder.phone)
    TELEMETRY.inc("calls_total", pack=holder.rt.pack_id, channel=holder.channel.lower(), outcome=report.outcome.value)
    spec = report.speculation
    TELEMETRY.inc("speculation_started_total", spec.get("started", 0), pack=holder.rt.pack_id)
    TELEMETRY.inc("speculation_wasted_total", spec.get("wasted", 0), pack=holder.rt.pack_id)
    fallbacks = getattr(holder.session.llm, "fallbacks", 0)
    if fallbacks:
        TELEMETRY.inc("adapter_fallbacks_total", fallbacks, pack=holder.rt.pack_id)
    publish("session.ended", sid=sid, pack=holder.rt.pack_id, channel=holder.channel,
            outcome=report.outcome.value, call_id=report.conversation_id,
            receipts=len(report.receipts), turns=len(report.turns))
    TELEMETRY.gauge("live_sessions", max(0, len(_sessions) - 1))
    _push_outcome(holder, report)
    if holder.phone and report.receipts and store.has_open_missed(holder.rt.pack_id, holder.phone):
        store.mark_recovered(holder.rt.pack_id, holder.phone, report.receipts[-1])
    if holder.phone and report.outcome.value in ("BOOKED", "RESCHEDULED"):
        for entry in holder.rt.backend.waitlist(holder.rt.pack_id):
            if entry["phone"] == holder.phone and entry["status"] in ("WAITING", "OFFERED"):
                holder.rt.backend.waitlist_mark(holder.rt.pack_id, entry["entry_id"], "BOOKED")
    _sessions.pop(sid, None)
    _wa_sessions.pop((holder.rt.pack_id, holder.phone or ""), None)


def _push_outcome(holder: Holder, report) -> None:
    """The owner's phone buzzes for the outcomes that need a human eye."""
    titles = {"BOOKED": "Nayi booking", "RESCHEDULED": "Booking badli", "LEAD_CAPTURED": "Callback chahiye",
              "HANDED_OFF": "Call aapke liye"}
    title = titles.get(report.outcome.value)
    if not title or push.count(holder.rt.pack_id) == 0:
        return
    body = f"{holder.channel.lower()} · {_mask(holder.phone) or 'number nahi'} · {len(report.turns)} turns"
    if report.receipts:
        body += f" · receipt {report.receipts[-1]}"
    url = f"{(os.environ.get('HAANJI_CONSOLE_URL') or '').rstrip('/')}/calls/{report.conversation_id}"
    def _go() -> None:
        try:
            push.send(holder.rt.pack_id, f"{title} — {holder.rt.pack.persona.business_name}", body, url)
        except Exception as exc:                          # noqa: BLE001
            log.warning("push failed: %s", exc)
    try:
        # pywebpush is synchronous HTTP; keep it off the event loop so one
        # slow push service cannot stall every live call.
        asyncio.get_running_loop().run_in_executor(None, _go)
    except RuntimeError:
        _go()


# ──────────────────────────────────────────────────────────────── web-call api
class NewSession(BaseModel):
    pack: str = Field(default=DEFAULT_PACK, max_length=64)
    phone: str | None = Field(default=None, max_length=20)
    channel: Literal["WEB", "WHATSAPP", "PHONE"] = "WEB"


class TextIn(BaseModel):
    text: str = Field(max_length=2000)


@app.post("/api/sessions")
async def create_session(body: NewSession):
    phone = _norm_phone(body.phone) if body.phone else None
    if body.phone and len(phone or "") != 10:
        raise HTTPException(422, "phone must be ten digits")
    # The browser says who is calling; nothing proved it.
    sid, holder = await _new_session(body.pack, body.channel, phone, verified=False)
    return {"session_id": sid, "greeting": holder.session.ctx.last_agent_utterance,
            "pack": body.pack, "business": holder.rt.pack.persona.business_name}


@app.post("/api/sessions/{sid}/partial")
async def session_partial(sid: str, body: TextIn):
    holder = _sessions.get(sid)
    if holder is None:
        raise HTTPException(404, "no such session")
    holder.last_used = time.monotonic()
    await holder.session.handle_partial_text(body.text)
    publish("partial", sid=sid, pack=holder.rt.pack_id, text=body.text)
    return {"ok": True}


@app.post("/api/sessions/{sid}/utterance")
async def session_utterance(sid: str, body: TextIn):
    holder = _sessions.get(sid)
    if holder is None:
        raise HTTPException(404, "no such session")
    holder.last_used = time.monotonic()
    if holder.human:
        return _human_turn(sid, holder, body.text)
    async with holder.lock:
        record = await holder.session.handle_text_turn(body.text)
        payload = _turn_payload(record, holder)
        links = await _after_turn(holder, record, payload)
        if links:
            payload["payment_links"] = [{"amount_inr": l["amount_inr"], "link": l["link"]} for l in links]
        if payload["end_call"]:
            _finish(sid, holder)
    return payload


@app.delete("/api/sessions/{sid}")
async def close_session(sid: str):
    holder = _sessions.get(sid)
    if holder is None:
        return {"ok": True, "outcome": None, "call_id": None}
    call_id = holder.session.ctx.conversation_id
    _finish(sid, holder)
    row = store.call(holder.rt.pack_id, call_id)
    return {"ok": True, "outcome": row["outcome"] if row else None, "call_id": call_id}


# ─────────────────────────────────────────────────────────── whatsapp channel
class WaIn(BaseModel):
    pack: str = Field(default=DEFAULT_PACK, max_length=64)
    phone: str = Field(max_length=20)
    text: str = Field(max_length=4096)


async def _wa_turn(pack_id: str, phone: str, text: str, *, verified: bool = True) -> list[dict[str, Any]]:
    """One inbound WhatsApp message -> the agent's replies. Shared by the
    simulator and the real Meta webhook, so the demo and production run the
    same path."""
    store.add_wa(pack_id, phone, "in", text)
    replies: list[dict[str, Any]] = []
    key = (pack_id, phone)
    sid = _wa_sessions.get(key)
    holder = _sessions.get(sid) if sid else None
    if holder is None:
        sid, holder = await _new_session(pack_id, "WHATSAPP", phone, verified=verified)
        _wa_sessions[key] = sid
        greeting = holder.session.ctx.last_agent_utterance
        store.add_wa(pack_id, phone, "out", greeting)
        replies.append({"text": greeting})
    holder.last_used = time.monotonic()
    if holder.human:
        _human_turn(sid, holder, text)
        return replies                                 # the person at the console answers
    answered = await _reminder_reply(pack_id, phone, text, holder)
    if answered is not None:
        store.add_wa(pack_id, phone, "out", answered["text"], meta={"reminder_reply": True})
        replies.append(answered)
        return replies
    async with holder.lock:
        record = await holder.session.handle_text_turn(text)
        payload = _turn_payload(record, holder)
        text_out = record.said
        links = await _after_turn(holder, record, payload)
        if payload["receipts"]:
            text_out = f"{record.said}\n\n{receipt_note(pack_id, payload['receipts'])}"
            if links:
                text_out += "\n\n" + payment_note(links)
        store.add_wa(pack_id, phone, "out", text_out,
                     meta={"tools": record.tools, "receipts": payload["receipts"],
                           "corrections": payload["corrections"]})
        replies.append({"text": text_out, **{k: payload[k] for k in
                       ("corrections", "tools", "speculation_hits", "receipts", "latency_ms")}})
        if payload["end_call"]:
            _finish(sid, holder)
    return replies


@app.post("/api/wa/incoming")
async def wa_incoming(body: WaIn):
    """The simulator. It stands in for the real channel while no WhatsApp
    number is connected (so a typed number counts as the sender's); once a
    real number is connected, anyone could type anyone's number here, so
    the simulator's callers are treated as unverified."""
    if not re.fullmatch(r"\d{10}", body.phone):
        raise HTTPException(400, "phone must be ten digits")
    return {"replies": await _wa_turn(body.pack, body.phone, body.text.strip(),
                                      verified=not wa_channel.configured())}


@app.get("/api/wa/threads")
async def wa_threads(pack: str = DEFAULT_PACK):
    return {"threads": store.wa_threads(pack)}


@app.get("/api/wa/threads/{phone}")
async def wa_thread(phone: str, pack: str = DEFAULT_PACK):
    return {"messages": store.wa_thread(pack, phone)}


# Real Meta WhatsApp Cloud API webhook — used when HAANJI_WA_TOKEN etc. are
# configured; the simulator above uses the same _wa_turn.
@app.get("/wa/webhook")
async def wa_verify(request: Request):
    """Meta's one-time handshake when the webhook is registered."""
    q = request.query_params
    expected = os.environ.get("HAANJI_WA_VERIFY_TOKEN") or ("haanji" if not IS_PUBLIC else None)
    if expected and q.get("hub.mode") == "subscribe" and hmac.compare_digest(q.get("hub.verify_token", ""), expected):
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "bad verify token")


# Message ids Meta has already delivered; it retries anything it did not get a
# prompt 200 for, and a retried booking must not become two bookings.
_wa_seen: deque[str] = deque(maxlen=500)


@app.post("/wa/webhook")
async def wa_webhook(request: Request):
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(413, "request body too large")
    secret = os.environ.get("HAANJI_WA_APP_SECRET") or None
    if secret is None and IS_PUBLIC and wa_channel.configured():
        raise HTTPException(403, "HAANJI_WA_APP_SECRET is not set; refusing unsigned deliveries")
    if secret and not wa_channel.verify_signature(secret, raw, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(403, "bad signature")
    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "not json")
    pack = os.environ.get("HAANJI_WA_PACK") or DEFAULT_PACK
    handled = 0
    for msg_id, phone, text in wa_channel.extract_incoming(payload):
        if msg_id and msg_id in _wa_seen:
            continue
        if msg_id:
            _wa_seen.append(msg_id)
        replies = await _wa_turn(pack, phone[-10:], text, verified=True)   # Meta vouches for the sender
        for r in replies:
            await wa_channel.send_text(phone, r["text"])
        handled += 1
    return {"ok": True, "handled": handled}


# ───────────────────────────────────────────────────── missed-call recovery
class MissedIn(BaseModel):
    pack: str = Field(default=DEFAULT_PACK, max_length=64)
    phone: str = Field(max_length=20)


@app.post("/api/telephony/missed-call")
async def missed_call(body: MissedIn, request: Request):
    """The telephony provider tells us a call rang out (Exotel/Plivo webhook
    shape documented in channels/telephony.py). We open the WhatsApp thread
    with an outreach message — and, with a real number connected, actually
    send it; when the caller's reply ends in a booking, the missed call is
    counted as recovered. HAANJI_MISSED_CALL_SECRET, when set, must arrive
    in X-HaanJi-Secret; a public server refuses the call without it."""
    secret = os.environ.get("HAANJI_MISSED_CALL_SECRET")
    if secret:
        if not hmac.compare_digest(request.headers.get("X-HaanJi-Secret", ""), secret):
            raise HTTPException(403, "bad secret")
    elif IS_PUBLIC:
        raise HTTPException(403, "set HAANJI_MISSED_CALL_SECRET to accept missed-call webhooks")
    phone = _norm_phone(body.phone)
    if len(phone) != 10:
        raise HTTPException(422, "phone must be ten digits")
    body.phone = phone
    rt = runtime(body.pack)
    store.record_missed(body.pack, body.phone)
    outreach = (f"Namaste! Aapne abhi {rt.pack.persona.business_name} ko call kiya tha — "
                f"maaf kijiye, hum utha nahi paye. Main yahin WhatsApp par appointment "
                f"book kar sakta hoon. Kaunsi service chahiye?")
    key = (body.pack, body.phone)
    if key in _wa_sessions:                       # a fresh thread for the recovery
        _sessions.pop(_wa_sessions.pop(key), None)
    sid, holder = await _new_session(body.pack, "WHATSAPP", body.phone, verified=True)
    _wa_sessions[key] = sid
    holder.session.ctx.last_agent_utterance = outreach
    store.add_wa(body.pack, body.phone, "out", outreach, meta={"missed_call_recovery": True})
    delivered = None
    if wa_channel.configured():
        delivered = await wa_channel.send_template(body.phone, "outreach", [rt.pack.persona.business_name],
                                                  fallback_text=outreach)
    return {"ok": True, "outreach": outreach, "delivered": delivered}


# ─────────────────────────────────────────────────────── insights + history
@app.get("/api/insights")
async def insights(pack: str = DEFAULT_PACK):
    rt = runtime(pack)
    return compute_insights(pack, store, rt.backend)


@app.get("/api/conversations")
async def conversations(pack: str = DEFAULT_PACK, limit: int = 50):
    return {"conversations": store.calls(pack, limit)}


@app.get("/api/conversations/{call_id}")
async def conversation(call_id: str, pack: str = DEFAULT_PACK):
    row = store.call(pack, call_id)
    if row is None:
        raise HTTPException(404, "no such call")
    return row


@app.get("/api/lexicon")
async def lexicon(pack: str = DEFAULT_PACK, probe: str | None = None):
    """The tenant's sound-indexed vocabulary, built exactly as the pipeline
    builds it, and optionally where a heard phrase would land in it."""
    try:
        p = load_pack(pack)
    except Exception:
        raise HTTPException(404, "no such pack")
    lex = TenantLexicon.build(version=p.version, **p.lexicon_seed())
    out: dict[str, Any] = {
        "pack": pack, "version": lex.version,
        "entries": [{"surface": e.surface, "entry_type": e.entry_type.value,
                     "variants": e.variants, "keys": sorted(e.keys()),
                     "weight": round(e.weight, 2)} for e in lex.entries],
    }
    if probe and probe.strip():
        text = probe.strip()
        key = LexEntry.key_of(text.lower())
        out["probe"] = {"text": text, "key": key,
                        "matches": [c.surface for c in lex.candidates(key)]}
    return out

# ───────────────────────────────────────────────────────── pramaan endpoints
@app.get("/api/receipts/export")
async def receipts_export(pack: str = DEFAULT_PACK):
    rt = runtime(pack)
    receipts = rt.ledger.receipts(pack)
    key_id = rt.ledger.ensure_key(pack)
    from cryptography.hazmat.primitives import serialization
    public = rt.ledger.public_key(key_id).public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    return {"tenant_id": pack, "algorithm": "Ed25519", "public_key": public,
            "exported_at": dt.datetime.now().isoformat(timespec="seconds"),
            "receipts": [r.to_row() for r in receipts]}


# ─────────────────────────────────────────────────────── pack studio endpoints
@app.get("/api/packs")
async def packs():
    out = []
    for pid in list_packs():
        p = load_pack(pid)
        out.append({"pack_id": pid, "display_name": p.display_name, "version": p.version,
                    "language": p.language, "services": len(p.services),
                    "staff": len(p.staff), "scenarios": len(p.scenarios),
                    "issues": p.validate()})
    return {"packs": out}


@app.get("/api/packs/{pack_id}")
async def pack_get(pack_id: str):
    path = os.path.join(PACK_DIR, f"{pack_id}.yaml")
    if not os.path.exists(path):
        raise HTTPException(404, "no such pack")
    raw = open(path, encoding="utf-8").read()
    return {"pack_id": pack_id, "yaml": raw, "parsed": yaml.safe_load(raw)}


class PackBody(BaseModel):
    yaml: str = Field(max_length=400_000)


def _validate_yaml(text: str) -> tuple[dict, list[str]]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise HTTPException(422, f"not valid YAML: {exc}")
    try:
        pack = from_dict(data)
    except (PackError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, f"not a valid pack: {exc}")
    return data, pack.validate()


class DraftIn(BaseModel):
    business_name: str
    business_type: str = "other"
    pack_id: str | None = None
    display_name: str | None = None
    language: str = "hinglish"
    agent_name: str = "Haanji"
    staff_role: str | None = None
    greeting: str | None = None
    closing: str | None = None
    staff: list[str] = []
    hours: dict[str, list[str] | None] = {}
    services: list[dict[str, Any]] = []
    places: list[str] = []


@app.post("/api/packs/draft")
async def pack_draft(body: DraftIn):
    """Onboarding: answers in, a complete validated pack out (not saved)."""
    try:
        text, problems, data = onboard_mod.draft(body.model_dump())
    except (PackError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, f"could not build a pack: {exc}")
    return {"pack_id": data["pack"], "yaml": text, "problems": problems,
            "exists": data["pack"] in list_packs()}


@app.post("/api/packs/validate")
async def pack_validate(body: PackBody):
    _, problems = _validate_yaml(body.yaml)
    return {"ok": not problems, "problems": problems}


@app.put("/api/packs/{pack_id}")
async def pack_put(pack_id: str, body: PackBody):
    data, problems = _validate_yaml(body.yaml)
    if data.get("pack") != pack_id:
        raise HTTPException(422, f"yaml says pack '{data.get('pack')}', URL says '{pack_id}'")
    path = os.path.join(PACK_DIR, f"{pack_id}.yaml")
    if os.path.exists(path):
        open(path + ".bak", "w", encoding="utf-8").write(open(path, encoding="utf-8").read())
    open(path, "w", encoding="utf-8").write(body.yaml)
    _runtimes.pop(pack_id, None)                   # next session sees the new pack
    return {"ok": True, "problems": problems, "backup": os.path.basename(path + ".bak")}


@app.post("/api/packs/{pack_id}/selftest")
async def pack_selftest(pack_id: str):
    """Run the pack's own scenarios in a subprocess, so the simulated clock of
    the test run cannot interfere with live sessions on this server."""
    if pack_id not in list_packs():
        raise HTTPException(404, "no such pack")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "haanji.cli", "selftest", "--pack", pack_id, "--speed", "150",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(504, "the pack's scenarios did not finish in two minutes")
    lines = out.decode().splitlines()
    results = [{"passed": l.startswith("PASS"), "line": l.split(None, 1)[1].strip()}
               for l in lines if l.startswith(("PASS", "FAIL"))]
    summary = next((l for l in lines if "scenarios reached" in l), "")
    return {"ok": proc.returncode == 0, "results": results, "summary": summary}


# ─────────────────────────────────────────────────────────────── static pages
# ───────────────────────────────────────────── research: recordings and study
REC_DIR = os.path.join(VAR_DIR, "recordings")
STUDY_DB = os.path.join(VAR_DIR, "study.sqlite")
_AUDIO_EXT = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/wav": "wav",
              "audio/x-wav": "wav", "audio/mpeg": "mp3", "audio/aiff": "aiff", "audio/x-aiff": "aiff"}


def _manifest_rows() -> list[dict[str, Any]]:
    path = os.path.join(REC_DIR, "manifest.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class RecordIn(BaseModel):
    pack: str
    truth: str
    kind: str = "catalogue"
    speaker: str = "anon"
    mime: str = "audio/webm"
    audio_b64: str


@app.get("/api/record/prompts")
async def record_prompts(pack: str = DEFAULT_PACK, limit: int = 20):
    try:
        return collect_mod.prompts_for(load_pack(pack), limit=max(1, min(limit, 80)))
    except (FileNotFoundError, PackError):
        raise HTTPException(404, f"unknown pack {pack}")


@app.post("/api/record")
async def record_save(body: RecordIn):
    """One recorded prompt: the audio file, and a manifest line that pairs it
    with what the volunteer was asked to say. Transcription happens offline
    (research/collect/transcribe.py); the server never runs a recogniser."""
    if body.pack not in list_packs():
        raise HTTPException(404, f"unknown pack {body.pack}")
    try:
        audio = base64.b64decode(body.audio_b64, validate=True)
    except (ValueError, TypeError):
        raise HTTPException(400, "audio is not base64")
    if not audio or len(audio) > 25 * 1024 * 1024:
        raise HTTPException(400, "audio is empty or too large")
    os.makedirs(REC_DIR, exist_ok=True)
    rid = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    ext = _AUDIO_EXT.get(body.mime.split(";")[0].strip().lower(), "bin")
    fname = f"{rid}.{ext}"
    with open(os.path.join(REC_DIR, fname), "wb") as fh:
        fh.write(audio)
    row = {"id": rid, "file": fname, "pack": body.pack, "truth": body.truth.strip(),
           "kind": body.kind, "speaker": re.sub(r"[^\w .-]", "", body.speaker)[:40] or "anon",
           "mime": body.mime, "bytes": len(audio),
           "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    with open(os.path.join(REC_DIR, "manifest.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"ok": True, "id": rid, "count": len(_manifest_rows())}


@app.get("/api/record/manifest")
async def record_manifest():
    rows = _manifest_rows()
    speakers = sorted({r.get("speaker", "") for r in rows})
    return {"count": len(rows), "speakers": speakers, "rows": rows}


@app.get("/api/record/export")
async def record_export():
    """Everything in var/recordings as one zip, for a host whose disk is
    wiped on redeploy."""
    rows = _manifest_rows()
    if not rows:
        raise HTTPException(404, "no recordings yet")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(REC_DIR, "manifest.jsonl"), "manifest.jsonl")
        for r in rows:
            path = os.path.join(REC_DIR, r["file"])
            if os.path.exists(path):
                z.write(path, r["file"])
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="haanji-recordings.zip"'})


SUS_ITEMS = 10


def sus_score(answers: list[int]) -> float:
    """Brooke's System Usability Scale: odd items score answer-1, even items
    5-answer, times 2.5. 0..100."""
    if len(answers) != SUS_ITEMS:
        raise ValueError("ten answers")
    total = 0
    for i, a in enumerate(answers):
        a = max(1, min(5, int(a)))
        total += (a - 1) if i % 2 == 0 else (5 - a)
    return round(total * 2.5, 1)


class StudyTask(BaseModel):
    id: str
    expected: str = ""
    success: bool = False
    seconds: int | None = None


class StudyIn(BaseModel):
    participant: str
    pack: str = DEFAULT_PACK
    tasks: list[StudyTask]
    sus: list[int]
    wrong: str = ""
    good: str = ""
    duration_s: int | None = None


def _study_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(STUDY_DB)
    conn.execute("CREATE TABLE IF NOT EXISTS responses (id TEXT PRIMARY KEY, participant TEXT, "
                 "pack TEXT, created TEXT, sus_score REAL, payload TEXT)")
    return conn


@app.post("/api/study")
async def study_save(body: StudyIn):
    try:
        score = sus_score(body.sus)
    except ValueError:
        raise HTTPException(400, "sus needs exactly ten answers")
    rid = uuid.uuid4().hex[:12]
    created = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    payload = body.model_dump()
    conn = _study_conn()
    with conn:
        conn.execute("INSERT INTO responses VALUES (?,?,?,?,?,?)",
                     (rid, body.participant[:40], body.pack, created, score,
                      json.dumps(payload, ensure_ascii=False)))
    conn.close()
    return {"ok": True, "id": rid, "sus_score": score,
            "tasks_done": sum(1 for t in body.tasks if t.success)}


def _study_rows() -> list[dict[str, Any]]:
    if not os.path.exists(STUDY_DB):
        return []
    conn = _study_conn()
    rows = [{"id": r[0], "participant": r[1], "pack": r[2], "created": r[3], "sus_score": r[4],
             **json.loads(r[5])} for r in conn.execute(
                 "SELECT id, participant, pack, created, sus_score, payload FROM responses ORDER BY created")]
    conn.close()
    return rows


@app.get("/api/study/responses")
async def study_responses():
    return {"count": len(_study_rows()), "rows": _study_rows()}


@app.get("/api/study/export")
async def study_export():
    """One CSV row per participant and task, SUS items alongside, which is
    what research/harness/study_analysis.py reads."""
    rows = _study_rows()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["response_id", "participant", "pack", "created", "task", "expected", "success",
                "seconds", "sus_score"] + [f"sus{i + 1}" for i in range(SUS_ITEMS)] + ["wrong", "good", "duration_s"])
    for r in rows:
        for t in r.get("tasks", []):
            w.writerow([r["id"], r["participant"], r["pack"], r["created"], t.get("id"), t.get("expected"),
                        int(bool(t.get("success"))), t.get("seconds") if t.get("seconds") is not None else "",
                        r["sus_score"]] + list(r.get("sus", [])) + [r.get("wrong", ""), r.get("good", ""), r.get("duration_s")])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="haanji-study.csv"'})


# ───────────────────────────────────────── trust: anchors, digest, scheduler
def _public_key_hex(rt: TenantRuntime) -> str:
    from cryptography.hazmat.primitives import serialization
    key_id = rt.ledger.ensure_key(rt.pack_id)
    return rt.ledger.public_key(key_id).public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def seal_pending_days(rt: TenantRuntime) -> list[str]:
    """Anchor every day that has receipts and no anchor yet, plus today again
    if it gained receipts since it was last sealed (INSERT OR REPLACE)."""
    have = {a["day"]: a for a in rt.ledger.anchors(rt.pack_id)}
    sealed: list[str] = []
    today = dt.datetime.now(IST).date().isoformat()
    for day in rt.ledger.days_with_receipts(rt.pack_id):
        if day not in have or day == today:
            rt.ledger.anchor_day(rt.pack_id, day)
            sealed.append(day)
    return sealed


@app.get("/api/anchors")
async def anchors(pack: str = DEFAULT_PACK):
    """The tenant's daily Merkle roots and their signatures: everything a
    third party needs to check that a day's receipts were not rewritten
    after the fact. Published daily to the repository's transparency branch."""
    rt = runtime(pack)
    return {"tenant_id": pack, "algorithm": "Ed25519 over sha256(merkle_root) || day",
            "public_key": _public_key_hex(rt), "anchors": rt.ledger.anchors(pack),
            "pending_days": [d for d in rt.ledger.days_with_receipts(pack)
                             if d not in {a["day"] for a in rt.ledger.anchors(pack)}]}


@app.post("/api/anchors/seal")
async def anchors_seal(pack: str = DEFAULT_PACK):
    rt = runtime(pack)
    return {"sealed": seal_pending_days(rt), "anchors": rt.ledger.anchors(pack)}


def digest_text(pack_id: str) -> str:
    """The owner's evening message: what the desk did today, in six lines."""
    rt = runtime(pack_id)
    ins = compute_insights(pack_id, store, rt.backend)
    name = rt.pack.persona.business_name
    today = dt.datetime.now(IST).strftime("%d %b")
    booked = ins["outcomes"].get("BOOKED", 0)
    lines = [f"HaanJi · {name} · {today}",
             f"Aaj {ins['calls_today']} calls uthayi (kul {ins['calls_total']}).",
             f"{ins['bookings_confirmed']} bookings calendar pe, lagbhag ₹{ins['revenue_booked_inr']:,} ki.",
             f"{booked} calls booking bani; {ins['leads_open']} log callback chahte hain."]
    m = ins["missed_calls"]
    if m.get("total"):
        lines.append(f"{m['recovered']} of {m['total']} missed calls WhatsApp pe wapas aayi.")
    if ins["by_hour"]:
        busiest = max(ins["by_hour"], key=lambda h: h["calls"])
        lines.append(f"Sabse busy ghanta: {busiest['hour']}:00 ({busiest['calls']} calls).")
    lines.append(f"Receipts aur poora hisaab: {PUBLIC_URL}/verify?pack={pack_id}")
    return "\n".join(lines)


@app.get("/api/digest")
async def digest(pack: str = DEFAULT_PACK):
    if pack not in list_packs():
        raise HTTPException(404, f"unknown pack {pack}")
    return {"pack": pack, "text": digest_text(pack), "to": OWNER_PHONE,
            "whatsapp_configured": wa_channel.configured(), "hour_ist": DIGEST_HOUR}


@app.post("/api/digest/send")
async def digest_send(pack: str = DEFAULT_PACK, to: str | None = None):
    if pack not in list_packs():
        raise HTTPException(404, f"unknown pack {pack}")
    number = to or OWNER_PHONE
    text = digest_text(pack)
    if not number:
        raise HTTPException(409, "no owner number: set HAANJI_OWNER_PHONE or pass ?to=")
    if not wa_channel.configured():
        raise HTTPException(409, "WhatsApp is not connected; the text is in the preview")
    await wa_channel.send_text(number, text)
    return {"sent": True, "to": number, "text": text}


async def send_due_reminders(now: dt.datetime | None = None) -> int:
    """Every pack's day-before (or same-day) reminders that are due now."""
    sent = 0
    for pid in list_packs():
        rt = runtime(pid)
        cfg = settings.get(pid)
        for b in rem_mod.due_today(rt.backend, pid, cfg, now):
            text = rem_mod.reminder_text(b, rt.pack.persona.business_name, rt.backend.today,
                                         rt.backend.resolve_date, rt.pack.language, PUBLIC_URL)
            delivered = None
            if wa_channel.configured():
                delivered = await wa_channel.send_template(b.phone, "reminder", [b.service, f"{b.date} {b.time}"],
                                                          fallback_text=text)
            rt.backend.mark_reminded(pid, b.booking_id)
            store.add_wa(pid, b.phone, "out", text, meta={"reminder": b.booking_id, "delivered": delivered})
            publish("reminder.sent", pack=pid, booking_id=b.booking_id, phone=_mask(b.phone), delivered=delivered)
            TELEMETRY.inc("reminders_sent_total", pack=pid)
            sent += 1
    return sent


async def _reminder_loop() -> None:
    while True:
        try:
            await send_due_reminders()
        except Exception as exc:                      # noqa: BLE001 - keep the loop alive
            log.warning("reminders: %s", exc)
        await asyncio.sleep(15 * 60)


async def _reminder_reply(pack_id: str, phone: str, text: str, holder: Holder) -> dict[str, Any] | None:
    """A WhatsApp message that answers a reminder (or a waitlist offer is
    handled by the primed session, not here). '1'/'haan' confirms; '2'/
    'cancel' cancels through the ledger with the reminder as the question
    and this message as the proof. None when the message is not a reply."""
    pending = store.last_outbound_with(pack_id, phone, "reminder")
    if pending is None or pending["meta"].get("answered"):
        return None
    verdict = rem_mod.interpret_reply(text)
    if verdict is None:
        return None
    rt = holder.rt
    booking = rt.backend.booking(pack_id, pending["meta"]["reminder"])
    store.set_meta(pending["msg_id"], answered=verdict)
    if booking is None or booking.status != "CONFIRMED":
        return {"text": "Ye booking ab calendar par nahi hai. Nayi booking chahiye to likh dijiye."}
    if verdict == "confirm":
        publish("reminder.confirmed", pack=pack_id, booking_id=booking.booking_id, phone=_mask(phone))
        return {"text": f"Shukriya! {rt.pack.persona.business_name} aapka intezaar karega. Milte hain."}
    asked_ms = int(dt.datetime.fromisoformat(pending["at"]).timestamp() * 1000)
    proof = rem_mod.proof_for(pending["text"], text, asked_ms, int(time.time() * 1000))
    result = await rt.registry.execute("cancel_appointment", {
        "phone": phone, "identity": "channel", "proof": proof,
        "excerpt": f"reminder reply: {text}", "conversation_id": f"reminder:{booking.booking_id}"})
    if not result.ok:
        return {"text": result.spoken or "Cancel nahi ho paya, team aapko call karegi."}
    publish("reminder.cancelled", pack=pack_id, booking_id=booking.booking_id, phone=_mask(phone),
            receipt=(result.data or {}).get("receipt_code"))
    asyncio.ensure_future(offer_waitlist(rt, booking.date, booking.service))
    return {"text": f"{result.spoken} Dobara booking chahiye to kabhi bhi likh dijiye.",
            "receipts": [c for c in [(result.data or {}).get("receipt_code")] if c]}


def seconds_until(hour: int, minute: int = 0, now: dt.datetime | None = None) -> float:
    """Seconds from ``now`` (IST) to the next occurrence of hour:minute IST."""
    now = now or dt.datetime.now(IST)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return (target - now).total_seconds()


async def _evening_loop() -> None:
    """Every evening: seal every pack's day in the ledger, then message the
    owner. Both are idempotent, so a restart never doubles anything."""
    while True:
        await asyncio.sleep(seconds_until(DIGEST_HOUR))
        for pid in list_packs():
            try:
                seal_pending_days(runtime(pid))
            except Exception as exc:                  # noqa: BLE001 - keep the loop alive
                log.warning(f"anchor {pid}: {exc}")
        try:
            purge_old_records(RETENTION_DAYS)
        except Exception as exc:                      # noqa: BLE001
            log.warning(f"retention: {exc}")
        if backup_mod.s3_configured():
            try:
                where = backup_mod.upload_s3(backup_mod.make_backup(VAR_DIR), backup_mod.backup_name())
                log.warning("nightly backup written to %s", where)
            except Exception as exc:                  # noqa: BLE001
                log.warning(f"backup: {exc}")
        digest_pack = os.environ.get("HAANJI_WA_PACK") or DEFAULT_PACK
        if OWNER_PHONE and wa_channel.configured():
            try:
                await wa_channel.send_text(OWNER_PHONE, digest_text(digest_pack))
            except Exception as exc:                  # noqa: BLE001
                log.warning(f"digest: {exc}")


# ─────────────────────────────────────────────────────── auth endpoints
class OtpIn(BaseModel):
    phone: str


class VerifyIn(BaseModel):
    phone: str
    code: str


class UserIn(BaseModel):
    phone: str
    role: str = "staff"
    packs: list[str] = ["*"]
    name: str = ""


@app.post("/api/auth/otp")
async def auth_otp(body: OtpIn):
    if not AUTH_ENABLED:
        raise HTTPException(409, "auth is off (HAANJI_AUTH=on to enable)")
    phone = normalise_phone(body.phone)
    if len(phone) < 10 or auth.user(phone) is None:
        # Same answer for unknown numbers: no account enumeration.
        return {"sent": True, "channel": "whatsapp" if wa_channel.configured() else "dev"}
    try:
        code = auth.issue_otp(phone)
    except OtpThrottled as exc:
        raise HTTPException(429, str(exc), headers={"Retry-After": "900"})
    if wa_channel.configured():
        ok = await wa_channel.send_template(
            phone, "otp", [code],
            fallback_text=f"HaanJi console login code: {code}\nYeh code 5 minute tak chalega. Kisi ko mat batayein.")
        if ok is False:                       # None = an adapter that does not report delivery
            raise HTTPException(503, "could not deliver the code on WhatsApp; try again in a minute")
        return {"sent": True, "channel": "whatsapp"}
    if AUTH_DEV:
        return {"sent": True, "channel": "dev", "dev_code": code}
    raise HTTPException(503, "no way to deliver the code: connect WhatsApp or set HAANJI_AUTH_DEV=1")


@app.post("/api/auth/verify")
async def auth_verify(body: VerifyIn):
    if not AUTH_ENABLED:
        raise HTTPException(409, "auth is off")
    phone = normalise_phone(body.phone)
    user = auth.user(phone)
    if user is None or not auth.check_otp(phone, body.code):
        raise HTTPException(401, "wrong or expired code")
    return {"token": auth.token_for(user), "user": user.as_dict()}


@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    """Sign out everywhere: every token this number holds stops working."""
    if not AUTH_ENABLED:
        return {"ok": True}
    who = principal_of(request)
    if who is not None:
        auth.revoke(who.phone)
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(request: Request):
    if not AUTH_ENABLED:
        return {"enabled": False, "user": None}
    who = principal_of(request)
    if who is None:
        raise HTTPException(401, "sign in first")
    return {"enabled": True, "user": who.as_dict()}


@app.get("/api/auth/users")
async def auth_users():
    return {"users": [u.as_dict() for u in auth.users()]}


@app.post("/api/auth/users")
async def auth_users_add(body: UserIn):
    try:
        return {"user": auth.upsert_user(body.phone, body.role, body.packs, body.name).as_dict()}
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.delete("/api/auth/users/{phone}")
async def auth_users_remove(phone: str, request: Request):
    me: Principal | None = getattr(request.state, "user", None)
    if me and normalise_phone(phone) == me.phone:
        raise HTTPException(409, "you cannot remove yourself")
    return {"removed": auth.remove_user(phone)}


# ───────────────────────────────────────────────────────── calendar
PROTECTED.append(("GET", re.compile(r"^/api/calendar/feed-url$"), "owner"))
PROTECTED.append(("GET|POST|DELETE", re.compile(r"^/api/google/(connect|disconnect|status)$"), "owner"))


@app.get("/api/calendar/feed-url")
async def calendar_feed_url(pack: str = DEFAULT_PACK):
    if pack not in list_packs():
        raise HTTPException(404, f"unknown pack {pack}")
    token = cal_mod.feed_token(auth.secret, pack)
    return {"pack": pack, "url": f"{PUBLIC_URL}/api/calendar/{pack}.ics?token={token}",
            "webcal": f"{PUBLIC_URL.replace('https://', 'webcal://').replace('http://', 'webcal://')}/api/calendar/{pack}.ics?token={token}"}


@app.get("/api/calendar/{pack}.ics")
async def calendar_feed(pack: str, token: str = ""):
    """The tenant's bookings as an iCalendar feed. Subscribe once in any
    calendar app; the URL carries its own secret because calendar apps
    cannot send headers."""
    if pack not in list_packs():
        raise HTTPException(404, f"unknown pack {pack}")
    if not hmac.compare_digest(token, cal_mod.feed_token(auth.secret, pack)):
        raise HTTPException(403, "bad feed token")
    rt = runtime(pack)
    body = cal_mod.feed(rt.backend.bookings(pack), rt.pack.persona.business_name, pack, PUBLIC_URL)
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'inline; filename="{pack}.ics"', "Cache-Control": "no-cache"})


@app.get("/api/bookings/{pack}/{booking_id}.ics")
async def booking_ics(pack: str, booking_id: str):
    """One booking as a calendar file, for the customer's own phone."""
    rt = runtime(pack)
    b = next((x for x in rt.backend.bookings(pack) if x.booking_id == booking_id), None)
    if b is None:
        raise HTTPException(404, "no such booking")
    body = cal_mod.feed([b], rt.pack.persona.business_name, pack, PUBLIC_URL)
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="booking-{booking_id}.ics"'})


@app.get("/api/google/status")
async def google_status(pack: str = DEFAULT_PACK):
    link = gcal.link(pack)
    return {"configured": gcal.configured, "connected": link is not None,
            "connected_at": link["connected_at"] if link else None, "redirect_uri": gcal.redirect_uri}


@app.get("/api/google/connect")
async def google_connect(pack: str = DEFAULT_PACK):
    if not gcal.configured:
        raise HTTPException(409, "set HAANJI_GOOGLE_CLIENT_ID and HAANJI_GOOGLE_CLIENT_SECRET first")
    if pack not in list_packs():
        raise HTTPException(404, f"unknown pack {pack}")
    return {"url": gcal.connect_url(pack)}


@app.get("/api/google/callback")
async def google_callback(code: str = "", state: str = "", error: str = ""):
    """Google sends the owner back here; the state ties the code to a pack."""
    if error:
        return PlainTextResponse(f"Google said: {error}", status_code=400)
    pack = gcal.tenant_for_state(state)
    if pack is None:
        return PlainTextResponse("This link has expired. Start again from the console.", status_code=400)
    try:
        await gcal.finish(pack, code)
    except Exception as exc:                          # noqa: BLE001
        return PlainTextResponse(f"Could not connect: {exc}", status_code=502)
    console = os.environ.get("HAANJI_CONSOLE_URL") or "/"
    return PlainTextResponse(f"Google Calendar connected for {pack}. You can close this tab and go back to the console: {console}")


@app.delete("/api/google/disconnect")
async def google_disconnect(pack: str = DEFAULT_PACK):
    return {"disconnected": gcal.disconnect(pack)}


# ──────────────────────────────────────────────────────────── telephony
def phone_configured() -> bool:
    return bool(os.environ.get("HAANJI_DEEPGRAM_KEY") and os.environ.get("HAANJI_ELEVENLABS_KEY")
                and os.environ.get("HAANJI_ELEVENLABS_VOICE"))


def phone_status() -> dict[str, Any]:
    return {"configured": phone_configured(), "number": os.environ.get("HAANJI_PHONE_DISPLAY") or None,
            "stream_url": twilio_mod.stream_url(PUBLIC_URL)}


@app.post("/telephony/twilio/voice")
async def twilio_voice(request: Request, pack: str = DEFAULT_PACK):
    """Twilio asks what to do with the ringing call: stream it to us."""
    import urllib.parse
    raw = (await request.body()).decode("utf-8", "replace")
    form = {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}
    token = os.environ.get("HAANJI_TWILIO_AUTH_TOKEN")
    if not token and IS_PUBLIC and phone_configured():
        raise HTTPException(403, "HAANJI_TWILIO_AUTH_TOKEN is not set; refusing unsigned calls")
    # Twilio signed the public https URL; behind the platform's proxy the
    # request we see may say http://, so rebuild the URL from PUBLIC_URL.
    signed_url = (f"{PUBLIC_URL}{request.url.path}" + (f"?{request.url.query}" if request.url.query else "")
                  if IS_PUBLIC else str(request.url))
    if token and not twilio_mod.verify_signature(token, signed_url, {k: str(v) for k, v in form.items()},
                                                 request.headers.get("X-Twilio-Signature")):
        raise HTTPException(403, "bad Twilio signature")
    if pack not in list_packs():
        pack = DEFAULT_PACK
    if not phone_configured():
        rt = runtime(pack)
        return Response(twilio_mod.twiml_say(f"{rt.pack.persona.business_name}. The voice bridge is not configured yet."),
                        media_type="application/xml")
    caller = str(form.get("From", "")) or None
    ticket = None
    if token:
        # The media WebSocket carries no signature of its own: this ticket,
        # minted here and checked once when the stream starts, is what ties
        # the socket to a call Twilio really placed.
        now = time.monotonic()
        for t in [t for t, (_p, _c, exp) in _phone_tickets.items() if exp < now]:
            _phone_tickets.pop(t, None)
        ticket = secrets.token_urlsafe(18)
        _phone_tickets[ticket] = (pack, caller, now + 120)
    return Response(twilio_mod.twiml_connect(twilio_mod.stream_url(PUBLIC_URL), pack, caller, ticket), media_type="application/xml")


_phone_tickets: dict[str, tuple[str, str | None, float]] = {}


def _phone_stt_factory(on_text):
    from .telephony.deepgram import DeepgramStream
    return DeepgramStream(on_text=on_text)


def _phone_tts(text: str):
    from .telephony.elevenlabs import synth_ulaw
    return synth_ulaw(text)


async def _phone_open(pack: str, caller: str | None, params: dict[str, Any] | None = None):
    if os.environ.get("HAANJI_TWILIO_AUTH_TOKEN"):
        entry = _phone_tickets.pop(str((params or {}).get("ticket") or ""), None)
        if entry is None or entry[2] < time.monotonic() or entry[0] != pack:
            TELEMETRY.inc("telephony_rejected_total")
            log.warning("telephony stream without a valid ticket was refused")
            return None
    phone = "".join(ch for ch in (caller or "") if ch.isdigit())[-10:] or None
    return await _new_session(pack, "PHONE", phone, verified=phone is not None)   # network caller-id


def _phone_human(sid: str, holder: Holder, text: str) -> bool:
    """Telephony bridge asks: is a person holding this call? If so, log the
    caller's words for the console and do not run the policy."""
    if holder.human:
        _human_turn(sid, holder, text)
        return True
    return False


async def _phone_turn(record, holder: Holder) -> None:
    payload = _turn_payload(record, holder)
    await _after_turn(holder, record, payload)


PHONE_FACTORIES: dict[str, Any] = {"stt": _phone_stt_factory, "tts": _phone_tts}   # tests swap these


@app.websocket("/telephony/twilio/stream")
async def twilio_stream(ws: WebSocket):
    await ws.accept()
    bridge = twilio_mod.TwilioBridge(ws, open_session=_phone_open, close_session=_finish,
                                     stt_factory=PHONE_FACTORIES["stt"], tts=PHONE_FACTORIES["tts"],
                                     on_turn=_phone_turn, human_hook=_phone_human,
                                     on_partial=lambda text, holder: publish("partial", sid=holder_sid(holder),
                                                                             pack=holder.rt.pack_id, text=text))
    await bridge.run()


# ───────────────────────────────────────────────────── human takeover
PROTECTED.append(("GET|POST", re.compile(r"^/api/sessions/(live|[^/]+/(takeover|handback|human-reply))$"), "staff"))


def _human_turn(sid: str, holder: Holder, text: str) -> dict[str, Any]:
    """The caller spoke while a person holds the call: log it, tell the
    console, say nothing. The policy does not run."""
    session = holder.session
    seq = len(session.ctx.turns) + 1
    session.ctx.add(Turn(seq, Speaker.CALLER, text))
    publish("turn", sid=sid, pack=holder.rt.pack_id, channel=holder.channel, heard=text, corrected=text,
            reply="", corrections=[], tools=[], speculation_hits=[], receipts=[], guard="", latency_ms=0.0,
            spans=[], outcome=_provisional_outcome(session), human=True, awaiting_human=True)
    return {"reply": "", "heard": text, "corrected": text, "corrections": [], "tools": [], "speculation_hits": [],
            "guard": "", "latency_ms": 0.0, "receipts": [], "end_call": False, "outcome": None, "spans": [],
            "human": True}


async def _human_reply(sid: str, holder: Holder, text: str) -> dict[str, Any]:
    session = holder.session
    seq = len(session.ctx.turns) + 1
    session.ctx.add(Turn(seq, Speaker.AGENT, text))
    session.ctx.last_agent_utterance = text
    session.ctx.last_agent_started_ms = int(time.time() * 1000)
    session.turns.append(TurnRecord(seq, "", "", text))          # recorded with the call, as a human turn
    session.turns[-1].guard = "human"
    if holder.channel == "WHATSAPP" and holder.phone:
        store.add_wa(holder.rt.pack_id, holder.phone, "out", text, meta={"human": True})
        if wa_channel.configured():
            try:
                await wa_channel.send_text(holder.phone, text)
            except Exception as exc:                      # noqa: BLE001
                log.warning(f"human reply over WhatsApp failed: {exc}")
    if holder.speak is not None:
        await holder.speak(text)                           # telephony: synthesise on the line
    publish("turn", sid=sid, pack=holder.rt.pack_id, channel=holder.channel, heard="", corrected="",
            reply=text, corrections=[], tools=[], speculation_hits=[], receipts=[], guard="human",
            latency_ms=0.0, spans=[], outcome=_provisional_outcome(session), human=True)
    return {"ok": True, "reply": text}


class HumanReply(BaseModel):
    text: str = Field(max_length=2000)


@app.get("/api/sessions/live")
async def sessions_live(request: Request, pack: str | None = None):
    allowed = _allowed_packs(request)
    if pack and allowed is not None and pack not in allowed:
        raise HTTPException(403, "not your pack")
    out = []
    for sid, h in _sessions.items():
        if pack and h.rt.pack_id != pack:
            continue
        if allowed is not None and h.rt.pack_id not in allowed:
            continue
        last_caller = next((t.text for t in reversed(h.session.ctx.turns) if t.speaker is Speaker.CALLER), "")
        out.append({"sid": sid, "pack": h.rt.pack_id, "channel": h.channel, "phone": _mask(h.phone),
                    "human": h.human, "turns": len(h.session.ctx.turns), "last_caller": last_caller,
                    "idle_s": round(time.monotonic() - h.last_used, 1)})
    return {"sessions": out}


@app.post("/api/sessions/{sid}/takeover")
async def session_takeover(sid: str, request: Request):
    holder = _sessions.get(sid)
    if holder is None:
        raise HTTPException(404, "no such session")
    holder.human = True
    who = getattr(request.state, "user", None)
    publish("session.takeover", sid=sid, pack=holder.rt.pack_id, channel=holder.channel,
            by=(who.name or who.phone) if who else "console")
    return {"ok": True, "human": True}


@app.post("/api/sessions/{sid}/handback")
async def session_handback(sid: str):
    holder = _sessions.get(sid)
    if holder is None:
        raise HTTPException(404, "no such session")
    holder.human = False
    publish("session.handback", sid=sid, pack=holder.rt.pack_id, channel=holder.channel)
    return {"ok": True, "human": False}


@app.post("/api/sessions/{sid}/human-reply")
async def session_human_reply(sid: str, body: HumanReply):
    holder = _sessions.get(sid)
    if holder is None:
        raise HTTPException(404, "no such session")
    if not holder.human:
        raise HTTPException(409, "take the call over first")
    holder.last_used = time.monotonic()
    return await _human_reply(sid, holder, body.text.strip())


# ─────────────────────────────────────────────────────────── web push
PROTECTED.append(("POST|DELETE", re.compile(r"^/api/push/(subscribe|unsubscribe|test)$"), "staff"))


class PushSubIn(BaseModel):
    pack: str = DEFAULT_PACK
    subscription: dict[str, Any]
    label: str = ""


@app.get("/api/push/vapid-public-key")
async def push_key():
    return {"public_key": push.public_key}


@app.post("/api/push/subscribe")
async def push_subscribe(body: PushSubIn):
    if body.pack not in list_packs():
        raise HTTPException(404, f"unknown pack {body.pack}")
    try:
        n = push.subscribe(body.pack, body.subscription, body.label)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"ok": True, "subscribers": n}


@app.delete("/api/push/unsubscribe")
async def push_unsubscribe(endpoint: str):
    return {"removed": push.unsubscribe(endpoint)}


@app.post("/api/push/test")
async def push_test(pack: str = DEFAULT_PACK):
    return push.send(pack, f"HaanJi — {runtime(pack).pack.persona.business_name}", "Notifications chal rahi hain.",
                     (os.environ.get("HAANJI_CONSOLE_URL") or "/"))


# ──────────────────────────────────────────────────────────── privacy
PROTECTED.append(("GET|DELETE", re.compile(r"^/api/privacy/customer/.*$"), "owner"))


def _customer_phone(phone: str) -> str:
    """The ten digits of a customer's number, or a 400. An empty or partial
    number used to reach a LIKE '%...' and match everyone in the tenant."""
    p = _norm_phone(phone)
    if len(p) != 10:
        raise HTTPException(400, "phone must be a ten-digit number")
    return p


def _phone_forms(p: str) -> tuple[str, ...]:
    """How the same number may have been stored: bare, 0-prefixed, +91/91-prefixed."""
    return (p, "0" + p, "91" + p, "+91" + p)


def customer_record(pack: str, phone: str) -> dict[str, Any]:
    """Everything the platform holds about one number (right of access)."""
    rt = runtime(pack)
    p = _customer_phone(phone)
    forms = _phone_forms(p)
    marks = ",".join("?" * len(forms))
    bookings = [b.as_dict() for b in rt.backend.bookings(pack) if _norm_phone(b.phone) == p]
    leads = [dict(r) for r in rt.backend.conn.execute(f"SELECT * FROM leads WHERE tenant_id=? AND phone IN ({marks})", (pack, *forms))]
    calls = [{"call_id": c["call_id"], "started_at": c["started_at"], "outcome": c["outcome"]}
             for c in store.calls(pack, limit=1000) if _norm_phone(c.get("phone")) == p]
    wa = store.conn.execute(f"SELECT COUNT(*) c FROM wa_messages WHERE tenant_id=? AND phone IN ({marks})", (pack, *forms)).fetchone()["c"]
    subjects = {vault.subject(p, pack), vault.subject(p)}        # per-tenant, and the older unscoped form
    shredded = vault.is_shredded(p, pack) or vault.is_shredded(p)
    receipts = []
    for r in rt.ledger.receipts(pack):
        if r.action_args.get("subject") in subjects:
            receipts.append({"code": r.short_code(), "action": r.action, "occurred_at": r.occurred_at,
                             "pii_readable": not shredded})
    return {"pack": pack, "phone": p, "bookings": bookings, "leads": leads, "calls": calls, "whatsapp_messages": wa,
            "receipts": receipts, "erased": shredded}


def erase_customer(pack: str, phone: str) -> dict[str, int | bool]:
    """Right to erasure: shred the receipt key, anonymise bookings, delete the
    rest. Receipts stay sealed and verifiable; their personal fields become
    unreadable. Scoped to this tenant: the same person at another shop keeps
    their records there."""
    rt = runtime(pack)
    p = _customer_phone(phone)
    forms = _phone_forms(p)
    marks = ",".join("?" * len(forms))
    shredded = vault.forget(p, pack)
    with rt.backend.conn:
        b = rt.backend.conn.execute(f"UPDATE bookings SET customer_name='erased', phone=NULL WHERE tenant_id=? AND phone IN ({marks})", (pack, *forms)).rowcount
        l = rt.backend.conn.execute(f"DELETE FROM leads WHERE tenant_id=? AND phone IN ({marks})", (pack, *forms)).rowcount
        rt.backend.conn.execute(f"DELETE FROM customers WHERE tenant_id=? AND phone IN ({marks})", (pack, *forms))
    with store.conn:
        c = store.conn.execute(f"DELETE FROM calls WHERE tenant_id=? AND phone IN ({marks})", (pack, *forms)).rowcount
        w = store.conn.execute(f"DELETE FROM wa_messages WHERE tenant_id=? AND phone IN ({marks})", (pack, *forms)).rowcount
        m = store.conn.execute(f"DELETE FROM missed_calls WHERE tenant_id=? AND phone IN ({marks})", (pack, *forms)).rowcount
    _wa_sessions.pop((pack, p), None)
    publish("privacy.erased", pack=pack, phone=_mask(p))
    return {"key_shredded": shredded, "bookings_anonymised": b, "leads_deleted": l, "calls_deleted": c,
            "whatsapp_messages_deleted": w, "missed_calls_deleted": m}


def purge_old_records(days: int, now: dt.datetime | None = None) -> dict[str, int]:
    """Storage limitation: call records and messages older than ``days`` go;
    bookings and receipts (the business's records) stay."""
    if days <= 0:
        return {"calls": 0, "whatsapp_messages": 0, "missed_calls": 0}
    cutoff = ((now or dt.datetime.now(dt.timezone.utc)) - dt.timedelta(days=days)).isoformat(timespec="seconds")
    with store.conn:
        c = store.conn.execute("DELETE FROM calls WHERE started_at < ?", (cutoff,)).rowcount
        w = store.conn.execute("DELETE FROM wa_messages WHERE at < ?", (cutoff,)).rowcount
        m = store.conn.execute("DELETE FROM missed_calls WHERE at < ?", (cutoff,)).rowcount
    return {"calls": c, "whatsapp_messages": w, "missed_calls": m}


@app.get("/api/privacy/policy")
async def privacy_policy():
    return {"retention_days": RETENTION_DAYS, "consent_line": CONSENT_LINE or None, "vault": vault.count(),
            "pii_in_receipts": "encrypted per customer; erasure shreds the key",
            "logs": "phone numbers masked to the last four digits in the live feed"}


@app.get("/api/privacy/customer/{phone}")
async def privacy_customer(phone: str, pack: str = DEFAULT_PACK):
    if pack not in list_packs():
        raise HTTPException(404, f"unknown pack {pack}")
    return customer_record(pack, phone)


@app.delete("/api/privacy/customer/{phone}")
async def privacy_erase(phone: str, pack: str = DEFAULT_PACK):
    if pack not in list_packs():
        raise HTTPException(404, f"unknown pack {pack}")
    return erase_customer(pack, phone)


@app.get("/api/receipts/{code}/open")
async def receipt_open(code: str, pack: str = DEFAULT_PACK):
    """The personal fields of one receipt, for whoever holds its code (the
    customer's link). Null once the customer has been forgotten."""
    rt = runtime(pack)
    r = rt.ledger.by_code(pack, code.replace("-", "")) or rt.ledger.by_code(pack, code)
    if r is None:
        raise HTTPException(404, "no such receipt")
    opened = vault.open_args(r.action_args)
    return {"code": r.short_code(), "action": r.action, "occurred_at": r.occurred_at,
            "fields": {k: opened.get(k) for k in ("service", "date", "time", "staff", "customer_name", "phone", "name", "reason")},
            "erased": opened.get("pii") == "erased" or (bool(r.action_args.get("subject")) and all(
                opened.get(f) is None for f in ("customer_name", "phone", "name") if f"{f}_enc" in r.action_args))}


# ───────────────────────────────────────────────────── observability
SLO_TURN_MS = int(os.environ.get("HAANJI_MAX_TURN_LATENCY_MS", "1500"))


@app.get("/metrics")
async def metrics(request: Request):
    """Prometheus scrape target; ops/prometheus.yml points here. With
    HAANJI_METRICS_TOKEN set the scraper sends it as a bearer token; with
    sign-in on and no token, a staff token is needed."""
    want = os.environ.get("HAANJI_METRICS_TOKEN")
    header = request.headers.get("authorization", "")
    bearer = header[7:] if header.lower().startswith("bearer ") else ""
    if want:
        if not hmac.compare_digest(bearer, want):
            raise HTTPException(401, "metrics token needed")
    elif AUTH_ENABLED and principal_of(request) is None:
        raise HTTPException(401, "sign in first")
    TELEMETRY.gauge("live_sessions", len(_sessions))
    return PlainTextResponse(TELEMETRY.render(), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/api/ops")
async def ops(pack: str = DEFAULT_PACK, calls: int = 200):
    """The service-level view the console's Ops page draws: the latency
    objective against what callers actually got, where the time went, and
    the counters a pager would watch."""
    rows = store.calls(pack, limit=calls)
    turns = [t for r in rows for t in json.loads(r["turns_json"] or "[]")]
    lat = [float(t["latency_ms"]) for t in turns if t.get("latency_ms")]
    tool_turns = [t for t in turns if t.get("tools")]
    spans: dict[str, list[float]] = {}
    for t in turns:
        for sp in t.get("spans", []) or []:
            spans.setdefault(sp["name"], []).append(float(sp["ms"]))
    edges = [50, 100, 200, 400, 800, 1500, 3000]
    hist = []
    lo = 0
    for e in edges:
        hist.append({"bucket": f"≤{e}", "turns": sum(1 for v in lat if lo < v <= e)})
        lo = e
    hist.append({"bucket": f">{edges[-1]}", "turns": sum(1 for v in lat if v > edges[-1])})
    latest = rows[0] if rows else None
    return {
        "pack": pack, "calls": len(rows), "turns": len(lat),
        "slo": {"target_ms": SLO_TURN_MS,
                "p50": round(percentile(lat, 0.5), 1), "p90": round(percentile(lat, 0.9), 1),
                "p95": round(percentile(lat, 0.95), 1), "max": round(max(lat), 1) if lat else 0.0,
                "within": round(sum(1 for v in lat if v <= SLO_TURN_MS) / len(lat), 4) if lat else 1.0,
                "tool_turn_p90": round(percentile([float(t["latency_ms"]) for t in tool_turns if t.get("latency_ms")], 0.9), 1)},
        "histogram": hist,
        "spans": [{"name": k, "n": len(v), "p50": round(percentile(v, 0.5), 1), "p90": round(percentile(v, 0.9), 1)}
                  for k, v in sorted(spans.items(), key=lambda kv: -sum(kv[1]))],
        "speculation": {"started": int(TELEMETRY.counter("speculation_started_total", pack=pack)),
                        "hits": int(TELEMETRY.counter("speculation_hits_total", pack=pack)),
                        "wasted": int(TELEMETRY.counter("speculation_wasted_total", pack=pack))},
        "counters": {"rate_limited": int(TELEMETRY.total("http_rate_limited_total")),
                     "auth_denied": int(TELEMETRY.total("auth_denied_total")),
                     "unconfirmed_refused": int(TELEMETRY.total("ledger_unconfirmed_refused_total")),
                     "adapter_fallbacks": int(TELEMETRY.total("adapter_fallbacks_total")),
                     "events": int(TELEMETRY.total("events_published_total"))},
        "live_sessions": len(_sessions),
        "uptime_s": round(time.time() - TELEMETRY.started),
        "providers": {"stt": os.environ.get("HAANJI_PROVIDER_STT", "mock"), "llm": os.environ.get("HAANJI_PROVIDER_LLM", "mock"),
                      "tts": os.environ.get("HAANJI_PROVIDER_TTS", "mock")},
        "latest_call": {"call_id": latest["call_id"], "started_at": latest["started_at"], "outcome": latest["outcome"],
                        "turns": json.loads(latest["turns_json"] or "[]")} if latest else None,
    }


class TextsIn(BaseModel):
    texts: list[str]


@app.post("/api/devanagari")
async def devanagari(body: TextsIn):
    """Approximate Devanagari for Hinglish lines, for the owner who reads
    Hindi faster than Roman letters."""
    if len(body.texts) > 500:
        raise HTTPException(413, "at most 500 lines per request")
    return {"texts": [transliterate(t) for t in body.texts], "approximate": True}


@app.get("/api/status")
async def status():
    return {"name": "HaanJi demo server", "version": app.version,
            "default_pack": DEFAULT_PACK, "packs": list_packs(),
            "public_url": PUBLIC_URL,
            "digest": {"owner_configured": bool(OWNER_PHONE), "hour_ist": DIGEST_HOUR},
            "auth": {"enabled": AUTH_ENABLED},
            "demo_readonly": DEMO_READONLY,
            "google": {"configured": gcal.configured, "connected": gcal.connected()},
            "phone": phone_status(),
            "privacy": {"retention_days": RETENTION_DAYS, "consent": bool(CONSENT_LINE)},
            "push": {"public_key": push.public_key},
            "payments": {"provider": "razorpay" if payments_configured_fn() else "mock"},
            "backup": {"s3": backup_mod.s3_configured(), "restore_from": bool(os.environ.get("HAANJI_RESTORE_FROM"))},
            # Where the owner console lives, so the pages can link to it
            # without hard-coding a host.
            "console_url": os.environ.get("HAANJI_CONSOLE_URL", "http://localhost:5173"),
            "whatsapp": wa_channel.status()}


def _page(name: str) -> FileResponse:
    return FileResponse(os.path.join(WEB_DIR, name), media_type="text/html")


@app.get("/")
async def index():
    return _page("index.html")


@app.get("/talk")
async def talk():
    return _page("talk.html")


@app.get("/whatsapp")
async def whatsapp():
    return _page("whatsapp.html")


@app.get("/verify")
async def verify():
    return _page("verify.html")


@app.get("/record")
async def record_page():
    return _page("record.html")


@app.get("/study")
async def study_page():
    return _page("study.html")


@app.get("/transparency")
async def transparency_page():
    return _page("transparency.html")


@app.get("/design")
async def design_page():
    return _page("design.html")


@app.get("/static/{name}")
async def static_file(name: str):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or ".." in name:
        raise HTTPException(404)
    path = os.path.join(WEB_DIR, name)
    if not os.path.exists(path):
        raise HTTPException(404)
    media = {".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml",
             ".html": "text/html"}.get(os.path.splitext(name)[1], "text/plain")
    # Vendored libraries carry their version in the name, so they never change
    # under a URL: a browser keeps them (three.js is 690 kB).
    headers = {"Cache-Control": "public, max-age=31536000, immutable"} if re.match(r"three-\d", name) else None
    return FileResponse(path, media_type=media, headers=headers)


# ───────────────────────────────────────────────── the operator console's routes
from .payments import configured as payments_configured_fn    # noqa: E402

async def notify_customer(pack_id: str, phone: str, text: str, *, meta: dict[str, Any] | None = None,
                          template: str = "receipt", params: list[str] | None = None) -> bool | None:
    """A message from the shop to a customer, recorded in their WhatsApp thread
    and sent when a real number is connected (None = nothing to send with)."""
    store.add_wa(pack_id, phone, "out", text, meta=meta or {})
    if not wa_channel.configured():
        return None
    try:
        return await wa_channel.send_template(phone, template, params or [], fallback_text=text)
    except Exception as exc:                          # noqa: BLE001 - a courtesy, not the record
        log.warning("customer notice to …%s failed: %s", phone[-4:], exc)
        return False


app.include_router(admin_mod.build_router(admin_mod.Deps(
    runtime=runtime, list_packs=list_packs, default_pack=DEFAULT_PACK, store=store, settings=settings,
    payments=payments, vault=vault, publish=publish, mask=_mask,
    user_of=lambda request: getattr(request.state, "user", None),
    offer_waitlist=offer_waitlist, var_dir=VAR_DIR, public_url=PUBLIC_URL,
    notify=notify_customer, auth_enabled=lambda: AUTH_ENABLED, is_public=lambda: IS_PUBLIC)))
