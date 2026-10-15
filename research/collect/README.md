# Real recogniser data

The benchmark's noise is synthetic (`haanji/corrupt.py`). This folder is the
pipeline that replaces it with a real recogniser's output, in two stages of
honesty:

1. **Synthetic speech, real recogniser** (can run today, on a Mac): the
   operating system's Indian-English voices read the prompt sentences and
   faster-whisper transcribes them with no hints and no vocabulary. This
   measures a real recogniser's errors on Indian-English *synthesis*, which is
   not the same as Indian callers, and every file produced is labelled
   `synthetic: true`.
2. **Recorded speech, real recogniser** (needs volunteers): people read the
   same prompts into the `/record` page of the demo server; the same
   transcription and scoring run over the recordings.

Either way the output is a `pairs.jsonl` of `(heard, truth)` lines with
per-word confidence, and `evaluate.py` scores it with the Bhasha Bridge off
and on using exactly the measurement the benchmark uses (entity error rate,
correction precision, harmful corrections), plus plain word error rate.

## Commands

```bash
pip install faster-whisper                      # once; the model downloads on first use

# stage 1: synthetic speech (macOS)
python research/collect/synth.py --per-pack 20                     # -> data/synthetic/{audio,manifest.jsonl}
python research/collect/transcribe.py --manifest research/collect/data/synthetic/manifest.jsonl \
    --out research/collect/data/synthetic/pairs.jsonl --model small
python research/collect/evaluate.py --pairs research/collect/data/synthetic/pairs.jsonl   # -> research/real_asr.json

# stage 2: volunteers
haanji serve                                     # open http://localhost:8090/record
#   each volunteer picks a pack, records 20 sentences; files land in engine/var/recordings/
python research/collect/transcribe.py --manifest engine/var/recordings/manifest.jsonl \
    --out research/collect/data/volunteers/pairs.jsonl --model small
python research/collect/evaluate.py --pairs research/collect/data/volunteers/pairs.jsonl \
    --label "volunteer recordings, faster-whisper small"
```

If the server runs on a host with an ephemeral disk (Render), download
`/api/record/export` (a zip of the audio and manifest) before each redeploy.

## For volunteers (Hinglish)

`/record` page kholo, pack chuno, apna code likho, "Shuru karo". Har vaakya
jaise likha hai waise bolo, apni normal awaaz mein — saaf bolne ki koshish mat
karo, galtiyan hi naapni hain. Awaaz sirf is evaluation ke liye hai; naam ya
number kahin nahi jaata.

## Files

| path | what |
|---|---|
| `synth.py` | prompts → `say` → `manifest.jsonl` + audio (synthetic, labelled) |
| `transcribe.py` | manifest → faster-whisper → `pairs.jsonl` (word probabilities become confidences) |
| `evaluate.py` | pairs → `research/real_asr.json` + Markdown table |
| `data/<set>/pairs.jsonl` | committed; audio under `data/<set>/audio/` is not |
| `engine/haanji/collect.py` | prompt list, pair format, the scoring (shared with the server's `/record`) |
