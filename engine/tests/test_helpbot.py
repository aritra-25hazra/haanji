"""The console's help assistant: it always answers (the FAQ when no model is
configured or a vendor fails), it uses the model the person picked, it keeps
the history short, it stops paying for replies past the daily cap, and it
never exposes a key."""
import asyncio
import types

from fastapi.testclient import TestClient

from haanji import helpbot as hb
from haanji.server import app


def bot(**kw):
    return hb.HelpBot(measured="- Bhasha: 30.7% -> 0.96%", **kw)


class FakeClaude:
    def __init__(self, text="From Claude.", fail=False):
        self.text, self.fail, self.seen = text, fail, []
        self.messages = self

    async def create(self, **kw):
        self.seen.append(kw)
        if self.fail:
            raise RuntimeError("vendor down")
        return types.SimpleNamespace(stop_reason="end_turn", content=[types.SimpleNamespace(type="text", text=self.text)],
                                     usage=types.SimpleNamespace(input_tokens=900, output_tokens=40))


class FakeHttp:
    def __init__(self, text="From Gemini."):
        self.text, self.seen = text, []

    async def post(self, url, json, headers):
        self.seen.append((url, json, headers))
        text = self.text
        return types.SimpleNamespace(raise_for_status=lambda: None,
                                     json=lambda: {"candidates": [{"content": {"parts": [{"text": text}]}}],
                                                   "usageMetadata": {"promptTokenCount": 800, "candidatesTokenCount": 30}})


def ask(b, text, **kw):
    return asyncio.run(b.answer([{"role": "user", "content": text}], **kw))


def test_with_no_keys_the_faq_answers_in_the_person_s_language():
    b = bot()
    assert b.providers() == ["faq"]
    r = ask(b, "how do I book an appointment?")
    assert r["provider"] == "faq" and "book" in r["reply"]
    r = ask(b, "booking kaise hoti hai?")
    assert "haan ke baad" in r["reply"]
    assert ask(b, "tell me a joke")["reply"] == hb.FALLBACK[0]


def test_the_picked_model_answers_and_the_other_is_the_fallback():
    b = bot(claude_key="k1", gemini_key="k2")
    b._claude, b._http = FakeClaude(), FakeHttp()
    assert b.providers() == ["claude", "gemini", "faq"]
    assert ask(b, "what is pramaan?", provider="gemini") == {"reply": "From Gemini.", "provider": "gemini", "model": hb.GEMINI_MODEL}
    assert ask(b, "what is pramaan?", provider="claude")["provider"] == "claude"
    b._claude.fail = True
    assert ask(b, "what is pramaan?", provider="claude")["provider"] == "gemini"


def test_claude_gets_the_guide_the_page_and_a_capped_reply():
    b = bot(claude_key="k")
    b._claude = FakeClaude()
    asyncio.run(b.answer([{"role": "user", "content": "x" * 5000}], page="/calendar"))
    kw = b._claude.seen[0]
    assert kw["model"] == hb.CLAUDE_MODEL and kw["max_tokens"] == hb.MAX_REPLY_TOKENS
    assert "/calendar" in kw["system"][0]["text"] and "30.7% -> 0.96%" in kw["system"][0]["text"]
    assert len(kw["messages"][0]["content"]) == hb.MAX_CHARS


def test_history_is_short_alternating_and_starts_with_the_person():
    msgs = [{"role": "assistant", "content": "hi"}] + [{"role": r, "content": str(i)} for i, r in
                                                       enumerate(["user", "assistant"] * 10 + ["user"])]
    out = hb.clean(msgs)
    assert out[0]["role"] == "user" and out[-1]["role"] == "user" and len(out) <= hb.MAX_TURNS
    assert all(a["role"] != b["role"] for a, b in zip(out, out[1:]))


def test_past_the_daily_cap_no_model_is_paid_for():
    b = bot(claude_key="k", daily_limit=2)
    b._claude = FakeClaude()
    assert [ask(b, "what is bhasha")["provider"] for _ in range(3)] == ["claude", "claude", "faq"]
    assert len(b._claude.seen) == 2


def test_the_endpoints_answer_without_keys_and_never_show_one(monkeypatch):
    from haanji import server
    monkeypatch.setattr(server, "helpbot", hb.HelpBot(claude_key="sk-ant-secret-value"))
    server.helpbot._claude = FakeClaude()
    c = TestClient(app)
    s = c.get("/api/help/status")
    assert s.status_code == 200 and "sk-ant" not in s.text and s.json()["providers"] == ["claude", "faq"]
    r = c.post("/api/help/chat", json={"messages": [{"role": "user", "content": "what is haanji"}], "lang": "en", "page": "/"})
    assert r.status_code == 200 and r.json()["provider"] == "claude"
    assert c.post("/api/help/chat", json={"messages": [{"role": "robot", "content": "x"}]}).status_code == 422


def test_the_engine_quotes_the_benchmark_from_its_own_results_file():
    from haanji import server
    text = server._measured_summary()
    assert "Bhasha" in text and "Pramaan" in text and "ms" in text
