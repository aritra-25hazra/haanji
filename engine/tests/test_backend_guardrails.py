"""The business rules the agent is not allowed to talk its way around."""
import datetime as dt

import pytest

from haanji.backend.local import BackendError
from haanji.guardrails import Action, Guard

TENANT = "t_test"
TOMORROW = "2026-09-08"


def test_the_same_slot_cannot_be_booked_twice(backend):
    backend.book(tenant_id=TENANT, service="root canal", date=TOMORROW, time="09:30",
                 staff="Dr Sheikh", phone="9876543210")
    with pytest.raises(BackendError):
        backend.book(tenant_id=TENANT, service="root canal", date=TOMORROW, time="09:30",
                     staff="Dr Sheikh", phone="9811111111")


def test_a_time_outside_working_hours_is_refused(backend):
    with pytest.raises(BackendError):
        backend.book(tenant_id=TENANT, service="root canal", date=TOMORROW, time="23:00",
                     staff="Dr Sheikh", phone="9876543210")


def test_a_closed_day_offers_nothing(backend):
    async def go():
        return await backend.availability(TENANT, "root canal", "2026-09-13")   # Sunday
    import asyncio
    data = asyncio.run(go())
    assert data["closed"] and data["slots"] == []


def test_availability_skips_what_is_already_booked(backend):
    import asyncio
    first = asyncio.run(backend.availability(TENANT, "root canal", "tomorrow"))["slots"][0]
    backend.book(tenant_id=TENANT, service="root canal", date=first["date"],
                 time=first["time"], staff=first["staff"], phone="9876543210")
    after = asyncio.run(backend.availability(TENANT, "root canal", "tomorrow"))["slots"]
    assert all(s["time"] != first["time"] for s in after if s["staff"] == first["staff"])


def test_availability_respects_the_lunch_break(backend):
    import asyncio
    slots = asyncio.run(backend.availability(TENANT, "root canal", "tomorrow", limit=20))
    assert all(not ("14:00" <= s["time"] < "15:30") for s in slots["slots"])


def test_a_booking_updates_the_customer_record(backend):
    backend.book(tenant_id=TENANT, service="root canal", date=TOMORROW, time="09:30",
                 staff="Dr Sheikh", customer_name="Vijay", phone="9876543210")
    import asyncio
    found = asyncio.run(backend.lookup_customer(TENANT, "9876543210"))
    assert found["found"] and found["customer"]["name"] == "Vijay"


def test_date_tokens_resolve_relative_to_the_business_day(backend):
    assert backend.resolve_date("today") == "2026-09-07"
    assert backend.resolve_date("tomorrow") == "2026-09-08"
    assert backend.resolve_date("day_after_tomorrow") == "2026-09-09"
    assert backend.resolve_date("friday") == "2026-09-11"


ESCALATE = ["bahut zyada khoon aa raha hai", "accident ho gaya hai",
            "refund chahiye mujhe", "manager se baat karao",
            "pichhli baar service kharab thi"]
REFUSE = ["kaunsi dawai lun", "report mein sugar zyada hai kya khatra hai",
          "guarantee do ki selection ho jayega", "thoda discount kar do"]
ALLOW = ["clinic ke timings kya hain", "report kab milegi",
         "kal root canal ka slot chahiye", "parking hai kya",
         "insurance chalta hai kya", "mera naam Vijay hai"]


@pytest.mark.parametrize("text", ESCALATE)
def test_emergencies_and_disputes_leave_the_automation(pack, text):
    assert Guard(pack).check(text).action is Action.ESCALATE


@pytest.mark.parametrize("text", REFUSE)
def test_advice_and_promises_are_refused(pack, text):
    assert Guard(pack).check(text).action is Action.REFUSE


@pytest.mark.parametrize("text", ALLOW)
def test_ordinary_business_questions_pass(pack, text):
    assert Guard(pack).check(text).action is Action.ALLOW


def test_a_price_outside_the_catalogue_is_never_quoted(pack):
    guard = Guard(pack)
    assert guard.price_allowed("root canal")
    assert not guard.price_allowed("teeth whitening")
    assert not guard.price_allowed(None)


def test_phone_numbers_are_redacted_in_stored_excerpts(pack):
    assert Guard.redact("number 9876543210 hai") == "number 98XXXXXX10 hai"
