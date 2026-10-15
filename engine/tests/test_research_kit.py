"""The research kit: the recording page, the study page, and the scoring of real recogniser output."""
import base64
import csv
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from haanji import collect, server
from haanji.vertical import load_pack


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "REC_DIR", str(tmp_path / "recordings"))
    monkeypatch.setattr(server, "STUDY_DB", str(tmp_path / "study.sqlite"))
    return TestClient(server.app)


# ── prompts and pairs ─────────────────────────────────────────────────────────
def test_prompts_start_with_the_scenario_lines_and_cover_the_catalogue(pack):
    prompts = collect.prompts_for(pack, limit=40)
    assert prompts and prompts[0]["kind"] == "scenario"
    assert all(p["pack"] == "dental_clinic" and p["truth"] for p in prompts)
    assert len({collect.normalise(p["truth"]) for p in prompts}) == len(prompts), "no duplicates"
    catalogue = [p["truth"].lower() for p in prompts if p["kind"] == "catalogue"]
    assert any(s.name.lower() in " ".join(catalogue) for s in pack.services)
    assert collect.prompts_for(pack, limit=5) == prompts[:5], "same order every time"


def test_pairs_round_trip_and_normalise(tmp_path):
    path = tmp_path / "pairs.jsonl"
    path.write_text(json.dumps({"id": "a", "pack": "dental_clinic", "truth": "root canal kal",
                                "heard": "Rut canal, kal.", "confidences": [0.4, 0.9, 0.95],
                                "speaker": "say:Rishi", "recogniser": "fw:small"}) + "\n", encoding="utf-8")
    [p] = collect.load_pairs(path)
    assert [t.text for t in p.tokens()] == ["rut", "canal", "kal"]
    assert [t.confidence for t in p.tokens()] == [0.4, 0.9, 0.95]
    assert collect.normalise("Dr. Sheikh, kal!") == "dr sheikh kal"
    assert collect.word_error_rate("root canal kal", "rut canal kal") == pytest.approx(1 / 3)


def test_real_pairs_are_scored_like_the_benchmark(pack):
    pairs = [
        collect.Pair("dental_clinic", "mujhe root canal karwana hai", "mujhe rut kanal karwana hai",
                     [0.9, 0.4, 0.45, 0.9, 0.9], speaker="say:Rishi", id="1"),
        collect.Pair("dental_clinic", "mujhe root canal karwana hai", "mujhe root canal karwana hai",
                     [0.9, 0.95, 0.95, 0.9, 0.9], speaker="say:Tara", id="2"),
    ]
    res = collect.real_pairs_experiment([pack], pairs)
    o = res["overall"]
    assert o["utterances"] == 2 and o["entities"] == 2
    assert o["entity_error_rate_off"] == 0.5 and o["entity_error_rate_on"] == 0.0
    assert o["corrections"]["beneficial"] >= 1 and o["corrections"]["harmful"] == 0
    assert set(res["per_speaker"]) == {"say:Rishi", "say:Tara"} and "dental_clinic" in res["per_pack"]
    assert res["examples"] and res["examples"][0]["corrected"] == "mujhe root canal karwana hai"


# ── the recording page ────────────────────────────────────────────────────────
def test_the_record_page_serves_prompts_and_stores_a_clip(client):
    assert client.get("/record").status_code == 200 and "Shuru karo" in client.get("/record").text
    prompts = client.get("/api/record/prompts", params={"pack": "salon_spa", "limit": 7}).json()
    assert len(prompts) == 7 and all(p["pack"] == "salon_spa" for p in prompts)
    assert client.get("/api/record/prompts", params={"pack": "nope"}).status_code == 404
    audio = base64.b64encode(b"RIFF....WAVEfmt ").decode()
    r = client.post("/api/record", json={"pack": "salon_spa", "truth": prompts[0]["truth"], "kind": "scenario",
                                          "speaker": "P01", "mime": "audio/webm;codecs=opus", "audio_b64": audio})
    assert r.status_code == 200 and r.json()["count"] == 1
    m = client.get("/api/record/manifest").json()
    assert m["count"] == 1 and m["speakers"] == ["P01"] and m["rows"][0]["file"].endswith(".webm")
    assert client.post("/api/record", json={"pack": "salon_spa", "truth": "x", "audio_b64": "@@"}).status_code == 400
    z = client.get("/api/record/export")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert "manifest.jsonl" in names and any(n.endswith(".webm") for n in names)


def test_export_without_recordings_is_a_404(client):
    assert client.get("/api/record/export").status_code == 404


# ── the study page ────────────────────────────────────────────────────────────
def test_sus_is_scored_the_brooke_way():
    assert server.sus_score([5, 1, 5, 1, 5, 1, 5, 1, 5, 1]) == 100.0
    assert server.sus_score([1, 5, 1, 5, 1, 5, 1, 5, 1, 5]) == 0.0
    assert server.sus_score([3] * 10) == 50.0
    with pytest.raises(ValueError):
        server.sus_score([3] * 9)


def test_a_study_response_is_stored_and_exported_as_csv(client):
    assert "Teen kaam" in client.get("/study").text
    body = {"participant": "P07", "pack": "dental_clinic",
            "tasks": [{"id": "book", "expected": "BOOKED", "success": True, "seconds": 71},
                      {"id": "price", "expected": "FAQ_ANSWERED", "success": True, "seconds": 30},
                      {"id": "closed", "expected": "LEAD_CAPTURED", "success": False, "seconds": 95}],
            "sus": [4, 2, 5, 1, 4, 2, 5, 2, 4, 2], "wrong": "Sunday wala samajh nahi aaya", "good": "tez tha",
            "duration_s": 420}
    r = client.post("/api/study", json=body)
    assert r.status_code == 200 and r.json()["sus_score"] == 82.5 and r.json()["tasks_done"] == 2
    assert client.post("/api/study", json={**body, "sus": [3]}).status_code == 400
    rows = list(csv.DictReader(io.StringIO(client.get("/api/study/export").text)))
    assert len(rows) == 3 and rows[0]["participant"] == "P07" and rows[2]["success"] == "0"
    assert rows[0]["sus1"] == "4" and rows[0]["sus_score"] == "82.5" and rows[0]["wrong"].startswith("Sunday")
    assert client.get("/api/study/responses").json()["count"] == 1


def test_the_talk_page_honours_a_study_link(client):
    text = client.get("/talk").text
    assert 'q.get("pack")' in text and 'q.get("study")' in text
