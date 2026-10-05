# Evaluation results

Run began (UTC): 2026-10-05T13:07:47.811031+00:00.
25 frozen questions, 1 repeat(s) per model and retrieval mode.

## Overall (all query types)

| Model | Tier | RAG mode | Succ/Att | Accuracy | Reasoning | Citation | Src-support | p50 lat | p95 lat | Errors |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen2.5:7b | 7b | none | 0 / 25 | n/a | n/a | n/a | n/a | n/a | n/a | 25 |
| qwen2.5:7b | 7b | fixed | 0 / 25 | n/a | n/a | n/a | n/a | n/a | n/a | 25 |
| qwen2.5:7b | 7b | agentic | 0 / 25 | n/a | n/a | n/a | n/a | n/a | n/a | 25 |
| qwen2.5:3b | 3b | none | 0 / 25 | n/a | n/a | n/a | n/a | n/a | n/a | 25 |
| qwen2.5:3b | 3b | fixed | 0 / 25 | n/a | n/a | n/a | n/a | n/a | n/a | 25 |
| qwen2.5:3b | 3b | agentic | 0 / 25 | n/a | n/a | n/a | n/a | n/a | n/a | 25 |

## Named-ticker queries only

| Model | Tier | RAG mode | Succ/Att | Accuracy | Reasoning | Citation | Src-support | p50 lat | p95 lat | Errors |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen2.5:7b | 7b | none | 0 / 25 | n/a | n/a | n/a | n/a | n/a | n/a | 25 |
| qwen2.5:7b | 7b | fixed | 0 / 25 | n/a | n/a | n/a | n/a | n/a | n/a | 25 |
| qwen2.5:7b | 7b | agentic | 0 / 25 | n/a | n/a | n/a | n/a | n/a | n/a | 25 |
| qwen2.5:3b | 3b | none | 0 / 25 | n/a | n/a | n/a | n/a | n/a | n/a | 25 |
| qwen2.5:3b | 3b | fixed | 0 / 25 | n/a | n/a | n/a | n/a | n/a | n/a | 25 |
| qwen2.5:3b | 3b | agentic | 0 / 25 | n/a | n/a | n/a | n/a | n/a | n/a | 25 |

## Discovery queries only (no explicit ticker)

| Model | Tier | RAG mode | Succ/Att | Accuracy | Reasoning | Citation | Src-support | p50 lat | p95 lat | Errors |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen2.5:7b | 7b | none | 0 / 0 | n/a | n/a | n/a | n/a | n/a | n/a | 0 |
| qwen2.5:7b | 7b | fixed | 0 / 0 | n/a | n/a | n/a | n/a | n/a | n/a | 0 |
| qwen2.5:7b | 7b | agentic | 0 / 0 | n/a | n/a | n/a | n/a | n/a | n/a | 0 |
| qwen2.5:3b | 3b | none | 0 / 0 | n/a | n/a | n/a | n/a | n/a | n/a | 0 |
| qwen2.5:3b | 3b | fixed | 0 / 0 | n/a | n/a | n/a | n/a | n/a | n/a | 0 |
| qwen2.5:3b | 3b | agentic | 0 / 0 | n/a | n/a | n/a | n/a | n/a | n/a | 0 |

Scores exclude failed requests; error counts are explicit.
Accuracy = strict labeled-term matching, not expert judgment.
Reasoning = citation/rationale proxy (automated).
Source-support = human reviewer score 0–2 (0=unsupported, 1=partial, 2=fully supported); n/a until --scored-csv supplied.
Latency is real wall-clock time per request; p95 captures tail latency.
With one repeat, consistency is n/a; use ≥3 repeats for a consistency comparison.
Raw LLM answers preserved in raw_answers/ for trace inspection.
No trading performance inference from these scores.
