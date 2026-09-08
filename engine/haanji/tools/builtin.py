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
                   require_confirmation: bool = True) -> ToolRegistry:
    reg = ToolRegistry()
    lang = pack.language

    def _p(key: str, default: str) -> str:
        return phrase(lang, key, default)

    # ------------------------------------------------------------ read-only
    async def check_availability(service: str = "__default__", date: str = "tomorrow",
                                 staff: str | None = None) -> ToolResult:
        data = await backend.availability(tenant_id, service, date, staff=staff)
        if data.get("closed"):
            return ToolResult("check_availability", ok=True, data=data,
                              spoken=_p("closed_day", "Us din hum band rehte hain."))
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
        receipt = ledger.append(tenant_id=tenant_id, conversation_id=conversation_id,
                                action=action, action_args=args, confirmation=proof,
                                transcript_excerpt=excerpt,
                                agent_config_version=pack.version,
                                require_confirmation=needs_proof and require_confirmation)
        return receipt.short_code()

    async def book_appointment(service: str, date: str, time: str,
                               customer_name: str | None = None, phone: str | None = None,
                               staff: str | None = None,
                               proof: ConfirmationProof | None = None,
                               excerpt: str = "", conversation_id: str = "") -> ToolResult:
        try:
            booking = backend.book(tenant_id=tenant_id, service=service, date=date, time=time,
                                   staff=staff, customer_name=customer_name, phone=phone)
        except BackendError as exc:
            return ToolResult("book_appointment", ok=False, error=str(exc),
                              spoken=_p("slot_gone",
                                        f"Maaf kijiye, {exc}. Doosra time dekh lein?"))
        args = {"service": booking.service, "date": booking.date, "time": booking.time,
                "staff": booking.staff, "customer_name": customer_name, "phone": phone,
                "booking_id": booking.booking_id}
        try:
            code = _seal("book_appointment", args, proof, excerpt, conversation_id, True)
        except LedgerError as exc:
            backend.cancel(tenant_id, booking.booking_id)   # never leave an unsealed write
            return ToolResult("book_appointment", ok=False, error=str(exc),
                              spoken="Ek baar phir se confirm kar dijiye, main tab hi book karunga.")
        if code:
            backend.conn.execute("UPDATE bookings SET receipt_code=? WHERE booking_id=?",
                                 (code, booking.booking_id))
            backend.conn.commit()
            booking.receipt_code = code
        when = (f"{spoken_date(booking.date, backend.today, backend.resolve_date, lang)} "
                f"{spoken_time(booking.time, lang)}")
        spoken = _p("booked", "Ho gaya. {when}, {staff} ke saath.").format(
            when=when[0].upper() + when[1:], staff=booking.staff)
        if code:
            spoken += _p("booked_code", " Confirmation code {code}.").format(code=code)
        return ToolResult("book_appointment", ok=True, data=booking.as_dict(), spoken=spoken)

    async def cancel_appointment(phone: str, proof: ConfirmationProof | None = None,
                                 excerpt: str = "", conversation_id: str = "") -> ToolResult:
        booking = backend.find_booking(tenant_id, phone)
        if booking is None:
            return ToolResult("cancel_appointment", ok=False, error="no booking found",
                              spoken="Is number par koi booking nahi mili.")
        try:
            code = _seal("cancel_appointment",
                         {"booking_id": booking.booking_id, "phone": phone},
                         proof, excerpt, conversation_id, True)
        except LedgerError as exc:
            return ToolResult("cancel_appointment", ok=False, error=str(exc),
                              spoken="Cancel karne se pehle ek baar haan bol dijiye.")
        backend.cancel(tenant_id, booking.booking_id)
        when = spoken_date(booking.date, backend.today, backend.resolve_date)
        return ToolResult("cancel_appointment", ok=True, data={"booking_id": booking.booking_id,
                                                               "receipt_code": code},
                          spoken=f"Aapki {when} ki booking cancel kar di hai.")

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

    async def handoff(reason: str, phone: str | None = None,
                      proof: ConfirmationProof | None = None,
                      excerpt: str = "", conversation_id: str = "") -> ToolResult:
        code = _seal("handoff", {"reason": reason, "phone": phone}, proof, excerpt,
                     conversation_id, False)
        return ToolResult("handoff", ok=True, data={"reason": reason, "receipt_code": code},
                          spoken=pack.guardrails.escalation_line)

    # --------------------------------------------------------------- register
    reg.register(Tool("check_availability",
                      "Free slots for a service on a day.",
                      {"service": "service name from the catalogue",
                       "date": "today | tomorrow | day_after_tomorrow | weekday | ISO date",
                       "staff": "optional staff member"},
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
                       "phone": "ten digit phone number", "staff": "staff member"},
                      book_appointment, read_only=False, requires_confirmation=True,
                      ledgered=True, nominal_ms=260,
                      required=["service", "date", "time", "phone"]))
    reg.register(Tool("cancel_appointment",
                      "Cancel the caller's existing appointment. Requires confirmation.",
                      {"phone": "ten digit phone number"},
                      cancel_appointment, read_only=False, requires_confirmation=True,
                      ledgered=True, nominal_ms=210, required=["phone"]))
    reg.register(Tool("capture_lead",
                      "Record a caller the agent could not book, for a human to call back.",
                      {"intent": "what they wanted", "name": "caller's name",
                       "phone": "ten digit phone number", "note": "free text"},
                      capture_lead, read_only=False, ledgered=True, nominal_ms=110,
                      required=["intent"]))
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
