"""The owner console's operations: the calendar, customers, settings, the
waitlist, payments and backups.

A router built against a small set of dependencies the server hands in, so
this file stays readable and testable on its own. Every write a person makes
here is sealed in the Pramaan ledger like the agent's own writes — a staff
cancellation is as much a fact about the booking as the caller's was."""
from __future__ import annotations
import datetime as dt
import io
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from . import backup as backup_mod
from .backend.local import BOOKING_STATUSES, BackendError
from .payments import PaymentStore, configured as payments_configured, verify_razorpay_signature
from .settings import SettingsError, SettingsStore

log = logging.getLogger("haanji.admin")


@dataclass
class Deps:
    runtime: Callable[[str], Any]
    list_packs: Callable[[], list[str]]
    default_pack: str
    store: Any
    settings: SettingsStore
    payments: PaymentStore
    vault: Any
    publish: Callable[..., Any]
    mask: Callable[[str | None], str | None]
    user_of: Callable[[Request], Any]
    offer_waitlist: Callable[[Any, str, str | None], Awaitable[Any]]
    var_dir: str
    public_url: str


class StatusIn(BaseModel):
    status: str = Field(max_length=16)


def _who(request: Request, deps: Deps) -> str:
    who = deps.user_of(request)
    return (who.name or who.phone) if who else "console"


def _is_owner(request: Request, deps: Deps) -> bool:
    who = deps.user_of(request)
    return who is None or who.role == "owner"        # auth off: the console is the owner's


def _seal(rt, action: str, args: dict[str, Any], who: str) -> str | None:
    """A console action in the ledger: who did it, when, to which booking."""
    args = {**args, "by": who, "channel": "console"}
    receipt = rt.ledger.append(tenant_id=rt.pack_id, conversation_id="console", action=action,
                               action_args=args, confirmation=None, transcript_excerpt=f"console: {who}",
                               agent_config_version=rt.pack.version, require_confirmation=False)
    return receipt.short_code()


def build_router(deps: Deps) -> APIRouter:
    r = APIRouter()

    def _pack(pack: str):
        if pack not in deps.list_packs():
            raise HTTPException(404, f"unknown pack {pack}")
        return deps.runtime(pack)

    # ----------------------------------------------------------- bookings
    @r.get("/api/bookings")
    async def bookings(request: Request, pack: str = deps.default_pack, from_: str | None = None,
                       to: str | None = None, status: str = "CONFIRMED"):
        rt = _pack(pack)
        start = request.query_params.get("from") or from_ or rt.backend.today.isoformat()
        try:
            end = to or (dt.date.fromisoformat(start) + dt.timedelta(days=6)).isoformat()
            dt.date.fromisoformat(start), dt.date.fromisoformat(end)
        except ValueError:
            raise HTTPException(422, "from/to must be YYYY-MM-DD")
        if status not in BOOKING_STATUSES and status != "ALL":
            raise HTTPException(422, f"status must be one of {', '.join(BOOKING_STATUSES)} or ALL")
        owner = _is_owner(request, deps)
        out = []
        for b in rt.backend.bookings_between(pack, start, end, status):
            d = b.as_dict()
            if not owner:
                d["phone"] = deps.mask(d["phone"])
            pay = deps.payments.for_booking(b.booking_id)
            d["deposit_inr"] = pay["amount_inr"] if pay else 0
            d["payment_link"] = pay["link"] if pay and pay["status"] == "CREATED" else None
            d["payment_status"] = pay["status"] if pay else None
            out.append(d)
        return {"pack": pack, "from": start, "to": end, "status": status, "bookings": out}

    @r.post("/api/bookings/{booking_id}/cancel")
    async def booking_cancel(booking_id: str, request: Request, pack: str = deps.default_pack):
        rt = _pack(pack)
        b = rt.backend.booking(pack, booking_id)
        if b is None:
            raise HTTPException(404, "no such booking")
        if b.status != "CONFIRMED":
            raise HTTPException(409, f"booking is {b.status}")
        who = _who(request, deps)
        code = _seal(rt, "staff_cancel", deps.vault.seal_args(
            {"booking_id": b.booking_id, "service": b.service, "date": b.date, "time": b.time, "staff": b.staff,
             "customer_name": b.customer_name, "phone": b.phone, "previous_receipt": b.receipt_code}, pack), who)
        rt.backend.cancel(pack, b.booking_id)
        deps.publish("booking.cancelled", pack=pack, booking_id=b.booking_id, by=who, receipt=code)
        try:
            await deps.offer_waitlist(rt, b.date, b.service)
        except Exception as exc:                              # noqa: BLE001 - a courtesy
            log.warning("waitlist offer failed: %s", exc)
        return {"ok": True, "booking_id": b.booking_id, "receipt_code": code}

    @r.post("/api/bookings/{booking_id}/status")
    async def booking_status(booking_id: str, body: StatusIn, request: Request, pack: str = deps.default_pack):
        rt = _pack(pack)
        b = rt.backend.booking(pack, booking_id)
        if b is None:
            raise HTTPException(404, "no such booking")
        status = body.status.upper()
        if status not in ("NO_SHOW", "COMPLETED", "CONFIRMED"):
            raise HTTPException(422, "status must be NO_SHOW, COMPLETED or CONFIRMED")
        try:
            changed = rt.backend.set_status(pack, b.booking_id, status)
        except BackendError as exc:
            raise HTTPException(422, str(exc))
        if not changed:
            raise HTTPException(409, "a cancelled booking cannot change status")
        who = _who(request, deps)
        code = _seal(rt, "staff_update", {"booking_id": b.booking_id, "from": b.status, "to": status,
                                          "previous_receipt": b.receipt_code}, who)
        deps.publish("booking.status", pack=pack, booking_id=b.booking_id, status=status, by=who)
        return {"ok": True, "booking_id": b.booking_id, "status": status, "receipt_code": code}

    # ---------------------------------------------------------- customers
    @r.get("/api/customers")
    async def customers(request: Request, pack: str = deps.default_pack, q: str | None = None):
        rt = _pack(pack)
        owner = _is_owner(request, deps)
        rows = rt.backend.customers(pack, q)
        if not owner:
            for row in rows:
                row["phone"] = deps.mask(row["phone"])
        return {"pack": pack, "customers": rows}

    # ----------------------------------------------------------- settings
    @r.get("/api/settings")
    async def settings_get(pack: str = deps.default_pack):
        _pack(pack)
        return {"pack": pack, "settings": deps.settings.get(pack),
                "payments_provider": "razorpay" if payments_configured() else "mock"}

    @r.put("/api/settings")
    async def settings_put(request: Request, pack: str = deps.default_pack):
        _pack(pack)
        try:
            changes = await request.json()
        except ValueError:
            raise HTTPException(400, "not json")
        if not isinstance(changes, dict):
            raise HTTPException(422, "a JSON object of settings")
        try:
            current = deps.settings.update(pack, changes)
        except SettingsError as exc:
            raise HTTPException(422, str(exc))
        deps.publish("settings.changed", pack=pack, keys=sorted(changes), by=_who(request, deps))
        return {"pack": pack, "settings": current}

    # ----------------------------------------------------------- waitlist
    @r.get("/api/waitlist")
    async def waitlist(pack: str = deps.default_pack, status: str | None = None):
        rt = _pack(pack)
        return {"pack": pack, "entries": rt.backend.waitlist(pack, status)}

    @r.delete("/api/waitlist/{entry_id}")
    async def waitlist_remove(entry_id: str, pack: str = deps.default_pack):
        rt = _pack(pack)
        return {"removed": rt.backend.waitlist_remove(pack, entry_id)}

    # ----------------------------------------------------------- payments
    @r.get("/api/payments")
    async def payments(pack: str = deps.default_pack):
        _pack(pack)
        return {"pack": pack, "provider": "razorpay" if payments_configured() else "mock",
                "payments": deps.payments.list(pack), "summary": deps.payments.summary(pack)}

    async def _settle(payment_id: str, status: str, provider_id: str | None) -> dict[str, Any] | None:
        pay = deps.payments.get(payment_id)
        if pay is None:
            return None
        if status == "PAID" and pay["status"] != "PAID":
            rt = deps.runtime(pay["tenant_id"])
            code = _seal(rt, "payment_received", {"payment_id": payment_id, "booking_id": pay["booking_id"],
                                                  "amount_inr": pay["amount_inr"], "provider": pay["provider"],
                                                  "provider_payment_id": provider_id}, "payment-webhook")
            rt.backend.mark_paid(pay["tenant_id"], pay["booking_id"], payment_id, True)
            pay = deps.payments.mark(payment_id, "PAID", receipt_code=code)
            deps.publish("payment.received", pack=pay["tenant_id"], booking_id=pay["booking_id"],
                         amount_inr=pay["amount_inr"], receipt=code)
        elif status != "PAID":
            pay = deps.payments.mark(payment_id, status)
        return pay

    @r.post("/payments/razorpay/webhook")
    async def razorpay_webhook(request: Request):
        raw = await request.body()
        secret = os.environ.get("HAANJI_RAZORPAY_WEBHOOK_SECRET")
        if not secret:
            raise HTTPException(403, "HAANJI_RAZORPAY_WEBHOOK_SECRET is not set")
        if not verify_razorpay_signature(secret, raw, request.headers.get("X-Razorpay-Signature")):
            raise HTTPException(403, "bad signature")
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            raise HTTPException(400, "not json")
        payment_id, provider_id, status = PaymentStore.from_webhook(payload)
        if not payment_id or not status:
            return {"ok": True, "ignored": True}
        pay = await _settle(payment_id, status, provider_id)
        return {"ok": True, "payment_id": payment_id, "status": pay["status"] if pay else None}

    # The mock provider: a page on this server that "pays" with one click.
    @r.get("/pay/{payment_id}", response_class=HTMLResponse)
    async def pay_page(payment_id: str):
        pay = deps.payments.get(payment_id)
        if pay is None:
            raise HTTPException(404, "no such payment")
        rt = deps.runtime(pay["tenant_id"])
        business = rt.pack.persona.business_name
        if pay["provider"] != "mock":
            return RedirectResponse(pay["link"])
        paid = pay["status"] == "PAID"
        body = f"""<!doctype html><html lang="hi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Deposit · {business}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:28rem;margin:3rem auto;padding:0 1rem;color:#1b1b1b}}
button{{font:inherit;padding:.8rem 1.4rem;border:0;border-radius:.6rem;background:#1F6B45;color:#fff;cursor:pointer}}
.ok{{color:#1F6B45}} small{{color:#666}}</style>
<h1>{business}</h1>
<p>Booking deposit: <strong>₹{pay['amount_inr']:,}</strong></p>
{'<p class="ok">Paid. Shukriya!</p>' if paid else
 f'<form method="post" action="/pay/{payment_id}/mock-pay"><button>Pay ₹{pay["amount_inr"]:,} (demo)</button></form>'}
<p><small>Demo payment page: koi asli paisa nahi jaata. Razorpay keys lagte hi yahi link UPI/card par le jaata hai.</small></p>
</html>"""
        return HTMLResponse(body)

    @r.post("/pay/{payment_id}/mock-pay")
    async def pay_mock(payment_id: str):
        pay = deps.payments.get(payment_id)
        if pay is None:
            raise HTTPException(404, "no such payment")
        if pay["provider"] != "mock":
            raise HTTPException(409, "a real provider settles this link")
        await _settle(payment_id, "PAID", "mock_" + payment_id)
        return RedirectResponse(f"/pay/{payment_id}", status_code=303)

    @r.get("/pay/{payment_id}/done")
    async def pay_done(payment_id: str):
        return RedirectResponse(f"/pay/{payment_id}", status_code=303)

    # ------------------------------------------------------------- backup
    @r.get("/api/admin/backup")
    async def admin_backup(request: Request):
        if not _is_owner(request, deps):
            raise HTTPException(403, "owner role needed")
        data = backup_mod.make_backup(deps.var_dir)
        return Response(data, media_type="application/gzip",
                        headers={"Content-Disposition": f'attachment; filename="{backup_mod.backup_name()}"'})

    return r
