"""The Devanagari reading aid: the words of a call come out right; the rest is approximate but Devanagari."""
import re

from fastapi.testclient import TestClient

from haanji import server
from haanji.devanagari import transliterate

DEV = re.compile(r"^[\u0900-\u097F\s0-9.,:?!'-]+$")


def test_a_booking_line_reads_as_hindi():
    assert transliterate("haan ji mujhe root canal karwana hai") == "हाँ जी मुझे रूट कैनल करवाना है"
    assert transliterate("kal subah ka time mil jayega") == "कल सुबह का टाइम मिल जाएगा"
    assert transliterate("mera naam Vijay Sharma hai number 9876543210") == "मेरा नाम विजय शर्मा है नंबर 9876543210"
    assert transliterate("haan confirm kar do") == "हाँ कन्फ़र्म कर दो"


def test_unknown_words_still_become_devanagari_and_other_text_passes_through():
    out = transliterate("Bhawarkuan branch, 10:30 baje?")
    assert DEV.match(out) and "10:30" in out and out.endswith("बजे?")
    assert transliterate("kya") == "क्या" and transliterate("karwana") == "करवाना" and transliterate("Sharma") == "शर्मा"
    assert transliterate("Anita Rao") == "अनिता राओ" and transliterate("Dr Sheikh") == "डॉ शेख"


def test_the_endpoint_returns_one_line_per_input():
    c = TestClient(server.app)
    r = c.post("/api/devanagari", json={"texts": ["haan ji", "theek hai"]}).json()
    assert r == {"texts": ["हाँ जी", "ठीक है"], "approximate": True}
    assert c.post("/api/devanagari", json={"texts": ["x"] * 501}).status_code == 413
