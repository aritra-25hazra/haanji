# Harness

Scripts that produce the numbers in the report. Each one writes its result
next to this folder and prints the Markdown it was pasted from.

| Script | What it measures | Output |
|---|---|---|
| `llm_ablation.py` | The deterministic policy against a hosted model (Claude) on the 21 packaged scenarios: outcomes, receipts, engine-side latency, speculation hit rate, fallbacks, tokens. The `claude` half runs only when `ANTHROPIC_API_KEY` is set (shell or `engine/.env`). | `research/llm_ablation.json` |

```bash
python research/harness/llm_ablation.py              # both providers
python research/harness/llm_ablation.py --only mock  # offline
```
