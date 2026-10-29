# Harness

Scripts that produce the numbers in the report. Each one writes its result
next to this folder and prints the Markdown it was pasted from.

| Script | What it measures | Output |
|---|---|---|
| `llm_ablation.py` | The deterministic policy against a hosted model (Claude) on the 21 packaged scenarios: outcomes, receipts, engine-side latency, speculation hit rate, fallbacks, tokens. The `claude` half runs only when `ANTHROPIC_API_KEY` is set (shell or `engine/.env`). | `research/llm_ablation.json` |
| `stt_compare.py` | Five recognisers (whisper, sarvam, bhashini, deepgram, google) on the same recordings, scored before and after Bhasha repair with the §4.5 measurement. Scores whatever `collect/transcribe.py --engine X` has written; an engine with no key is listed as `not run: key needed`, never invented. | `research/stt_compare.json`, `research/stt_compare_tables.md` |
| `readme_sync.py` | Not a measurement: rewrites the test, pack, scenario and language counts quoted in `README.md` and `REPORT.md` (badge, §3.2 table, Appendix A/B/C) from what the repository contains; `--check` exits 1 when they are stale, and CI runs it (`make readme-sync` / `make readme-check`). | the two documents |

```bash
python research/harness/llm_ablation.py              # both providers
python research/harness/llm_ablation.py --only mock  # offline
```
