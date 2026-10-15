"""The Claude dialogue adapter: what it decides, and what it is never allowed to decide."""
from types import SimpleNamespace

import pytest

from haanji.adapters.claude import ClaudeLLM, build_tools
from haanji.adapters.factory import make_llm
from haanji.adapters.mock import MockLLM
from haanji.adapters.prompt import build_system_prompt, tool_schemas
from haanji.config import EngineConfig
from haanji.models import ConversationContext, Speaker, ToolResult, Turn
from haanji.pipeline import CallSession
from haanji.policy import DialoguePolicy

TENANT = "t_test"


# ── a scripted stand-in for anthropic.AsyncAnthropic ─────────────────────────
def text(t: str):
    return SimpleNamespace(type="text", text=t)


def tool_use(name: str, inp: dict, id: str = "tu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id=id)


class FakeMessages:
    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    async def create(self, **kw):
        self.calls.append(kw)
        content = self.script.pop(0)
        stop = "tool_use" if any(b.type == "tool_use" for b in content) else "end_turn"
        return SimpleNamespace(content=content, stop_reason=stop,
                               usage=SimpleNamespace(input_tokens=100, output_tokens=20))


class FakeClient:
    def __init__(self, script):
        self.messages = FakeMessages(script)


class ExplodingMessages:
    async def create(self, **kw):
        raise RuntimeError("vendor is down")


class ExplodingClient:
    messages = ExplodingMessages()


@pytest.fixture
def policy(pack, backend):
    return DialoguePolicy(pack, backend, TENANT)


@pytest.fixture
def ctx():
    c = ConversationContext(tenant_id=TENANT)
    c.add(Turn(1, Speaker.AGENT, "Haanji, Smile Care Dental. Main aapki kya madad karun?"))
    return c


def step(ctx, text_: str):
    ctx.add(Turn(len(ctx.turns) + 1, Speaker.CALLER, text_))
    return {"content": text_, "context": ctx}


async def test_a_text_reply_becomes_say(pack, policy, registry, ctx):
    llm = ClaudeLLM(policy, pack, registry, client=FakeClient([[text("Kis din ka time dekhun?")]]))
    turn = await llm.respond(llm.system, [step(ctx, "mujhe root canal karwana hai")], llm.tools)
    assert turn.say == "Kis din ka time dekhun?" and turn.tool_calls == [] and not turn.end_call
    [call] = llm.client.messages.calls
    assert call["model"] == llm.model and call["messages"][-1] == {"role": "user", "content": "mujhe root canal karwana hai"}
    assert pack.persona.business_name in call["system"][0]["text"]
    assert {t["name"] for t in call["tools"]} >= {"check_availability", "book_appointment", "end_call"}


async def test_a_read_only_tool_call_round_trips_with_its_id(pack, policy, registry, ctx):
    client = FakeClient([
        [tool_use("check_availability", {"service": "root canal", "date": "2026-09-08"}, "tu_7")],
        [text("Kal subah saade 9 baje khaali hai. Chalega?")],
    ])
    llm = ClaudeLLM(policy, pack, registry, client=client)
    h = step(ctx, "kal subah ka time mil jayega")
    first = await llm.respond(llm.system, [h], llm.tools)
    assert [(c.name, c.args) for c in first.tool_calls] == [("check_availability", {"service": "root canal", "date": "2026-09-08"})]
    results = [ToolResult(name="check_availability", ok=True, spoken="Kal 9:30 khaali hai", data={"slots": 2})]
    second = await llm.respond(llm.system, [{**h, "results": results}], llm.tools)
    assert second.say.startswith("Kal subah saade 9 baje") and second.tool_calls == []
    msgs = client.messages.calls[1]["messages"]
    assert msgs[-2]["role"] == "assistant" and msgs[-2]["content"][0].id == "tu_7"
    assert msgs[-1] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_7",
                                                      "content": msgs[-1]["content"][0]["content"]}]}
    assert '"ok": true' in msgs[-1]["content"][0]["content"]


async def test_a_write_is_turned_into_the_packs_confirmation_question(pack, policy, registry, ctx):
    client = FakeClient([[tool_use("book_appointment", {
        "service": "root canal", "date": "2026-09-08", "time": "09:30", "staff": "Dr Sheikh",
        "customer_name": "Vijay Sharma", "phone": "9876543210"})]])
    llm = ClaudeLLM(policy, pack, registry, client=client)
    turn = await llm.respond(llm.system, [step(ctx, "haan book kar do, Vijay Sharma 9876543210")], llm.tools)
    assert turn.tool_calls == [] and not turn.end_call
    assert ctx.pending_confirmation and ctx.pending_confirmation["action"] == "book_appointment"
    assert ctx.service == "root canal" and ctx.customer_name == "Vijay Sharma" and ctx.customer_phone == "9876543210"
    assert "confirm" in turn.say.lower()


async def test_a_confirmed_yes_goes_through_the_policy_and_the_ledger(pack, backend, registry, ledger):
    client = FakeClient([
        [tool_use("book_appointment", {"service": "root canal", "date": "2026-09-08", "time": "09:30",
                                       "staff": "Dr Sheikh", "customer_name": "Vijay Sharma", "phone": "9876543210"})],
    ])
    policy = DialoguePolicy(pack, backend, TENANT)
    llm = ClaudeLLM(policy, pack, registry, client=client)
    session = CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry,
                          ledger=ledger, config=EngineConfig(), llm=llm)
    await session.open()
    asked = await session.handle_text_turn("root canal kal subah 9:30 Dr Sheikh, Vijay Sharma 9876543210")
    assert "confirm" in asked.said.lower() and not session.receipts
    done = await session.handle_text_turn("haan confirm kar do")
    assert session.ctx.outcome is not None and session.ctx.outcome.value == "BOOKED"
    assert len(session.receipts) == 1 and "book_appointment" in done.tools
    assert len(client.messages.calls) == 1, "the confirmed yes never went to the model"


async def test_end_call_is_a_signal_not_a_tool(pack, policy, registry, ctx):
    llm = ClaudeLLM(policy, pack, registry, client=FakeClient([[text("Dhanyavaad, milte hain."), tool_use("end_call", {}, "tu_9")]]))
    turn = await llm.respond(llm.system, [step(ctx, "theek hai bye")], llm.tools)
    assert turn.say == "Dhanyavaad, milte hain." and turn.end_call and turn.tool_calls == []


async def test_a_vendor_failure_falls_back_to_the_policy(pack, policy, registry, ctx):
    llm = ClaudeLLM(policy, pack, registry, client=ExplodingClient())
    h = step(ctx, "mujhe root canal karwana hai")
    turn = await llm.respond(llm.system, [h], llm.tools)
    expected = await MockLLM(DialoguePolicy(pack, policy.backend, TENANT)).respond("", [step(ConversationContext(tenant_id=TENANT), h["content"])], [])
    assert turn.say == expected.say and llm.fallbacks == 1 and llm.calls == 1


def test_the_prompt_and_tools_describe_the_pack(pack, registry):
    system = build_system_prompt(pack)
    assert pack.persona.business_name in system and pack.language in system
    assert any(s.name in system for s in pack.services)
    if pack.guardrails.refuse_topics:
        assert pack.guardrails.refuse_topics[0] in system
    tools = build_tools(registry)
    names = {t["name"] for t in tools}
    assert {"check_availability", "search_knowledge", "book_appointment", "end_call"} <= names
    assert all("x-haanji" not in t and "input_schema" in t for t in tools)
    book = next(t for t in tools if t["name"] == "book_appointment")
    assert "confirm" in book["description"].lower()
    assert all("parameters" in s for s in tool_schemas(registry))


def test_the_factory_maps_names_to_adapters(pack, policy, registry):
    assert isinstance(make_llm("mock", policy, pack, registry), MockLLM)
    assert isinstance(make_llm("claude", policy, pack, registry, client=FakeClient([])), ClaudeLLM)
    with pytest.raises(ValueError):
        make_llm("nope", policy, pack, registry)


async def test_the_session_uses_the_mock_adapter_by_default(pack, backend, registry, ledger):
    session = CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry,
                          ledger=ledger, config=EngineConfig())
    assert isinstance(session.llm, MockLLM) and session.llm.name == "mock"


def test_the_dotenv_loader_fills_gaps_and_never_overrides(tmp_path, monkeypatch):
    from haanji.config import load_dotenv
    env = tmp_path / ".env"
    env.write_text("# local secrets\nANTHROPIC_API_KEY='sk-test'\nHAANJI_LLM_EFFORT=high\n\nbroken line\n")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("HAANJI_LLM_EFFORT", "low")
    assert load_dotenv(env) == 1
    import os
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-test" and os.environ["HAANJI_LLM_EFFORT"] == "low"
    assert load_dotenv(tmp_path / "missing.env") == 0
