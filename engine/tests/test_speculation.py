"""Speculative Turn Execution is only safe because of four properties. Each one
has a test, and each test is written to fail loudly if the property is weakened.
"""
import asyncio

import pytest

from haanji.config import SpeculationConfig
from haanji.models import ConversationContext
from haanji.speculation.cache import SpeculationCache, speculation_key
from haanji.speculation.engine import SpeculationEngine
from haanji.speculation.predictor import IntentPredictor

TENANT = "t_spec"


class Recorder:
    def __init__(self, delay_ms=5.0):
        self.calls = []
        self.delay_ms = delay_ms

    async def __call__(self, name, args):
        self.calls.append((name, dict(args)))
        await asyncio.sleep(self.delay_ms / 1000)
        return {"tool": name, "args": args}


READ_ONLY = {"check_availability", "search_knowledge", "lookup_customer"}


def engine(recorder, **overrides):
    cfg = SpeculationConfig(**{"min_partial_words": 3, **overrides})
    return SpeculationEngine(TENANT, recorder, lambda n: n in READ_ONLY, cfg,
                             IntentPredictor(services=["root canal", "teeth cleaning"]))


def ctx():
    return ConversationContext(tenant_id=TENANT)


async def test_a_read_only_tool_is_executed_early_and_claimed():
    rec = Recorder()
    eng = engine(rec)
    eng.begin_turn()
    fired = eng.on_partial("kal subah root canal ka slot", ctx())
    assert fired and fired[0].tool == "check_availability"
    await asyncio.sleep(0.02)
    result = await eng.claim("check_availability", fired[0].args)
    assert result is not None
    assert eng.stats.hits == 1
    await eng.end_turn()


async def test_purity_a_write_is_never_speculated():
    rec = Recorder()
    eng = engine(rec)

    class WriteOnly(IntentPredictor):
        def predict(self, partial, c):
            from haanji.speculation.predictor import ToolGuess
            return [ToolGuess("book_appointment", 0.99, {"service": "root canal"})]

    eng.predictor = WriteOnly()
    eng.begin_turn()
    assert eng.on_partial("kal subah root canal book kar do", ctx()) == []
    assert rec.calls == []
    await eng.end_turn()


async def test_argument_identity_a_different_argument_does_not_claim():
    rec = Recorder()
    eng = engine(rec)
    eng.begin_turn()
    fired = eng.on_partial("kal subah root canal ka slot", ctx())
    await asyncio.sleep(0.02)
    other = dict(fired[0].args) | {"date": "today"}
    assert await eng.claim("check_availability", other) is None
    assert eng.stats.hits == 0
    await eng.end_turn()


async def test_a_result_can_only_be_claimed_once():
    rec = Recorder()
    eng = engine(rec)
    eng.begin_turn()
    fired = eng.on_partial("kal subah root canal ka slot", ctx())
    await asyncio.sleep(0.02)
    assert await eng.claim("check_availability", fired[0].args) is not None
    assert await eng.claim("check_availability", fired[0].args) is None
    await eng.end_turn()


async def test_a_write_invalidates_everything_computed_before_it():
    rec = Recorder()
    eng = engine(rec)
    eng.begin_turn()
    fired = eng.on_partial("kal subah root canal ka slot", ctx())
    await asyncio.sleep(0.02)
    eng.on_write()
    assert await eng.claim("check_availability", fired[0].args) is None
    assert eng.stats.wasted >= 1
    await eng.end_turn()


async def test_stale_results_expire():
    rec = Recorder()
    eng = engine(rec, ttl_ms=10)
    eng.begin_turn()
    fired = eng.on_partial("kal subah root canal ka slot", ctx())
    await asyncio.sleep(0.05)
    assert await eng.claim("check_availability", fired[0].args) is None
    await eng.end_turn()


async def test_the_budget_bounds_wasted_work():
    rec = Recorder()
    eng = engine(rec, max_per_turn=1, max_inflight=1)
    eng.begin_turn()
    eng.on_partial("kal subah root canal ka slot chahiye", ctx())
    eng.on_partial("kal subah teeth cleaning ka slot chahiye", ctx())
    eng.on_partial("parso shaam root canal ka slot chahiye", ctx())
    await asyncio.sleep(0.02)
    assert len(rec.calls) <= 1
    await eng.end_turn()


async def test_the_same_prediction_twice_costs_one_call():
    rec = Recorder()
    eng = engine(rec)
    eng.begin_turn()
    eng.on_partial("kal subah root canal ka slot", ctx())
    eng.on_partial("kal subah root canal ka slot chahiye mujhe", ctx())
    await asyncio.sleep(0.02)
    assert len(rec.calls) == 1
    await eng.end_turn()


async def test_disabled_speculation_never_runs_anything():
    rec = Recorder()
    eng = engine(rec, enabled=False)
    eng.begin_turn()
    assert eng.on_partial("kal subah root canal ka slot", ctx()) == []
    assert await eng.claim("check_availability", {"a": 1}) is None
    await eng.end_turn()


async def test_very_short_partials_are_ignored():
    rec = Recorder()
    eng = engine(rec)
    eng.begin_turn()
    assert eng.on_partial("kal", ctx()) == []
    await eng.end_turn()


def test_the_key_is_stable_and_argument_order_free():
    a = speculation_key(TENANT, "t", {"x": 1, "y": 2})
    b = speculation_key(TENANT, "t", {"y": 2, "x": 1})
    c = speculation_key("other", "t", {"x": 1, "y": 2})
    assert a == b and a != c


async def test_a_failing_speculation_is_a_miss_not_a_crash():
    async def boom(name, args):
        raise RuntimeError("provider down")
    eng = engine(boom)
    eng.begin_turn()
    fired = eng.on_partial("kal subah root canal ka slot", ctx())
    await asyncio.sleep(0.02)
    assert await eng.claim("check_availability", fired[0].args) is None
    await eng.end_turn()


def test_the_predictor_stays_quiet_on_a_pure_question():
    p = IntentPredictor(services=["root canal"])
    guesses = p.predict("root canal ka kitna charge hai", ctx())
    assert all(g.tool != "check_availability" for g in guesses)
    assert any(g.tool == "search_knowledge" for g in guesses)


def test_the_predictor_refuses_to_guess_on_a_cancellation():
    p = IntentPredictor(services=["root canal"])
    guesses = p.predict("kal ka appointment cancel karna hai", ctx())
    assert all(g.tool != "check_availability" for g in guesses)
