"""Hinglish (Hindi in Latin letters) to Devanagari, for display.

Romanised Hindi has no spelling standard, so this is a reading aid, not a
translation: a dictionary of the words a receptionist's call is made of,
the pack's own English catalogue words, and a small set of letter rules for
everything else. The output is labelled approximate wherever it is shown.
"""
from __future__ import annotations
import re

# The words a booking call is made of. Spellings people actually type.
WORDS: dict[str, str] = {
    "haan": "हाँ", "haanji": "हाँजी", "han": "हाँ", "ji": "जी", "nahi": "नहीं", "nahin": "नहीं", "na": "ना",
    "hai": "है", "hain": "हैं", "tha": "था", "thi": "थी", "the": "थे", "ho": "हो", "hoon": "हूँ", "hun": "हूँ", "hoga": "होगा", "hogi": "होगी",
    "main": "मैं", "mujhe": "मुझे", "mera": "मेरा", "meri": "मेरी", "mere": "मेरे", "hum": "हम", "hume": "हमें", "humein": "हमें", "hamara": "हमारा",
    "aap": "आप", "aapka": "आपका", "aapki": "आपकी", "aapke": "आपके", "aapko": "आपको", "tum": "तुम",
    "kya": "क्या", "kab": "कब", "kahan": "कहाँ", "kaun": "कौन", "kaise": "कैसे", "kyun": "क्यों", "kitna": "कितना", "kitne": "कितने", "kitni": "कितनी", "kaunsa": "कौनसा", "kaunse": "कौनसे",
    "ka": "का", "ki": "की", "ke": "के", "ko": "को", "se": "से", "me": "में", "mein": "में", "par": "पर", "pe": "पे", "aur": "और", "ya": "या", "bhi": "भी", "to": "तो", "toh": "तो", "hi": "ही", "bas": "बस", "sirf": "सिर्फ़",
    "kal": "कल", "aaj": "आज", "parso": "परसों", "abhi": "अभी", "subah": "सुबह", "shaam": "शाम", "dopahar": "दोपहर", "raat": "रात", "baje": "बजे", "din": "दिन", "ghanta": "घंटा", "minute": "मिनट", "hafta": "हफ़्ता",
    "theek": "ठीक", "thik": "ठीक", "accha": "अच्छा", "achha": "अच्छा", "acha": "अच्छा", "pakka": "पक्का", "zaroor": "ज़रूर", "sahi": "सही", "wahi": "वही", "yahi": "यही", "wo": "वो", "woh": "वो", "ye": "ये", "yeh": "ये",
    "karwana": "करवाना", "karana": "कराना", "karna": "करना", "karni": "करनी", "kar": "कर", "karo": "करो", "kijiye": "कीजिए", "karun": "करूँ", "karein": "करें", "kardo": "कर दो", "do": "दो", "dijiye": "दीजिए", "dena": "देना", "lena": "लेना", "lijiye": "लीजिए",
    "chahiye": "चाहिए", "chahie": "चाहिए", "chahta": "चाहता", "chahti": "चाहती", "milega": "मिलेगा", "milegi": "मिलेगी", "mil": "मिल", "jayega": "जाएगा", "jayegi": "जाएगी", "gaya": "गया", "gayi": "गई", "hua": "हुआ", "hui": "हुई", "raha": "रहा", "rahi": "रही", "rahe": "रहे",
    "naam": "नाम", "number": "नंबर", "phone": "फ़ोन", "time": "टाइम", "slot": "स्लॉट", "booking": "बुकिंग", "book": "बुक", "appointment": "अपॉइंटमेंट", "confirm": "कन्फ़र्म", "cancel": "कैंसल", "charge": "चार्ज", "charges": "चार्जेस", "price": "प्राइस", "rupaye": "रुपये", "rupees": "रुपये",
    "doctor": "डॉक्टर", "dr": "डॉ", "clinic": "क्लिनिक", "hospital": "हॉस्पिटल", "lab": "लैब", "test": "टेस्ट", "report": "रिपोर्ट", "salon": "सैलून", "service": "सर्विस", "madad": "मदद", "jaankari": "जानकारी", "pata": "पता",
    "dhanyavaad": "धन्यवाद", "dhanyawad": "धन्यवाद", "shukriya": "शुक्रिया", "namaste": "नमस्ते", "bye": "बाय", "thanks": "थैंक्स", "thank": "थैंक", "you": "यू", "ok": "ओके", "okay": "ओके",
    "root": "रूट", "canal": "कैनल", "cleaning": "क्लीनिंग", "teeth": "टीथ", "tooth": "टूथ", "extraction": "एक्सट्रैक्शन", "braces": "ब्रेसेस", "implant": "इम्प्लांट", "whitening": "व्हाइटनिंग", "checkup": "चेकअप", "haircut": "हेयरकट", "hair": "हेयर", "spa": "स्पा", "colour": "कलर", "color": "कलर", "facial": "फ़ेशियल", "makeup": "मेकअप", "bridal": "ब्राइडल", "beard": "बियर्ड", "trim": "ट्रिम",
    "blood": "ब्लड", "sugar": "शुगर", "thyroid": "थायरॉइड", "profile": "प्रोफ़ाइल", "vitamin": "विटामिन", "fasting": "फ़ास्टिंग", "sample": "सैंपल", "collection": "कलेक्शन", "demo": "डेमो", "class": "क्लास", "batch": "बैच", "fees": "फ़ीस", "fee": "फ़ी",
    "emergency": "इमरजेंसी", "urgent": "अर्जेंट", "dard": "दर्द", "bahut": "बहुत", "zyada": "ज़्यादा", "kam": "कम", "thoda": "थोड़ा", "jaldi": "जल्दी", "please": "प्लीज़", "sorry": "सॉरी", "sunday": "संडे", "monday": "मंडे", "band": "बंद", "khula": "खुला", "khali": "खाली", "available": "अवेलेबल",
    "dohra": "दोहरा", "deta": "देता", "deti": "देती", "ek": "एक", "baar": "बार", "dun": "दूँ", "kar dun": "कर दूँ", "saath": "साथ", "wali": "वाली", "wala": "वाला", "wale": "वाले", "branch": "ब्रांच", "nagar": "नगर", "road": "रोड", "lake": "लेक",
    "kaam": "काम", "log": "लोग", "baat": "बात", "poochna": "पूछना", "puchna": "पूछना", "dekh": "देख", "dekhun": "देखूँ", "dekhiye": "देखिए", "bata": "बता", "bataiye": "बताइए", "batao": "बताओ", "bol": "बोल", "boliye": "बोलिए", "sun": "सुन", "suniye": "सुनिए",
}

VOWEL_INIT = [("aa", "आ"), ("ai", "ऐ"), ("au", "औ"), ("ee", "ई"), ("ii", "ई"), ("oo", "ऊ"), ("uu", "ऊ"), ("a", "अ"), ("e", "ए"), ("i", "इ"), ("o", "ओ"), ("u", "उ")]
MATRA = [("aa", "ा"), ("ai", "ै"), ("au", "ौ"), ("ao", "ाओ"), ("ee", "ी"), ("ei", "े"), ("ii", "ी"), ("oo", "ू"), ("uu", "ू"), ("a", ""), ("e", "े"), ("i", "ि"), ("o", "ो"), ("u", "ु")]
CONS = [("chh", "छ"), ("shh", "श"), ("kh", "ख"), ("gh", "घ"), ("ch", "च"), ("jh", "झ"), ("th", "थ"), ("dh", "ध"), ("ph", "फ"), ("bh", "भ"), ("sh", "श"),
        ("k", "क"), ("g", "ग"), ("j", "ज"), ("t", "त"), ("d", "द"), ("n", "न"), ("p", "प"), ("b", "ब"), ("m", "म"), ("y", "य"), ("r", "र"), ("l", "ल"),
        ("v", "व"), ("w", "व"), ("s", "स"), ("h", "ह"), ("f", "फ़"), ("z", "ज़"), ("x", "क्स"), ("q", "क़"), ("c", "क")]
# Clusters written with a halant (conjunct) rather than an inherent vowel.
CONJUNCT_SECOND = set("yrlvwnmstkpdgbjch")
HALANT = "्"


def _word(w: str) -> str:
    low = w.lower()
    if low in WORDS:
        return WORDS[low]
    if not re.fullmatch(r"[a-z]+", low):
        return w
    out: list[str] = []
    i = 0
    n = len(low)
    after_consonant = False
    while i < n:
        matched = False
        if not after_consonant:
            for form, char in VOWEL_INIT:
                if low.startswith(form, i):
                    out.append(char); i += len(form); matched = True; break
            if matched:
                continue
        else:
            for form, char in MATRA:
                if low.startswith(form, i):
                    if form == "a" and i == n - 1:
                        char = "ा"                 # a word-final a is long: Sharma, Anita, mera
                    out.append(char); i += len(form); after_consonant = False; matched = True; break
            if matched:
                continue
        for form, char in CONS:
            if low.startswith(form, i):
                if after_consonant:
                    # consonant after consonant: a conjunct, except r + w/v/y which is read with a vowel
                    prev = out[-1] if out else ""
                    if not (prev == "र" and form in ("w", "v", "y")) and form[0] in CONJUNCT_SECOND:
                        out.append(HALANT)
                out.append(char); i += len(form); after_consonant = True; matched = True; break
        if not matched:
            out.append(low[i]); i += 1; after_consonant = False
    text = "".join(out)
    # word-final n after a long vowel: nasal sign
    text = re.sub(r"ा न$", "ाँ", text).replace("ान$", "ाँ")
    if text.endswith("ान"):
        text = text[:-2] + "ाँ"
    elif text.endswith("ैन") or text.endswith("ीन") or text.endswith("ें"):
        pass
    return text


def transliterate(text: str) -> str:
    """Approximate Devanagari for a Hinglish sentence; digits and punctuation pass through."""
    def repl(m: re.Match) -> str:
        return _word(m.group(0))
    return re.sub(r"[A-Za-z]+", repl, text)


# ------------------------------------------------------------- the other way
# Devanagari -> Latin, for scoring public Hindi corpora whose transcripts are
# in Devanagari against the engine's Latin-script lexicon. A plain,
# deterministic scheme (close to ITRANS without case tricks); it is used on
# both the truth and the recogniser's output, so it cancels out of the
# comparison as long as it is consistent.
_DEV_VOWEL_INIT = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ए": "e", "ऐ": "ai",
                   "ओ": "o", "औ": "au", "ऋ": "ri", "ऑ": "o", "ऍ": "e"}
_DEV_MATRA = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
              "ृ": "ri", "ॉ": "o", "ॅ": "e"}
_DEV_CONS = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
             "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
             "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
             "ष": "sh", "स": "s", "ह": "h", "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f", "य़": "y"}
_NUKTA = "़"
_VIRAMA = "्"
_ANUSVARA, _CHANDRABINDU, _VISARGA = "ं", "ँ", "ः"


def to_latin(text: str) -> str:
    """Devanagari to Latin letters, word by word; everything else passes through."""
    out: list[str] = []
    i = 0
    n = len(text)
    pending_cons = False                      # a consonant without an explicit vowel yet
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if ch in _DEV_CONS or (ch + nxt) in _DEV_CONS:
            if (ch + nxt) in _DEV_CONS:
                base = _DEV_CONS[ch + nxt]; i += 2
            else:
                base = _DEV_CONS[ch]; i += 1
                if i < n and text[i] == _NUKTA:
                    i += 1
            if pending_cons:
                out.append("a")               # inherent vowel of the previous consonant
            out.append(base)
            pending_cons = True
            continue
        if ch == _VIRAMA:
            pending_cons = False; i += 1; continue
        if ch in _DEV_MATRA:
            out.append(_DEV_MATRA[ch]); pending_cons = False; i += 1; continue
        if ch in _DEV_VOWEL_INIT:
            if pending_cons:
                out.append("a")
            out.append(_DEV_VOWEL_INIT[ch]); pending_cons = False; i += 1; continue
        if ch in (_ANUSVARA, _CHANDRABINDU):
            if pending_cons:
                out.append("a"); pending_cons = False
            out.append("n"); i += 1; continue
        if ch == _VISARGA:
            if pending_cons:
                out.append("a"); pending_cons = False
            out.append("h"); i += 1; continue
        if "\u0966" <= ch <= "\u096f":          # Devanagari digits
            if pending_cons:
                out.append("a"); pending_cons = False
            out.append(str(ord(ch) - 0x966)); i += 1; continue
        # anything else (space, Latin, punctuation): close the syllable
        if pending_cons:
            out.append("a"); pending_cons = False
        out.append(ch); i += 1
    if pending_cons:
        out.append("a")
    # word-final inherent 'a' is silent in Hindi: "kal", not "kala"
    words = "".join(out).split(" ")
    fixed = []
    for w in words:
        if len(w) > 2 and w.endswith("a") and not w.endswith("aa") and any("\u0900" <= c <= "\u097f" for c in w) is False:
            w = w[:-1]
        fixed.append(w)
    return " ".join(fixed)
