"""The Gemini dialogue adapter keeps every guarantee the Claude one does: it
talks and looks things up, but a write becomes the pack's read-back question,
the caller's yes goes through the policy and the ledger, and a vendor failure
falls back to the policy. Only Gemini's wire is different."""
from types import SimpleNamespace

import pytest

from haanji.adapters.factory import make_llm
from haanji.adapters.gemini import GeminiLLM, gemini_schema
from haanji.config import EngineConfig
from haanji.models import ConversationContext, Speaker, ToolResult, Turn
from haanji.pipeline import CallSession
from haanji.policy import DialoguePolicy

TENANT = "t_test"


class FakeGemini:
    """Plays generateContent: each post returns the next scripted list of parts."""

    def __init__(self, script, fail=False):
        self.script, self.fail, self.posts = list(script), fail, []

    async def post(self, url, json, headers):
        self.posts.append({"url": url, "json": json, "headers": headers})
        if self.fail:
            raise RuntimeError("vendor is down")
        parts = self.script.pop(0)
        return SimpleNamespace(raise_for_status=lambda: None,
                               json=lambda: {"candidates": [{"content": {"role": "model", "parts": parts}}],
                                             "usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 30,
                                                               "thoughtsTokenCount": 12}})


def call(name, args, id_=None, sig="sig-1"):
    fc = {"name": name, "args": args}
    if id_:
        fc["id"] = id_
    return {"functionCall": fc, "thoughtSignature": sig}


@pytest.fixture
def policy(pack, backend):
    return DialoguePolicy(pack, backend, TENANT)


@pytest.fixture
def ctx():
    c = ConversationContext(tenant_id=TENANT)
    c.add(Turn(1, Speaker.AGENT, "Haanji, Smile Care Dental. Main aapki kya madad karun?"))
    return c


def step(ctx, text_):
    ctx.add(Turn(len(ctx.turns) + 1, Speaker.CALLER, text_))
    return {"content": text_, "context": ctx}


def test_tool_schemas_become_gemini_declarations():
    s = gemini_schema({"type": "object", "additionalProperties": False, "x-haanji": {"a": 1},
                       "properties": {"phone": {"type": ["string", "null"], "default": None},
                                      "party": {"type": "integer", "minimum": 1}},
                       "required": ["phone"]})
    assert s == {"type": "OBJECT", "properties": {"phone": {"type": "STRING", "nullable": True},
                                                 "party": {"type": "INTEGER"}}, "required": ["phone"]}


async def test_a_text_reply_becomes_say_and_the_request_is_gemini_s(pack, policy, registry, ctx):
    g = FakeGemini([[{"text": "Kis din ka time dekhun?"}]])
    llm = GeminiLLM(policy, pack, registry, client=g, api_key="k", model="gemini-test")
    turn = await llm.respond(llm.system, [step(ctx, "mujhe root canal karwana hai")], llm.tools)
    assert turn.say == "Kis din ka time dekhun?" and not turn.tool_calls
    body = g.posts[0]["json"]
    assert g.posts[0]["url"].endswith("/models/gemini-test:generateContent") and g.posts[0]["headers"] == {"x-goog-api-key": "k"}
    assert body["contents"][-1] == {"role": "user", "parts": [{"text": "mujhe root canal karwana hai"}]}
    assert pack.persona.business_name in body["systemInstruction"]["parts"][0]["text"]
    names = {d["name"] for d in body["tools"][0]["functionDeclarations"]}
    assert {"check_availability", "book_appointment", "end_call"} <= names
    assert llm.usage == {"input": 900, "output": 42}


async def test_a_lookup_round_trips_with_the_model_s_own_parts(pack, policy, registry, ctx):
    g = FakeGemini([[call("check_availability", {"service": "root canal", "date": "2026-09-08"}, "fc_7", "SIG")],
                    [{"text": "Kal subah saade 9 baje khaali hai. Chalega?"}]])
    llm = GeminiLLM(policy, pack, registry, client=g, api_key="k")
    h = step(ctx, "kal subah ka time mil jayega")
    first = await llm.respond(llm.system, [h], llm.tools)
    assert [(c.name, c.args) for c in first.tool_calls] == [("check_availability", {"service": "root canal", "date": "2026-09-08"})]
    results = [ToolResult(name="check_availability", ok=True, spoken="Kal 9:30 khaali hai", data={"slots": 2})]
    second = await llm.respond(llm.system, [{**h, "results": results}], llm.tools)
    assert second.say.startswith("Kal subah saade 9 baje")
    contents = g.posts[1]["json"]["contents"]
    assert contents[-2] == {"role": "model", "parts": [call("check_availability", {"service": "root canal", "date": "2026-09-08"}, "fc_7", "SIG")]}, \
        "the model's parts go back unchanged, thought signature included"
    answer = contents[-1]["parts"][0]["functionResponse"]
    assert answer["name"] == "check_availability" and answer["id"] == "fc_7" and answer["response"]["ok"] is True


async def test_a_write_is_turned_into_the_packs_confirmation_question(pack, policy, registry, ctx):
    g = FakeGemini([[call("book_appointment", {"service": "root canal", "date": "2026-09-08", "time": "09:30",
                                               "staff": "Dr Sheikh", "customer_name": "Vijay Sharma", "phone": "9876543210"})]])
    llm = GeminiLLM(policy, pack, registry, client=g, api_key="k")
    turn = await llm.respond(llm.system, [step(ctx, "haan book kar do, Vijay Sharma 9876543210")], llm.tools)
    assert turn.tool_calls == [] and ctx.pending_confirmation["action"] == "book_appointment"
    assert "confirm" in turn.say.lower()


async def test_the_caller_s_yes_goes_through_the_policy_and_the_ledger(pack, backend, registry, ledger):
    g = FakeGemini([[call("book_appointment", {"service": "root canal", "date": "2026-09-08", "time": "09:30",
                                               "staff": "Dr Sheikh", "customer_name": "Vijay Sharma", "phone": "9876543210"})]])
    llm = GeminiLLM(DialoguePolicy(pack, backend, TENANT), pack, registry, client=g, api_key="k")
    session = CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry,
                          ledger=ledger, config=EngineConfig(), llm=llm)
    await session.open()
    asked = await session.handle_text_turn("root canal kal subah 9:30 Dr Sheikh, Vijay Sharma 9876543210")
    assert "confirm" in asked.said.lower() and not session.receipts
    await session.handle_text_turn("haan confirm kar do")
    assert session.ctx.outcome.value == "BOOKED" and len(session.receipts) == 1
    assert len(g.posts) == 1, "the confirmed yes never went to the model"


async def test_end_call_and_a_vendor_failure(pack, policy, registry, ctx):
    llm = GeminiLLM(policy, pack, registry, client=FakeGemini([[{"text": "Dhanyavaad."}, call("end_call", {})]]), api_key="k")
    turn = await llm.respond(llm.system, [step(ctx, "theek hai bye")], llm.tools)
    assert turn.end_call and turn.say == "Dhanyavaad."
    down = GeminiLLM(policy, pack, registry, client=FakeGemini([], fail=True), api_key="k")
    turn = await down.respond(down.system, [step(ctx, "mujhe root canal karwana hai")], down.tools)
    assert turn.say and down.fallbacks == 1


async def test_thoughts_are_never_spoken_and_the_factory_knows_gemini(pack, policy, registry, ctx):
    g = FakeGemini([[{"text": "planning the reply", "thought": True}, {"text": "Ji, bataiye."}]])
    llm = GeminiLLM(policy, pack, registry, client=g, api_key="k")
    turn = await llm.respond(llm.system, [step(ctx, "hello")], llm.tools)
    assert turn.say == "Ji, bataiye."
    assert isinstance(make_llm("gemini", policy, pack, registry), GeminiLLM)
