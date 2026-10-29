"""Phase G: what the 2026-10-29 analysis found, pinned down.

Every case here reproduced a wrong booking, a hung-up caller, a false
refusal or a security hole against v1.0.0. Each test is the sentence a real
caller (or attacker) used, and what must happen now."""
import asyncio
import datetime as dt
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from haanji import nlu, server
from haanji.adapters.mock import NullTTS
from haanji.auth import AuthStore, OtpThrottled
from haanji.backend.local import BackendError, LocalBackend
from haanji.models import Outcome
from haanji.pipeline import CallSession
from haanji.pramaan.ledger import Ledger
from haanji.tools.builtin import build_registry, open_backend
from haanji.vertical import load_pack

TODAY = dt.date(2026, 10, 29)          # a Thursday
TENANT = "t_g"


# ───────────────────────────────────────────────────────────── nlu
def test_hindi_fractions_and_number_words_are_read_as_clock_times():
    assert nlu.normalise_time("saade 10 baje") == "10:30"
    assert nlu.normalise_time("saade dus baje") == "10:30"
    assert nlu.normalise_time("paune gyarah") == "10:45"
    assert nlu.normalise_time("sava nau") == "09:15"
    assert nlu.normalise_time("dhai baje") == "14:30"
    assert nlu.normalise_time("dedh baje") == "13:30"
    assert nlu.normalise_time("shaam 6 baje") == "18:00"
    assert nlu.normalise_time("egaro tay") == "11:00" and nlu.normalise_time("sakali daha vajta") == "10:00"


def test_dates_are_resolved_or_left_open_never_guessed():
    assert nlu.normalise_date("15 tarikh ko", None, TODAY) == "2026-11-15"
    assert nlu.normalise_date("pandrah tarikh", None, TODAY) == "2026-11-15"
    assert nlu.normalise_date("3 november ko", None, TODAY) == "2026-11-03"
    assert nlu.normalise_date("do din baad", None, TODAY) == "2026-10-31"
    assert nlu.normalise_date("30 tarikh", None, TODAY) == "2026-10-30"
    assert nlu.normalise_date("agle somvar", None, TODAY) == "monday"
    assert nlu.normalise_date("next week", None, TODAY) is None and nlu.date_unclear("next week")
    assert nlu.normalise_date("cleaning chahiye", None, TODAY) is None
    assert nlu.normalise_date("kalke shokale") == "tomorrow"           # the older forms still work


def test_phone_numbers_are_one_breath_not_every_digit_in_the_sentence():
    assert nlu.extract_phone("mera number 98765 43210 hai aur 2 log aayenge") == "9876543210"
    assert nlu.extract_phone("+91 98765 43210") == "9876543210"
    assert nlu.extract_phone("call 09876543210") == "9876543210"
    assert nlu.extract_phone("mera number 1234567890") is None            # not an Indian mobile
    assert nlu.extract_name("mera number 98765 43210 hai aur 2 log aayenge") is None
    assert nlu.extract_name("Anita Rao 9812345678") == "Anita Rao"
    assert nlu.extract_name("kal 10 baje 9876543210") is None


def test_party_staff_period_and_farewell_cues():
    assert nlu.party_size("mujhe aur meri wife ko cleaning karwani hai") == 2
    assert nlu.party_size("hum teen log aayenge") == 3 and nlu.party_size("akela hoon") is None
    assert nlu.match_staff("Dr Iyer se root canal", ["Dr Sheikh", "Dr Iyer"]) == "Dr Iyer"
    assert nlu.match_staff("doctor Shaikh se", ["Dr Sheikh"]) == "Dr Sheikh"
    assert nlu.time_period("kal shaam ka slot") == "evening" and nlu.time_period("tomorrow afternoon") == "afternoon"
    assert not nlu.is_farewell("nahi parso") and not nlu.is_farewell("nahi shaam ko")
    assert nlu.is_farewell("nahi bas itna hi tha dhanyavaad") and nlu.is_farewell("bye")


# ─────────────────────────────────────────────────────────── dialogue
def _session(pack_id="dental_clinic", phone=None, verified=False):
    pack = load_pack(pack_id)
    backend, _ = open_backend(pack, TENANT, today=TODAY)
    ledger = Ledger(sqlite3.connect(":memory:"))
    registry = build_registry(TENANT, backend, pack, ledger)
    s = CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry, ledger=ledger, tts=NullTTS())
    asyncio.run(s.open(phone=phone, verified=verified))
    return s, backend, ledger


def _say(s, *lines):
    out = []
    for line in lines:
        out.append(asyncio.run(s.handle_text_turn(line)))
        if s.ctx.flags.get("ended"):
            break
    return out


def test_an_evening_request_gets_an_evening_slot():
    s, _, _ = _session()
    r = _say(s, "kal shaam ka cleaning ka slot chahiye")[0]
    assert "shaam" in r.said and s.ctx.last_offered_slots[0]["time"] >= "16:00"
    _say(s, "haan ji", "Anita Rao 9812345678", "haan pakka")
    assert s.finish().outcome is Outcome.BOOKED and s.ctx.time >= "16:00"


def test_rejecting_the_offer_with_a_new_part_of_day_looks_again_instead_of_repeating():
    s, _, _ = _session()
    first = _say(s, "kal cleaning karwani hai")[0].said
    second = _say(s, "nahi shaam ko koi time hai")[0].said
    assert first != second and "shaam" in second and "check_availability" in s.turns[-1].tools


def test_nahi_parso_changes_the_day_rather_than_ending_the_call():
    s, _, _ = _session()
    _say(s, "kal cleaning")
    r = _say(s, "nahi parso")[0]
    assert not s.ctx.flags.get("ended") and r.said.startswith("Parso") and s.ctx.date == "day_after_tomorrow"


def test_a_half_hour_time_is_checked_exactly_and_booked_as_said():
    s, _, _ = _session()
    r = _say(s, "root canal kal saade dus baje")[0]
    assert "check_availability" in r.tools and s.ctx.time == "10:30" and "naam" in r.said
    _say(s, "Vijay Sharma 9876543210", "haan confirm kar do")
    assert s.finish().outcome is Outcome.BOOKED and s.ctx.time == "10:30"


def test_an_out_of_hours_time_gets_alternatives_before_any_details_are_asked():
    s, _, _ = _session("salon_spa")
    r = _say(s, "kal 8 baje haircut ka slot milega")[0]
    assert "jagah nahi" in r.said and "chalega" in r.said and s.ctx.last_offered_slots and s.ctx.time is None
    assert "naam" not in r.said


def test_the_named_doctor_is_the_one_booked():
    s, _, _ = _session()
    _say(s, "Dr Iyer se root canal karwana hai kal", "haan", "Kabir Nair 9765432100", "ji confirm")
    assert s.finish().outcome is Outcome.BOOKED and s.ctx.staff == "Dr Iyer"


def test_a_group_is_booked_together_under_one_receipt():
    s, backend, ledger = _session()
    r = _say(s, "mujhe aur meri wife ko cleaning karwani hai kal")[0]
    assert "2 logon" in r.said
    last = _say(s, "haan", "Sunil 9811111111", "haan")[-1]
    assert s.finish().outcome is Outcome.BOOKED and "2 logon" in last.said
    confirmed = [b for b in backend.bookings(TENANT) if b.status == "CONFIRMED" and b.phone == "9811111111"]
    assert len(confirmed) == 2 and len({b.receipt_code for b in confirmed}) == 1
    receipt = ledger.receipts(TENANT)[-1]
    assert receipt.action_args["party"] == 2 and len(receipt.action_args["bookings"]) == 2


def test_an_explicit_date_that_falls_on_a_closed_day_is_not_silently_tomorrow():
    s, _, _ = _session()
    r = _say(s, "15 tarikh ko cleaning ka appointment chahiye")[0]     # 15 Nov 2026 is a Sunday
    assert s.ctx.date == "2026-11-15" and "band" in r.said


def test_an_unclear_date_is_asked_about():
    s, _, _ = _session()
    r = _say(s, "agle hafte cleaning karwani hai")[0]
    assert "tarikh" in r.said.lower() or "din" in r.said.lower()
    assert s.ctx.date is None


def test_refusals_speak_the_refusal_line_and_the_call_goes_on():
    s, _, ledger = _session()
    r = _say(s, "cleaning pe koi discount milega kya")[0]
    assert r.guard == "promise.discount" and "Discount" in r.said and "emergency" not in r.said
    assert not s.ctx.flags.get("ended") and ledger.receipts(TENANT)[-1].action == "refuse"
    s2, _, _ = _session()
    r2 = _say(s2, "mujhe batao kaunsi dawai lun dard ke liye")[0]
    assert r2.guard == "advice.medicine" and r2.said == s2.pack.guardrails.refusal_line
    assert s2.finish().outcome is Outcome.REFUSED


def test_a_question_about_a_medicine_shop_is_not_a_prescription_request():
    s, _, _ = _session()
    r = _say(s, "clinic ke paas koi dawai ki dukaan hai kya")[0]
    assert r.guard == "" and "emergency" not in r.said


def test_a_pack_can_add_its_own_guardrail_rule():
    from haanji.guardrails import Action, Guard
    pack = load_pack("dental_clinic")
    pack.guardrails.rules = [{"id": "pack.whitening_promise", "action": "refuse",
                              "match": r"\b(whitening|safed)\b.*\b(guarantee|pakka)\b", "unless": None, "line": "Result dekh kar hi bata payenge."}]
    pack.guardrails.disable = ["promise.discount"]
    g = Guard(pack)
    v = g.check("whitening se daant pakka safed ho jayenge?")
    assert v.action is Action.REFUSE and v.rule == "pack.whitening_promise" and v.line == "Result dekh kar hi bata payenge."
    assert g.check("discount milega?").action is Action.ALLOW


# ──────────────────────────────────────────── who may cancel a booking
def _booked(phone="9876543210"):
    s, backend, ledger = _session()
    _say(s, "mujhe root canal karwana hai", "kal subah ka time mil jayega", "haan ji wahi theek hai",
         f"mera naam Vijay Sharma hai number {phone}", "haan confirm kar do")
    assert s.finish().outcome is Outcome.BOOKED
    return backend, ledger, backend.find_booking(TENANT, phone)


def test_a_typed_number_cannot_cancel_without_the_receipt_code():
    backend, ledger, booking = _booked()
    pack = load_pack("dental_clinic")
    registry = build_registry(TENANT, backend, pack, ledger)
    s = CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry, ledger=ledger, tts=NullTTS())
    asyncio.run(s.open(phone="9876543210", verified=False))             # the web page said so; nothing proved it
    r = _say(s, "meri booking cancel kar do")[0]
    assert "code" in r.said.lower() and s.ctx.pending_confirmation is None
    r = _say(s, "1234-ABCD")[0]                                          # wrong code
    assert s.ctx.pending_confirmation is None and backend.find_booking(TENANT, "9876543210") is not None
    s3 = CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry, ledger=ledger, tts=NullTTS())
    asyncio.run(s3.open(phone="9876543210", verified=False))
    _say(s3, "meri booking cancel kar do", booking.receipt_code, "haan")
    assert backend.find_booking(TENANT, "9876543210") is None, "the right code cancels"
    assert ledger.receipts(TENANT)[-1].action_args["identity"] == "receipt_code"


def test_a_number_the_channel_vouched_for_cancels_directly():
    backend, ledger, booking = _booked("9811122233")
    pack = load_pack("dental_clinic")
    registry = build_registry(TENANT, backend, pack, ledger)
    s = CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry, ledger=ledger, tts=NullTTS())
    asyncio.run(s.open(phone="9811122233", verified=True))              # caller-id / WhatsApp sender
    r = _say(s, "meri booking cancel kar do")[0]
    assert "cancel kar dun" in r.said
    _say(s, "haan")
    assert backend.find_booking(TENANT, "9811122233") is None
    assert ledger.receipts(TENANT)[-1].action_args["identity"] == "channel"


# ────────────────────────────────────────────────────────── backend
def test_today_is_live_and_the_past_cannot_be_booked():
    be = LocalBackend(sqlite3.connect(":memory:"))
    assert be.today == dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).date()
    pinned = LocalBackend(sqlite3.connect(":memory:"), now=dt.datetime(2026, 10, 29, 11, 0))
    pinned.load_pack(TENANT, load_pack("dental_clinic"))
    assert pinned.today == TODAY and pinned.now_minutes(TODAY) == 660
    with pytest.raises(BackendError):
        pinned.book(tenant_id=TENANT, service="teeth cleaning", date="2026-10-01", time="10:00")
    with pytest.raises(BackendError):
        pinned.book(tenant_id=TENANT, service="teeth cleaning", date="today", time="10:00")
    slots = asyncio.run(pinned.availability(TENANT, "teeth cleaning", "today"))["slots"]
    assert slots and all(s["time"] > "11:30" for s in slots), "nothing in the past is offered"


# ─────────────────────────────────────────────────────────── server
@pytest.fixture
def client():
    server._buckets.clear()
    return TestClient(server.app)


@pytest.fixture
def authed(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "auth", AuthStore(str(tmp_path / "auth.sqlite"), "test-secret"))
    monkeypatch.setattr(server, "AUTH_ENABLED", True)
    monkeypatch.setattr(server, "AUTH_DEV", True)
    monkeypatch.delenv("HAANJI_WA_TOKEN", raising=False)
    server._buckets.clear()
    server.auth.upsert_user("9800000001", "owner", ["*"], name="Owner")
    server.auth.upsert_user("9800000002", "staff", ["salon_spa"], name="Salon staff")
    return TestClient(server.app)


def _login(client, phone):
    code = client.post("/api/auth/otp", json={"phone": phone}).json()["dev_code"]
    return {"Authorization": "Bearer " + client.post("/api/auth/verify", json={"phone": phone, "code": code}).json()["token"]}


def test_erasure_needs_a_whole_number_and_touches_only_that_number(client):
    for line in ("mujhe teeth cleaning karwani hai", "kal subah ka time mil jayega", "haan ji wahi theek hai",
                 "mera naam Rina hai number 9822200011", "haan confirm kar do"):
        client.post("/api/wa/incoming", json={"pack": "dental_clinic", "phone": "9822200011", "text": line})
    for line in ("mujhe teeth cleaning karwani hai", "parso subah ka time mil jayega", "haan ji wahi theek hai",
                 "mera naam Mina hai number 9822200022", "haan confirm kar do"):
        client.post("/api/wa/incoming", json={"pack": "dental_clinic", "phone": "9822200022", "text": line})
    assert client.delete("/api/privacy/customer/abc", params={"pack": "dental_clinic"}).status_code == 400
    assert client.delete("/api/privacy/customer/0011", params={"pack": "dental_clinic"}).status_code == 400
    gone = client.delete("/api/privacy/customer/9822200011", params={"pack": "dental_clinic"}).json()
    assert gone["bookings_anonymised"] == 1 and gone["calls_deleted"] >= 1
    other = client.get("/api/privacy/customer/9822200022", params={"pack": "dental_clinic"}).json()
    assert other["bookings"] and not other["erased"], "the neighbour's records survive"


def test_scoped_staff_cannot_read_another_pack_by_omitting_the_pack(authed):
    staff = _login(authed, "9800000002")
    assert authed.get("/api/insights", headers=staff).status_code == 403          # no ?pack= used to mean "any"
    assert authed.get("/api/insights", params={"pack": "salon_spa"}, headers=staff).status_code == 200
    assert authed.get("/api/ops", params={"pack": "dental_clinic"}, headers=staff).status_code == 403
    assert authed.get("/api/ops", params={"pack": "dental_clinic"}).status_code == 401, "ops is no longer public"
    sid = authed.post("/api/sessions", json={"pack": "dental_clinic"}).json()["session_id"]
    assert authed.post(f"/api/sessions/{sid}/takeover", headers=staff).status_code == 403
    live = authed.get("/api/sessions/live", headers=staff).json()["sessions"]
    assert all(h["pack"] == "salon_spa" for h in live)
    recent = authed.get("/api/events/recent", headers=staff).json()["events"]
    assert all(e.get("pack") in (None, "salon_spa") for e in recent)
    assert authed.get("/metrics").status_code == 401 and authed.get("/metrics", headers=staff).status_code == 200


def test_otp_issuing_is_throttled_and_logout_revokes_every_token(authed):
    for _ in range(3):
        assert authed.post("/api/auth/otp", json={"phone": "9800000001"}).status_code == 200
    assert authed.post("/api/auth/otp", json={"phone": "9800000001"}).status_code == 429
    a = AuthStore(":memory:", "s")
    a.issue_otp("9811111111", now=1000.0)
    for _ in range(10):
        a.check_otp("9811111111", "000000", now=1001.0)
    with pytest.raises(OtpThrottled):
        a.issue_otp("9811111111", now=1002.0)
    assert a.otp_locked_until("9811111111", now=1002.0) > 1002.0
    owner = _login(authed, "9800000002")
    assert authed.get("/api/auth/me", headers=owner).status_code == 200
    assert authed.post("/api/auth/logout", headers=owner).status_code == 200
    time.sleep(1.1)                                       # revocation is second-granular
    assert authed.get("/api/auth/me", headers=owner).status_code == 401


def test_a_demoted_user_loses_the_role_without_waiting_for_expiry(tmp_path):
    a = AuthStore(str(tmp_path / "a.sqlite"), "s")
    p = a.upsert_user("9800000005", "owner", ["*"])
    tok = a.token_for(p, now=1000.0)
    a.upsert_user("9800000005", "staff", ["salon_spa"])
    who = a.verify_token(tok, now=1001.0)
    assert who.role == "staff" and who.packs == ["salon_spa"]
    a.remove_user("9800000005", now=1002.0)
    assert a.verify_token(tok, now=1003.0) is None


def test_oversized_bodies_and_too_many_live_calls_are_refused(client, monkeypatch):
    r = client.post("/api/sessions", content=b"{}", headers={"Content-Type": "application/json", "Content-Length": str(2 * 1024 * 1024)})
    assert r.status_code == 413
    assert client.post("/api/sessions", json={"pack": "dental_clinic", "channel": "SPACE"}).status_code == 422
    assert client.post("/api/sessions", json={"pack": "dental_clinic", "phone": "12"}).status_code == 422
    import dataclasses
    monkeypatch.setattr(server, "ENGINE_CFG", dataclasses.replace(server.ENGINE_CFG, max_concurrent_calls=len(server._sessions) + 1))
    assert client.post("/api/sessions", json={"pack": "dental_clinic"}).status_code == 200
    assert client.post("/api/sessions", json={"pack": "dental_clinic"}).status_code == 429


def test_the_status_page_no_longer_tells_the_world_where_the_data_lives(client):
    st = client.get("/api/status").json()
    assert "var_dir" not in st and "dev" not in st["auth"]


def test_a_web_caller_who_types_a_number_is_not_verified_but_a_whatsapp_sender_is(client):
    sid = client.post("/api/sessions", json={"pack": "dental_clinic", "phone": "9876543210"}).json()["session_id"]
    assert server._sessions[sid].session.ctx.phone_verified is False
    client.post("/api/wa/incoming", json={"pack": "dental_clinic", "phone": "9876543299", "text": "hello"})
    sid2 = server._wa_sessions[("dental_clinic", "9876543299")]
    assert server._sessions[sid2].session.ctx.phone_verified is True, "no real number connected: the simulator is the channel"


def test_receipts_are_found_by_an_indexed_code():
    ledger = Ledger(sqlite3.connect(":memory:"))
    from haanji.pramaan.receipt import ConfirmationProof
    proof = ConfirmationProof(prompt_text="Confirm?", prompt_start_ms=0, reply_text="haan", reply_start_ms=10, asr_confidence=0.9)
    r = ledger.append(tenant_id="t", conversation_id="c", action="book_appointment", action_args={"x": 1},
                      confirmation=proof, transcript_excerpt="")
    assert ledger.by_code("t", r.short_code()).seq == 1 and ledger.by_code("t", r.short_code().replace("-", "").lower()).seq == 1
    assert ledger.by_code("t", "0000-0000") is None


def test_signing_keys_can_be_encrypted_at_rest(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "l.sqlite"))
    ledger = Ledger(conn, key_secret="s3cret")
    kid = ledger.ensure_key("t")
    stored = conn.execute("SELECT private_key FROM tenant_keys WHERE key_id=?", (kid,)).fetchone()[0]
    assert stored.startswith("enc:")
    from haanji.pramaan.receipt import ConfirmationProof
    proof = ConfirmationProof(prompt_text="Confirm?", prompt_start_ms=0, reply_text="haan", reply_start_ms=10, asr_confidence=0.9)
    r = ledger.append(tenant_id="t", conversation_id="c", action="book_appointment", action_args={}, confirmation=proof, transcript_excerpt="")
    ledger.public_key(kid).verify(r.signature, r.chain_hash)
    with pytest.raises(Exception):
        Ledger(sqlite3.connect(str(tmp_path / "l.sqlite")))._private_key(kid)      # no secret: cannot sign
