"""The tools a Haanji agent actually has, bound to one tenant.

Read-only tools are the ones Speculative Turn Execution is allowed to run
early. Write tools are ledgered, and the two that change a caller's
commitments refuse to run without a confirmation proof.
"""
from __future__ import annotations
import sqlite3
from typing import Any

from ..backend.local import BackendError, LocalBackend
from ..models import ToolResult
from ..speak import phrase, rupees as _rupees, spoken_date, spoken_time
from ..pramaan.ledger import Ledger, LedgerError
from ..pramaan.receipt import ConfirmationProof
from ..vertical import Pack
from . import Tool, ToolRegistry


def build_registry(tenant_id: str, backend: LocalBackend, pack: Pack,
                   ledger: Ledger | None = None, *,
                   require_confirmation: bool = True, vault=None) -> ToolRegistry:
    reg = ToolRegistry()
    lang = pack.language

    def _p(key: str, default: str) -> str:
        return phrase(lang, key, default)

    # ------------------------------------------------------------ read-only
    async def check_availability(service: str = "__default__", date: str = "tomorrow",
                                 staff: str | None = None, period: str | None = None,
                                 at: str | None = None, party: int | str | None = None) -> ToolResult:
        n = int(party) if party not in (None, "", 0, "0") else 1
        data = await backend.availability(tenant_id, service, date, staff=staff or None,
                                          period=period or None, at=at or None, party=n)
        if data.get("closed"):
            return ToolResult("check_availability", ok=True, data=data,
                              spoken=_p("closed_day", "Us din hum band rehte hain."))
        if data.get("past"):
            return ToolResult("check_availability", ok=True, data=data,
                              spoken=_p("past_day", "Wo din to nikal gaya. Kaunsa din dekhun?"))
        if at and not data.get("at_free"):
            alts = data.get("alternatives") or []
            if not alts:
                spoken = _p("no_slot_at_none", "{at} pe jagah nahi hai, aur us din koi aur slot bhi khaali nahi.").format(
                    at=spoken_time(at, lang).capitalize())
            else:
                alt = " ya ".join(spoken_time(a["time"], lang) for a in alts[:2])
                spoken = _p("no_slot_at", "{at} pe jagah nahi hai. {alt} chalega?").format(
                    at=spoken_time(at, lang).capitalize(), alt=alt)
            return ToolResult("check_availability", ok=True, data=data, spoken=spoken)
        if not data["slots"]:
            return ToolResult("check_availability", ok=True, data=data,
                              spoken=_p("no_slots", "Us din koi slot khaali nahi bacha."))
        first = data["slots"][0]
        spoken = _p("offer", "{when} khaali hai, {staff} ke saath.").format(
            when=spoken_time(first["time"], lang), staff=first["staff"])
        if len(data["slots"]) > 1:
            spoken += _p("offer_alt", " Uske baad {alt} bhi hai.").format(
                alt=spoken_time(data["slots"][1]["time"], lang))
        return ToolResult("check_availability", ok=True, data=data, spoken=spoken)

    async def search_knowledge(query: str) -> ToolResult:
        data = await backend.search_knowledge(tenant_id, query)
        if not data["hits"]:
            return ToolResult("search_knowledge", ok=True, data=data, spoken=None)
        return ToolResult("search_knowledge", ok=True, data=data,
                          spoken=data["hits"][0]["answer"])

    async def lookup_customer(phone: str) -> ToolResult:
        data = await backend.lookup_customer(tenant_id, phone)
        if not data["found"]:
            return ToolResult("lookup_customer", ok=True, data=data, spoken=None)
        c = data["customer"]
        return ToolResult("lookup_customer", ok=True, data=data,
                          spoken=f"Haanji {c['name']}, aapka record mil gaya.")

    async def quote_price(service: str) -> ToolResult:
        svc = backend.service(tenant_id, service)
        if svc is None:
            # Guardrail: the agent never invents a price for something the
            # tenant did not put in the catalogue.
            return ToolResult("quote_price", ok=False, error="service not in catalogue",
                              spoken=pack.guardrails.refusal_line)
        spoken = f"{svc['name'].capitalize()} {_rupees(svc['price_inr'])} hai."
        if svc.get("prep_note"):
            spoken += " " + svc["prep_note"]
        return ToolResult("quote_price", ok=True, data=svc, spoken=spoken)

    # ---------------------------------------------------------------- writes
    def _seal(action: str, args: dict[str, Any], proof: ConfirmationProof | None,
              excerpt: str, conversation_id: str, needs_proof: bool) -> str | None:
        if ledger is None:
            return None
        if vault is not None:
            args = vault.seal_args(args, tenant_id)   # names and numbers go in encrypted, per tenant
        receipt = ledger.append(tenant_id=tenant_id, conversation_id=conversation_id,
                                action=action, action_args=args, confirmation=proof,
                                transcript_excerpt=excerpt,
                                agent_config_version=pack.version,
                                require_confirmation=needs_proof and require_confirmation)
        return receipt.short_code()

    async def book_appointment(service: str, date: str, time: str,
                               customer_name: str | None = None, phone: str | None = None,
                               staff: str | None = None, party: int | str | None = None,
                               party_slots: list | None = None, identity: str | None = None,
                               proof: ConfirmationProof | None = None,
                               excerpt: str = "", conversation_id: str = "") -> ToolResult:
        """One confirmed appointment, or one per person for a group (``party``):
        the group is booked together under one receipt, and if any seat
        cannot be taken none of them is."""
        n = int(party) if party not in (None, "", 0, "0") else 1
        plan = [dict(x) for x in (party_slots or [])] if n > 1 else []
        if n > 1 and len(plan) != n:
            probe = await backend.availability(tenant_id, service, date, staff=staff or None, at=time, party=n)
            slot = (probe.get("slots") or [None])[0]
            if not slot or not slot.get("party"):
                return ToolResult("book_appointment", ok=False, error="no room for the group at that time",
                                  spoken=_p("slot_gone", "Us time par itne logon ki jagah nahi hai. Doosra time dekh lein?"))
            plan = slot["party"]
        seats = plan or [{"time": time, "staff": staff}]
        booked = []
        try:
            for seat in seats:
                booked.append(backend.book(tenant_id=tenant_id, service=service, date=date,
                                           time=seat["time"], staff=seat.get("staff") or staff,
                                           customer_name=customer_name, phone=phone))
        except BackendError as exc:
            for b in booked:
                backend.cancel(tenant_id, b.booking_id)
            return ToolResult("book_appointment", ok=False, error=str(exc),
                              spoken=_p("slot_gone",
                                        f"Maaf kijiye, {exc}. Doosra time dekh lein?"))
        booking = booked[0]
        args = {"service": booking.service, "date": booking.date, "time": booking.time,
                "staff": booking.staff, "customer_name": customer_name, "phone": phone,
                "booking_id": booking.booking_id}
        if len(booked) > 1:
            args["party"] = len(booked)
            args["bookings"] = [{"booking_id": b.booking_id, "time": b.time, "staff": b.staff} for b in booked]
        if identity:
            args["identity"] = identity
        try:
            code = _seal("book_appointment", args, proof, excerpt, conversation_id, True)
        except LedgerError as exc:
            for b in booked:
                backend.cancel(tenant_id, b.booking_id)   # never leave an unsealed write
            return ToolResult("book_appointment", ok=False, error=str(exc),
                              spoken="Ek baar phir se confirm kar dijiye, main tab hi book karunga.")
        if code:
            for b in booked:
                backend.conn.execute("UPDATE bookings SET receipt_code=? WHERE booking_id=?",
                                     (code, b.booking_id))
                b.receipt_code = code
            backend.conn.commit()
        when = (f"{spoken_date(booking.date, backend.today, backend.resolve_date, lang)} "
                f"{spoken_time(booking.time, lang)}")
        spoken = _p("booked", "Ho gaya. {when}, {staff} ke saath.").format(
            when=when[0].upper() + when[1:], staff=booking.staff)
        if len(booked) > 1:
            same_time = all(b.time == booking.time for b in booked)
            if same_time:
                spoken += _p("party_together", " {n} logon ke liye, ek saath.").format(n=len(booked))
            else:
                times = ", ".join(spoken_time(b.time, lang) for b in booked)
                spoken += _p("party_sequence", " {n} logon ke liye, ek ke baad ek: {times}.").format(
                    n=len(booked), times=times)
        if code:
            spoken += _p("booked_code", " Confirmation code {code}.").format(code=code)
        data = booking.as_dict()
        if len(booked) > 1:
            data["party"] = [b.as_dict() for b in booked]
        return ToolResult("book_appointment", ok=True, data=data, spoken=spoken)

    async def cancel_appointment(phone: str, identity: str | None = None,
                                 proof: ConfirmationProof | None = None,
                                 excerpt: str = "", conversation_id: str = "") -> ToolResult:
        booking = backend.find_booking(tenant_id, phone)
        if booking is None:
            return ToolResult("cancel_appointment", ok=False, error="no booking found",
                              spoken="Is number par koi booking nahi mili.")
        args = {"booking_id": booking.booking_id, "phone": phone}
        if identity:
            args["identity"] = identity
        try:
            code = _seal("cancel_appointment", args, proof, excerpt, conversation_id, True)
        except LedgerError as exc:
            return ToolResult("cancel_appointment", ok=False, error=str(exc),
                              spoken="Cancel karne se pehle ek baar haan bol dijiye.")
        backend.cancel(tenant_id, booking.booking_id)
        when = spoken_date(booking.date, backend.today, backend.resolve_date)
        return ToolResult("cancel_appointment", ok=True, data={"booking_id": booking.booking_id,
                                                               "receipt_code": code},
                          spoken=f"Aapki {when} ki booking cancel kar di hai.")

    async def reschedule_appointment(booking_id: str, service: str, date: str, time: str,
                                     phone: str, customer_name: str | None = None,
                                     staff: str | None = None, identity: str | None = None,
                                     proof: ConfirmationProof | None = None,
                                     excerpt: str = "", conversation_id: str = "") -> ToolResult:
        """Move a booking: the new slot is taken first, the old one released
        after, and one receipt records both so the chain shows the move."""
        old = next((b for b in backend.bookings(tenant_id) if b.booking_id == booking_id and b.status == "CONFIRMED"), None)
        if old is None:
            return ToolResult("reschedule_appointment", ok=False, error="no such booking",
                              spoken="Wo booking ab nahi mili.")
        try:
            new = backend.book(tenant_id=tenant_id, service=service, date=date, time=time, staff=staff,
                               customer_name=customer_name or old.customer_name, phone=phone)
        except BackendError as exc:
            return ToolResult("reschedule_appointment", ok=False, error=str(exc),
                              spoken=_p("slot_gone", "Wo slot abhi nahi mil raha, doosra dekh lete hain."))
        try:
            code = _seal("reschedule_appointment",
                         {"service": service, "date": date, "time": time, "staff": new.staff,
                          "customer_name": customer_name or old.customer_name, "phone": phone,
                          "booking_id": new.booking_id, "previous_booking_id": old.booking_id,
                          "previous_receipt": old.receipt_code, "previous_slot": f"{old.date} {old.time}",
                          **({"identity": identity} if identity else {})},
                         proof, excerpt, conversation_id, True)
        except LedgerError as exc:
            backend.cancel(tenant_id, new.booking_id)
            return ToolResult("reschedule_appointment", ok=False, error=str(exc),
                              spoken="Badalne se pehle ek baar haan bol dijiye.")
        backend.cancel(tenant_id, old.booking_id)
        if code:
            backend.conn.execute("UPDATE bookings SET receipt_code=? WHERE tenant_id=? AND booking_id=?",
                                 (code, tenant_id, new.booking_id))
            backend.conn.commit()
        when = f"{spoken_date(date, backend.today, backend.resolve_date, lang)} {spoken_time(time, lang)}"
        spoken = _p("rescheduled", "Badal diya. Ab aapki booking {when}, {staff} ke saath.").format(when=when, staff=new.staff)
        if code:
            spoken += _p("booked_code", " Confirmation code {code}.").format(code=code)
        return ToolResult("reschedule_appointment", ok=True,
                          data={"booking_id": new.booking_id, "previous_booking_id": old.booking_id,
                                "receipt_code": code, "date": date, "time": time, "staff": new.staff},
                          spoken=spoken)

    async def capture_lead(intent: str, name: str | None = None, phone: str | None = None,
                           note: str = "", proof: ConfirmationProof | None = None,
                           excerpt: str = "", conversation_id: str = "") -> ToolResult:
        lead_id = backend.capture_lead(tenant_id=tenant_id, name=name, phone=phone,
                                       intent=intent, note=note)
        code = _seal("capture_lead", {"lead_id": lead_id, "name": name, "phone": phone,
                                      "intent": intent}, proof, excerpt, conversation_id, False)
        return ToolResult("capture_lead", ok=True, data={"lead_id": lead_id, "receipt_code": code},
                          spoken=_p("lead_saved",
                                    "Aapka number note kar liya hai, humari team call karegi."))

    async def handoff(reason: str, phone: str | None = None, line: str | None = None,
                      proof: ConfirmationProof | None = None,
                      excerpt: str = "", conversation_id: str = "") -> ToolResult:
        code = _seal("handoff", {"reason": reason, "phone": phone}, proof, excerpt,
                     conversation_id, False)
        return ToolResult("handoff", ok=True, data={"reason": reason, "receipt_code": code},
                          spoken=line or pack.guardrails.escalation_line)

    async def refuse(reason: str, line: str | None = None,
                     proof: ConfirmationProof | None = None,
                     excerpt: str = "", conversation_id: str = "") -> ToolResult:
        """The agent declines to answer (advice, a promise, a discount) and
        says so in the pack's own words. Recorded in the ledger like a
        handoff, but the call goes on: a refused question is not an
        emergency, and the caller may still want a booking."""
        code = _seal("refuse", {"reason": reason}, proof, excerpt, conversation_id, False)
        return ToolResult("refuse", ok=True, data={"reason": reason, "receipt_code": code},
                          spoken=line or pack.guardrails.refusal_line)

    # --------------------------------------------------------------- register
    reg.register(Tool("check_availability",
                      "Free slots for a service on a day.",
                      {"service": "service name from the catalogue",
                       "date": "today | tomorrow | day_after_tomorrow | weekday | ISO date",
                       "staff": "optional staff member",
                       "period": "optional: morning | afternoon | evening, when the caller gave no clock time",
                       "at": "optional exact time HH:MM the caller asked for; returns whether it is free and alternatives",
                       "party": "optional number of people, when the booking is for a group"},
                      check_availability, read_only=True, nominal_ms=180,
                      required=["service", "date"]))
    reg.register(Tool("search_knowledge",
                      "Answer a question from the tenant's own knowledge base.",
                      {"query": "the caller's question"},
                      search_knowledge, read_only=True, nominal_ms=120, required=["query"]))
    reg.register(Tool("lookup_customer",
                      "Find a returning caller by phone number.",
                      {"phone": "ten digit phone number"},
                      lookup_customer, read_only=True, nominal_ms=90, required=["phone"]))
    reg.register(Tool("quote_price",
                      "State the catalogue price of a service. Never invents one.",
                      {"service": "service name"},
                      quote_price, read_only=True, nominal_ms=10, required=["service"]))
    reg.register(Tool("book_appointment",
                      "Create a confirmed appointment. Requires spoken confirmation.",
                      {"service": "service name", "date": "date token or ISO date",
                       "time": "HH:MM", "customer_name": "caller's name",
                       "phone": "ten digit phone number", "staff": "staff member",
                       "party": "number of people, when more than one"},
                      book_appointment, read_only=False, requires_confirmation=True,
                      ledgered=True, nominal_ms=260,
                      required=["service", "date", "time", "phone"]))
    reg.register(Tool("cancel_appointment",
                      "Cancel the caller's existing appointment. Requires confirmation.",
                      {"phone": "ten digit phone number"},
                      cancel_appointment, read_only=False, requires_confirmation=True,
                      ledgered=True, nominal_ms=210, required=["phone"]))
    reg.register(Tool("reschedule_appointment",
                      "Move an existing booking to a new slot; the old slot is released.",
                      {"booking_id": "the booking to move", "service": "service name", "date": "YYYY-MM-DD",
                       "time": "HH:MM", "phone": "ten digit phone number", "customer_name": "caller's name",
                       "staff": "staff member"},
                      reschedule_appointment, read_only=False, requires_confirmation=True, ledgered=True, nominal_ms=280,
                      required=["booking_id", "service", "date", "time", "phone"]))
    reg.register(Tool("capture_lead",
                      "Record a caller the agent could not book, for a human to call back.",
                      {"intent": "what they wanted", "name": "caller's name",
                       "phone": "ten digit phone number", "note": "free text"},
                      capture_lead, read_only=False, ledgered=True, nominal_ms=110,
                      required=["intent"]))
    reg.register(Tool("refuse",
                      "Decline a question the agent must not answer (advice, a promise, a discount), "
                      "in the pack's own words. The call continues.",
                      {"reason": "which rule applied", "line": "what to say"},
                      refuse, read_only=False, ledgered=True, required=["reason"]))
    reg.register(Tool("handoff",
                      "Escalate the call to a human immediately.",
                      {"reason": "why the call is being escalated"},
                      handoff, read_only=False, ledgered=True, required=["reason"]))
    return reg


def open_backend(pack: Pack, tenant_id: str, *, path: str = ":memory:",
                 today=None) -> tuple[LocalBackend, sqlite3.Connection]:
    conn = sqlite3.connect(path, check_same_thread=False)
    backend = LocalBackend(conn, today=today)
    backend.load_pack(tenant_id, pack)
    return backend, conn
