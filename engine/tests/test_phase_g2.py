"""Phase G2: the product features a shop actually pays for — reminders,
deposits, the waitlist, the console's calendar and settings, backups — and
the audio hash that makes a phone receipt stronger evidence."""
import asyncio
import datetime as dt
import hashlib
import hmac
import io
import json
import os
import sqlite3
import tarfile

import pytest
from fastapi.testclient import TestClient

from haanji import backup as backup_mod
from haanji import reminders as rem_mod
from haanji import server
from haanji.adapters.mock import NullTTS
from haanji.auth import AuthStore
from haanji.channels import whatsapp as wa
from haanji.payments import PaymentStore
from haanji.pipeline import CallSession
from haanji.pramaan.ledger import Ledger
from haanji.pramaan.verifier import verify_chain
from haanji.settings import SettingsError, SettingsStore
from haanji.tools.builtin import build_registry, open_backend
from haanji.vertical import load_pack

PACK = "dental_clinic"


@pytest.fixture
def client(monkeypatch):
    server._buckets.clear()
    monkeypatch.setattr(server, "AUTH_ENABLED", False)
    return TestClient(server.app)


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def fake_text(to, text):
        out.append((to, text))
        return True

    async def fake_template(to, kind, params, *, fallback_text=None, language=None):
        out.append((to, fallback_text or f"<{kind}:{params}>"))
        return True

    monkeypatch.setattr(wa, "send_text", fake_text)
    monkeypatch.setattr(wa, "send_template", fake_template)
    return out


def _book(client, phone, lines=None, day="kal"):
    for line in lines or ("mujhe teeth cleaning karwani hai", f"{day} subah ka time mil jayega", "haan ji wahi theek hai",
                          f"mera naam Rina hai number {phone}", "haan confirm kar do"):
        r = client.post("/api/wa/incoming", json={"pack": PACK, "phone": phone, "text": line}).json()
    return r["replies"]


# ───────────────────────────────────────────────────────── settings
def test_settings_have_defaults_types_and_limits(tmp_path):
    st = SettingsStore(str(tmp_path / "s.sqlite"))
    assert st.get(PACK)["reminders_on"] is True and st.get(PACK)["deposit_inr"] == 0
    cur = st.update(PACK, {"deposit_inr": "500", "reminders_on": "false", "reminder_hour_ist": 9})
    assert cur["deposit_inr"] == 500 and cur["reminders_on"] is False and cur["reminder_hour_ist"] == 9
    with pytest.raises(SettingsError):
        st.update(PACK, {"nonsense": 1})
    with pytest.raises(SettingsError):
        st.update(PACK, {"reminder_hour_ist": 25})
    assert st.get("salon_spa")["deposit_inr"] == 0, "per pack"


def test_the_console_reads_and_writes_settings(client):
    assert client.get("/api/settings", params={"pack": PACK}).json()["settings"]["waitlist_on"] is True
    r = client.put("/api/settings", params={"pack": PACK}, json={"digest_hour_ist": 21})
    assert r.status_code == 200 and r.json()["settings"]["digest_hour_ist"] == 21
    assert client.put("/api/settings", params={"pack": PACK}, json={"bogus": 1}).status_code == 422
    client.put("/api/settings", params={"pack": PACK}, json={"digest_hour_ist": 20})


# ────────────────────────────────────────────────── calendar + customers
def test_the_calendar_lists_cancels_and_marks_attendance_with_receipts(client):
    phone = "9833300011"
    _book(client, phone)
    rt = server.runtime(PACK)
    booking = rt.backend.find_booking(PACK, phone)
    week = client.get("/api/bookings", params={"pack": PACK, "from": booking.date, "to": booking.date}).json()
    mine = [b for b in week["bookings"] if b["booking_id"] == booking.booking_id]
    assert mine and mine[0]["phone"] == phone and mine[0]["status"] == "CONFIRMED" and mine[0]["duration_min"] == 30
    assert client.get("/api/bookings", params={"pack": PACK, "from": "nope"}).status_code == 422
    n_before = len(rt.ledger.receipts(PACK))
    r = client.post(f"/api/bookings/{booking.booking_id}/status", params={"pack": PACK}, json={"status": "NO_SHOW"}).json()
    assert r["status"] == "NO_SHOW" and r["receipt_code"]
    assert rt.backend.booking(PACK, booking.booking_id).status == "NO_SHOW"
    assert client.get("/api/bookings", params={"pack": PACK, "from": booking.date, "to": booking.date, "status": "NO_SHOW"}).json()["bookings"]
    client.post(f"/api/bookings/{booking.booking_id}/status", params={"pack": PACK}, json={"status": "CONFIRMED"})
    r = client.post(f"/api/bookings/{booking.booking_id}/cancel", params={"pack": PACK}).json()
    assert r["ok"] and rt.backend.booking(PACK, booking.booking_id).status == "CANCELLED"
    assert client.post(f"/api/bookings/{booking.booking_id}/cancel", params={"pack": PACK}).status_code == 409
    receipts = rt.ledger.receipts(PACK)
    assert len(receipts) == n_before + 3 and [x.action for x in receipts[-3:]] == ["staff_update", "staff_update", "staff_cancel"]
    assert receipts[-1].action_args["by"] == "console" and "phone_enc" in receipts[-1].action_args
    assert str(verify_chain(receipts, lambda _k: rt.ledger.public_key(receipts[-1].key_id))).startswith("VALID")
    customers = client.get("/api/customers", params={"pack": PACK, "q": "Rina"}).json()["customers"]
    assert any(c["phone"] == phone and c["name"] == "Rina" for c in customers)


# ──────────────────────────────────────────────────────────── payments
def test_a_deposit_makes_a_link_a_mock_payment_settles_it_and_the_ledger_shows_the_money(client):
    client.put("/api/settings", params={"pack": PACK}, json={"deposit_inr": 300})
    try:
        phone = "9833300022"
        replies = _book(client, phone)
        last = replies[-1]["text"]
        assert "deposit" in last and "/pay/pay_" in last, last
        pay_id = last.split("/pay/")[1].split()[0].strip()
        pays = client.get("/api/payments", params={"pack": PACK}).json()
        row = next(p for p in pays["payments"] if p["payment_id"] == pay_id)
        assert row["status"] == "CREATED" and row["amount_inr"] == 300 and pays["provider"] == "mock"
        page = client.get(f"/pay/{pay_id}")
        assert page.status_code == 200 and "₹300" in page.text
        done = client.post(f"/pay/{pay_id}/mock-pay", follow_redirects=False)
        assert done.status_code == 303
        row = client.get("/api/payments", params={"pack": PACK}).json()["payments"]
        row = next(p for p in row if p["payment_id"] == pay_id)
        assert row["status"] == "PAID" and row["receipt_code"]
        rt = server.runtime(PACK)
        b = rt.backend.find_booking(PACK, phone)
        assert b.paid is True and b.payment_id == pay_id
        assert rt.ledger.receipts(PACK)[-1].action == "payment_received"
        cal = client.get("/api/bookings", params={"pack": PACK, "from": b.date, "to": b.date}).json()["bookings"]
        assert next(x for x in cal if x["booking_id"] == b.booking_id)["paid"] is True
        assert client.post(f"/pay/{pay_id}/mock-pay", follow_redirects=False).status_code == 303, "idempotent"
    finally:
        client.put("/api/settings", params={"pack": PACK}, json={"deposit_inr": 0})


def test_the_razorpay_webhook_is_signed_and_understood(client, monkeypatch, tmp_path):
    secret = "whsec"
    monkeypatch.setenv("HAANJI_RAZORPAY_WEBHOOK_SECRET", secret)
    body = json.dumps({"event": "payment_link.paid", "payload": {
        "payment_link": {"entity": {"id": "plink_1", "reference_id": "pay_doesnotexist"}},
        "payment": {"entity": {"id": "pay_rzp_1"}}}}).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert client.post("/payments/razorpay/webhook", content=body, headers={"X-Razorpay-Signature": "bad"}).status_code == 403
    r = client.post("/payments/razorpay/webhook", content=body, headers={"X-Razorpay-Signature": sig})
    assert r.status_code == 200 and r.json()["status"] is None            # unknown link: acknowledged, nothing changed
    assert PaymentStore.from_webhook({"event": "order.paid"}) == (None, None, None)
    monkeypatch.delenv("HAANJI_RAZORPAY_WEBHOOK_SECRET")
    assert client.post("/payments/razorpay/webhook", content=body).status_code == 403


# ──────────────────────────────────────────────────────────── reminders
def test_reminder_text_due_list_and_replies():
    pack = load_pack(PACK)
    backend, _ = open_backend(pack, "t", today=dt.date(2026, 10, 29))
    b = backend.book(tenant_id="t", service="teeth cleaning", date="2026-10-30", time="10:30",
                     customer_name="Vijay Sharma", phone="9876543210", receipt_code="2504-7863")
    text = rem_mod.reminder_text(b, "Smile Care", backend.today, backend.resolve_date, "hinglish", "https://x")
    assert "Vijay ji" in text and "kal subah saade 10 baje" in text and "1 = haan" in text and "2504-7863" in text
    cfg = {"reminders_on": True, "reminder_hour_ist": 18, "reminder_day_before": True}
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    assert rem_mod.due_today(backend, "t", cfg, dt.datetime(2026, 10, 29, 17, 0, tzinfo=ist)) == []
    due = rem_mod.due_today(backend, "t", cfg, dt.datetime(2026, 10, 29, 18, 5, tzinfo=ist))
    assert [x.booking_id for x in due] == [b.booking_id]
    backend.mark_reminded("t", b.booking_id)
    assert rem_mod.due_today(backend, "t", cfg, dt.datetime(2026, 10, 29, 18, 5, tzinfo=ist)) == []
    assert rem_mod.due_today(backend, "t", {**cfg, "reminders_on": False}, dt.datetime(2026, 10, 29, 19, 0, tzinfo=ist)) == []
    assert rem_mod.interpret_reply("1") == "confirm" and rem_mod.interpret_reply("Haan aa raha hoon") == "confirm"
    assert rem_mod.interpret_reply("2") == "cancel" and rem_mod.interpret_reply("cancel kar do") == "cancel"
    assert rem_mod.interpret_reply("kitne baje?") is None


def test_a_reminder_goes_out_and_the_reply_cancels_through_the_ledger(client, sent, monkeypatch):
    phone = "9833300033"
    monkeypatch.setenv("HAANJI_WA_TOKEN", "t"); monkeypatch.setenv("HAANJI_WA_PHONE_ID", "1")
    _book(client, phone, lines=("mujhe teeth cleaning karwani hai", "kal subah ka time mil jayega", "haan ji wahi theek hai",
                                f"mera naam Rina hai number {phone}", "haan confirm kar do"))
    rt = server.runtime(PACK)
    booking = rt.backend.find_booking(PACK, phone)
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    now = dt.datetime.combine(dt.date.fromisoformat(booking.date) - dt.timedelta(days=1), dt.time(18, 30), tzinfo=ist)
    n = asyncio.run(server.send_due_reminders(now))
    assert n >= 1 and any(to == phone and "yaad dilana" in text for to, text in sent)
    assert rt.backend.booking(PACK, booking.booking_id).reminder_sent_at
    # the real webhook path: Meta vouches for the sender, "2" cancels
    reply = asyncio.run(server._wa_turn(PACK, phone, "2", verified=True))
    assert reply and "cancel" in reply[-1]["text"].lower() and reply[-1].get("receipts")
    assert rt.backend.booking(PACK, booking.booking_id).status == "CANCELLED"
    last = rt.ledger.receipts(PACK)[-1]
    assert last.action == "cancel_appointment" and last.confirmation["reply_text"] == "2" and "yaad dilana" in last.confirmation["prompt_text"]
    assert last.action_args["identity"] == "channel"
    again = asyncio.run(server._wa_turn(PACK, phone, "2", verified=True))
    assert "cancel kar di" not in again[-1]["text"], "a reminder is answered once"


# ───────────────────────────────────────────────────────────── waitlist
def test_a_full_day_puts_the_caller_on_the_waitlist_and_a_cancellation_offers_the_slot(client, sent):
    rt = server.runtime(PACK)
    day = (rt.backend.today + dt.timedelta(days=10))
    while day.weekday() == 6:
        day += dt.timedelta(days=1)
    iso = day.isoformat()
    # fill the day for cleaning with every staff member
    for staff in ("Dr Sheikh", "Dr Malhotra", "Dr Iyer"):
        for start in range(9 * 60 + 30, 20 * 60, 30):
            try:
                rt.backend.book(tenant_id=PACK, service="teeth cleaning", date=iso, time=f"{start // 60:02d}:{start % 60:02d}",
                                staff=staff, customer_name="walk-in", phone=None)
            except Exception:
                pass
    waiting = "9833300044"
    replies = _book(client, waiting, lines=(f"{iso.split('-')[2]} tarikh ko teeth cleaning karwani hai",
                                             f"mera naam Mona hai number {waiting}"))
    assert "WhatsApp karenge" in replies[-1]["text"]
    entries = client.get("/api/waitlist", params={"pack": PACK}).json()["entries"]
    mine = [e for e in entries if e["phone"] == waiting and e["date"] == iso]
    assert mine and mine[0]["status"] == "WAITING" and mine[0]["service"] == "teeth cleaning"
    # a walk-in cancels from the console: the waiting caller is offered the slot
    victim = next(b for b in rt.backend.bookings_between(PACK, iso, iso) if b.customer_name == "walk-in" and b.time == "10:00")
    sent.clear()
    r = client.post(f"/api/bookings/{victim.booking_id}/cancel", params={"pack": PACK}).json()
    assert r["ok"]
    entry = next(e for e in client.get("/api/waitlist", params={"pack": PACK}).json()["entries"] if e["entry_id"] == mine[0]["entry_id"])
    assert entry["status"] == "OFFERED" and entry["offered_slot"].startswith(iso)
    thread = client.get(f"/api/wa/threads/{waiting}", params={"pack": PACK}).json()["messages"]
    assert "khaali hua hai" in thread[-1]["text"]
    # "haan" books it through the ordinary read-back
    first = client.post("/api/wa/incoming", json={"pack": PACK, "phone": waiting, "text": "haan"}).json()["replies"][-1]["text"]
    assert "Confirm kar dun" in first
    done = client.post("/api/wa/incoming", json={"pack": PACK, "phone": waiting, "text": "haan"}).json()["replies"][-1]
    assert done.get("receipts") and rt.backend.find_booking(PACK, waiting).date == iso
    entry = next(e for e in client.get("/api/waitlist", params={"pack": PACK}).json()["entries"] if e["entry_id"] == mine[0]["entry_id"])
    assert entry["status"] == "BOOKED"
    assert client.delete(f"/api/waitlist/{mine[0]['entry_id']}", params={"pack": PACK}).json()["removed"] is True


# ─────────────────────────────────────────────────────────────── backup
def test_backups_are_consistent_restorable_and_never_overwrite_a_live_shop(tmp_path):
    var = tmp_path / "var"
    var.mkdir()
    conn = sqlite3.connect(str(var / "store.sqlite"))
    conn.execute("CREATE TABLE t (x)"); conn.execute("INSERT INTO t VALUES (1)"); conn.commit()
    (var / "vapid.json").write_text("{}")
    (var / "auth.sqlite.secret").write_text("s")
    (var / "ignored.log").write_text("x")
    data = backup_mod.make_backup(str(var))
    names = {m.name for m in tarfile.open(fileobj=io.BytesIO(data), mode="r:gz").getmembers()}
    assert names == {"store.sqlite", "vapid.json", "auth.sqlite.secret"}
    fresh = tmp_path / "fresh"
    files = backup_mod.restore(str(fresh), data)
    assert sorted(files) == sorted(names)
    assert sqlite3.connect(str(fresh / "store.sqlite")).execute("SELECT x FROM t").fetchone()[0] == 1
    with pytest.raises(RuntimeError):
        backup_mod.restore(str(fresh), data)                       # never over a live directory
    assert backup_mod.restore(str(fresh), data, only_if_empty=False)


def test_the_owner_downloads_a_backup_from_the_console(client):
    r = client.get("/api/admin/backup")
    assert r.status_code == 200 and r.headers["content-type"] == "application/gzip"
    names = {m.name for m in tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz").getmembers()}
    assert "store.sqlite" in names and any(n.startswith("ledger-") for n in names)


# ─────────────────────────────────────────────────── audio in the receipt
def test_a_phone_confirmation_binds_the_reply_audio_into_the_receipt():
    pack = load_pack(PACK)
    backend, _ = open_backend(pack, "t", today=dt.date(2026, 10, 29))
    ledger = Ledger(sqlite3.connect(":memory:"))
    registry = build_registry("t", backend, pack, ledger)
    s = CallSession(tenant_id="t", pack=pack, backend=backend, registry=registry, ledger=ledger, tts=NullTTS())
    asyncio.run(s.open(phone="9876543210", verified=True))
    for line in ("mujhe root canal karwana hai", "kal subah ka time mil jayega", "haan ji wahi theek hai", "Vijay Sharma"):
        asyncio.run(s.handle_text_turn(line))
    clip = b"\xff" * 1600
    asyncio.run(s.handle_text_turn("haan confirm kar do", audio=clip))
    r = ledger.receipts("t")[-1]
    assert r.action == "book_appointment" and r.confirmation["audio_sha256"] == hashlib.sha256(clip).hexdigest()
    pub = ledger.public_key(r.key_id)
    assert str(verify_chain(ledger.receipts("t"), lambda _k: pub)).startswith("VALID")
    # a receipt without audio hashes exactly as before 1.1: the field is absent, not null
    from haanji.pramaan.receipt import ConfirmationProof
    assert "audio_sha256" not in ConfirmationProof("q", 0, "a", 1, 0.9).to_dict()
