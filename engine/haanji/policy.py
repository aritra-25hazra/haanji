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
import re
from typing import Any

from . import nlu
from .adapters import LLMTurn
from .backend.local import LocalBackend
from .models import ConversationContext, Outcome, ToolCall, ToolResult
from .speak import phrase, spoken_date, spoken_time
from .vertical import Pack

GOODBYE = nlu.FAREWELL_WORDS
MORE_HELP = "Aur kuch puchna tha?"
PERIOD_WORD = {"morning": "subah", "afternoon": "dopahar", "evening": "shaam"}
_CODE = re.compile(r"\b([0-9A-Fa-f]{4})[\s-]?([0-9A-Fa-f]{4})\b")


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
    def _fresh_look(self, ctx: ConversationContext) -> None:
        """Something that decides the slot changed: forget the offered slots
        and any time we had already checked."""
        ctx.time = None
        ctx.last_offered_slots = []
        ctx.flags.pop("time_checked", None)
        ctx.flags.pop("party_plan", None)
        ctx.flags.pop("period_relaxed", None)

    def absorb(self, text: str, ctx: ConversationContext) -> None:
        """Fold whatever the caller just said into the state of the call."""
        service = nlu.match_service(text, self.aliases)
        if service:
            if ctx.service and service != ctx.service:
                self._fresh_look(ctx)          # a different service needs a fresh look
            ctx.service = service
        w = nlu.words(text)
        if w & nlu.DATE_WORDS:
            new_date = nlu.normalise_date(text, ctx.date, self.backend.today)
            if new_date is None and nlu.date_unclear(text):
                ctx.flags["date_unclear"] = True
            if new_date != ctx.date:
                self._fresh_look(ctx)
                ctx.flags.pop("date_unclear", None)
            ctx.date = new_date
        if w & nlu.TIME_WORDS:
            spoken = nlu.normalise_time(text)
            if spoken:
                if spoken != ctx.time:
                    self._fresh_look(ctx)
                ctx.time = spoken              # the caller named a clock time: check that one
                ctx.period = None
            else:
                period = nlu.time_period(text)
                if period and period != ctx.period:
                    self._fresh_look(ctx)      # "shaam ko" after a morning offer: look again
                    ctx.period = period
        person = nlu.match_staff(text, self.pack.staff)
        if person and person != ctx.staff:
            ctx.staff = person
            ctx.last_offered_slots = []
            ctx.flags.pop("time_checked", None)
        party = nlu.party_size(text)
        if party and party != ctx.party_size:
            ctx.party_size = party
            ctx.last_offered_slots = []
            ctx.flags.pop("time_checked", None)
        name = nlu.extract_name(text)
        if name:
            ctx.customer_name = name
        phone = nlu.extract_phone(text)
        if phone:
            if ctx.customer_phone and phone != ctx.customer_phone:
                ctx.phone_verified = False     # a different number than the one the channel gave us
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

        # 1b. We asked for the receipt code before touching an existing booking.
        if ctx.flags.get("await_code"):
            return self._identity_reply(text, ctx)

        # 2. A slot is on the table. "nahi" here is a rejection, never a goodbye.
        if ctx.last_offered_slots and not ctx.time:
            chosen = self._chosen_slot(text, ctx)
            if chosen:
                ctx.date, ctx.time, ctx.staff = chosen["date"], chosen["time"], chosen["staff"]
                if chosen.get("party"):
                    ctx.flags["party_plan"] = chosen["party"]
                ctx.flags["time_checked"] = True
                ctx.last_offered_slots = []
                return self._advance_booking(ctx)
            if nlu.is_negative(text) and not (nlu.words(text) & GOODBYE):
                ctx.last_offered_slots = []
                if ctx.period or ctx.date:   # absorb() found nothing new: ask instead of repeating
                    ctx.period = None
                return LLMTurn(say=self._p("ask_period", "Theek hai. Subah, dopahar ya shaam — kaunsa time theek rahega?"))

        # 2b. The caller is winding up.
        if nlu.is_farewell(text) and not ctx.flags.get("await_details"):
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
                ctx.flags["await_cancel"] = True
                return LLMTurn(say=self._p("ask_booking_number", "Zaroor. Jis number se booking hui thi wo bata dijiye."))
            gate = self._identity_gate(ctx, "cancel")
            if gate is not None:
                return gate
            ctx.flags.pop("await_cancel", None)
            ctx.pending_confirmation = {"action": "cancel_appointment",
                                        "args": {"phone": ctx.customer_phone, "identity": self._identity(ctx)}}
            return LLMTurn(say="Aapki booking cancel kar dun? Haan ya na bol dijiye.")
        if ctx.flags.get("await_cancel") and ctx.customer_phone:
            gate = self._identity_gate(ctx, "cancel")
            if gate is not None:
                return gate
            ctx.flags.pop("await_cancel", None)
            ctx.pending_confirmation = {"action": "cancel_appointment",
                                        "args": {"phone": ctx.customer_phone, "identity": self._identity(ctx)}}
            return LLMTurn(say="Aapki booking cancel kar dun? Haan ya na bol dijiye.")

        # 4b. Rescheduling: find the booking, then run the ordinary slot flow
        #     with the write parked behind reschedule_appointment.
        wants_move = bool(w_all := nlu.words(text)) and bool(w_all & nlu.RESCHEDULE_WORDS) and \
            ("booking" in w_all or "appointment" in w_all or "slot" in w_all or "time" in w_all
             or ctx.flags.get("await_reschedule") or ctx.flags.get("reschedule_booking_id"))
        if (wants_move or ctx.flags.get("await_reschedule")) and not ctx.flags.get("reschedule_booking_id") \
                and not ctx.flags.get("await_details"):
            if not ctx.customer_phone:
                ctx.flags["await_reschedule"] = True
                return LLMTurn(say=self._p("ask_booking_number", "Zaroor. Jis number se booking hui thi wo bata dijiye."))
            gate = self._identity_gate(ctx, "reschedule")
            if gate is not None:
                return gate
            ctx.flags.pop("await_reschedule", None)
            booking = self.backend.find_booking(self.tenant_id, ctx.customer_phone)
            if booking is None:
                return LLMTurn(say=self._p("no_booking", "Is number par koi booking nahi mili. Nayi booking kar dun?"))
            ctx.flags["reschedule_booking_id"] = booking.booking_id
            ctx.flags["reschedule_from"] = f"{booking.date} {booking.time}"
            ctx.service, ctx.staff = booking.service, booking.staff
            ctx.date, ctx.time, ctx.last_offered_slots = None, None, []
            if not ctx.customer_name:
                ctx.customer_name = booking.customer_name
            self.absorb(text, ctx)                     # the caller may have named the new day already
            when = f"{_spoken_date(booking.date, self.backend, self.lang)} {_spoken_time(booking.time, self.lang)}"
            lead = self._p("found_booking", "Aapki {when} ki {service} booking mili.").format(when=when, service=booking.service)
            nxt = self._advance_booking(ctx)
            if nxt.say:
                nxt.say = f"{lead} {nxt.say}"
            else:
                ctx.flags["reschedule_lead"] = lead      # said once the slots come back
            return nxt

        # 6. A question that is not a booking request.
        w = nlu.words(text)
        if (w & nlu.QUESTION_WORDS) and not self._wants_booking(w, ctx):
            return LLMTurn(tool_calls=[ToolCall("search_knowledge", {"query": text.strip()})])

        # 7. The booking path.
        if self._wants_booking(w, ctx) or ctx.service or ctx.date or ctx.flags.get("date_unclear"):
            return self._advance_booking(ctx)

        # 8. Nothing recognisable yet.
        if w & nlu.QUESTION_WORDS:
            return LLMTurn(tool_calls=[ToolCall("search_knowledge", {"query": text.strip()})])
        return LLMTurn(say="Main appointment book kar sakta hoon ya jaankari de sakta hoon. "
                           "Aapko kya chahiye?")

    # ------------------------------------------------------- after tool calls
    def after_tools(self, text: str, ctx: ConversationContext,
                    results: list[ToolResult]) -> LLMTurn:
        lead = ctx.flags.pop("reschedule_lead", None)
        turn = self._after_tools(text, ctx, results)
        if lead and turn.say:
            turn.say = f"{lead} {turn.say}"
        return turn

    def _after_tools(self, text: str, ctx: ConversationContext,
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

        if "reschedule_appointment" in by_name:
            r = by_name["reschedule_appointment"]
            ctx.pending_confirmation = None
            if r.ok:
                ctx.outcome = Outcome.RESCHEDULED
                ctx.flags.pop("reschedule_booking_id", None)
                return LLMTurn(say=f"{r.spoken} {self.closing()}", end_call=True)
            ctx.time = None
            ctx.last_offered_slots = []
            return LLMTurn(say=r.spoken or "Wo slot nahi ho paya, doosra dekh lete hain.")

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

        if "refuse" in by_name:
            ctx.flags["refusals"] = int(ctx.flags.get("refusals", 0)) + 1
            return LLMTurn(say=by_name["refuse"].spoken or self.pack.guardrails.refusal_line)

        if "check_availability" in by_name:
            r = by_name["check_availability"]
            data = r.data or {}
            slots = data.get("slots", [])
            if data.get("past"):
                ctx.date = None
                self._fresh_look(ctx)
                return LLMTurn(say=self._p("past_day", "Wo din to nikal gaya. Kaunsa din dekhun?"))
            if data.get("requested"):
                # The caller named a time; we asked about that one exactly.
                if data.get("at_free") and slots:
                    ctx.time, ctx.staff = slots[0]["time"], slots[0]["staff"]
                    if slots[0].get("party"):
                        ctx.flags["party_plan"] = slots[0]["party"]
                    ctx.flags["time_checked"] = True
                    return self._advance_booking(ctx)
                alts = data.get("alternatives") or []
                ctx.time = None
                ctx.flags.pop("time_checked", None)
                at = _spoken_time(data["requested"], self.lang).capitalize()
                if not alts:
                    ctx.flags["await_details"] = True
                    ctx.flags["lead_intent"] = ctx.service or "appointment"
                    return LLMTurn(say=self._p("no_slot_at_none", "{at} pe jagah nahi hai, aur us din koi aur slot bhi khaali nahi.").format(at=at)
                                   + self._p("leave_details", " Aap apna naam aur number de dijiye, hum call karke time set kar denge."))
                ctx.last_offered_slots = alts
                alt = " ya ".join(_spoken_time(a["time"], self.lang) for a in alts[:2])
                return LLMTurn(say=self._p("no_slot_at", "{at} pe jagah nahi hai. {alt} chalega?").format(at=at, alt=alt))
            if not slots and ctx.period and not ctx.flags.get("period_relaxed"):
                # Nothing in the asked part of the day: look at the whole day once,
                # and say why the offer is not what they asked for.
                ctx.flags["period_relaxed"] = self._p(f"{ctx.period}_w", PERIOD_WORD[ctx.period])
                ctx.period = None
                return LLMTurn(tool_calls=[ToolCall("check_availability", self._avail_args(ctx))])
            if not slots:
                ctx.flags["await_details"] = True
                ctx.flags["lead_intent"] = ctx.service or "appointment"
                reason = (self._p("closed_day", "Us din hum band rehte hain.")
                          if data.get("closed")
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
            if ctx.party_size > 1:
                line += self._p("party_for", " {n} logon ke liye").format(n=ctx.party_size) + "."
            if len(slots) > 1:
                line += self._p("offer_alt", " Ya phir {alt}."
                                ).format(alt=_spoken_time(slots[1]["time"], self.lang))
            relaxed = ctx.flags.pop("period_relaxed", None)
            if relaxed:
                line = self._p("period_relaxed", "{period} mein jagah nahi hai.").format(period=relaxed.capitalize()) + " " + line
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
    def _avail_args(self, ctx: ConversationContext) -> dict[str, Any]:
        """Exactly what :func:`nlu.availability_args` derives from the same
        sentence, so a speculated availability can be claimed."""
        args: dict[str, Any] = {"service": ctx.service or "__default__", "date": ctx.date}
        if ctx.time:
            args["at"] = ctx.time
        elif ctx.period:
            args["period"] = ctx.period
        if ctx.staff:
            args["staff"] = ctx.staff
        if ctx.party_size > 1:
            args["party"] = ctx.party_size
        return args

    def _advance_booking(self, ctx: ConversationContext) -> LLMTurn:
        if not ctx.service:
            names = ", ".join(self.pack.service_names[:3])
            return LLMTurn(say=self._p("ask_service",
                "Zaroor. Kaunsi service chahiye — {services}, ya kuch aur?"
                ).format(services=names))
        if not ctx.date:
            if ctx.flags.pop("date_unclear", None):
                return LLMTurn(say=self._p("ask_date", "Kaunsi tarikh ya kaunsa din? Jaise 'kal', 'somvar' ya '15 tarikh'."))
            return LLMTurn(say=self._p("ask_day", "Theek hai. Kis din ka time dekhun?"))
        if not ctx.time or not ctx.flags.get("time_checked"):
            # Either we need slots to offer, or the caller named a time and we
            # check that exact time before asking for their name and number.
            return LLMTurn(tool_calls=[ToolCall("check_availability", self._avail_args(ctx))])
        if not ctx.customer_phone:
            return LLMTurn(say=self._p("ask_name_number", "Bas aapka naam aur mobile number bata dijiye."))
        if not ctx.customer_name and not ctx.flags.get("asked_name"):
            # The channel already gave us the number (WhatsApp, a web call with
            # a known caller) — only the name is worth one extra turn.
            ctx.flags["asked_name"] = True
            return LLMTurn(say=self._p("ask_name", "Kis naam se booking karun?"))
        return self._ask_confirmation(ctx)

    def ask_confirmation(self, ctx: ConversationContext, action: str,
                         args: dict[str, Any]) -> LLMTurn:
        """Park a write behind the caller's yes. Public so that a hosted model's
        request to book or cancel becomes the same read-back question the
        deterministic policy asks — the words the ledger will later bind the
        caller's reply to are never the model's own."""
        if action == "book_appointment":
            for field_name, key in (("service", "service"), ("date", "date"), ("time", "time"),
                                    ("staff", "staff"), ("customer_name", "customer_name"),
                                    ("customer_phone", "phone")):
                if args.get(key):
                    setattr(ctx, field_name, args[key])
            return self._ask_confirmation(ctx)
        if action == "cancel_appointment":
            if args.get("phone"):
                ctx.customer_phone = args["phone"]
            if not ctx.customer_phone:
                return LLMTurn(say="Zaroor. Jis number se booking hui thi wo bata dijiye.")
            ctx.pending_confirmation = {"action": "cancel_appointment",
                                        "args": {"phone": ctx.customer_phone}}
            return LLMTurn(say="Aapki booking cancel kar dun? Haan ya na bol dijiye.",
                           needs_confirmation=True)
        raise ValueError(f"{action} does not take a confirmation")

    def _ask_confirmation(self, ctx: ConversationContext) -> LLMTurn:
        args: dict[str, Any] = {"service": ctx.service, "date": ctx.date, "time": ctx.time,
                                "customer_name": ctx.customer_name, "phone": ctx.customer_phone,
                                "staff": ctx.staff}
        action = "book_appointment"
        if ctx.flags.get("reschedule_booking_id"):
            action = "reschedule_appointment"
            args["booking_id"] = ctx.flags["reschedule_booking_id"]
            args["identity"] = self._identity(ctx)
        elif ctx.party_size > 1:
            args["party"] = ctx.party_size
            if ctx.flags.get("party_plan"):
                args["party_slots"] = ctx.flags["party_plan"]
        ctx.pending_confirmation = {"action": action, "args": args}
        what = ctx.service
        if ctx.party_size > 1:
            what += self._p("party_for", " {n} logon ke liye").format(n=ctx.party_size)
        if self._p("confirm", ""):
            who = self._p("with", " {staff} er sathe").format(staff=ctx.staff) if ctx.staff else ""
            say = self._p("confirm", "").format(
                what=what,
                when=f"{_spoken_date(ctx.date, self.backend, self.lang)} "
                     f"{_spoken_time(ctx.time, self.lang)}",
                who=who, name=ctx.customer_name or "apnar")
        else:
            who = f" {ctx.staff} ke saath" if ctx.staff else ""
            say = (f"Ek baar dohra deta hoon — {what}, "
                   f"{_spoken_date(ctx.date, self.backend)} {_spoken_time(ctx.time)}{who}, "
                   f"{ctx.customer_name or 'aapke'} naam se. Confirm kar dun?")
        return LLMTurn(say=say, needs_confirmation=True)

    # ------------------------------------------------- who is on the line
    @staticmethod
    def _identity(ctx: ConversationContext) -> str:
        if ctx.phone_verified:
            return "channel"                   # caller-id / WhatsApp sender
        if ctx.flags.get("identity_code"):
            return "receipt_code"              # they quoted the booking's receipt code
        return "unverified"

    def _identity_gate(self, ctx: ConversationContext, intent: str) -> LLMTurn | None:
        """Before an existing booking is cancelled or moved, the caller has to
        be its owner. A number the channel proved (phone caller-id, WhatsApp
        sender) is enough; a number typed into a web page is not, so there we
        ask for the receipt code the customer was given when they booked."""
        if ctx.phone_verified or ctx.flags.get("identity_code"):
            return None
        if self.backend.find_booking(self.tenant_id, ctx.customer_phone) is None:
            return None                        # nothing to protect; the ordinary "no booking" reply follows
        ctx.flags["await_code"] = intent
        return LLMTurn(say=self._p("ask_code", "Suraksha ke liye booking ka confirmation code bata dijiye (jaise 2504-7863)."))

    def _identity_reply(self, text: str, ctx: ConversationContext) -> LLMTurn:
        intent = ctx.flags.get("await_code")
        m = _CODE.search(text)
        booking = self.backend.find_booking(self.tenant_id, ctx.customer_phone) if ctx.customer_phone else None
        code = (m.group(1) + m.group(2)).upper() if m else None
        if code and booking and booking.receipt_code and booking.receipt_code.replace("-", "").upper() == code:
            ctx.flags.pop("await_code", None)
            ctx.flags["identity_code"] = code
            if intent == "cancel":
                ctx.pending_confirmation = {"action": "cancel_appointment",
                                            "args": {"phone": ctx.customer_phone, "identity": "receipt_code"}}
                return LLMTurn(say="Shukriya. Aapki booking cancel kar dun? Haan ya na bol dijiye.")
            ctx.flags["await_reschedule"] = True
            return self.plan(text, ctx)
        if nlu.is_negative(text) or nlu.is_farewell(text) or (m is None and ctx.flags.get("code_asked")):
            # No code to hand: the shop calls the number on the booking back.
            ctx.flags.pop("await_code", None)
            ctx.flags["await_details"] = True
            ctx.flags["lead_intent"] = f"{intent}_request"
            if ctx.customer_phone:
                return self.plan(text, ctx)
            return LLMTurn(say=self._p("code_not_found", "Is code par booking nahi mili. Naam aur number de dijiye, hum us number par call karke kar denge."))
        ctx.flags["code_asked"] = True
        return LLMTurn(say=self._p("code_not_found", "Is code par booking nahi mili. Naam aur number de dijiye, hum us number par call karke kar denge."))

    def _chosen_slot(self, text: str, ctx: ConversationContext) -> dict[str, Any] | None:
        w = nlu.words(text)
        asked = nlu.normalise_time(text) if w & nlu.TIME_WORDS else None
        if asked:
            for slot in ctx.last_offered_slots:
                if slot["time"] == asked:
                    return slot
            return None                        # a time we did not offer: look it up, do not guess
        if w & {"pehla", "pehli", "first", "wahi", "prothom", "pahila", "pahili"} and not (w & nlu.NO_WORDS):
            return ctx.last_offered_slots[0]
        if w & {"doosra", "dusra", "dusri", "second", "baad", "ditiyo", "dusre", "wala"} and len(ctx.last_offered_slots) > 1 \
                and not (w & nlu.NO_WORDS):
            return ctx.last_offered_slots[1]
        if nlu.is_affirmative(text) and not nlu.is_negative(text):
            return ctx.last_offered_slots[0]
        return None

    @staticmethod
    def _wants_booking(w: set[str], ctx: ConversationContext) -> bool:
        return bool(w & nlu.BOOKING_VERBS) or bool(ctx.service and ctx.date)

    @staticmethod
    def _is_goodbye(low: str) -> bool:
        return nlu.is_farewell(low)
