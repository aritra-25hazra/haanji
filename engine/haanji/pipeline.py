"""The turn controller: where the three contributions meet the call.

One pass through :meth:`CallSession.handle_utterance` is the whole hot path of
the product:

  audio  ->  partial transcripts
             |-> Bhasha Bridge corrects the tenant's own vocabulary
             |-> the predictor guesses a read-only tool and runs it early
         ->  final transcript
             -> guardrails
             -> dialogue policy
             -> tool execution, claiming any speculation that matches exactly
             -> Pramaan Ledger seals every write against the caller's own words
             -> speech, cancellable the instant the caller speaks again
"""
from __future__ import annotations
import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .adapters import LLMTurn
from .adapters.mock import MockSTT, MockTTS
from .backend.local import LocalBackend
from .bhasha.bridge import BhashaBridge
from .bhasha.lexicon import TenantLexicon
from .clock import CLOCK
from .config import EngineConfig
from .guardrails import Action, Guard
from .metrics import Metrics
from .models import (ConversationContext, Correction, Outcome, Speaker, Token,
                     ToolCall, ToolResult, Transcript, Turn)
from .policy import DialoguePolicy
from .pramaan.ledger import Ledger
from .pramaan.receipt import ConfirmationProof
from .scenario import Utterance
from .speculation.engine import SpeculationEngine
from .speculation.predictor import IntentPredictor
from .tools import ToolRegistry
from .vertical import Pack

MAX_TOOL_ROUNDS = 3


@dataclass
class TurnRecord:
    seq: int
    heard: str
    corrected: str
    said: str
    corrections: list[Correction] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    speculation_hits: list[str] = field(default_factory=list)
    truth: str = ""
    guard: str = ""
    latency_ms: float = 0.0
    interrupted: bool = False
    all_read_only: bool = False


@dataclass
class CallReport:
    conversation_id: str
    tenant_id: str
    pack_id: str
    outcome: Outcome
    turns: list[TurnRecord]
    speculation: dict[str, Any]
    corrections: int
    receipts: list[str]
    metrics: Metrics

    @property
    def latencies(self) -> list[float]:
        return [t.latency_ms for t in self.turns if t.latency_ms > 0]

    @property
    def tool_latencies(self) -> list[float]:
        return [t.latency_ms for t in self.turns if t.tools]

    @property
    def read_latencies(self) -> list[float]:
        """Turns whose work was entirely read-only — the only ones speculation
        can help. Write turns are excluded because speculating a write is
        forbidden by construction, so including them would understate and then
        misattribute the effect."""
        return [t.latency_ms for t in self.turns if t.tools and t.all_read_only]


class CallSession:
    """One phone call. Everything with per-call state lives here."""

    def __init__(self, *, tenant_id: str, pack: Pack, backend: LocalBackend,
                 registry: ToolRegistry, ledger: Ledger | None = None,
                 config: EngineConfig | None = None, stt: MockSTT | None = None,
                 tts: MockTTS | None = None, metrics: Metrics | None = None,
                 lexicon: TenantLexicon | None = None):
        self.cfg = config or EngineConfig()
        self.tenant_id = tenant_id
        self.pack = pack
        self.backend = backend
        self.registry = registry
        self.ledger = ledger
        self.metrics = metrics or Metrics()

        self.lexicon = lexicon or TenantLexicon.build(version=pack.version, **pack.lexicon_seed())
        self.bhasha = BhashaBridge(self.lexicon, self.cfg.bhasha)
        self.guard = Guard(pack)
        self.policy = DialoguePolicy(pack, backend, tenant_id)
        self.stt = stt or MockSTT()
        self.tts = tts or MockTTS()
        self.stt.set_hints(self.bhasha.hints())

        self.ctx = ConversationContext(tenant_id=tenant_id)
        self.speculation = SpeculationEngine(
            tenant_id, self._execute_tool, registry.is_read_only, self.cfg.speculation,
            IntentPredictor(services=pack.service_aliases()))
        self.turns: list[TurnRecord] = []
        self.receipts: list[str] = []
        self._seq = 0
        self._speaking: asyncio.Task | None = None

    # ------------------------------------------------------------------ speech
    async def say(self, text: str) -> None:
        """Start speaking. Returns as soon as audio is on its way, because the
        caller can interrupt at any point and the loop has to be listening
        while the agent talks."""
        if not text:
            return
        await self._finish_speaking()
        self.ctx.last_agent_utterance = text
        self.ctx.last_agent_started_ms = int(time.time() * 1000)
        self._speaking = asyncio.ensure_future(self._speak(text))

    async def _speak(self, text: str) -> None:
        async for _ in self.tts.speak(text):
            pass
        self.ctx.add(Turn(self._next_seq(), Speaker.AGENT, text))

    async def _finish_speaking(self) -> None:
        """Let the current line play out — the caller waited politely."""
        if self._speaking is not None:
            await self._speaking
            self._speaking = None

    async def _cut_off_speaking(self) -> bool:
        """Barge-in: stop mid-word. Returns whether anything was actually cut."""
        if self._speaking is None or self._speaking.done():
            await self._finish_speaking()
            return False
        await self.tts.cancel()
        await self._speaking
        self._speaking = None
        return True

    async def hangup(self) -> None:
        await self._finish_speaking()

    async def open(self, *, phone: str | None = None) -> None:
        """Answer the call. When the channel already knows the caller's number,
        a returning customer is looked up and greeted by name, and the number
        is pre-filled so the policy never asks for it again."""
        customer = None
        if phone:
            self.ctx.customer_phone = phone
            found = await self.backend.lookup_customer(self.tenant_id, phone)
            if found.get("found"):
                customer = found["customer"]
                if customer.get("name"):
                    self.ctx.customer_name = customer["name"]
        await self.say(self.policy.greeting(customer))
        await self._finish_speaking()

    # ------------------------------------------------------------------- turn
    async def handle_utterance(self, utterance: Utterance | str) -> TurnRecord:
        utt = utterance if isinstance(utterance, Utterance) else Utterance(str(utterance))
        self.speculation.begin_turn()

        if not utt.barge_in:
            await self._finish_speaking()        # the caller let the agent finish

        final: Transcript | None = None
        interrupted = False
        first_partial = True
        async for partial in self.stt.stream(utt):
            if partial.is_final:
                final = partial
                break
            if first_partial:
                first_partial = False
                interrupted = await self._cut_off_speaking()
            # Correct the partial before predicting from it: a prediction made
            # on a mangled service name would produce arguments the real turn
            # never asks for, and would be wasted work.
            partial_text = self.bhasha.correct(partial).text
            self.speculation.on_partial(partial_text, self.ctx)

        assert final is not None
        return await self._complete_turn(final, interrupted, truth=utt.truth)

    # Words a text channel treats as confidently known. Everything else is a
    # candidate for repair — the text-channel analogue of low ASR confidence
    # is "not a word this tenant or this language model of ours knows".
    _COMMON_TEXT = {
        "hello", "hi", "namaste", "nomoshkar", "please", "sir", "madam", "mujhe",
        "muze", "apna", "apni", "wali", "wala", "karna", "karni", "hai", "hain",
        "kar", "do", "kijiye", "dijiye", "lena", "dena", "sakta", "sakti", "hoon",
        "number", "phone", "mobile", "clinic", "salon", "lab", "test", "doctor",
        "price", "prices", "cost", "rate", "amount", "rupees", "taka", "rupaye",
        "morning", "evening", "message", "whatsapp", "call", "help", "madad",
    }

    def _known_text_words(self) -> set[str]:
        if not hasattr(self, "_known_cache"):
            from . import nlu
            from .policy import GOODBYE
            known: set[str] = set(self._COMMON_TEXT) | set(GOODBYE)
            for group in (nlu.DATE_WORDS, nlu.TIME_WORDS, nlu.BOOKING_VERBS,
                          nlu.QUESTION_WORDS, nlu.IDENTITY_WORDS, nlu.CANCEL_WORDS,
                          nlu.HANDOFF_WORDS, nlu.YES_WORDS, nlu.NO_WORDS):
                known |= group
            for entry in self.lexicon.entries:
                for form in entry.forms():
                    known |= {w.lower() for w in form.split()}
            self._known_cache = known
        return self._known_cache

    def _text_transcript(self, text: str, final: bool) -> Transcript:
        """Per-token confidence for a channel that has no recogniser.

        A token the tenant's lexicon or our shared vocabulary already knows is
        marked confident and is therefore never touched (Bhasha's condition 1
        fails for it, exactly as it does for confidently-recognised speech).
        An out-of-vocabulary token is the text analogue of a low-confidence
        one, so the same two-condition repair applies to it."""
        known = self._known_text_words()
        # A reply to a question that asked for the caller's name IS a name:
        # nothing in it may be "repaired", however unusual it looks. This is
        # the text-channel form of the phone path's name guard.
        asked_name = bool(re.search(r"\b(naam|name)\b", self.ctx.last_agent_utterance,
                                    re.IGNORECASE))
        tokens = [Token(w, 0.95 if asked_name or w.lower().strip('.,!?') in known
                        or w.isdigit() else 0.62)
                  for w in text.split()]
        return Transcript(tokens, is_final=final)

    async def handle_partial_text(self, text: str) -> None:
        """A partial transcript that arrived as text — the web-call path.

        In the browser channel the recogniser runs client-side and sends its
        interim results here, so speculation gets the same early signal it has
        on the telephone path. Corrections run first for the same reason as in
        :meth:`handle_utterance`."""
        if not text.strip():
            return
        corrected = self.bhasha.correct(self._text_transcript(text, final=False)).text
        self.speculation.on_partial(corrected, self.ctx)

    async def handle_text_turn(self, text: str, *, confidence: float | None = None,
                               interrupted: bool = False) -> TurnRecord:
        """One caller turn that arrived as text — WhatsApp, or a web call whose
        recogniser lives in the browser. Runs the identical hot path: correction,
        guardrails, policy, tools with speculation claims, and the ledger.

        ``confidence`` is the browser recogniser's utterance-level figure when
        one exists; it is recorded into the confirmation proof, while the
        per-token repair decision uses the out-of-vocabulary model above."""
        self.speculation.begin_turn()
        await self._finish_speaking()
        final = self._text_transcript(text, final=True)
        if confidence is not None:
            for token in final.tokens:
                token.confidence = min(token.confidence, max(confidence, 0.3))                     if token.confidence < 0.95 else token.confidence
        return await self._complete_turn(final, interrupted)

    async def _complete_turn(self, final: Transcript, interrupted: bool,
                             truth: str = "") -> TurnRecord:
        t0 = time.perf_counter()
        corrected = self.bhasha.correct(final)
        self.metrics.observe("bhasha_ms", CLOCK.nominal(corrected.elapsed_ms))
        self.metrics.inc("corrections", len(corrected.corrections))

        record = TurnRecord(self._seq, final.text, corrected.text, "",
                            corrections=list(corrected.corrections), interrupted=interrupted)
        record.truth = truth or final.text
        self.ctx.add(Turn(self._next_seq(), Speaker.CALLER, corrected.text,
                          corrections=list(corrected.corrections)))
        caller_confidence = min((t.confidence for t in final.tokens), default=1.0)
        caller_started_ms = int(time.time() * 1000)

        verdict = self.guard.check(corrected.text)
        if verdict.action is Action.ESCALATE:
            record.guard = verdict.rule
            turn = LLMTurn(tool_calls=[ToolCall("handoff", {"reason": verdict.rule})])
        elif verdict.action is Action.REFUSE:
            record.guard = verdict.rule
            turn = LLMTurn(tool_calls=[ToolCall("handoff", {"reason": verdict.rule})])
        else:
            turn = self.policy.plan(corrected.text, self.ctx)

        rounds = 0
        while turn.tool_calls and rounds < MAX_TOOL_ROUNDS:
            rounds += 1
            results = await self._run_tools(turn.tool_calls, corrected.text,
                                            caller_confidence, caller_started_ms, record)
            turn = self.policy.after_tools(corrected.text, self.ctx, results)

        if verdict.action is not Action.ALLOW and not turn.say:
            turn = LLMTurn(say=verdict.line, end_call=True)

        record.latency_ms = CLOCK.nominal((time.perf_counter() - t0) * 1000)
        record.all_read_only = bool(record.tools) and all(
            self.registry.is_read_only(t) for t in record.tools)
        self.metrics.observe("turn_latency_ms", record.latency_ms)
        if record.all_read_only:
            self.metrics.observe("read_turn_latency_ms", record.latency_ms)
        if record.tools:
            # The only latency comparison that means anything is over turns
            # that actually had work to do. Turns the policy answers from
            # state finish in microseconds and would swamp the median.
            self.metrics.observe("tool_turn_latency_ms", record.latency_ms)
        record.said = turn.say
        self.turns.append(record)

        await self.speculation.end_turn()
        await self.say(turn.say)
        if turn.end_call:
            await self._finish_speaking()
            self.ctx.flags["ended"] = True
        return record

    # ------------------------------------------------------------------ tools
    async def _run_tools(self, calls: list[ToolCall], transcript_text: str,
                         confidence: float, caller_started_ms: int,
                         record: TurnRecord) -> list[ToolResult]:
        results: list[ToolResult] = []
        for call in calls:
            record.tools.append(call.name)
            if self.registry.is_read_only(call.name):
                cached = await self.speculation.claim(call.name, call.args)
                if cached is not None:
                    record.speculation_hits.append(call.name)
                    self.metrics.inc("speculation_hits")
                    cached.from_speculation = True
                    results.append(cached)
                    continue
            args = dict(call.args)
            if self.registry.requires_confirmation(call.name) or \
                    self.registry.get(call.name).ledgered:
                args["proof"] = self._proof(transcript_text, confidence, caller_started_ms)
                args["excerpt"] = Guard.redact(self.ctx.transcript(4))
                args["conversation_id"] = self.ctx.conversation_id
            result = await self._execute_tool(call.name, args)
            if not self.registry.is_read_only(call.name):
                self.speculation.on_write()     # invalidate: the world just changed
            if isinstance(result, ToolResult) and result.ok and result.data:
                code = (result.data or {}).get("receipt_code")
                if code:
                    self.receipts.append(code)
            results.append(result)
        return results

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> ToolResult:
        t0 = time.perf_counter()
        result = await self.registry.execute(name, args)
        if isinstance(result, ToolResult):
            result.duration_ms = int(CLOCK.nominal((time.perf_counter() - t0) * 1000))
            self.metrics.observe(f"tool_{name}_ms", result.duration_ms)
        self.metrics.inc(f"tool_{name}")
        return result

    def _proof(self, reply_text: str, confidence: float, reply_started_ms: int) -> ConfirmationProof:
        """Bind the write to the exact words that authorised it."""
        return ConfirmationProof(
            prompt_text=self.ctx.last_agent_utterance,
            prompt_start_ms=self.ctx.last_agent_started_ms,
            reply_text=reply_text,
            reply_start_ms=reply_started_ms,
            asr_confidence=round(confidence, 3),
            audio_offset_ms=max(0, reply_started_ms - self.ctx.last_agent_started_ms))

    # ------------------------------------------------------------------ close
    def finish(self) -> CallReport:
        outcome = self.ctx.outcome
        if outcome is None:
            outcome = (Outcome.FAQ_ANSWERED if self.ctx.answered_questions
                       else Outcome.ABANDONED)
        self.metrics.inc(f"outcome_{outcome.value}")
        return CallReport(
            conversation_id=self.ctx.conversation_id, tenant_id=self.tenant_id,
            pack_id=self.pack.pack_id, outcome=outcome, turns=self.turns,
            speculation=self.speculation.stats.as_dict(),
            corrections=sum(len(t.corrections) for t in self.turns),
            receipts=self.receipts, metrics=self.metrics)

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq


async def run_scenario(scenario, *, pack: Pack, backend: LocalBackend,
                       registry: ToolRegistry, ledger: Ledger | None = None,
                       config: EngineConfig | None = None,
                       tenant_id: str = "t_demo",
                       metrics: Metrics | None = None,
                       seed: int = 7) -> tuple[CallSession, CallReport]:
    session = CallSession(tenant_id=tenant_id, pack=pack, backend=backend, registry=registry,
                          ledger=ledger, config=config, metrics=metrics, stt=MockSTT(seed=seed))
    await session.open()
    for utt in scenario.utterances:
        await session.handle_utterance(utt)
        if session.ctx.flags.get("ended"):
            break
    await session.hangup()
    return session, session.finish()
