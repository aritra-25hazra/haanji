#!/usr/bin/env python3
"""Speech recognisers behind one interface, for the Indic STT comparison (REPORT §4.12).

    engine = make_engine("whisper", model="small")
    words = engine.transcribe(path)            # [(word, confidence or None), ...]

Five adapters share the interface: ``whisper`` (faster-whisper on the CPU, the
pilot's recogniser), ``sarvam`` (Sarvam AI Saarika), ``bhashini`` (the
MeitY/ULCA ASR pipeline), ``deepgram`` (prerecorded API, Hinglish ``hi-Latn``)
and ``google`` (Cloud Speech-to-Text v1, ``hi-IN``). Each imports its client
lazily and raises :class:`EngineUnavailable` naming the key or package it is
missing, so ``transcribe.py --engine X`` and ``harness/stt_compare.py`` can
say exactly why an engine was skipped instead of failing half-way through.

Two honesty notes carried in every output row:

* ``confidence``: Whisper, Deepgram and Google give a per-word figure; Sarvam
  and Bhashini do not, and the adapter returns ``None`` for those words. The
  caller (``transcribe.py``) then applies the text channel's out-of-vocabulary
  confidence model and labels the row ``confidence_source: oov-model``.
* ``script``: Saarika, Bhashini and Google in ``hi-IN`` return Devanagari; the
  adapter romanises it with ``haanji.devanagari.latinise`` (the same table the
  Hindi-script input path uses) so the pairs can be scored against the Latin
  truth. The row records that the words went through the transliteration.

Nothing here is fabricated when a key is missing: ``availability()`` reports
the reason and no output file is written.
"""
from __future__ import annotations
import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

Word = tuple[str, "float | None"]

KEYS = {
    "whisper": [],
    "sarvam": ["SARVAM_API_KEY"],
    "bhashini": ["BHASHINI_USER_ID", "BHASHINI_API_KEY"],
    "deepgram": ["HAANJI_DEEPGRAM_KEY"],
    "google": ["GOOGLE_APPLICATION_CREDENTIALS"],
}


class EngineUnavailable(RuntimeError):
    """The engine cannot run here: a key, a package or an audio converter is missing."""


# ------------------------------------------------------------------ seams
def _post(url: str, **kw: Any):
    """Every REST call goes through here, so a test can monkeypatch it and
    hand back ``httpx.Response`` objects in the vendors' documented shapes."""
    import httpx
    return httpx.post(url, **kw)


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise EngineUnavailable(f"{name} not set")
    return value


def _latinise(text: str) -> str:
    """Devanagari to Latin with the engine's own table (an approximation, labelled)."""
    if str(ROOT / "engine") not in sys.path:
        sys.path.insert(0, str(ROOT / "engine"))
    from haanji.devanagari import latinise
    return latinise(text)


def _has_devanagari(text: str) -> bool:
    return any("ऀ" <= ch <= "ॿ" for ch in text)


def _words(text: str) -> list[str]:
    return [w for w in text.replace("\n", " ").split(" ") if w.strip()]


# ------------------------------------------------------------------ audio
def to_wav(path: str | Path, out_dir: str | Path | None = None, rate: int = 16000) -> Path:
    """16 kHz mono 16-bit PCM WAV, which every hosted recogniser accepts.

    The pilot's clips are AIFF (macOS ``say``) and volunteers' are WebM/Opus;
    conversion uses ``ffmpeg`` when present, else macOS ``afconvert``. A WAV
    input is returned untouched. Converted files are cached next to the
    audio, in ``wav16k/``, so a second engine does not convert again."""
    src = Path(path)
    if src.suffix.lower() == ".wav":
        return src
    target_dir = Path(out_dir) if out_dir else src.parent.parent / "wav16k"
    target_dir.mkdir(parents=True, exist_ok=True)
    dst = target_dir / (src.stem + ".wav")
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return dst
    if shutil.which("ffmpeg"):
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", str(rate),
               "-sample_fmt", "s16", "-f", "wav", str(dst)]
    elif shutil.which("afconvert"):
        cmd = ["afconvert", "-f", "WAVE", "-d", f"LEI16@{rate}", "-c", "1", str(src), str(dst)]
    else:
        raise EngineUnavailable(f"no ffmpeg or afconvert to convert {src.suffix} to wav")
    subprocess.run(cmd, check=True)
    return dst


# ---------------------------------------------------------------- engines
class BaseEngine:
    """What every adapter provides. ``label`` is what the pairs file records as
    the recogniser; ``word_confidence`` says whether the vendor scores words;
    ``script`` is what the raw output is in before any transliteration."""

    name = "base"
    word_confidence = False
    script = "latin"
    supports_hints = False

    def __init__(self, language: str = "", **_: Any):
        self.language = language

    @property
    def label(self) -> str:
        return f"{self.name}:{self.language}"

    def transcribe(self, path: str | Path, prompt: str | None = None) -> list[Word]:
        """Words with confidences for one clip. ``prompt`` is the pack's
        vocabulary for engines that can be biased; the rest ignore it."""
        raise NotImplementedError

    def _finish(self, text: str, confidences: list[float | None] | None = None) -> list[Word]:
        """Romanise if the vendor answered in Devanagari, then pair words
        with their confidences (``None`` when the vendor gives none)."""
        if _has_devanagari(text):
            text = _latinise(text)
        words = _words(text)
        confs = list(confidences or [])
        confs += [None] * (len(words) - len(confs))
        return list(zip(words, confs[:len(words)], strict=False))


class WhisperEngine(BaseEngine):
    """faster-whisper on the CPU: the pilot's path, unchanged. Word
    probabilities become confidences; ``prompt`` becomes ``initial_prompt``
    (the only biasing Whisper has)."""

    name = "faster-whisper"
    word_confidence = True
    supports_hints = True

    def __init__(self, model: str = "small", language: str = "en", bias: bool = False, **_: Any):
        super().__init__(language)
        try:
            import faster_whisper  # noqa: F401  - the optional research extra
        except ImportError as exc:
            raise EngineUnavailable("faster-whisper not installed (pip install faster-whisper)") from exc
        self.model_size = model
        self.bias = bias
        self._model = None

    @property
    def label(self) -> str:
        return f"faster-whisper:{self.model_size}:{self.language}" + (":biased" if self.bias else "")

    def _loaded(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    def transcribe(self, path: str | Path, prompt: str | None = None) -> list[Word]:
        segments, _info = self._loaded().transcribe(
            str(path), language=self.language, beam_size=5, word_timestamps=True,
            vad_filter=False, condition_on_previous_text=False,
            initial_prompt=prompt if self.bias else None)
        out: list[Word] = []
        for seg in segments:
            for w in (seg.words or []):
                if w.word.strip():
                    out.append((w.word.strip(), round(float(w.probability), 3)))
        return out


class SarvamEngine(BaseEngine):
    """Sarvam AI Saarika over REST.

    ``POST https://api.sarvam.ai/speech-to-text`` with header
    ``api-subscription-key``, multipart ``file`` and form fields ``model``,
    ``language_code`` and ``with_timestamps``; the reply is
    ``{"request_id", "transcript", "language_code", "timestamps": {"words": [...],
    "start_time_seconds": [...], "end_time_seconds": [...]}}``. Saarika gives no
    per-word confidence and answers ``hi-IN`` in Devanagari."""

    name = "sarvam-saarika"
    script = "devanagari"
    URL = "https://api.sarvam.ai/speech-to-text"

    def __init__(self, model: str = "saarika:v2.5", language: str = "hi-IN", **_: Any):
        super().__init__(language)
        self.key = _env("SARVAM_API_KEY")
        self.model = model

    @property
    def label(self) -> str:
        return f"sarvam:{self.model}:{self.language}"

    def transcribe(self, path: str | Path, prompt: str | None = None) -> list[Word]:
        wav = to_wav(path)
        r = _post(self.URL, headers={"api-subscription-key": self.key},
                  files={"file": (wav.name, wav.read_bytes(), "audio/wav")},
                  data={"model": self.model, "language_code": self.language, "with_timestamps": "true"},
                  timeout=60.0)
        r.raise_for_status()
        body = r.json()
        words = (body.get("timestamps") or {}).get("words")
        text = " ".join(words) if words else body.get("transcript", "")
        return self._finish(text)


class BhashiniEngine(BaseEngine):
    """Bhashini (MeitY / ULCA) ASR pipeline, two REST calls.

    1. ``POST .../ulca/apis/v0/model/getModelsPipeline`` with headers ``userID``
       and ``ulcaApiKey`` returns the ASR ``serviceId`` for the language and
       the inference endpoint (``pipelineInferenceAPIEndPoint.callbackUrl`` plus
       the header name/value in ``inferenceApiKey``).
    2. ``POST <callbackUrl>`` with that header and ``inputData.audio[0].audioContent``
       (base64 WAV) returns ``pipelineResponse[0].output[0].source``.

    No word confidence; Hindi comes back in Devanagari."""

    name = "bhashini"
    script = "devanagari"
    AUTH_URL = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
    PIPELINE_ID = "64392f96daac500b55c543cd"          # MeitY's public pipeline

    def __init__(self, language: str = "hi", pipeline_id: str | None = None, **_: Any):
        super().__init__(language)
        self.user_id = _env("BHASHINI_USER_ID")
        self.api_key = _env("BHASHINI_API_KEY")
        self.pipeline_id = pipeline_id or self.PIPELINE_ID
        self._config: dict[str, str] | None = None

    def _configure(self) -> dict[str, str]:
        if self._config is None:
            r = _post(self.AUTH_URL, headers={"userID": self.user_id, "ulcaApiKey": self.api_key},
                      json={"pipelineTasks": [{"taskType": "asr",
                                               "config": {"language": {"sourceLanguage": self.language}}}],
                            "pipelineRequestConfig": {"pipelineId": self.pipeline_id}},
                      timeout=30.0)
            r.raise_for_status()
            body = r.json()
            service = body["pipelineResponseConfig"][0]["config"][0]["serviceId"]
            endpoint = body["pipelineInferenceAPIEndPoint"]
            key = endpoint["inferenceApiKey"]
            self._config = {"service_id": service, "url": endpoint["callbackUrl"],
                            "header": key["name"], "value": key["value"]}
        return self._config

    def transcribe(self, path: str | Path, prompt: str | None = None) -> list[Word]:
        cfg = self._configure()
        wav = to_wav(path)
        r = _post(cfg["url"], headers={cfg["header"]: cfg["value"]},
                  json={"pipelineTasks": [{"taskType": "asr",
                                           "config": {"language": {"sourceLanguage": self.language},
                                                      "serviceId": cfg["service_id"],
                                                      "audioFormat": "wav", "samplingRate": 16000}}],
                        "inputData": {"audio": [{"audioContent": base64.b64encode(wav.read_bytes()).decode()}]}},
                  timeout=60.0)
        r.raise_for_status()
        text = r.json()["pipelineResponse"][0]["output"][0]["source"]
        return self._finish(text)


class DeepgramEngine(BaseEngine):
    """Deepgram prerecorded API, the recogniser the telephony bridge uses live.

    ``POST https://api.deepgram.com/v1/listen?model=...&language=hi-Latn`` with
    ``Authorization: Token <key>`` and the WAV bytes as the body; the reply is
    ``results.channels[0].alternatives[0].words[] = {word, confidence, ...}``.
    ``hi-Latn`` is Deepgram's romanised-Hindi mode, the one output that needs
    no transliteration; ``keywords`` carry the pack vocabulary as biasing."""

    name = "deepgram"
    word_confidence = True
    supports_hints = True
    URL = "https://api.deepgram.com/v1/listen"

    def __init__(self, model: str = "nova-2", language: str = "hi-Latn", bias: bool = False, **_: Any):
        super().__init__(language)
        self.key = _env("HAANJI_DEEPGRAM_KEY")
        self.model = model
        self.bias = bias

    @property
    def label(self) -> str:
        return f"deepgram:{self.model}:{self.language}" + (":biased" if self.bias else "")

    def transcribe(self, path: str | Path, prompt: str | None = None) -> list[Word]:
        wav = to_wav(path)
        params: list[tuple[str, str]] = [("model", self.model), ("language", self.language),
                                         ("punctuate", "false"), ("smart_format", "false")]
        if self.bias and prompt:
            params += [("keywords", f"{w}:1") for w in prompt_words(prompt)]
        r = _post(self.URL, params=params,
                  headers={"Authorization": f"Token {self.key}", "Content-Type": "audio/wav"},
                  content=wav.read_bytes(), timeout=60.0)
        r.raise_for_status()
        alt = r.json()["results"]["channels"][0]["alternatives"][0]
        words = alt.get("words") or []
        if words:
            return [(w["word"], round(float(w.get("confidence", 0.0)), 3)) for w in words if w.get("word")]
        return self._finish(alt.get("transcript", ""))


class GoogleEngine(BaseEngine):
    """Google Cloud Speech-to-Text v1 over REST.

    ``POST https://speech.googleapis.com/v1/speech:recognize`` with a bearer
    token minted from the service account in ``GOOGLE_APPLICATION_CREDENTIALS``
    (``google-auth``, imported lazily; a test passes ``token`` directly).
    ``enableWordConfidence`` gives ``results[].alternatives[0].words[] = {word,
    confidence}``; ``speechContexts`` carry the pack vocabulary. ``hi-IN``
    answers in Devanagari."""

    name = "google-stt"
    word_confidence = True
    supports_hints = True
    script = "devanagari"
    URL = "https://speech.googleapis.com/v1/speech:recognize"
    SCOPE = "https://www.googleapis.com/auth/cloud-platform"

    def __init__(self, language: str = "hi-IN", bias: bool = False, token: str | None = None, **_: Any):
        super().__init__(language)
        self._token = token
        if token is None:
            creds = _env("GOOGLE_APPLICATION_CREDENTIALS")
            if not Path(creds).is_file():
                raise EngineUnavailable(f"GOOGLE_APPLICATION_CREDENTIALS points at a missing file: {creds}")
            self.credentials_path = creds
        self.bias = bias

    @property
    def label(self) -> str:
        return f"google-stt:v1:{self.language}" + (":biased" if self.bias else "")

    def token(self) -> str:
        if self._token is None:
            try:
                from google.auth.transport.requests import Request
                from google.oauth2 import service_account
            except ImportError as exc:
                raise EngineUnavailable("google-auth not installed (pip install google-auth requests)") from exc
            creds = service_account.Credentials.from_service_account_file(
                self.credentials_path, scopes=[self.SCOPE])
            creds.refresh(Request())
            self._token = creds.token
        return self._token

    def transcribe(self, path: str | Path, prompt: str | None = None) -> list[Word]:
        wav = to_wav(path)
        config: dict[str, Any] = {"encoding": "LINEAR16", "sampleRateHertz": 16000,
                                  "languageCode": self.language, "alternativeLanguageCodes": ["en-IN"],
                                  "enableWordConfidence": True}
        if self.bias and prompt:
            config["speechContexts"] = [{"phrases": prompt_words(prompt)}]
        r = _post(self.URL, headers={"Authorization": f"Bearer {self.token()}"},
                  json={"config": config, "audio": {"content": base64.b64encode(wav.read_bytes()).decode()}},
                  timeout=60.0)
        r.raise_for_status()
        words: list[str] = []
        confs: list[float | None] = []
        for result in r.json().get("results", []):
            alt = (result.get("alternatives") or [{}])[0]
            if alt.get("words"):
                for w in alt["words"]:
                    words.append(w["word"])
                    confs.append(round(float(w["confidence"]), 3) if "confidence" in w else None)
            else:
                for w in _words(alt.get("transcript", "")):
                    words.append(w)
                    confs.append(None)
        return self._finish(" ".join(words), confs)


ENGINES: dict[str, type[BaseEngine]] = {
    "whisper": WhisperEngine,
    "sarvam": SarvamEngine,
    "bhashini": BhashiniEngine,
    "deepgram": DeepgramEngine,
    "google": GoogleEngine,
}


def prompt_words(prompt: str) -> list[str]:
    """The pack vocabulary prompt ("Smile Care Dental. root canal, Dr Sheikh.")
    as a list of phrases for engines that take keywords rather than text."""
    parts = [p.strip(" .") for p in prompt.replace(".", ",").split(",")]
    return [p for p in parts if p]


def make_engine(name: str, **opts: Any) -> BaseEngine:
    try:
        cls = ENGINES[name]
    except KeyError as exc:
        raise ValueError(f"unknown engine {name!r}; one of {', '.join(ENGINES)}") from exc
    return cls(**opts)


def availability(name: str, **opts: Any) -> str | None:
    """``None`` when the engine can be built here, else the reason it cannot."""
    try:
        make_engine(name, **opts)
    except EngineUnavailable as exc:
        return str(exc)
    return None


def missing_keys(name: str) -> list[str]:
    return [k for k in KEYS.get(name, []) if not os.environ.get(k, "").strip()]
