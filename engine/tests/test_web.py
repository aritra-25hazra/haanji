"""The demo server's pages and the small contracts the pages rely on."""
import os
import re

import pytest
from fastapi.testclient import TestClient

from haanji.server import app

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "haanji", "web")
PAGES = {"/": "index.html", "/talk": "talk.html", "/whatsapp": "whatsapp.html", "/verify": "verify.html"}


@pytest.fixture
def client():
    return TestClient(app)


def test_status_exposes_the_console_url(client, monkeypatch):
    monkeypatch.delenv("HAANJI_CONSOLE_URL", raising=False)
    assert client.get("/api/status").json()["console_url"] == "http://localhost:5173"
    monkeypatch.setenv("HAANJI_CONSOLE_URL", "https://haanji-kappa.vercel.app")
    assert client.get("/api/status").json()["console_url"] == "https://haanji-kappa.vercel.app"


def test_static_files_are_served_with_their_media_type(client):
    assert client.get("/static/verifier.js").headers["content-type"].startswith("text/javascript")
    assert client.get("/static/signboard.css").headers["content-type"].startswith("text/css")


def test_a_correction_carries_the_sound_keys_that_justified_it(client):
    sid = client.post("/api/sessions", json={"pack": "dental_clinic"}).json()["session_id"]
    turn = client.post(f"/api/sessions/{sid}/utterance",
                       json={"text": "haan ji mujhe rut kanal karwana tha"}).json()
    [c] = turn["corrections"]
    assert c["from_token"] == "rut kanal" and c["to_surface"] == "root canal"
    assert c["key"] and c["key"] == c["to_key"]


TOKENS = ["--cobalt:", "--cobalt-deep:", "--marigold:", "--chalk:", "--ink:", "--haze:",
          "--sindoor:", "--leaf:", "--t-micro:", "--t-base:", "--t-paint:", "--ease-out:"]


def test_the_design_system_defines_every_token(client):
    css = client.get("/static/signboard.css").text
    for token in TOKENS:
        assert token in css, token
    assert "prefers-reduced-motion" in css
    assert ":focus-visible" in css


def test_the_shared_script_exposes_the_signboard_api(client):
    js = client.get("/static/signboard.js").text
    for name in ["icon", "mountIcons", "reveal", "paintRepair", "stamp", "typingDots",
                 "timer", "waveform", "status", "esc", "repairNode"]:
        assert name in js, name
    assert 'fetch("api/status")' in js            # relative, never root-relative


def test_the_landing_page_has_its_hero_pillars_and_links(client):
    html = client.get("/").text
    assert "Phone uthata hai." in html and "सबूत" in html
    assert 'id="hero-call"' in html and 'id="pillars"' in html
    for href in ('href="talk"', 'href="whatsapp"', 'href="verify"'):
        assert href in html, href
    assert 'href="static/signboard.css"' in html and 'src="static/hero-call.js"' in html
    assert "31.6% → 1.1%" in html and "239 → 137 ms" in html and "80 / 80" in html
    assert "http://localhost" not in html


def test_the_talk_page_has_the_call_and_the_engine_panel(client):
    html = client.get("/talk").text
    for el_id in ("log", "interim", "panel-bhasha", "panel-spec", "panel-pramaan", "mic", "text", "send", "sheet-toggle"):
        assert f'id="{el_id}"' in html, el_id
    assert 'aria-live="polite"' in html
    assert "Start call" in html and "Call khatam karo" in html
    assert "haanji serve" not in html and "http://localhost" not in html


def test_the_whatsapp_page_keeps_its_simulator_controls(client):
    html = client.get("/whatsapp").text
    for el_id in ("threads", "msgs", "missed", "open", "phone", "text", "send", "pack"):
        assert f'id="{el_id}"' in html, el_id
    assert "missed call" in html.lower()
    assert 'href="static/signboard.css"' in html


def test_the_verify_page_has_its_verdict_chain_and_register(client):
    html = client.get("/verify").text
    for el_id in ("verdict", "chainstrip", "rows", "tbl", "load", "paste", "tamper", "json", "key", "pack"):
        assert f'id="{el_id}"' in html, el_id
    assert 'src="static/nacl-fast.min.js"' in html and 'src="static/verifier.js"' in html
    assert 'href="static/signboard.css"' in html


EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")
ROOT_RELATIVE = re.compile(r'(?:href|src|action)="/[^/]|fetch\("/|open\("[A-Z]+",\s*"/')


def _web_files():
    for name in sorted(os.listdir(WEB)):
        if name.endswith((".html", ".js")) and name not in ("nacl-fast.min.js", "verifier.js"):
            with open(os.path.join(WEB, name), encoding="utf-8") as f:
                yield name, f.read()


@pytest.mark.parametrize("name,text", list(_web_files()))
def test_no_emoji_is_used_as_an_icon(name, text):
    found = EMOJI.findall(text)
    assert not found, f"{name}: {found[:5]} — use Signboard.icon() instead"


@pytest.mark.parametrize("name,text", list(_web_files()))
def test_every_url_is_relative_so_the_page_works_behind_a_prefix(name, text):
    hits = ROOT_RELATIVE.findall(text)
    assert not hits, f"{name}: {hits[:5]} — drop the leading slash"
