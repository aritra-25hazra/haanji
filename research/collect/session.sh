#!/usr/bin/env bash
# The volunteer and user-study sessions, on this laptop only (docs/study/KIT.md).
#
#   research/collect/session.sh start     # the local server; open the printed pages
#   research/collect/session.sh results   # with the server still running: export and analyse
#
# Everything stays on this machine: recordings in engine/var/recordings/, the
# study answers in engine/var/study.sqlite, and every export and result in
# research/collect/data/volunteers/ (all three are gitignored; never commit them).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$ROOT/engine/.venv/bin/python"
OUT="${SESSION_OUT:-$ROOT/research/collect/data/volunteers}"
VAR="${SESSION_VAR:-var}"            # relative to engine/ (the default) or absolute
PORT="${PORT:-8090}"
BASE="http://localhost:$PORT"

case "${1:-}" in
  start)
    git -C "$ROOT" check-ignore -q engine/var/x && git -C "$ROOT" check-ignore -q research/collect/data/volunteers/x \
      || { echo "engine/var or research/collect/data/volunteers is not gitignored: stop" >&2; exit 1; }
    cat <<MSG

  HaanJi, local session server on $BASE
    recording (volunteers):   $BASE/record
    user study (participants): $BASE/study
    the console (runner):     run 'npm run dev' in console/ and open http://localhost:5173/calls

  Ctrl+C stops it. Keep it running while you run 'session.sh results'.

MSG
    cd "$ROOT/engine"
    # No HAANJI_PUBLIC_URL: a local server, sign-in off, nothing leaves the laptop.
    exec env -u HAANJI_PUBLIC_URL -u RENDER_EXTERNAL_URL HAANJI_VAR_DIR="$VAR" "$PY" -m haanji.cli serve --port "$PORT" --var-dir "$VAR"
    ;;
  results)
    mkdir -p "$OUT"
    curl -fsS "$BASE/api/study/export" -o "$OUT/study.csv" && echo "study answers  -> $OUT/study.csv"
    if [ "$(wc -l < "$OUT/study.csv")" -gt 1 ]; then
      "$PY" "$ROOT/research/harness/study_analysis.py" "$OUT/study.csv" > "$OUT/study_summary.md"
      echo "study summary  -> $OUT/study_summary.md"
    else
      echo "no study answers yet"
    fi
    case "$VAR" in /*) VARDIR="$VAR" ;; *) VARDIR="$ROOT/engine/$VAR" ;; esac
    MANIFEST="$VARDIR/recordings/manifest.jsonl"
    if [ -s "$MANIFEST" ]; then
      "$PY" "$ROOT/research/collect/transcribe.py" --manifest "$MANIFEST" --out "$OUT/pairs.jsonl" --model "${MODEL:-small}"
      "$PY" "$ROOT/research/collect/evaluate.py" --pairs "$OUT/pairs.jsonl" --out "$OUT/real_asr_volunteers.json" \
        --label "volunteer recordings, faster-whisper ${MODEL:-small}"
      echo "recordings     -> $OUT/real_asr_volunteers.json"
    else
      echo "no recordings yet"
    fi
    echo
    echo "Nothing here is committed. Send the two summary files to Claude to write them into the report."
    ;;
  *)
    sed -n '2,10p' "$0"; exit 2 ;;
esac
