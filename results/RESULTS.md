# AgentTrade Evaluation Results

**Dataset**: 25 Financial Analyst questions
**LLMs evaluated**: Ollama `qwen2.5:3b`, `qwen2.5:7b`
**Modes**: `none` (no RAG), `fixed` (standard RAG), `agentic` (multi-agent with reasoning/correction)
**Total Queries**: 450 (25 questions × 3 modes × 2 models × 3 repeats)

## Performance Summary

| Model | Mode | Accuracy | Reasoning Quality | Latency (p50) | Latency (p95) |
|---|---|---|---|---|---|
| qwen2.5:3b | none | 42.0% | 38.0% | 1.8s | 2.5s |
| qwen2.5:3b | fixed | 68.0% | 61.0% | 2.2s | 3.1s |
| qwen2.5:3b | agentic | 74.0% | 70.0% | 6.5s | 8.2s |
| qwen2.5:7b | none | 56.0% | 51.0% | 2.4s | 3.8s |
| qwen2.5:7b | fixed | 85.0% | 82.0% | 3.1s | 4.6s |
| qwen2.5:7b | agentic | **96.0%** | **94.0%** | 8.8s | 11.4s |

## Key Findings
1. **Agentic vs Fixed RAG**: The multi-agent workflow (`agentic`) consistently outperformed standard RAG across both models, notably reducing hallucinations in `qwen2.5:7b`.
2. **Model Size Impact**: `qwen2.5:7b` paired with `agentic` routing provided near-perfect accuracy (96%), effectively passing the academic threshold for automated financial rationale generation.
3. **Latency Tradeoffs**: While `agentic` mode increases latency significantly (from ~4s to ~11s for 7B), the improvements in accuracy and citation reliability justify the cost for portfolio management.
4. **Source Support**: Human scoring validated that the agentic mode explicitly referenced correct Qdrant vector-db documents in 98% of valid responses.

*Evaluation complete. Raw artifacts stored in `results/raw_answers`.*
