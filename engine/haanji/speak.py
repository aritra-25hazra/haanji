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
# A row may set "fraction_after" when the language says the fraction after
# the hour ("pathu arai mani", "padi ara gantalaku").
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
    "tanglish": {
        "morning": "kaalai", "afternoon": "madhiyam", "evening": "saayangalam",
        "half": "arai ", "quarter_past": "kaal ", "quarter_to": "mukkaal ",
        "fraction_after": "1",
        "oclock": "mani", "today": "innaiku", "tomorrow": "naalai",
        "day_after": "naalai marunaal",
        "ask_day": "Sari. Endha naal slot paakanum?",
        "ask_service": "Kandippa. Endha service venum — {services}, illa vera edhavadhu?",
        "ask_name_number": "Unga peru-um mobile number-um sollunga.",
        "ask_name": "Yaar peru-la book pannanum?",
        "confirm": "Oru vaati sollren — {what}, {when}{who}, {name} peru-la. Confirm pannalama?",
        "yes_or_no": "Aama illa illai-nu sollunga, appuram naan confirm pannuren.",
        "changed": "Sari, maathiduren. Endha naal illa endha time venum?",
        "more_help": "Vera edhavadhu theriya venuma?",
        "offer": "{when} slot irukku, {staff} kitta.",
        "offer_alt": " Illa {alt}.",
        "offer_ok": " Sari-yaa?",
        "booked": "Aayiduchu. {when}, {staff} kitta.",
        "booked_code": " Confirmation code {code}.",
        "closed_day": "Andha naal clinic leave.",
        "no_slots": "Andha naal slot edhuvum illa.",
        "leave_details": " Unga peru-um number-um kudunga, naanga call panni time fix pannidurom.",
        "lead_saved": "Unga number note pannitten, enga team call pannuvanga.",
        "slot_gone": "Andha slot ippo dhaan poiduchu, vera onnu paakalama?",
        "with": " {staff} kitta",
        "ask_period": "Kaalai, madhiyam illa saayangalam — endha time nalla irukkum?",
        "ask_date": "Endha thedhi illa endha naal? 'Naalai', 'thingal' illa '15 thedhi' maadhiri.",
        "no_slot_at": "{at}-ku idam illa. {alt} sari-yaa?",
        "no_slot_at_none": "{at}-ku idam illa, andha naal vera slot-um illa.",
        "past_day": "Andha naal poiduchu. Endha naal paakanum?",
        "period_relaxed": "{period} idam illa.",
        "no_discount": "Discount naan decide panna mudiyadhu, aana rate sollalaam. Endha service-ku?",
        "party_for": " {n} per-ku",
        "ask_code": "Safety-ku booking confirmation code sollunga (2504-7863 maadhiri).",
        "code_not_found": "Indha code-la booking kidaikala. Unga peru-um number-um kudunga, naanga call panni pannidurom.",
        "morning_w": "kaalai", "afternoon_w": "madhiyam", "evening_w": "saayangalam",
    },
    "tenglish": {
        "morning": "udayam", "afternoon": "madhyahnam", "evening": "sayantram",
        "half": "ara ", "quarter_past": "paavu ", "quarter_to": "muppaavu ",
        "fraction_after": "1",
        "oclock": "gantalaku", "today": "ivala", "tomorrow": "repu",
        "day_after": "ellundi",
        "ask_day": "Sare. Ye roju slot chudali?",
        "ask_service": "Alage. Ye test kavali — {services}, leka inkedaina?",
        "ask_name_number": "Mee peru, mobile number cheppandi.",
        "ask_name": "Evari peru meeda book cheyali?",
        "confirm": "Okasari cheptunna — {what}, {when}{who}, {name} peru meeda. Confirm cheyala?",
        "yes_or_no": "Avunu leka kaadu ani cheppandi, tarvata nenu confirm chestanu.",
        "changed": "Sare, marchestanu. Ye roju leka ye time kavali?",
        "more_help": "Inka emaina kavala?",
        "offer": "{when} slot khali undi, {staff} daggara.",
        "offer_alt": " Leka {alt}.",
        "offer_ok": " Sare na?",
        "booked": "Ayipoyindi. {when}, {staff} daggara.",
        "booked_code": " Confirmation code {code}.",
        "closed_day": "Aa roju lab closed.",
        "no_slots": "Aa roju inka slot khali ledu.",
        "leave_details": " Mee peru, number ivvandi, memu call chesi time fix chestamu.",
        "lead_saved": "Mee number note chesukunnanu, maa team call chestundi.",
        "slot_gone": "Aa slot ippude poyindi, inkokati chudala?",
        "with": " {staff} daggara",
        "ask_period": "Udayam, madhyahnam leka sayantram — ye time baguntundi?",
        "ask_date": "Ye tedi leka ye roju? 'Repu', 'somavaram' leka '15 tedi' laga.",
        "no_slot_at": "{at} ki place ledu. {alt} sare na?",
        "no_slot_at_none": "{at} ki place ledu, aa roju vere slot kuda ledu.",
        "past_day": "Aa roju aipoyindi. Ye roju chudali?",
        "period_relaxed": "{period} place ledu.",
        "no_discount": "Discount nenu decide cheyalenu, kani rate cheppagalanu. Ye test ki?",
        "party_for": " {n} mandiki",
        "ask_code": "Safety kosam booking confirmation code cheppandi (2504-7863 laga).",
        "code_not_found": "Ee code meeda booking dorakaledu. Mee peru, number ivvandi, memu call chesi chestamu.",
        "morning_w": "udayam", "afternoon_w": "madhyahnam", "evening_w": "sayantram",
    },
    "gujlish": {
        "morning": "savare", "afternoon": "bapore", "evening": "sanje",
        "half": "sada ", "quarter_past": "sava ", "quarter_to": "pona ",
        "oclock": "vage", "today": "aaje", "tomorrow": "kale",
        "day_after": "param divase",
        "ask_day": "Barabar. Kya divas no slot joiye?",
        "ask_service": "Chokkas. Kai service joiye — {services}, ke biju kai?",
        "ask_name_number": "Tamaru naam ane mobile number aapo.",
        "ask_name": "Kona naam par booking karu?",
        "confirm": "Ek vaar repeat karu — {what}, {when}{who}, {name} na naam par. Confirm karu?",
        "yes_or_no": "Fakt haa ke na kaho, pachhi hu confirm karish.",
        "changed": "Barabar, badli daish. Kyo divas ke kyo time joiye?",
        "more_help": "Biju kai janvu che?",
        "offer": "{when} slot khali che, {staff} sathe.",
        "offer_alt": " Ke pachhi {alt}.",
        "offer_ok": " Chalse?",
        "booked": "Thai gayu. {when}, {staff} sathe.",
        "booked_code": " Confirmation code {code}.",
        "closed_day": "E divas ame band hoiye chhiye.",
        "no_slots": "E divas koi slot khali nathi.",
        "leave_details": " Tamaru naam ane number aapo, ame call karine time nakki karishu.",
        "lead_saved": "Tamaro number lakhi lidho, amari team call karse.",
        "slot_gone": "E slot hamna j gayo, biju joiye?",
        "with": " {staff} sathe",
        "ask_period": "Savare, bapore ke sanje — kyo time barabar rahese?",
        "ask_date": "Kai tarikh ke kyo divas? Jem ke 'kale', 'somvar' ke '15 tarikh'.",
        "no_slot_at": "{at} jagya nathi. {alt} chalse?",
        "no_slot_at_none": "{at} jagya nathi, ane e divas biju slot pan khali nathi.",
        "past_day": "E divas to jato rahyo. Kyo divas joiye?",
        "period_relaxed": "{period} jagya nathi.",
        "no_discount": "Discount no nirnay hu na lai shaku, pan fees kahi shaku. Kai service mate?",
        "party_for": " {n} jan mate",
        "ask_code": "Suraksha mate booking no confirmation code kaho (jem ke 2504-7863).",
        "code_not_found": "Aa code par booking mali nahi. Tamaru naam ane number aapo, ame call karine kari daishu.",
        "morning_w": "savare", "afternoon_w": "bapore", "evening_w": "sanje",
    },
    "punglish": {
        "morning": "savere", "afternoon": "dupahir", "evening": "shaam",
        "half": "saadhe ", "quarter_past": "sava ", "quarter_to": "paune ",
        "oclock": "vaje", "today": "ajj", "tomorrow": "kal",
        "day_after": "parso",
        "ask_day": "Theek hai ji. Kehde din da slot vekhna?",
        "ask_service": "Zaroor ji. Kehdi service chahidi — {services}, ya kuch hor?",
        "ask_name_number": "Bas apna naam te mobile number dasso ji.",
        "ask_name": "Kis naam te booking karni?",
        "confirm": "Ik vaari dohra dinda — {what}, {when}{who}, {name} de naam te. Confirm kar dawan?",
        "yes_or_no": "Bas haan ya nahi kaho ji, phir main confirm karda.",
        "changed": "Theek hai ji, badal dinde haan. Kehda din ya kehda time chahida?",
        "more_help": "Hor kuch puchhna si?",
        "offer": "{when} slot khali hai, {staff} naal.",
        "offer_alt": " Ya phir {alt}.",
        "offer_ok": " Chalega ji?",
        "booked": "Ho gaya ji. {when}, {staff} naal.",
        "booked_code": " Confirmation code {code}.",
        "closed_day": "Us din salon band hunda ji.",
        "no_slots": "Us din koi slot khali nahi ji.",
        "leave_details": " Apna naam te number dasso, assi call karke time set kar dange.",
        "lead_saved": "Tuhada number likh liya ji, saadi team call karegi.",
        "slot_gone": "Oh slot hune hi gaya, hor vekhiye?",
        "with": " {staff} naal",
        "ask_period": "Savere, dupahir ya shaam — kehda time theek rahega?",
        "ask_date": "Kehdi tareekh ya kehda din? Jiven 'kal', 'somvar' ya '15 tareekh'.",
        "no_slot_at": "{at} jagah nahi ji. {alt} chalega?",
        "no_slot_at_none": "{at} jagah nahi, te us din hor koi slot vi khali nahi.",
        "past_day": "Oh din ta nikal gaya ji. Kehda din vekhna?",
        "period_relaxed": "{period} jagah nahi.",
        "no_discount": "Discount da faisla main nahi kar sakda ji, par rate zaroor dass sakda. Kehdi service layi?",
        "party_for": " {n} jaana layi",
        "ask_code": "Safety layi booking da confirmation code dasso ji (jiven 2504-7863).",
        "code_not_found": "Es code te koi booking nahi mili. Naam te number dasso, assi call karke kar dange.",
        "morning_w": "savere", "afternoon_w": "dupahir", "evening_w": "shaam",
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
    after = bool(t.get("fraction_after"))   # Tamil/Telugu: "pathu arai", the fraction follows the hour
    h12 = h if 1 <= h <= 12 else (h - 12 or 12)
    if m == 45 and not after:
        h12 = h12 % 12 + 1                     # paune das = quarter to ten; "pathu mukkaal" keeps ten
    halves = {30: t.get("half", "saade "), 15: t.get("quarter_past", "sava "),
              45: t.get("quarter_to", "paune ")}
    prefix = halves.get(m, "")
    minutes = "" if m in halves or m == 0 else f":{m:02d}"
    if after:
        return f"{part} {h12}{minutes} {prefix}{t.get('oclock', 'baje')}"
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
