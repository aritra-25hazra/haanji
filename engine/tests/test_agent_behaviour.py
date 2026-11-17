"""How the agent behaves on a real call, case by case from the live review:
it says it is an AI, knows how callers name dental work, keeps a name or a
number whenever it is given, explains a bad number and gives up after two,
says a requested time is free before asking for details, reads back the
number's last digits, asks "aur kuch?" once after a booking, and never
promises a transfer when the shop is closed."""
import datetime as dt
import sqlite3

from haanji.adapters.mock import NullTTS
from haanji.models import Outcome
from haanji.pipeline import CallSession
from haanji.pramaan.ledger import Ledger
from haanji.tools.builtin import build_registry, open_backend

TODAY = dt.date(2026, 9, 7)          # a Monday
TENANT = "t_behaviour"


def call(pack, now: dt.datetime | None = None):
    backend, _ = open_backend(pack, TENANT, today=TODAY)
    if now is not None:
        backend._now = now
    ledger = Ledger(sqlite3.connect(":memory:"))
    registry = build_registry(TENANT, backend, pack, ledger)
    session = CallSession(tenant_id=TENANT, pack=pack, backend=backend, registry=registry, ledger=ledger, tts=NullTTS())
    return session, ledger


async def say(s, *lines):
    record = None
    for line in lines:
        record = await s.handle_text_turn(line)
    return record


async def test_the_greeting_and_the_answer_to_are_you_a_robot_say_it_is_an_ai(pack):
    s, _ = call(pack)
    await s.open()
    assert "AI assistant" in s.ctx.last_agent_utterance
    r = await say(s, "aap insaan ho ya robot?")
    assert "Smile Care Dental ka AI assistant" in r.said and "staff se jod" in r.said
    assert "Kaunsi service" not in r.said


async def test_a_pack_can_switch_the_greeting_s_ai_note_off(pack):
    pack.persona.ai_note = ""
    s, _ = call(pack)
    await s.open()
    assert s.ctx.last_agent_utterance == pack.persona.greeting


async def test_everyday_words_for_dental_work_reach_the_right_service(pack):
    cases = {"akal daad nikalwani hai": "tooth extraction", "daant ukhadwana hai": "tooth extraction",
             "daant mein keeda lag gaya hai": "dental checkup", "masoodon se khoon aata hai, dikhana hai": "dental checkup",
             "daant ki safai karwani hai": "teeth cleaning"}
    for text, service in cases.items():
        s, _ = call(pack)
        await say(s, text)
        assert s.ctx.service == service, text


async def test_a_name_given_while_choosing_a_slot_is_kept_and_never_asked_again(pack):
    s, _ = call(pack)
    await say(s, "kal subah teeth cleaning karwani hai")
    assert s.ctx.last_offered_slots
    r = await say(s, "naam Amit hai, pehla wala theek hai")
    assert s.ctx.customer_name == "Amit"
    assert "naam" not in r.said.lower() and "mobile number" in r.said


async def test_a_bad_number_is_explained_and_the_second_one_hands_off(pack):
    s, _ = call(pack)
    await say(s, "kal subah teeth cleaning karwani hai", "haan pehla wala theek hai")
    r = await say(s, "naam Amit hai number 12345")
    assert "10 digit" in r.said and s.ctx.customer_name == "Amit"
    r = await say(s, "98765 432")
    assert "handoff" in r.tools and s.ctx.outcome == Outcome.HANDED_OFF
    assert "WhatsApp" in r.said
    assert s.ctx.flags.get("ended")


async def test_a_named_time_is_said_to_be_free_before_details_are_asked(pack):
    s, _ = call(pack)
    r = await say(s, "kal subah 10 baje teeth cleaning karwani hai")
    assert "khaali hai" in r.said and "ke saath" in r.said
    assert r.said.index("khaali hai") < r.said.lower().index("naam")


async def test_the_confirmation_reads_back_the_number_s_last_four_digits_and_asks_for_more_once(pack):
    s, ledger = call(pack)
    r = await say(s, "kal subah 10 baje teeth cleaning karwani hai", "Amit Verma 9876543210")
    assert "3 2 1 0" in r.said and "Confirm kar dun" in r.said
    r = await say(s, "haan confirm kar do")
    assert s.ctx.outcome == Outcome.BOOKED and "Aur kuch madad chahiye" in r.said
    assert not s.ctx.flags.get("ended")
    r = await say(s, "nahi bas, dhanyavaad")
    assert s.ctx.flags.get("ended") and r.said == pack.persona.closing


async def test_an_emergency_after_hours_promises_no_transfer_and_is_an_urgent_callback(pack):
    late = dt.datetime(2026, 9, 7, 21, 0)            # the clinic closes at 20:00
    s, ledger = call(pack, now=late)
    r = await say(s, "khoon ruk nahi raha daant se")
    assert "jod raha" not in r.said and "band" in r.said and "hospital" in r.said
    assert s.ctx.outcome == Outcome.HANDED_OFF and r.guard == "emergency.bleeding"
    sealed = [rc for rc in ledger.receipts(TENANT) if rc.action == "handoff"]
    assert sealed and sealed[-1].action_args.get("urgent") is True


async def test_an_emergency_in_opening_hours_still_puts_the_caller_through(pack):
    s, _ = call(pack, now=dt.datetime(2026, 9, 7, 11, 0))
    r = await say(s, "khoon ruk nahi raha daant se")
    assert r.said.startswith(pack.guardrails.escalation_line[:20])


async def test_a_pack_can_name_its_own_emergency_contact(pack):
    pack.guardrails.emergency_contact = "108"
    s, _ = call(pack, now=dt.datetime(2026, 9, 7, 22, 30))
    r = await say(s, "bahut zyada khoon aa raha hai")
    assert "108" in r.said
