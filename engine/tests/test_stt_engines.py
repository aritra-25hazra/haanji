"""The Indic STT comparison harness (REPORT §4.12): one interface over five
recognisers, each vendor's documented response shape parsed correctly, a
missing key named rather than guessed around, and nothing fabricated."""
import json
import os
import sys
import wave
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "collect"))
sys.path.insert(0, str(ROOT / "research" / "harness"))

import engines                    # noqa: E402
import stt_compare                # noqa: E402
import transcribe                 # noqa: E402

VENDOR_KEYS = ["SARVAM_API_KEY", "BHASHINI_USER_ID", "BHASHINI_API_KEY", "HAANJI_DEEPGRAM_KEY",
               "GOOGLE_APPLICATION_CREDENTIALS"]


@pytest.fixture
def no_keys(monkeypatch):
    for k in VENDOR_KEYS:
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def wav(tmp_path):
    """A real (silent) 16 kHz mono WAV, so to_wav() returns it untouched and no converter is needed."""
    path = tmp_path / "clip.wav"
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(16000)
        fh.writeframes(b"\x00\x00" * 1600)
    return path


class FakeHTTP:
    """Stands in for engines._post: records every call, answers from a script keyed by URL prefix."""

    def __init__(self, answers):
        self.answers = answers            # url prefix -> dict (JSON body) or callable(kw) -> dict
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, **kw):
        self.calls.append((url, kw))
        for prefix, body in self.answers.items():
            if url.startswith(prefix):
                payload = body(kw) if callable(body) else body
                return httpx.Response(200, json=payload, request=httpx.Request("POST", url))
        return httpx.Response(404, json={"error": "no fake for " + url}, request=httpx.Request("POST", url))


# ── keys and packages ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("name,key", [("sarvam", "SARVAM_API_KEY"), ("bhashini", "BHASHINI_USER_ID"),
                                      ("deepgram", "HAANJI_DEEPGRAM_KEY"),
                                      ("google", "GOOGLE_APPLICATION_CREDENTIALS")])
def test_a_missing_key_is_named_not_guessed_around(no_keys, name, key):
    with pytest.raises(engines.EngineUnavailable) as err:
        engines.make_engine(name)
    assert key in str(err.value) and "not set" in str(err.value)
    assert engines.availability(name) is not None and key in engines.missing_keys(name)


def test_whisper_without_the_package_is_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    with pytest.raises(engines.EngineUnavailable) as err:
        engines.make_engine("whisper")
    assert "faster-whisper" in str(err.value)


def test_an_unknown_engine_is_a_usage_error():
    with pytest.raises(ValueError):
        engines.make_engine("siri")


def test_a_google_credentials_path_must_exist(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "missing.json"))
    with pytest.raises(engines.EngineUnavailable):
        engines.make_engine("google")


# ── vendor shapes ─────────────────────────────────────────────────────────────
def test_sarvam_parses_saarika_and_romanises_devanagari(monkeypatch, wav):
    monkeypatch.setenv("SARVAM_API_KEY", "sk_test")
    http = FakeHTTP({engines.SarvamEngine.URL: {
        "request_id": "r1", "language_code": "hi-IN", "transcript": "कल सुबह रूट कैनल",
        "timestamps": {"words": ["कल", "सुबह", "रूट", "कैनल"], "start_time_seconds": [0, 0.3, 0.6, 0.9],
                       "end_time_seconds": [0.3, 0.6, 0.9, 1.2]}}})
    monkeypatch.setattr(engines, "_post", http)
    eng = engines.make_engine("sarvam")
    words = eng.transcribe(wav)
    assert [w for w, _ in words] == ["kal", "subah", "root", "canal"]
    assert all(c is None for _, c in words), "Saarika scores no words; the caller applies the OOV model"
    assert not eng.word_confidence and eng.script == "devanagari"
    [(url, kw)] = http.calls
    assert kw["headers"]["api-subscription-key"] == "sk_test"
    assert kw["data"]["model"] == "saarika:v2.5" and kw["data"]["language_code"] == "hi-IN"
    assert kw["files"]["file"][0] == "clip.wav"


def test_bhashini_runs_the_two_step_ulca_pipeline(monkeypatch, wav):
    monkeypatch.setenv("BHASHINI_USER_ID", "u1")
    monkeypatch.setenv("BHASHINI_API_KEY", "k1")
    http = FakeHTTP({
        engines.BhashiniEngine.AUTH_URL: {
            "pipelineResponseConfig": [{"taskType": "asr", "config": [{"serviceId": "ai4bharat/conformer-hi",
                                                                       "language": {"sourceLanguage": "hi"}}]}],
            "pipelineInferenceAPIEndPoint": {"callbackUrl": "https://dhruva-api.bhashini.gov.in/services/inference/pipeline",
                                             "inferenceApiKey": {"name": "Authorization", "value": "infer-key"}}},
        "https://dhruva-api.bhashini.gov.in/": {
            "pipelineResponse": [{"taskType": "asr", "output": [{"source": "कल सुबह टाइम मिलेगा"}]}]},
    })
    monkeypatch.setattr(engines, "_post", http)
    eng = engines.make_engine("bhashini")
    words = eng.transcribe(wav)
    assert [w for w, _ in words] == ["kal", "subah", "time", "milega"] and all(c is None for _, c in words)
    auth, infer = http.calls
    assert auth[1]["headers"] == {"userID": "u1", "ulcaApiKey": "k1"}
    assert auth[1]["json"]["pipelineRequestConfig"]["pipelineId"] == engines.BhashiniEngine.PIPELINE_ID
    assert infer[1]["headers"] == {"Authorization": "infer-key"}
    task = infer[1]["json"]["pipelineTasks"][0]["config"]
    assert task["serviceId"] == "ai4bharat/conformer-hi" and task["audioFormat"] == "wav"
    assert infer[1]["json"]["inputData"]["audio"][0]["audioContent"]
    eng.transcribe(wav)
    assert len(http.calls) == 3, "the pipeline is configured once, not per clip"


def test_deepgram_keeps_word_confidences_and_sends_keywords(monkeypatch, wav):
    monkeypatch.setenv("HAANJI_DEEPGRAM_KEY", "dg_test")
    http = FakeHTTP({engines.DeepgramEngine.URL: {
        "results": {"channels": [{"alternatives": [{
            "transcript": "kal subah rut kanal",
            "words": [{"word": "kal", "confidence": 0.98}, {"word": "subah", "confidence": 0.91},
                      {"word": "rut", "confidence": 0.41}, {"word": "kanal", "confidence": 0.37}]}]}]}}})
    monkeypatch.setattr(engines, "_post", http)
    eng = engines.make_engine("deepgram", bias=True)
    words = eng.transcribe(wav, prompt="Smile Care Dental. root canal, Dr Sheikh.")
    assert words == [("kal", 0.98), ("subah", 0.91), ("rut", 0.41), ("kanal", 0.37)]
    assert eng.word_confidence and eng.label == "deepgram:nova-2:hi-Latn:biased"
    [(url, kw)] = http.calls
    assert kw["headers"]["Authorization"] == "Token dg_test"
    params = dict((k, v) for k, v in kw["params"] if k != "keywords")
    assert params["language"] == "hi-Latn" and params["model"] == "nova-2"
    assert ("keywords", "root canal:1") in kw["params"] and ("keywords", "Dr Sheikh:1") in kw["params"]
    assert kw["content"] == wav.read_bytes()


def test_google_parses_v1_word_confidence_and_romanises(monkeypatch, wav):
    http = FakeHTTP({engines.GoogleEngine.URL: {
        "results": [{"alternatives": [{"transcript": "कल सुबह", "confidence": 0.9,
                                       "words": [{"word": "कल", "confidence": 0.95}, {"word": "सुबह", "confidence": 0.7}]}]},
                    {"alternatives": [{"transcript": "root canal",
                                       "words": [{"word": "root", "confidence": 0.5}, {"word": "canal", "confidence": 0.45}]}]}]}})
    monkeypatch.setattr(engines, "_post", http)
    eng = engines.GoogleEngine(token="ya29.test", bias=True)
    words = eng.transcribe(wav, prompt="Smile Care Dental. root canal.")
    assert words == [("kal", 0.95), ("subah", 0.7), ("root", 0.5), ("canal", 0.45)]
    [(url, kw)] = http.calls
    assert kw["headers"]["Authorization"] == "Bearer ya29.test"
    cfg = kw["json"]["config"]
    assert cfg["languageCode"] == "hi-IN" and cfg["enableWordConfidence"] is True
    assert cfg["speechContexts"] == [{"phrases": ["Smile Care Dental", "root canal"]}]
    assert kw["json"]["audio"]["content"]


def test_a_vendor_error_surfaces_instead_of_an_empty_transcript(monkeypatch, wav):
    monkeypatch.setenv("SARVAM_API_KEY", "sk_test")

    def failing(url, **kw):
        return httpx.Response(401, json={"error": "invalid key"}, request=httpx.Request("POST", url))
    monkeypatch.setattr(engines, "_post", failing)
    with pytest.raises(httpx.HTTPStatusError):
        engines.make_engine("sarvam").transcribe(wav)


def test_to_wav_leaves_wav_alone_and_names_the_missing_converter(monkeypatch, wav, tmp_path):
    assert engines.to_wav(wav) == wav
    monkeypatch.setattr(engines.shutil, "which", lambda name: None)
    aiff = tmp_path / "audio" / "clip.aiff"
    aiff.parent.mkdir()
    aiff.write_bytes(b"FORM")
    with pytest.raises(engines.EngineUnavailable) as err:
        engines.to_wav(aiff)
    assert "ffmpeg" in str(err.value)


# ── transcribe.py --engine ────────────────────────────────────────────────────
def test_transcribe_names_the_output_per_engine_and_labels_the_confidence_source(monkeypatch, wav, tmp_path):
    monkeypatch.setenv("SARVAM_API_KEY", "sk_test")
    http = FakeHTTP({engines.SarvamEngine.URL: {"transcript": "kal subah rut kanal karwana hai",
                                                "timestamps": {"words": ["kal", "subah", "rut", "kanal", "karwana", "hai"]}}})
    monkeypatch.setattr(engines, "_post", http)
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps({"id": "c1", "file": "clip.wav", "pack": "dental_clinic",
                                    "truth": "kal subah root canal karwana hai", "speaker": "P01",
                                    "kind": "scenario", "synthetic": False}) + "\n", encoding="utf-8")
    assert transcribe.main(["--manifest", str(manifest), "--engine", "sarvam"]) == 0
    out = tmp_path / "pairs_sarvam.jsonl"
    assert out.exists(), "named for the engine, next to the manifest"
    [row] = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert row["heard"] == "kal subah rut kanal karwana hai" and row["engine"] == "sarvam"
    assert row["recogniser"] == "sarvam:saarika:v2.5:hi-IN" and row["confidence_source"] == "oov-model"
    confs = dict(zip(row["heard"].split(), row["confidences"], strict=True))
    assert confs["kal"] >= 0.9 and confs["karwana"] >= 0.9, "known words are confident"
    assert confs["rut"] < 0.85 and confs["kanal"] < 0.85, "out-of-vocabulary words are doubtful, so the bridge may repair them"
    assert transcribe.default_out(manifest, "whisper", False).name == "pairs.jsonl"
    assert transcribe.default_out(manifest, "whisper", True).name == "pairs_biased.jsonl"
    assert transcribe.default_out(manifest, "deepgram", True).name == "pairs_deepgram_biased.jsonl"


def test_transcribe_without_a_key_exits_with_the_reason(no_keys, tmp_path, capsys):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("", encoding="utf-8")
    assert transcribe.main(["--manifest", str(manifest), "--engine", "deepgram"]) == 2
    assert "HAANJI_DEEPGRAM_KEY not set" in capsys.readouterr().err
    assert not (tmp_path / "pairs_deepgram.jsonl").exists(), "no output is written for an engine that did not run"


# ── stt_compare.py ────────────────────────────────────────────────────────────
def test_the_comparison_reports_missing_keys_instead_of_inventing_rows(no_keys, tmp_path):
    payload = stt_compare.compare(tmp_path)
    for name in ("sarvam", "bhashini", "deepgram", "google"):
        assert payload["engines"][name]["status"].startswith("not run: key needed")
    assert "SARVAM_API_KEY" in payload["engines"]["sarvam"]["status"]
    assert payload["engines"]["whisper"]["status"].startswith("not run"), "no output in an empty folder"
    assert payload["scored"] == [] and set(payload["skipped"]) == {r[0] for r in stt_compare.RUNS}
    md = stt_compare.table(payload)
    assert "Not run:" in md and "`sarvam`" in md


def test_the_comparison_scores_whatever_output_is_present(no_keys, tmp_path):
    pairs = [{"id": "a", "pack": "dental_clinic", "truth": "mujhe root canal karwana hai",
              "heard": "mujhe rut kanal karwana hai", "confidences": [0.9, 0.4, 0.45, 0.9, 0.9],
              "speaker": "P01", "recogniser": "deepgram:nova-2:hi-Latn", "confidence_source": "vendor"},
             {"id": "b", "pack": "dental_clinic", "truth": "mujhe root canal karwana hai",
              "heard": "mujhe root canal karwana hai", "confidences": [0.9, 0.95, 0.95, 0.9, 0.9],
              "speaker": "P02", "recogniser": "deepgram:nova-2:hi-Latn", "confidence_source": "vendor"}]
    (tmp_path / "pairs_deepgram.jsonl").write_text("\n".join(json.dumps(p) for p in pairs) + "\n", encoding="utf-8")
    payload = stt_compare.compare(tmp_path, only=["deepgram", "sarvam"])
    dg = payload["engines"]["deepgram"]
    assert dg["status"] == "scored" and dg["pairs"] == 2 and dg["confidence_source"] == ["vendor"]
    assert dg["overall"]["entity_error_rate_off"] == 0.5 and dg["overall"]["entity_error_rate_on"] == 0.0
    assert dg["overall"]["corrections"]["harmful"] == 0
    assert payload["engines"]["sarvam"]["status"].startswith("not run: key needed")
    assert payload["scored"] == ["deepgram"]
    md = stt_compare.table(payload)
    assert "| deepgram" in md and "50.0 | 0.0 |" in md


def test_the_committed_comparison_file_is_honest_about_what_ran():
    """The checked-in research/stt_compare.json must never carry a number for an engine that did not run."""
    payload = json.loads((ROOT / "research" / "stt_compare.json").read_text(encoding="utf-8"))
    for name, row in payload["engines"].items():
        if row["status"] == "scored":
            assert row["pairs"] > 0 and "overall" in row, name
        else:
            assert row["status"].startswith("not run") and "overall" not in row, name
    assert os.path.exists(ROOT / "research" / "stt_compare_tables.md")
