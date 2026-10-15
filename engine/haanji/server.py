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
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel

from .adapters.mock import NullTTS
from .backend.local import LocalBackend
from .channels import whatsapp as wa_channel
from . import collect as collect_mod
from .bhasha.phonetics import phrase_key
from .bhasha.lexicon import LexEntry, TenantLexicon
from .insights import compute as compute_insights
from .pipeline import CallSession
from .pramaan.ledger import Ledger
from .store import DemoStore
from .tools.builtin import build_registry
from .vertical import PACK_DIR, PackError, from_dict, list_packs, load_pack

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
VAR_DIR = os.path.abspath(os.environ.get("HAANJI_VAR_DIR", "var"))
DEFAULT_PACK = os.environ.get("HAANJI_PACK", "dental_clinic")
SESSION_IDLE_S = 1800

os.makedirs(VAR_DIR, exist_ok=True)

app = FastAPI(title="HaanJi demo server", version="0.4.0")
# Same-origin in production, because the console is served through a rewrite;
# the regex is overridable so the engine can also be called directly.
CORS_ORIGIN_REGEX = os.environ.get(
    "HAANJI_CORS_ORIGIN_REGEX", r"http://(localhost|127\.0\.0\.1)(:\d+)?")
app.add_middleware(CORSMiddleware, allow_origin_regex=CORS_ORIGIN_REGEX,
                   allow_methods=["*"], allow_headers=["*"])

store = DemoStore(os.path.join(VAR_DIR, "store.sqlite"))


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
    if demo:
        backend.seed_customer(pack_id, *demo[:2], last_service=demo[2])
    ledger = Ledger(sqlite3.connect(os.path.join(VAR_DIR, f"ledger-{pack_id}.sqlite"),
                                    check_same_thread=False))
    registry = build_registry(pack_id, backend, pack, ledger)
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


_sessions: dict[str, Holder] = {}
_wa_sessions: dict[tuple[str, str], str] = {}      # (pack, phone) -> session id


def _gc() -> None:
    cutoff = time.monotonic() - SESSION_IDLE_S
    for sid in [k for k, h in _sessions.items() if h.last_used < cutoff]:
        holder = _sessions.pop(sid)
        _wa_sessions.pop((holder.rt.pack_id, holder.phone or ""), None)


async def _new_session(pack_id: str, channel: str, phone: str | None) -> tuple[str, Holder]:
    _gc()
    rt = runtime(pack_id)
    session = CallSession(tenant_id=pack_id, pack=rt.pack, backend=rt.backend,
                          registry=rt.registry, ledger=rt.ledger, tts=NullTTS())
    await session.open(phone=phone)
    sid = uuid.uuid4().hex[:16]
    holder = Holder(session, rt, channel, phone)
    _sessions[sid] = holder
    return sid, holder


def _turn_payload(record, holder: Holder) -> dict[str, Any]:
    session = holder.session
    new_receipts = session.receipts[holder.receipts_seen:]
    holder.receipts_seen = len(session.receipts)
    return {
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
        "outcome": session.ctx.outcome.value if session.ctx.outcome else None,
    }


def _finish(sid: str, holder: Holder) -> None:
    report = holder.session.finish()
    store.record_call(report, channel=holder.channel, phone=holder.phone)
    if holder.phone and report.receipts and store.has_open_missed(holder.rt.pack_id, holder.phone):
        store.mark_recovered(holder.rt.pack_id, holder.phone, report.receipts[-1])
    _sessions.pop(sid, None)
    _wa_sessions.pop((holder.rt.pack_id, holder.phone or ""), None)


# ──────────────────────────────────────────────────────────────── web-call api
class NewSession(BaseModel):
    pack: str = DEFAULT_PACK
    phone: str | None = None
    channel: str = "WEB"


class TextIn(BaseModel):
    text: str


@app.post("/api/sessions")
async def create_session(body: NewSession):
    sid, holder = await _new_session(body.pack, body.channel, body.phone)
    return {"session_id": sid, "greeting": holder.session.ctx.last_agent_utterance,
            "pack": body.pack, "business": holder.rt.pack.persona.business_name}


@app.post("/api/sessions/{sid}/partial")
async def session_partial(sid: str, body: TextIn):
    holder = _sessions.get(sid)
    if holder is None:
        raise HTTPException(404, "no such session")
    holder.last_used = time.monotonic()
    await holder.session.handle_partial_text(body.text)
    return {"ok": True}


@app.post("/api/sessions/{sid}/utterance")
async def session_utterance(sid: str, body: TextIn):
    holder = _sessions.get(sid)
    if holder is None:
        raise HTTPException(404, "no such session")
    holder.last_used = time.monotonic()
    async with holder.lock:
        record = await holder.session.handle_text_turn(body.text)
        payload = _turn_payload(record, holder)
        if payload["end_call"]:
            _finish(sid, holder)
    return payload


@app.delete("/api/sessions/{sid}")
async def close_session(sid: str):
    holder = _sessions.get(sid)
    if holder is not None:
        _finish(sid, holder)
    return {"ok": True}


# ─────────────────────────────────────────────────────────── whatsapp channel
class WaIn(BaseModel):
    pack: str = DEFAULT_PACK
    phone: str
    text: str


async def _wa_turn(pack_id: str, phone: str, text: str) -> list[dict[str, Any]]:
    """One inbound WhatsApp message -> the agent's replies. Shared by the
    simulator and the real Meta webhook, so the demo and production run the
    same path."""
    store.add_wa(pack_id, phone, "in", text)
    replies: list[dict[str, Any]] = []
    key = (pack_id, phone)
    sid = _wa_sessions.get(key)
    holder = _sessions.get(sid) if sid else None
    if holder is None:
        sid, holder = await _new_session(pack_id, "WHATSAPP", phone)
        _wa_sessions[key] = sid
        greeting = holder.session.ctx.last_agent_utterance
        store.add_wa(pack_id, phone, "out", greeting)
        replies.append({"text": greeting})
    holder.last_used = time.monotonic()
    async with holder.lock:
        record = await holder.session.handle_text_turn(text)
        payload = _turn_payload(record, holder)
        store.add_wa(pack_id, phone, "out", record.said,
                     meta={"tools": record.tools, "receipts": payload["receipts"],
                           "corrections": payload["corrections"]})
        replies.append({"text": record.said, **{k: payload[k] for k in
                       ("corrections", "tools", "speculation_hits", "receipts", "latency_ms")}})
        if payload["end_call"]:
            _finish(sid, holder)
    return replies


@app.post("/api/wa/incoming")
async def wa_incoming(body: WaIn):
    if not re.fullmatch(r"\d{10}", body.phone):
        raise HTTPException(400, "phone must be ten digits")
    return {"replies": await _wa_turn(body.pack, body.phone, body.text.strip())}


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
    expected = os.environ.get("HAANJI_WA_VERIFY_TOKEN") or "haanji"
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == expected:
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "bad verify token")


# Message ids Meta has already delivered; it retries anything it did not get a
# prompt 200 for, and a retried booking must not become two bookings.
_wa_seen: deque[str] = deque(maxlen=500)


@app.post("/wa/webhook")
async def wa_webhook(request: Request):
    raw = await request.body()
    secret = os.environ.get("HAANJI_WA_APP_SECRET") or None
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
        replies = await _wa_turn(pack, phone[-10:], text)
        for r in replies:
            await wa_channel.send_text(phone, r["text"])
        handled += 1
    return {"ok": True, "handled": handled}


# ───────────────────────────────────────────────────── missed-call recovery
class MissedIn(BaseModel):
    pack: str = DEFAULT_PACK
    phone: str


@app.post("/api/telephony/missed-call")
async def missed_call(body: MissedIn):
    """The telephony provider tells us a call rang out (Exotel/Plivo webhook
    shape documented in channels/telephony.py). We open the WhatsApp thread
    with an outreach message; when the caller's reply ends in a booking, the
    missed call is counted as recovered."""
    rt = runtime(body.pack)
    store.record_missed(body.pack, body.phone)
    outreach = (f"Namaste! Aapne abhi {rt.pack.persona.business_name} ko call kiya tha — "
                f"maaf kijiye, hum utha nahi paye. Main yahin WhatsApp par appointment "
                f"book kar sakta hoon. Kaunsi service chahiye?")
    key = (body.pack, body.phone)
    if key in _wa_sessions:                       # a fresh thread for the recovery
        _sessions.pop(_wa_sessions.pop(key), None)
    sid, holder = await _new_session(body.pack, "WHATSAPP", body.phone)
    _wa_sessions[key] = sid
    holder.session.ctx.last_agent_utterance = outreach
    store.add_wa(body.pack, body.phone, "out", outreach, meta={"missed_call_recovery": True})
    return {"ok": True, "outreach": outreach}


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
    yaml: str


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
    out, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
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


@app.get("/api/status")
async def status():
    return {"name": "HaanJi demo server", "version": app.version,
            "default_pack": DEFAULT_PACK, "packs": list_packs(),
            "var_dir": VAR_DIR,
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


@app.get("/static/{name}")
async def static_file(name: str):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or ".." in name:
        raise HTTPException(404)
    path = os.path.join(WEB_DIR, name)
    if not os.path.exists(path):
        raise HTTPException(404)
    media = {".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml",
             ".html": "text/html"}.get(os.path.splitext(name)[1], "text/plain")
    return FileResponse(path, media_type=media)
