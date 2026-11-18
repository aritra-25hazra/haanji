"""The console's help assistant: answers questions about HaanJi and how to
use the console. It is not the receptionist and never touches a shop's data.

Two hosted models can answer, Claude (Anthropic) and Gemini (Google); the
person asking can pick one in the widget. Each is on only when its key is
set (ANTHROPIC_API_KEY, GEMINI_API_KEY). With neither key, or when the
vendor fails, a small built-in FAQ answers instead, so the widget always
replies. Every reply says which one answered.

Cost is bounded three ways: a short history (the last few turns), a capped
reply length, and a daily cap on hosted replies for the whole server
(HAANJI_HELP_DAILY_LIMIT, default 100); past the cap the FAQ answers.

Environment:
    HAANJI_HELP              off  -> the widget answers from the FAQ only
    ANTHROPIC_API_KEY        turns Claude on
    HAANJI_HELP_CLAUDE_MODEL default claude-opus-4-8
    GEMINI_API_KEY           turns Gemini on (GOOGLE_API_KEY is accepted too)
    HAANJI_HELP_GEMINI_MODEL default gemini-3.5-flash-lite
    HAANJI_HELP_DAILY_LIMIT  hosted replies per UTC day, default 100
"""
from __future__ import annotations
import asyncio
import datetime as dt
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal

log = logging.getLogger("haanji.help")

Provider = Literal["claude", "gemini", "faq"]
CLAUDE_MODEL = "claude-opus-4-8"
GEMINI_MODEL = "gemini-3.5-flash-lite"     # a help answer wants speed; Flash-Lite with minimal thinking
MAX_TURNS = 8                  # history sent to a model
MAX_CHARS = 1200               # per message
MAX_REPLY_TOKENS = 700
TIMEOUT_S = 15.0               # Claude; Gemini thinks first, so it gets GEMINI_TIMEOUT_S
GEMINI_TIMEOUT_S = 30.0
_SECRET = re.compile(r"(sk-ant-[A-Za-z0-9_\-]+|AIza[0-9A-Za-z_\-]{20,})")


def _thinking(model: str) -> str:
    """The least thinking the model accepts: Flash-Lite and most Flash models
    take MINIMAL; gemini-3.8-flash starts at LOW."""
    return "LOW" if "3.8-flash" in model and "lite" not in model else "MINIMAL"


BENCH_S = 3600.0


def _operator_must_fix(exc: Exception) -> bool:
    """A refusal that retrying cannot cure: no credit, a bad or unauthorised key."""
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    text = describe_error(exc).lower()
    return status in (401, 403) or "credit balance" in text or "billing" in text or "api key not valid" in text


def describe_error(exc: Exception) -> str:
    """What went wrong with a vendor, for the operator: the error's kind, the
    HTTP status and the vendor's short reason. Anything shaped like a key is
    blanked out."""
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    reason = ""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error") or {}
        reason = f"{err.get('type', '')}: {err.get('message', '')}" if isinstance(err, dict) else str(err)
    resp = getattr(exc, "response", None)
    if not reason and resp is not None:
        try:
            err = (resp.json() or {}).get("error") or {}
            reason = f"{err.get('status', '')}: {err.get('message', '')}"
        except Exception:                                  # noqa: BLE001 - not JSON
            reason = ""
    text = " ".join(x for x in (type(exc).__name__, str(status or ""), reason.strip(": ")) if x)
    return _SECRET.sub("[key]", text)[:240]

GUIDE = """You are the help assistant inside HaanJi's web console. HaanJi is an AI voice
receptionist for small Indian businesses (dental clinics, salons, diagnostic labs,
coaching centres). It answers the shop's phone and WhatsApp in Hinglish, books
appointments, and keeps a signed receipt (Pramaan) for every booking.

The console's pages:
- Today (/dashboard): today's calls, bookings, callbacks to make, misheard-and-fixed words, revenue booked, calls by hour.
- Calendar (/calendar): the week as a time grid, one lane and colour per staff member; day view; add or move a booking.
- Customers (/customers): every caller with visits, no-shows and upcoming bookings; open one to see their whole record, call or WhatsApp them.
- Calls (/calls): every call with filters by outcome, channel, day and number; open one for the transcript, the corrections and the receipt.
- Settings (/settings, owner only): WhatsApp reminders, deposit, waitlist, the evening digest, the receptionist cost used for "rupees per call", users.
- Engine menu: How it works (/how), Pramaan (/ledger: verify receipts), Bhasha (/lexicon: the shop's words), Packs (/packs), Studio (/studio: edit a pack and run its scenarios), New shop (/onboard: a new business in 5 questions), Ops (/ops: reply speed and counters).
- The Sample switch in the top bar shows a made-up shop with 100 customers, for a demo; nothing in it is real. The EN / हिं switch changes the console's language.
- "Talk" opens a page where anyone can talk to the receptionist in the browser.

The three ideas, as measured by the project's benchmark on simulated calls (not live customers):
{measured}

How a call works: the caller speaks; Bhasha repairs misheard shop words against the shop's own word list;
the agent asks one thing at a time (service, day and time, name, number) and says when a time is free;
read-only lookups (free slots) start early while the caller is still talking; nothing is booked until the
caller says yes to a read-back; the booking and that yes are sealed into a Pramaan receipt.

Rules:
- Answer only questions about HaanJi and using this console. For anything else, say briefly that you can only help with HaanJi.
- Be short: two to five sentences, or a few numbered steps. Plain words, no marketing.
- Write plain text only: no markdown, no links, no asterisks. Name a page in words ("the Calendar page"), not as a path.
- Reply in the language the person writes in. If they write Hinglish or Hindi, reply in Roman-script Hinglish.
- Never invent numbers, prices, customers or features. Prices are "on request"; suggest asking for a demo.
  Quote only the measured numbers above, and say they come from simulated calls.
- You cannot see the shop's data, bookings or calls. If asked, point to the page where they can look.
- Never ask for passwords, OTPs, keys or payment details."""
PAGE_NOTE = "The person is on the console page: {page}"

FAQ: list[tuple[tuple[str, ...], str, str]] = [
    (("haanji", "about", "kaun", "who", "receptionist"),
     "HaanJi is an AI receptionist for small shops. It answers the phone and WhatsApp in Hinglish, books the appointment in your calendar, and keeps a signed receipt of what the caller agreed to.",
     "HaanJi chhoti dukaanon ka AI receptionist hai. Phone aur WhatsApp Hinglish mein uthata hai, appointment calendar mein book karta hai, aur caller ne jo maana uski signed receipt rakhta hai."),
    (("try", "talk", "demo", "test", "baat", "dekhna"),
     "Click Talk in the top bar to talk to the receptionist in your browser. To see a full shop, turn on the Sample switch: it shows a made-up shop with 100 customers.",
     "Upar Talk dabao aur browser mein receptionist se baat karo. Poori dukaan dekhni ho to Sample switch on karo: 100 nakli customers ki ek dukaan dikhegi."),
    (("sample", "fake", "nakli", "real", "asli", "data"),
     "Sample mode is a made-up shop for demos; nothing in it is real. Turn the Sample switch off to see the live engine's data.",
     "Sample mode demo ke liye nakli dukaan hai; isme kuch bhi asli nahi. Asli data ke liye Sample switch band karo."),
    (("book", "booking", "appointment", "slot", "calendar"),
     "The caller says the service and a time; HaanJi says if that time is free, asks the name and number, reads it back, and books only after a yes. You see it on the Calendar page.",
     "Caller service aur time batata hai; HaanJi batata hai time khaali hai ya nahi, naam aur number poochta hai, padh ke sunata hai, aur haan ke baad hi book karta hai. Calendar page pe dikh jaata hai."),
    (("pramaan", "receipt", "proof", "verify", "ledger", "saboot"),
     "Pramaan seals every booking and the caller's yes into a signed receipt. Any later edit shows up when the receipt is verified on the Pramaan page.",
     "Pramaan har booking aur caller ki haan ko ek signed receipt mein seal karta hai. Baad mein koi badlaav ho to Pramaan page pe verify karte hi pakda jaata hai."),
    (("bhasha", "misheard", "wrong", "galat", "word", "shabd", "suna"),
     "Speech recognisers mishear shop words, like 'route canal' for 'root canal'. Bhasha checks the shop's own word list and fixes a word only when it is sure. The Bhasha page lists the words.",
     "Speech recogniser dukaan ke shabd galat sunte hain, jaise 'root canal' ki jagah 'route canal'. Bhasha dukaan ki apni list se milata hai aur pakka ho tabhi theek karta hai. Bhasha page pe saare shabd hain."),
    (("price", "cost", "pricing", "kitna", "paisa", "plan", "rupaye", "buy", "kharid"),
     "Prices are on request. Ask for a demo on WhatsApp from the home page, and we set up a pilot for your shop.",
     "Price ke liye baat karni hogi. Home page se WhatsApp pe demo maango, hum aapki dukaan ke liye pilot set up karenge."),
    (("whatsapp", "reminder", "message"),
     "HaanJi answers WhatsApp like the phone, and sends the customer a reminder before the visit. Turn reminders on or off in Settings.",
     "HaanJi WhatsApp bhi phone ki tarah uthata hai, aur visit se pehle customer ko reminder bhejta hai. Settings mein reminder on/off karo."),
    (("new", "shop", "onboard", "add", "business", "nayi", "dukaan"),
     "Open Engine → New shop. Answer 5 questions (name, hours, services, staff, language) and HaanJi writes the pack, checks it and runs its scenarios.",
     "Engine → Nayi dukaan kholo. 5 sawaal ka jawab do (naam, time, services, staff, bhasha) aur HaanJi pack likh ke check karta hai aur scenarios chalata hai."),
    (("slow", "waking", "loading", "offline", "jaag", "load", "sleep"),
     "The engine runs on a free server that sleeps when idle; the first visit takes 30–60 seconds to wake it. Meanwhile you can look at the sample shop.",
     "Engine free server pe hai jo khaali hone pe so jaata hai; pehli baar jaagne mein 30–60 second lagte hain. Tab tak sample dukaan dekh sakte ho."),
    (("language", "hindi", "english", "switch"),
     "Use the EN / हिं switch in the top bar to change the console's language. The receptionist itself always speaks the shop's language.",
     "Upar EN / हिं switch se console ki bhasha badlo. Receptionist khud hamesha dukaan ki bhasha mein bolta hai."),
    (("callback", "missed", "lead", "wapas"),
     "Calls that could not finish the job are listed under 'Needs a callback' on the Today page, urgent ones first, with the line that triggered it.",
     "Jo calls kaam poora nahi kar paayi, wo Today page pe 'Callback chahiye' mein hain, urgent pehle, aur wajah wali line ke saath."),
]
FALLBACK = ("I can help with HaanJi and this console: how a booking works, the pages, sample mode, Pramaan, Bhasha, or asking for a demo. What would you like to know?",
            "Main HaanJi aur is console mein madad kar sakta hoon: booking kaise hoti hai, pages, sample mode, Pramaan, Bhasha, ya demo maangna. Kya jaanna hai?")
HINGLISH = re.compile(r"\b(kya|hai|kaise|kaha|kahan|nahi|karo|kar|mujhe|mera|aap|hota|chahiye|kyun|kab|batao|dikhao)\b", re.I)


def faq_answer(question: str, lang: str = "en") -> str:
    words = set(re.findall(r"[a-zऀ-ॿ]+", question.lower()))
    hindi = lang == "hi" or bool(HINGLISH.search(question))
    best, score = None, 0
    for keys, en, hi in FAQ:
        s = sum(1 for k in keys if k in words)
        if s > score:
            best, score = (en, hi), s
    en, hi = best if best and score > 0 else FALLBACK
    return hi if hindi else en


@dataclass
class HelpBot:
    measured: str = ""
    enabled: bool = True
    daily_limit: int = 100
    claude_model: str = CLAUDE_MODEL
    gemini_model: str = GEMINI_MODEL
    claude_key: str | None = None
    gemini_key: str | None = None
    _claude: Any = None
    _http: Any = None
    _day: str = ""
    last_error: dict = field(default_factory=dict)
    down_until: dict = field(default_factory=dict)      # provider -> time.monotonic() it may be tried again
    _used: int = 0
    usage: dict = field(default_factory=lambda: {"claude": {"replies": 0, "input": 0, "output": 0},
                                                 "gemini": {"replies": 0, "input": 0, "output": 0}, "faq": {"replies": 0}})

    @classmethod
    def from_env(cls, measured: str = "") -> "HelpBot":
        env = os.environ
        return cls(measured=measured, enabled=env.get("HAANJI_HELP", "on").lower() not in ("off", "0", "false", "no"),
                   daily_limit=int(env.get("HAANJI_HELP_DAILY_LIMIT", "100")),
                   claude_model=env.get("HAANJI_HELP_CLAUDE_MODEL") or CLAUDE_MODEL,
                   gemini_model=env.get("HAANJI_HELP_GEMINI_MODEL") or GEMINI_MODEL,
                   claude_key=env.get("ANTHROPIC_API_KEY") or None,
                   gemini_key=env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY") or None)

    # ------------------------------------------------------------ status
    def providers(self) -> list[Provider]:
        """The answerers to offer: a key is set, and the vendor has not just
        refused us for something only the operator can fix (no credit, a bad
        key); that one rests for BENCH_S and is not offered meanwhile."""
        now = time.monotonic()
        out: list[Provider] = []
        if self.enabled and self.claude_key and self.down_until.get("claude", 0) <= now:
            out.append("claude")
        if self.enabled and self.gemini_key and self.down_until.get("gemini", 0) <= now:
            out.append("gemini")
        return out + ["faq"]

    def status(self) -> dict:
        return {"providers": self.providers(), "models": {"claude": self.claude_model, "gemini": self.gemini_model},
                "daily_limit": self.daily_limit, "used_today": self._used_today(),
                "last_error": dict(self.last_error)}

    def _used_today(self) -> int:
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        if today != self._day:
            self._day, self._used = today, 0
        return self._used

    # ------------------------------------------------------------ answer
    async def answer(self, messages: list[dict], *, provider: str | None = None, lang: str = "en",
                     page: str = "/") -> dict:
        turns = clean(messages)
        if not turns or turns[-1]["role"] != "user":
            return {"reply": FALLBACK[1 if lang == "hi" else 0], "provider": "faq", "model": None}
        question = turns[-1]["content"]
        hosted = [p for p in self.providers() if p != "faq"]
        order = ([provider] if provider in hosted else []) + [p for p in hosted if p != provider]
        if provider == "faq" or self._used_today() >= self.daily_limit:
            order = []
        # The guide is the same on every page (so it can be cached); the page goes after it.
        system = (GUIDE.format(measured=self.measured or "(not available)"), PAGE_NOTE.format(page=page[:80]))
        for p in order:
            try:
                if p == "claude":
                    text = await self._ask_claude(system, turns)
                    model = self.claude_model
                else:
                    text = await self._ask_gemini(system, turns)
                    model = self.gemini_model
            except Exception as exc:                          # noqa: BLE001 - vendor boundary
                self.last_error[p] = describe_error(exc)
                if _operator_must_fix(exc):
                    self.down_until[p] = time.monotonic() + BENCH_S
                log.warning("help: %s failed: %s", p, self.last_error[p])
                continue
            self.last_error.pop(p, None)
            if text:
                self._used += 1
                self.usage[p]["replies"] += 1
                return {"reply": text, "provider": p, "model": model}
        self.usage["faq"]["replies"] += 1
        return {"reply": faq_answer(question, lang), "provider": "faq", "model": None}

    async def _ask_claude(self, system: tuple[str, str], turns: list[dict]) -> str:
        if self._claude is None:
            import anthropic  # the optional extra, imported late
            self._claude = anthropic.AsyncAnthropic(api_key=self.claude_key, timeout=TIMEOUT_S, max_retries=0)
        guide, page = system
        reply = await self._claude.messages.create(
            model=self.claude_model, max_tokens=MAX_REPLY_TOKENS,
            system=[{"type": "text", "text": guide, "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": page}],
            messages=turns)
        if getattr(reply, "stop_reason", None) == "refusal":
            return ""
        u = getattr(reply, "usage", None)
        if u is not None:
            self.usage["claude"]["input"] += int(getattr(u, "input_tokens", 0) or 0)
            self.usage["claude"]["output"] += int(getattr(u, "output_tokens", 0) or 0)
        return "".join(getattr(b, "text", "") for b in reply.content if getattr(b, "type", "") == "text").strip()

    async def _ask_gemini(self, system: tuple[str, str], turns: list[dict]) -> str:
        if self._http is None:
            import httpx
            self._http = httpx.AsyncClient(timeout=GEMINI_TIMEOUT_S)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent"
        body = {"systemInstruction": {"parts": [{"text": system[0]}, {"text": system[1]}]},
                "contents": [{"role": "model" if t["role"] == "assistant" else "user", "parts": [{"text": t["content"]}]}
                             for t in turns],
                # a help answer needs little thought: think briefly, answer fast
                "generationConfig": {"maxOutputTokens": MAX_REPLY_TOKENS * 3, "thinkingConfig": {"thinkingLevel": _thinking(self.gemini_model)}}}
        headers = {"x-goog-api-key": self.gemini_key or ""}
        r = await self._http.post(url, json=body, headers=headers)
        if r.status_code == 400 and "thinking" in r.text.lower():
            body["generationConfig"].pop("thinkingConfig")      # a model without thinking levels
            r = await self._http.post(url, json=body, headers=headers)
        r.raise_for_status()
        data = r.json()
        meta = data.get("usageMetadata") or {}
        self.usage["gemini"]["input"] += int(meta.get("promptTokenCount", 0) or 0)
        self.usage["gemini"]["output"] += int(meta.get("candidatesTokenCount", 0) or 0)
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()


def clean(messages: list[dict]) -> list[dict]:
    """The last few turns, alternating and starting with the person, each cut to MAX_CHARS."""
    out: list[dict] = []
    for m in messages[-MAX_TURNS * 2:]:
        role = "assistant" if m.get("role") == "assistant" else "user"
        text = str(m.get("content") or "").strip()[:MAX_CHARS]
        if not text:
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n" + text
        else:
            out.append({"role": role, "content": text})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out[-MAX_TURNS:] if len(out) <= MAX_TURNS or out[-MAX_TURNS]["role"] == "user" else out[-MAX_TURNS + 1:]


async def _close(bot: HelpBot) -> None:      # for tests
    if bot._http is not None:
        await bot._http.aclose()
    await asyncio.sleep(0)
