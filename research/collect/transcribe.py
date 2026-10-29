#!/usr/bin/env python3
"""Run a recogniser over a manifest of recordings and write (heard, truth)
pairs with per-word confidence, in the format ``haanji.collect`` scores.

The default engine is faster-whisper on the CPU (``pip install faster-whisper``;
the model is downloaded on first use), run as a general English model with no
hints and no vocabulary: the baseline Bhasha Bridge is meant to sit on top of.
``--engine`` swaps in a hosted Indic recogniser (``engines.py``) for the
comparison in REPORT §4.12; each one needs its own key and is skipped with a
clear message when the key is absent.

    python research/collect/transcribe.py --manifest research/collect/data/synthetic/manifest.jsonl \
        --out research/collect/data/synthetic/pairs.jsonl --model small
    python research/collect/transcribe.py --manifest ... --engine sarvam     # -> pairs_sarvam.jsonl

Without ``--out`` the file is named for the engine next to the manifest:
``pairs.jsonl`` (whisper), ``pairs_biased.jsonl`` (whisper ``--bias``) and
``pairs_<engine>.jsonl`` for the rest, which is what ``harness/stt_compare.py``
looks for.
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import engines  # noqa: E402

# A word a vendor does not score gets the confidence the text channel would
# give it: known words (the pack's vocabulary, the shared Hinglish vocabulary)
# are confident, out-of-vocabulary words are the text analogue of a doubtful
# recognition. Exactly the model CallSession._text_transcript applies.
_SESSIONS: dict[str, object] = {}


def _oov_confidences(pack_id: str, words: list[str]) -> list[float]:
    if pack_id not in _SESSIONS:
        if str(ROOT / "engine") not in sys.path:
            sys.path.insert(0, str(ROOT / "engine"))
        from haanji.adapters.mock import NullTTS
        from haanji.pipeline import CallSession
        from haanji.tools.builtin import build_registry, open_backend
        from haanji.vertical import load_pack
        pack = load_pack(pack_id)
        backend, _ = open_backend(pack, "t_stt")
        registry = build_registry("t_stt", backend, pack, None)
        _SESSIONS[pack_id] = CallSession(tenant_id="t_stt", pack=pack, backend=backend,
                                         registry=registry, tts=NullTTS())
    session = _SESSIONS[pack_id]
    transcript = session._text_transcript(" ".join(words), final=True)   # noqa: SLF001 - the model lives there
    return [t.confidence for t in transcript.tokens]


def default_out(manifest: Path, engine: str, bias: bool) -> Path:
    if engine == "whisper":
        return manifest.parent / ("pairs_biased.jsonl" if bias else "pairs.jsonl")
    return manifest.parent / f"pairs_{engine}{'_biased' if bias else ''}.jsonl"


def pack_prompts() -> dict[str, str]:
    """The business's name and its catalogue, as the recogniser's prompt."""
    if str(ROOT / "engine") not in sys.path:
        sys.path.insert(0, str(ROOT / "engine"))
    from haanji.vertical import list_packs, load_pack
    prompts: dict[str, str] = {}
    for pid in list_packs():
        pk = load_pack(pid)
        words = [s.name for s in pk.services] + pk.staff + pk.places + pk.brands
        prompts[pid] = f"{pk.persona.business_name}. " + ", ".join(words) + "."
    return prompts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", default=None, help="default: pairs[_<engine>].jsonl next to the manifest")
    ap.add_argument("--engine", default="whisper", choices=sorted(engines.ENGINES),
                    help="which recogniser (default whisper; the rest need a key, see engines.py)")
    ap.add_argument("--model", default=None,
                    help="whisper: tiny/base/small/medium; sarvam: saarika:v2.5; deepgram: nova-2")
    ap.add_argument("--language", default=None,
                    help="decode as this language; the default per engine is en (whisper), hi-IN (sarvam, "
                         "google), hi (bhashini), hi-Latn (deepgram)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--bias", action="store_true",
                    help="give the recogniser each clip's pack vocabulary (initial prompt, keywords or "
                         "speech context, whichever the engine has)")
    args = ap.parse_args(argv)

    opts = {"bias": args.bias}
    if args.model:
        opts["model"] = args.model
    if args.language:
        opts["language"] = args.language
    try:
        engine = engines.make_engine(args.engine, **opts)
    except engines.EngineUnavailable as exc:
        print(f"{args.engine}: not run — {exc}", file=sys.stderr)
        return 2
    if args.bias and not engine.supports_hints:
        print(f"{args.engine}: takes no vocabulary hints; --bias ignored", file=sys.stderr)

    manifest = Path(args.manifest)
    base = manifest.parent
    prompts = pack_prompts() if args.bias and engine.supports_hints else {}
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        rows = rows[:args.limit]
    out = Path(args.out) if args.out else default_out(manifest, args.engine, args.bias)
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    print(f"{engine.label}: {len(rows)} clips", flush=True)
    n = 0
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            path = base / r["file"]
            if not path.exists():
                print(f"  missing {path}", file=sys.stderr)
                continue
            try:
                pairs = engine.transcribe(path, prompt=prompts.get(r["pack"]))
            except engines.EngineUnavailable as exc:
                print(f"{args.engine}: stopped — {exc}", file=sys.stderr)
                return 2
            words = [w for w, _ in pairs if w]
            vendor = [c for w, c in pairs if w]
            if any(c is None for c in vendor):
                confs = _oov_confidences(r["pack"], words)
                source = "oov-model"
            else:
                confs = [float(c) for c in vendor]
                source = "vendor"
            fh.write(json.dumps({
                "id": r["id"], "pack": r["pack"], "truth": r["truth"], "heard": " ".join(words),
                "confidences": confs, "speaker": r.get("speaker", ""), "kind": r.get("kind", ""),
                "synthetic": bool(r.get("synthetic", False)),
                "recogniser": engine.label, "engine": args.engine,
                "confidence_source": source, "script": engine.script,
            }, ensure_ascii=False) + "\n")
            n += 1
            if n % 25 == 0:
                print(f"  {n}/{len(rows)}  {time.time() - t0:.0f}s", flush=True)
    print(f"wrote {n} pairs to {out} in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
