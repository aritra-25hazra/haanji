"""Turning data back into the way people say it.

A confirmation the caller cannot parse is not a confirmation, so dates and
times are read out the way a receptionist would say them — "kal subah saade
nau baje", not "2026-09-08 09:30". The ledger stores the machine form; only
the spoken layer is idiomatic."""
from __future__ import annotations
import datetime as dt

HALVES = {30: "saade ", 15: "sava ", 45: "paune "}

# Per-language surface forms. The default is the Hinglish the packs shipped
# with; "benglish" swaps the time-and-date words and the handful of fixed
# lines the policy and the tools speak. Adding a language is adding a row.
LANG: dict[str, dict[str, str]] = {
    "hinglish": {},
    "benglish": {
        "morning": "shokal", "afternoon": "dupur", "evening": "bikel",
        "half": "share ", "quarter_past": "shoa ", "quarter_to": "poune ",
        "oclock": "tay", "today": "aajke", "tomorrow": "kalke",
        "day_after": "porshu",
        "ask_day": "Thik ache. Kon din er slot dekhbo?",
        "ask_service": "Nishchoi. Kon service chai — {services}, na onno kichhu?",
        "ask_name_number": "Shudhu apnar naam ar mobile number ta bolun.",
        "ask_name": "Kar naame booking korbo?",
        "confirm": "Ek bar bole nichhi — {what}, {when}{who}, {name} er naame. Confirm korbo?",
        "yes_or_no": "Shudhu hyan ba na bolun, tarpor ami confirm korbo.",
        "changed": "Thik ache, bodle dichhi. Kon din ba kon shomoy chai?",
        "more_help": "Aar kichhu jante chan?",
        "offer": "{when} khali ache, {staff} er sathe.",
        "offer_alt": " Ba {alt}.",
        "offer_ok": " Cholbe?",
        "booked": "Hoye gechhe. {when}, {staff} er sathe.",
        "booked_code": " Confirmation code {code}.",
        "closed_day": "Oi din amra bondho thaki.",
        "no_slots": "Oi din ar kono slot khali nei.",
        "leave_details": " Apnar naam ar number diye din, amra phone kore shomoy thik kore debo.",
        "lead_saved": "Apnar number likhe niyechhi, amader team phone korbe.",
        "slot_gone": "Oi slot ektu aage chole gelo, onno ekta dekhi?",
        "with": " {staff} er sathe",
        "ask_period": "Shokal, dupur na bikel — kon shomoy ta bhalo hobe?",
        "ask_date": "Kon tarikh ba kon din? Jemon 'kalke', 'shombar' ba '15 tarikh'.",
        "no_slot_at": "{at} e jayga nei. {alt} cholbe?",
        "no_slot_at_none": "{at} e jayga nei, ar oi din onno slot o khali nei.",
        "past_day": "Oi din to chole gechhe. Kon din dekhbo?",
        "period_relaxed": "{period} e jayga nei.",
        "no_discount": "Discount er shiddhanto ami nite pari na, tobe rate bolte pari. Kon service er jonno?",
        "party_for": " {n} joner jonno",
        "ask_code": "Nirapottar jonno booking er confirmation code ta bolun (jemon 2504-7863).",
        "code_not_found": "Ei code e kono booking pelam na. Apnar naam ar number din, amra phone kore kore debo.",
        "morning_w": "shokal", "afternoon_w": "dupur", "evening_w": "bikel",
    },
    "marathinglish": {
        "morning": "sakali", "afternoon": "dupari", "evening": "sandhyakali",
        "half": "sade ", "quarter_past": "sava ", "quarter_to": "paune ",
        "oclock": "vajta", "today": "aaj", "tomorrow": "udya",
        "day_after": "parva",
        "ask_day": "Thik aahe. Kontya divshi slot baghu?",
        "ask_service": "Nakki. Konti service pahije — {services}, ki dusri kahi?",
        "ask_name_number": "Fakt tumcha naav ani mobile number sanga.",
        "ask_name": "Konachya naavane booking karu?",
        "confirm": "Ekda parat sangto — {what}, {when}{who}, {name} chya naavane. Confirm karu?",
        "yes_or_no": "Fakt ho kinva nahi sanga, mag mi confirm karto.",
        "changed": "Thik aahe, badalto. Konta divas kinva vel pahije?",
        "more_help": "Ajun kahi vicharaycha aahe?",
        "offer": "{when} slot rikama aahe, {staff} kade.",
        "offer_alt": " Kinva {alt}.",
        "offer_ok": " Chalel?",
        "booked": "Zala. {when}, {staff} kade.",
        "booked_code": " Confirmation code {code}.",
        "closed_day": "Tya divshi aamhi band asto.",
        "no_slots": "Tya divshi ajun slot rikama nahi.",
        "leave_details": " Tumcha naav ani number dya, aamhi phone karun vel tharvu.",
        "lead_saved": "Tumcha number lihun ghetla, aamchi team phone karel.",
        "slot_gone": "To slot aatach gela, dusra baghu?",
        "with": " {staff} kade",
        "ask_period": "Sakali, dupari ki sandhyakali — konti vel barobar aahe?",
        "ask_date": "Konti tarikh kinva konta divas? Jase 'udya', 'somvar' kinva '15 tarikh'.",
        "no_slot_at": "{at} la jaga nahi. {alt} chalel?",
        "no_slot_at_none": "{at} la jaga nahi, ani tya divshi dusra slot pan rikama nahi.",
        "past_day": "To divas tar nighun gela. Konta divas baghu?",
        "period_relaxed": "{period} jaga nahi.",
        "no_discount": "Discount cha nirnay mi gheu shakat nahi, pan rate sangu shakto. Kontya service sathi?",
        "party_for": " {n} lokansathi",
        "ask_code": "Surakshesathi booking cha confirmation code sanga (jase 2504-7863).",
        "code_not_found": "Ya code var booking sapadli nahi. Tumcha naav ani number dya, aamhi phone karun karu.",
        "morning_w": "sakali", "afternoon_w": "dupari", "evening_w": "sandhyakali",
    },
}


def phrase(lang: str, key: str, default: str) -> str:
    return LANG.get(lang, {}).get(key, default)


def spoken_time(hhmm: str, lang: str = "hinglish") -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    t = LANG.get(lang, {})
    parts = (t.get("morning", "subah"), t.get("afternoon", "dopahar"),
             t.get("evening", "shaam"))
    part = parts[0] if h < 12 else (parts[1] if h < 16 else parts[2])
    h12 = h if 1 <= h <= 12 else (h - 12 or 12)
    if m == 45:
        h12 = h12 % 12 + 1                     # paune das = quarter to ten
    halves = {30: t.get("half", "saade "), 15: t.get("quarter_past", "sava "),
              45: t.get("quarter_to", "paune ")}
    prefix = halves.get(m, "")
    minutes = "" if m in halves or m == 0 else f":{m:02d}"
    return f"{part} {prefix}{h12}{minutes} {t.get('oclock', 'baje')}"


def spoken_date(iso_or_token: str, today: dt.date, resolve, lang: str = "hinglish") -> str:
    t = LANG.get(lang, {})
    day = dt.date.fromisoformat(resolve(iso_or_token))
    delta = (day - today).days
    if delta == 0:
        return t.get("today", "aaj")
    if delta == 1:
        return t.get("tomorrow", "kal")
    if delta == 2:
        return t.get("day_after", "parso")
    if 3 <= delta <= 6:
        return day.strftime("%A")
    return day.strftime("%d %B")


def rupees(n: int | None) -> str:
    if n is None:
        return "charge counter par bata denge"
    if n == 0:
        return "bilkul free"
    return f"{n:,} rupaye"
