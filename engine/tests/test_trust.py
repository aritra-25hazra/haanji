"""The trust loop closed: receipt links for the customer, daily anchors, the owner's digest."""
import datetime as dt
import hashlib

import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.channels import whatsapp as wa
from haanji.scenario import scenarios_of
from haanji.vertical import load_pack

PHONE = "9811100011"


@pytest.fixture
def client(tmp_path, monkeypatch):
    server._buckets.clear()
    return TestClient(server.app)


@pytest.fixture
def sent(monkeypatch):
    out: list[tuple[str, str]] = []

    async def fake_send(to: str, text: str, phone_id: str | None = None) -> None:
        out.append((to, text))

    monkeypatch.setattr(wa, "send_text", fake_send)
    return out


def book_over_whatsapp(client, phone=PHONE, pack="dental_clinic"):
    sc = next(s for s in scenarios_of(load_pack(pack)) if s.name == "booking_with_asr_noise")
    replies = []
    for u in sc.utterances:
        r = client.post("/api/wa/incoming", json={"pack": pack, "phone": phone, "text": u.truth})
        assert r.status_code == 200, r.text
        replies += r.json()["replies"]
    return replies


def test_a_whatsapp_booking_reply_carries_the_customers_receipt_link(client, monkeypatch):
    monkeypatch.setattr(server, "PUBLIC_URL", "https://haanji.example")
    replies = book_over_whatsapp(client, phone="9811100012")
    final = [r for r in replies if r.get("receipts")]
    assert final, "the booking produced a receipt"
    code = final[-1]["receipts"][-1]
    assert f"https://haanji.example/verify?code={code}&pack=dental_clinic" in final[-1]["text"]
    assert server.receipt_link("salon_spa", "AB12-CD34") == "https://haanji.example/verify?code=AB12-CD34&pack=salon_spa"


def test_the_verify_page_opens_a_receipt_from_its_link(client):
    html = client.get("/verify").text
    assert 'q.get("code")' in html and 'id="mine"' in html and "showMine" in html
    talk = client.get("/talk").text
    assert 'href = "verify?code="' in talk


def test_days_are_sealed_and_the_anchor_signature_verifies(client):
    book_over_whatsapp(client, phone="9811100013")
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()     # sealed days are UTC days
    sealed = client.post("/api/anchors/seal", params={"pack": "dental_clinic"}).json()
    assert today in sealed["sealed"] and sealed["anchors"], "today is (re)sealed every time"
    after = client.get("/api/anchors", params={"pack": "dental_clinic"}).json()
    assert after["pending_days"] == [] and after["anchors"][-1]["merkle_root"]
    # Recompute the root from the export and check the signature with the published key.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    exp = client.get("/api/receipts/export", params={"pack": "dental_clinic"}).json()
    anchor = after["anchors"][-1]
    layer = [bytes.fromhex(r["chain_hash"]) for r in exp["receipts"] if r["occurred_at"].startswith(anchor["day"])]
    assert len(layer) == anchor["last_seq"] - anchor["first_seq"] + 1
    while len(layer) > 1:
        layer = [hashlib.sha256(layer[i] + (layer[i + 1] if i + 1 < len(layer) else layer[i])).digest()
                 for i in range(0, len(layer), 2)]
    assert layer[0].hex() == anchor["merkle_root"]
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(after["public_key"])).verify(
        bytes.fromhex(anchor["signature"]), layer[0] + anchor["day"].encode())
    assert "Transparency" in client.get("/transparency").text


def test_the_owner_digest_reads_like_a_message_and_sends_over_whatsapp(client, monkeypatch, sent):
    monkeypatch.setattr(server, "PUBLIC_URL", "https://haanji.example")
    d = client.get("/api/digest", params={"pack": "dental_clinic"}).json()
    assert d["text"].startswith("HaanJi · Smile Care Dental") and "Callback chahiye:" in d["text"]
    assert "https://haanji.example/verify?pack=dental_clinic" in d["text"]
    assert client.get("/api/digest", params={"pack": "nope"}).status_code == 404
    monkeypatch.setattr(server, "OWNER_PHONE", None)
    assert client.post("/api/digest/send", params={"pack": "dental_clinic"}).status_code == 409
    monkeypatch.setattr(server, "OWNER_PHONE", "9800000000")
    monkeypatch.delenv("HAANJI_WA_TOKEN", raising=False)
    assert client.post("/api/digest/send", params={"pack": "dental_clinic"}).status_code == 409
    monkeypatch.setenv("HAANJI_WA_TOKEN", "t"); monkeypatch.setenv("HAANJI_WA_PHONE_ID", "1")
    r = client.post("/api/digest/send", params={"pack": "dental_clinic"}).json()
    assert r["sent"] and sent and sent[-1][0] == "9800000000" and sent[-1][1] == r["text"]


def test_seconds_until_the_evening_hour():
    now = dt.datetime(2026, 10, 15, 19, 30, tzinfo=server.IST)
    assert server.seconds_until(20, now=now) == 1800
    assert server.seconds_until(20, now=now.replace(hour=20, minute=0)) == 24 * 3600
    assert server.seconds_until(20, now=now.replace(hour=21, minute=0)) == 23 * 3600


def test_a_web_caller_with_a_number_gets_the_link_on_whatsapp(client, monkeypatch, sent):
    monkeypatch.setenv("HAANJI_WA_TOKEN", "t"); monkeypatch.setenv("HAANJI_WA_PHONE_ID", "1")
    monkeypatch.setattr(server, "PUBLIC_URL", "https://haanji.example")
    sid = client.post("/api/sessions", json={"pack": "dental_clinic", "phone": "9811100014"}).json()["session_id"]
    sc = next(s for s in scenarios_of(load_pack("dental_clinic")) if s.name == "booking_with_asr_noise")
    codes = []
    for u in sc.utterances:
        t = client.post(f"/api/sessions/{sid}/utterance", json={"text": u.truth}).json()
        codes += t.get("receipts", [])
    assert codes and any(f"verify?code={codes[-1]}" in text and to == "9811100014" for to, text in sent)


def test_on_the_public_demo_a_typed_number_is_never_sent_a_whatsapp(client, monkeypatch, sent):
    """A stranger on the public demo must not be able to make the shop message
    someone else's number by typing it into the web call."""
    monkeypatch.setenv("HAANJI_WA_TOKEN", "t"); monkeypatch.setenv("HAANJI_WA_PHONE_ID", "1")
    monkeypatch.setattr(server, "DEMO_READONLY", True)
    sid = client.post("/api/sessions", json={"pack": "dental_clinic", "phone": "9811100015"}).json()["session_id"]
    sc = next(s for s in scenarios_of(load_pack("dental_clinic")) if s.name == "booking_with_asr_noise")
    codes = []
    for u in sc.utterances:
        r = client.post(f"/api/sessions/{sid}/utterance", json={"text": u.truth}).json()
        codes += r.get("receipts", [])
    assert codes, "the booking itself still happens"
    assert not [m for m in sent if m[0].endswith("9811100015")]


def test_a_receipt_after_todays_seal_is_in_the_next_seal_at_any_hour(client):
    """Sealed days are UTC days. Resealing "today" used India's date, so between
    midnight and 05:30 IST the current UTC day was never resealed and a booking
    made then stayed out of every anchor."""
    book_over_whatsapp(client, phone="9811100031")
    client.post("/api/anchors/seal", params={"pack": "dental_clinic"})
    book_over_whatsapp(client, phone="9811100032")
    client.post("/api/anchors/seal", params={"pack": "dental_clinic"})
    exp = client.get("/api/receipts/export", params={"pack": "dental_clinic"}).json()["receipts"]
    last = max(r["seq"] for r in exp)
    day = next(r["occurred_at"][:10] for r in exp if r["seq"] == last)
    anchor = next(a for a in client.get("/api/anchors", params={"pack": "dental_clinic"}).json()["anchors"]
                  if a["day"] == day)
    assert anchor["last_seq"] == last


def test_pages_carry_a_content_security_policy_and_the_api_does_not_need_one(client):
    page = client.get("/talk")
    csp = page.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert "content-security-policy" not in client.get("/api/status").headers
