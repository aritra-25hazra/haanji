"""Offline providers.

These stand in for a streaming recogniser, a language model and a speech
synthesiser. They are not toys: the recogniser emits growing partials with
per-word confidences at a realistic speaking rate, which is precisely the
signal Speculative Turn Execution consumes, and the synthesiser can be
cancelled mid-sentence, which is what barge-in needs. Running the whole system
offline is what makes the results in the report reproducible by anyone who
clones the repository.
"""
from __future__ import annotations
import random
from typing import AsyncIterator

from ..clock import CLOCK
from ..models import Token, Transcript
from ..scenario import Utterance
from . import LLMTurn

WORD_MS = 220.0          # nominal speaking rate of an Indian caller on the phone
TTS_WORD_MS = 170.0      # nominal synthesis-and-playback rate
HIGH = (0.90, 0.99)
LOW = (0.30, 0.62)


class MockSTT:
    """Streams partials word by word, marking the words it is unsure of."""

    name = "mock"

    def __init__(self, seed: int = 7, word_ms: float = WORD_MS):
        self.rng = random.Random(seed)
        self.word_ms = word_ms
        self.hints: list[str] = []
        self.hint_calls = 0

    def set_hints(self, hints: list[str]) -> None:
        self.hints = hints
        self.hint_calls += 1

    def _confidence(self, word: str, low_conf: set[str]) -> float:
        lo, hi = LOW if word.lower() in low_conf else HIGH
        conf = self.rng.uniform(lo, hi)
        # Biasing hints make the recogniser more certain about the tenant's own
        # vocabulary. A real provider does this inside its decoder; the effect
        # here is the same and it is applied to the same words.
        if any(word.lower() in h.lower().split() for h in self.hints):
            conf = min(0.995, conf + 0.03)
        return round(conf, 3)

    async def stream(self, utterance: Utterance | str) -> AsyncIterator[Transcript]:
        utt = utterance if isinstance(utterance, Utterance) else Utterance(str(utterance))
        low = {w.lower() for w in utt.low_conf}
        words = utt.heard.split()
        tokens: list[Token] = []
        elapsed = 0.0
        for word in words:
            await CLOCK.sleep_ms(self.word_ms)
            elapsed += self.word_ms
            tokens.append(Token(word, self._confidence(word, low),
                                int(elapsed - self.word_ms), int(elapsed)))
            yield Transcript(list(tokens), is_final=False)
        yield Transcript(list(tokens), is_final=True)


class MockTTS:
    """Speaks at a realistic rate and stops the moment it is cancelled."""

    name = "mock"

    def __init__(self, word_ms: float = TTS_WORD_MS):
        self.word_ms = word_ms
        self._cancelled = False
        self.spoken: list[str] = []
        self.interruptions = 0

    async def speak(self, text: str) -> AsyncIterator[bytes]:
        self._cancelled = False
        said: list[str] = []
        for word in text.split():
            if self._cancelled:
                self.interruptions += 1
                break
            await CLOCK.sleep_ms(self.word_ms)
            said.append(word)
            yield word.encode()
        self.spoken.append(" ".join(said))

    async def cancel(self) -> None:
        self._cancelled = True


class NullTTS(MockTTS):
    """Synthesis for channels where the client renders the speech itself —
    WhatsApp text, or a web call whose browser does the speaking. Emits the
    text instantly so an HTTP reply is never held up by simulated audio."""

    def __init__(self):
        super().__init__(word_ms=0.0)


class MockLLM:
    """Satisfies the LLM adapter protocol by delegating to the deterministic
    policy. Swapping in a hosted model means replacing this class and nothing
    else: the policy's decisions are already expressed as tool calls."""

    name = "mock"

    def __init__(self, policy):
        self.policy = policy
        self.calls = 0

    async def respond(self, system: str, history: list[dict], tools: list[dict]) -> LLMTurn:
        self.calls += 1
        return self.policy.plan(history[-1]["content"], history[-1]["context"])
