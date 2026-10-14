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
