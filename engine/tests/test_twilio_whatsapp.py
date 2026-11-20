"""WhatsApp through the Twilio Sandbox: Twilio's signature is required on a
public server, a redelivered message is answered once, the reply rides in
the TwiML answer (or, for a slow turn, goes by the REST API), every other
send goes through Twilio while Meta is not set up, and Twilio's errors reach
/api/status without the auth token."""
import asyncio
import base64
import hashlib
import hmac
import time
import urllib.parse

import httpx
import pytest
from fastapi.testclient import TestClient

from haanji import server
from haanji.channels import twilio_whatsapp as twilio
from haanji.channels import whatsapp as wa

TOKEN, URL = "twilio-auth-token", "https://engine.example"


def sign(url: str, form: dict) -> str:
    body = url + "".join(k + form[k] for k in sorted(form))
    return base64.b64encode(hmac.new(TOKEN.encode(), body.encode(), hashlib.sha1).digest()).decode()


def form(sid="SM1", text="haan ji mujhe dant dikhana hai", sender="whatsapp:+919876500001"):
    return {"MessageSid": sid, "From": sender, "To": "whatsapp:+14155238886", "Body": text, "NumMedia": "0"}


@pytest.fixture
def env(monkeypatch):
    for k in ("HAANJI_WA_TOKEN", "HAANJI_WA_PHONE_ID", "HAANJI_WA_PACK"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HAANJI_TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("HAANJI_TWILIO_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("HAANJI_TWILIO_WA_FROM", "whatsapp:+14155238886")
    monkeypatch.setenv("HAANJI_TWILIO_WA_JOIN", "join able-tiger")
    monkeypatch.setattr(server, "IS_PUBLIC", True)
    monkeypatch.setattr(server, "PUBLIC_URL", URL)
    server._wa_seen.clear()
    twilio.LAST_SEND.clear()
    before = set(server._sessions)
    with TestClient(server.app) as c:
        yield c
    # Chats left open would count against the concurrent-call cap for every
    # later test in the run ("the desk is busy").
    for sid in set(server._sessions) - before:
        server._sessions.pop(sid, None)
    for key, sid in list(server._wa_sessions.items()):
        if sid not in server._sessions:
            server._wa_sessions.pop(key, None)


def post(client, f, signed=True, path="/wa/twilio"):
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if signed:
        headers["X-Twilio-Signature"] = sign(URL + path, f)
    return client.post(path, content=urllib.parse.urlencode(f), headers=headers)


def test_an_unsigned_or_forged_message_is_refused_on_a_public_server(env):
    assert post(env, form(), signed=False).status_code == 403
    bad = {**form(), "Body": "something else"}
    r = env.post("/wa/twilio", content=urllib.parse.urlencode(bad), headers={
        "Content-Type": "application/x-www-form-urlencoded", "X-Twilio-Signature": sign(URL + "/wa/twilio", form())})
    assert r.status_code == 403


def test_without_the_auth_token_a_public_server_refuses_every_message(env, monkeypatch):
    monkeypatch.delenv("HAANJI_TWILIO_AUTH_TOKEN")
    assert post(env, form()).status_code == 403


def test_a_signed_message_is_answered_in_twiml_and_recorded(env):
    r = post(env, form())
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    assert r.text.startswith('<?xml') and r.text.count("<Message>") >= 1
    thread = server.store.wa_thread(server.DEFAULT_PACK, "9876500001")
    assert any(m["direction"] == "in" and "dant" in m["text"] for m in thread)


def test_a_redelivered_message_is_answered_once(env):
    assert "<Message>" in post(env, form(sid="SMdup", sender="whatsapp:+919876500002")).text
    again = post(env, form(sid="SMdup", sender="whatsapp:+919876500002"))
    assert again.status_code == 200 and "<Message>" not in again.text


def test_a_photo_without_text_gets_an_empty_answer(env):
    r = post(env, {**form(sid="SMimg"), "Body": "", "NumMedia": "1"})
    assert r.status_code == 200 and "<Message>" not in r.text


def test_a_slow_turn_answers_twilio_at_once_and_replies_by_the_api(env, monkeypatch):
    sent = []

    async def slow_turn(pack, phone, text, *, verified=True):
        await asyncio.sleep(0.3)
        return [{"text": "Ji, bataiye."}]

    async def fake_send(to, text, phone_id=None):
        sent.append((to, text))
        return True
    monkeypatch.setattr(server, "TWILIO_INLINE_S", 0.05)
    monkeypatch.setattr(server, "_wa_turn", slow_turn)
    monkeypatch.setattr(wa, "send_text", fake_send)
    r = post(env, form(sid="SMslow"))
    assert r.status_code == 200 and "<Message>" not in r.text
    deadline = time.time() + 3
    while not sent and time.time() < deadline:
        time.sleep(0.05)
    assert sent == [("9876500001", "Ji, bataiye.")]


def test_while_meta_is_not_set_up_every_send_goes_through_twilio(env, monkeypatch):
    out = []

    async def fake_twilio(to, text, status_callback=None):
        out.append((to, text, status_callback))
        return True
    monkeypatch.setattr(twilio, "send_text", fake_twilio)
    monkeypatch.setenv("HAANJI_PUBLIC_URL", URL)
    assert wa.provider() == "twilio" and wa.configured()
    assert asyncio.run(wa.send_template("9876500003", "otp", ["123456"], fallback_text="code 123456")) is True
    assert out == [("9876500003", "code 123456", URL + "/wa/twilio/status")]
    monkeypatch.setenv("HAANJI_WA_TOKEN", "t")
    monkeypatch.setenv("HAANJI_WA_PHONE_ID", "1")
    assert wa.provider() == "meta"                              # Meta wins once it is set up


def test_status_shows_the_sandbox_and_its_join_phrase(env):
    st = env.get("/api/status").json()["whatsapp"]
    assert st == {"configured": True, "provider": "twilio", "number": "+14155238886", "join_code": "join able-tiger",
                  "join_link": "https://wa.me/14155238886?text=join%20able-tiger", "sandbox": True}
    qr = env.get("/api/whatsapp/join-qr")
    assert qr.status_code == 200 and qr.headers["content-type"].startswith("image/svg+xml") and b"<svg" in qr.content


def test_no_join_qr_without_a_join_phrase(env, monkeypatch):
    monkeypatch.delenv("HAANJI_TWILIO_WA_JOIN")
    assert env.get("/api/whatsapp/join-qr").status_code == 404


def test_a_refused_send_is_described_without_the_token(env):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(400, json={"code": 63016, "message": "outside the allowed window"})
    ok = asyncio.run(twilio.send_text("9876500004", "hello", transport=httpx.MockTransport(handler)))
    assert ok is False
    req = seen[0]
    assert req.url.path == "/2010-04-01/Accounts/AC123/Messages.json"
    assert urllib.parse.parse_qs(req.content.decode())["To"] == ["whatsapp:+919876500004"]
    st = twilio.status()
    assert st["last_send"]["error"]["code"] == 63016 and st["last_send"]["error"]["to"] == "…0004"
    assert TOKEN not in str(st)


def test_a_long_reply_is_split_and_escaped():
    xml = twilio.twiml(["a & b <c>", "x" * 1700])
    assert "a &amp; b &lt;c&gt;" in xml and xml.count("<Message>") == 3
    assert twilio.to_address("98765 43210") == "whatsapp:+919876543210"
    assert twilio.to_address("+1 415 523 8886") == "whatsapp:+14155238886"
    assert twilio.phone_of("whatsapp:+919876543210") == "9876543210"


def test_twilio_reports_a_failed_delivery_for_the_console(env):
    f = {"MessageSid": "SMx", "MessageStatus": "undelivered", "To": "whatsapp:+919876500005",
         "ErrorCode": "63015", "ErrorMessage": "not joined to the sandbox"}
    assert post(env, f, signed=False, path="/wa/twilio/status").status_code == 403
    assert post(env, f, path="/wa/twilio/status").status_code == 204
    d = twilio.status()["last_send"]["delivery"]
    assert d["status"] == "failed" and d["code"] == "63015" and d["to"] == "…0005"


def test_a_public_server_refuses_unsigned_meta_deliveries_even_without_meta(env, monkeypatch):
    monkeypatch.delenv("HAANJI_WA_APP_SECRET", raising=False)
    assert env.post("/wa/webhook", json={"entry": []}).status_code == 403


def test_on_a_demo_server_real_whatsapp_lands_in_the_demo_twin(env, monkeypatch):
    monkeypatch.setattr(server, "demo_twins", lambda: {server.DEFAULT_PACK + server.DEMO_SUFFIX: server.DEFAULT_PACK})
    monkeypatch.setattr(server, "list_packs", lambda: [server.DEFAULT_PACK, server.DEFAULT_PACK + server.DEMO_SUFFIX])
    assert server._wa_pack() == server.DEFAULT_PACK + server.DEMO_SUFFIX
    monkeypatch.setenv("HAANJI_WA_PACK", "no_such_shop")
    assert server._wa_pack() == server.DEFAULT_PACK + server.DEMO_SUFFIX
    monkeypatch.setattr(server, "demo_twins", lambda: {})
    assert server._wa_pack() == server.DEFAULT_PACK


def test_a_demo_copy_never_messages_a_typed_number(env, monkeypatch):
    from types import SimpleNamespace
    twin = server.DEFAULT_PACK + server.DEMO_SUFFIX
    monkeypatch.setattr(server, "demo_twins", lambda: {twin: server.DEFAULT_PACK})
    out = []

    async def spy(to, kind, params, *, fallback_text=None, language=None):
        out.append(to)
        return True
    monkeypatch.setattr(wa, "send_template", spy)
    assert server.may_message(server.DEFAULT_PACK) and not server.may_message(twin) and server.may_message(twin, True)
    assert asyncio.run(server.notify_customer(twin, "9876500009", "receipt")) is None and out == []
    typed = SimpleNamespace(phone="9876500010", channel="WEB", rt=SimpleNamespace(pack_id=twin),
                            session=SimpleNamespace(ctx=SimpleNamespace(phone_verified=False)))
    monkeypatch.setattr(server, "PUBLIC_SIMULATOR", True)
    asyncio.run(server._notify_customer(typed, ["2504-7863"]))
    assert out == []
    typed.session.ctx.phone_verified = True
    asyncio.run(server._notify_customer(typed, ["2504-7863"]))
    assert out == ["9876500010"]
