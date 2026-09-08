"""The dialogue policy: what the agent decides to do next.

This is deliberately a deterministic state machine rather than a prompt. Three
reasons, all of which matter for a system that takes real bookings:

* every decision is reproducible, so a regression in the demo is a bug and not
  a sampling accident;
* the policy is the thing the Pramaan Ledger audits, and an audit trail over a
  non-deterministic decision-maker is worth much less;
* it runs in microseconds, which is what leaves room in the latency budget for
  the parts that genuinely need a model.

A hosted language model can be dropped in behind :class:`MockLLM` without the
rest of the engine changing, because the policy already speaks in tool calls.
"""
from __future__ import annotations
from typing import Any

from . import nlu
from .adapters import LLMTurn
from .backend.local import LocalBackend
from .models import ConversationContext, Outcome, ToolCall, ToolResult
from .speak import phrase, spoken_date, spoken_time
from .vertical import Pack

GOODBYE = {"bye", "byee", "dhanyavaad", "dhanyawad", "thanks", "thank", "shukriya",
           "alvida", "bas", "itna", "yahi", "khatam", "dhonnobad", "thak", "eituku"}
MORE_HELP = "Aur kuch puchna tha?"


def _spoken_time(hhmm: str, lang: str = "hinglish") -> str:
    return spoken_time(hhmm, lang)


def _spoken_date(iso_or_token: str, backend: LocalBackend, lang: str = "hinglish") -> str:
    return spoken_date(iso_or_token, backend.today, backend.resolve_date, lang)


class DialoguePolicy:
    def __init__(self, pack: Pack, backend: LocalBackend, tenant_id: str):
        self.pack = pack
        self.backend = backend
        self.tenant_id = tenant_id
        self.aliases = pack.service_aliases()
        self.lang = pack.language

    def _p(self, key: str, default: str) -> str:
        return phrase(self.lang, key, default)

    # ------------------------------------------------------------------ setup
    def greeting(self, customer: dict | None = None) -> str:
        """The opening line. A returning caller is greeted by name — their
        number reached us with the call, so the lookup costs nothing."""
        if customer and customer.get("name"):
            first = str(customer["name"]).split()[0]
            base = self.pack.persona.greeting
            opener = base.split(".")[0] if "." in base else base
            line = f"{opener}. {first} ji, wapas swagat hai!"
            if customer.get("last_service"):
                line += f" Pichhli baar {customer['last_service']} karaya tha."
            return line + " Aaj kya madad karun?"
        return self.pack.persona.greeting

    def closing(self) -> str:
        return self.pack.persona.closing

    # -------------------------------------------------------------- listening
    def absorb(self, text: str, ctx: ConversationContext) -> None:
        """Fold whatever the caller just said into the state of the call."""
        service = nlu.match_service(text, self.aliases)
        if service:
            if ctx.service and service != ctx.service:
                ctx.time = None                # a different service needs a fresh look
                ctx.last_offered_slots = []
            ctx.service = service
        w = nlu.words(text)
        if w & nlu.DATE_WORDS:
            new_date = nlu.normalise_date(text, ctx.date)
            if new_date != ctx.date:
                ctx.time = None
                ctx.last_offered_slots = []
            ctx.date = new_date
        if w & nlu.TIME_WORDS:
            spoken = nlu.normalise_time(text)
            if spoken:
                ctx.time = spoken
        name = nlu.extract_name(text)
        if name:
            ctx.customer_name = name
        phone = nlu.extract_phone(text)
        if phone:
            ctx.customer_phone = phone

    # ------------------------------------------------------------- deciding
    def plan(self, text: str, ctx: ConversationContext) -> LLMTurn:
        self.absorb(text, ctx)
        low = text.lower()

        # We just asked "kis naam se booking karun?" — this reply is the name.
        if ctx.flags.get("asked_name") and not ctx.customer_name:
            name = nlu.bare_name(text)
            if name:
                ctx.customer_name = name

        # 1. An outstanding confirmation outranks everything else in the call.
        if ctx.pending_confirmation:
            if nlu.is_affirmative(text):
                pending = ctx.pending_confirmation
                return LLMTurn(tool_calls=[ToolCall(pending["action"], dict(pending["args"]))],
                               needs_confirmation=True)
            if nlu.is_negative(text):
                ctx.pending_confirmation = None
                ctx.time = None
                ctx.last_offered_slots = []
                return LLMTurn(say=self._p("changed", "Theek hai, badal dete hain. Kaunsa din ya time chahiye?"))
            return LLMTurn(say=self._p("yes_or_no", "Bas ek baar haan ya na keh dijiye, phir main confirm kar dunga."))

        # 2. The caller is winding up.
        if self._is_goodbye(low) and not ctx.flags.get("await_details"):
            return LLMTurn(say=self.closing(), end_call=True)

        # 3. We asked for a name and number in order to leave a callback note.
        if ctx.flags.get("await_details") and ctx.customer_phone:
            ctx.flags.pop("await_details")
            return LLMTurn(tool_calls=[ToolCall("capture_lead", {
                "intent": ctx.flags.get("lead_intent", ctx.service or "enquiry"),
                "name": ctx.customer_name, "phone": ctx.customer_phone,
                "note": ctx.transcript(2)})])

        # 4. Cancellation.
        if nlu.words(text) & nlu.CANCEL_WORDS and not ctx.flags.get("await_details"):
            if not ctx.customer_phone:
                return LLMTurn(say="Zaroor. Jis number se booking hui thi wo bata dijiye.")
            ctx.pending_confirmation = {"action": "cancel_appointment",
                                        "args": {"phone": ctx.customer_phone}}
            return LLMTurn(say="Aapki booking cancel kar dun? Haan ya na bol dijiye.")

        # 5. The caller accepted a slot we offered.
        if ctx.last_offered_slots and not ctx.time:
            chosen = self._chosen_slot(text, ctx)
            if chosen:
                ctx.date, ctx.time, ctx.staff = chosen["date"], chosen["time"], chosen["staff"]
                ctx.last_offered_slots = []
                return self._advance_booking(ctx)

        # 6. A question that is not a booking request.
        w = nlu.words(text)
        if (w & nlu.QUESTION_WORDS) and not self._wants_booking(w, ctx):
            return LLMTurn(tool_calls=[ToolCall("search_knowledge", {"query": text.strip()})])

        # 7. The booking path.
        if self._wants_booking(w, ctx) or ctx.service or ctx.date:
            return self._advance_booking(ctx)

        # 8. Nothing recognisable yet.
        if w & nlu.QUESTION_WORDS:
            return LLMTurn(tool_calls=[ToolCall("search_knowledge", {"query": text.strip()})])
        return LLMTurn(say="Main appointment book kar sakta hoon ya jaankari de sakta hoon. "
                           "Aapko kya chahiye?")

    # ------------------------------------------------------- after tool calls
    def after_tools(self, text: str, ctx: ConversationContext,
                    results: list[ToolResult]) -> LLMTurn:
        by_name = {r.name: r for r in results}

        if "book_appointment" in by_name:
            r = by_name["book_appointment"]
            ctx.pending_confirmation = None
            if r.ok:
                ctx.outcome = Outcome.BOOKED
                return LLMTurn(say=f"{r.spoken} {self.closing()}", end_call=True)
            ctx.time = None
            ctx.last_offered_slots = []
            return LLMTurn(say=r.spoken or "Wo slot abhi nahi ho paya, doosra dekh lete hain.")

        if "cancel_appointment" in by_name:
            r = by_name["cancel_appointment"]
            ctx.pending_confirmation = None
            ctx.outcome = Outcome.HANDED_OFF if not r.ok else ctx.outcome
            return LLMTurn(say=f"{r.spoken} {self.closing()}", end_call=r.ok)

        if "capture_lead" in by_name:
            ctx.outcome = Outcome.LEAD_CAPTURED
            return LLMTurn(say=f"{by_name['capture_lead'].spoken} {self.closing()}",
                           end_call=True)

        if "handoff" in by_name:
            ctx.outcome = Outcome.HANDED_OFF
            return LLMTurn(say=by_name["handoff"].spoken or "", end_call=True)

        if "check_availability" in by_name:
            r = by_name["check_availability"]
            slots = (r.data or {}).get("slots", [])
            if not slots:
                ctx.flags["await_details"] = True
                ctx.flags["lead_intent"] = ctx.service or "appointment"
                reason = (self._p("closed_day", "Us din hum band rehte hain.")
                          if (r.data or {}).get("closed")
                          else self._p("no_slots", "Us din sab slot bhar gaye hain."))
                return LLMTurn(say=reason + self._p(
                    "leave_details", " Aap apna naam aur number de dijiye, hum call "
                    "karke time set kar denge."))
            ctx.last_offered_slots = slots
            first = slots[0]
            when = (f"{_spoken_date(first['date'], self.backend, self.lang).capitalize()} "
                    f"{_spoken_time(first['time'], self.lang)}")
            line = self._p("offer", "{when} khaali hai, {staff} ke saath."
                           ).format(when=when, staff=first["staff"])
            if len(slots) > 1:
                line += self._p("offer_alt", " Ya phir {alt}."
                                ).format(alt=_spoken_time(slots[1]["time"], self.lang))
            return LLMTurn(say=line + self._p("offer_ok", " Chalega?"))

        if "search_knowledge" in by_name:
            r = by_name["search_knowledge"]
            hits = (r.data or {}).get("hits", [])
            if hits:
                ctx.answered_questions += 1
                return LLMTurn(say=f"{hits[0]['answer']} "
                                   f"{self._p('more_help', MORE_HELP)}")
            if ctx.service:
                return LLMTurn(tool_calls=[ToolCall("quote_price", {"service": ctx.service})])
            ctx.flags["await_details"] = True
            ctx.flags["lead_intent"] = "enquiry"
            return LLMTurn(say="Ye jaankari mere paas nahi hai. Naam aur number de dijiye, "
                               "team aapko call kar legi.")

        if "quote_price" in by_name:
            r = by_name["quote_price"]
            if r.ok:
                ctx.answered_questions += 1
            return LLMTurn(say=f"{r.spoken} {MORE_HELP}")

        if "lookup_customer" in by_name:
            r = by_name["lookup_customer"]
            return LLMTurn(say=r.spoken or "Aapka naam aur number bata dijiye.")

        return LLMTurn(say=MORE_HELP)

    # ------------------------------------------------------------- internals
    def _advance_booking(self, ctx: ConversationContext) -> LLMTurn:
        if not ctx.service:
            names = ", ".join(self.pack.service_names[:3])
            return LLMTurn(say=self._p("ask_service",
                "Zaroor. Kaunsi service chahiye — {services}, ya kuch aur?"
                ).format(services=names))
        if not ctx.date:
            return LLMTurn(say=self._p("ask_day", "Theek hai. Kis din ka time dekhun?"))
        if not ctx.time:
            return LLMTurn(tool_calls=[ToolCall("check_availability",
                                                {"service": ctx.service, "date": ctx.date})])
        if not ctx.customer_phone:
            return LLMTurn(say=self._p("ask_name_number", "Bas aapka naam aur mobile number bata dijiye."))
        if not ctx.customer_name and not ctx.flags.get("asked_name"):
            # The channel already gave us the number (WhatsApp, a web call with
            # a known caller) — only the name is worth one extra turn.
            ctx.flags["asked_name"] = True
            return LLMTurn(say=self._p("ask_name", "Kis naam se booking karun?"))
        return self._ask_confirmation(ctx)

    def _ask_confirmation(self, ctx: ConversationContext) -> LLMTurn:
        args = {"service": ctx.service, "date": ctx.date, "time": ctx.time,
                "customer_name": ctx.customer_name, "phone": ctx.customer_phone,
                "staff": ctx.staff}
        ctx.pending_confirmation = {"action": "book_appointment", "args": args}
        if self.lang in ("benglish",):
            who = f" {ctx.staff} er sathe" if ctx.staff else ""
            say = self._p("confirm", "").format(
                what=ctx.service,
                when=f"{_spoken_date(ctx.date, self.backend, self.lang)} "
                     f"{_spoken_time(ctx.time, self.lang)}",
                who=who, name=ctx.customer_name or "apnar")
        else:
            who = f" {ctx.staff} ke saath" if ctx.staff else ""
            say = (f"Ek baar dohra deta hoon — {ctx.service}, "
                   f"{_spoken_date(ctx.date, self.backend)} {_spoken_time(ctx.time)}{who}, "
                   f"{ctx.customer_name or 'aapke'} naam se. Confirm kar dun?")
        return LLMTurn(say=say, needs_confirmation=True)

    def _chosen_slot(self, text: str, ctx: ConversationContext) -> dict[str, Any] | None:
        asked = nlu.normalise_time(text) if nlu.words(text) & nlu.TIME_WORDS else None
        if asked:
            for slot in ctx.last_offered_slots:
                if slot["time"] == asked:
                    return slot
        if nlu.is_affirmative(text) and not nlu.is_negative(text):
            return ctx.last_offered_slots[0]
        return None

    @staticmethod
    def _wants_booking(w: set[str], ctx: ConversationContext) -> bool:
        return bool(w & nlu.BOOKING_VERBS) or bool(ctx.service and ctx.date)

    @staticmethod
    def _is_goodbye(low: str) -> bool:
        w = nlu.words(low)
        if w & GOODBYE:
            return True
        return bool(w & nlu.NO_WORDS) and len(w) <= 3
