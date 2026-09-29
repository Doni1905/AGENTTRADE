# AGENTTRADE mini-project report

## Problem and scope

A single chatbot can invent current stock news or leap from weak evidence to an order. AGENTTRADE separates retrieval, analysis, critique and deterministic risk. The only execution is in a Alpaca paper account after a user's explicit form approval. The project accepts any valid US-listed ticker, confirmed against live market data, while the frozen classroom corpus stays seeded for AAPL and MSFT only. It is not a predictive trading product. A frozen, labeled classroom corpus makes retrieval evaluation reproducible; it is **not** real company financial data.

## Architecture and justification

n8n coordinates a retrieval agent, analyst and critic, with a single bounded correction pass. The retrieval agent uses Qdrant as a tool and chooses query terms; fixed RAG is implemented separately in the Python service to isolate retrieval policy. Three roles help trace evidence, proposed judgment, and failure checks. Ollama supplies local Qwen2.5 3B and Llama3.2 3B; Qdrant stores dated synthetic case cards; Python computes RSI14, SMA20/50, MACD and deterministic position/order limits. SQLite stores proposals and Alpaca order receipt IDs, while Alpaca paper account owns order status and positions. A single agent would make it harder to separate missing evidence from speculative judgment. The agent output does not authorize paper API submissions. Deployment is split: Docker Compose runs only the Qdrant and Python API containers, while n8n and Ollama run natively on the host machine. The API container reaches host Ollama at http://host.docker.internal:11434 and host n8n at http://host.docker.internal:5678.

## Core capabilities

- **Tool use and agentic RAG:** agent-chosen Qdrant tool query; source IDs and publication dates in retrieved payloads. No-RAG and fixed top-3 RAG are controlled baselines routed around the tool-connected agent. In agentic mode the prompt requires retrieval, but model behavior must be checked in execution logs.
- **Memory:** persistent Qdrant source-card store and SQLite proposal/trade history. This is external state, not conversational personal memory; no claim of long-term autonomous learning.
- **Reflection:** independent critic checks freshness, claims and risk; bounded one-pass revision prevents unconstrained self-talk.
- **Collaboration/HITL:** three agents collaborate; a separate form requires human choice for Alpaca paper orders.
- **Safety:** service validates tickers by format and against live market data and rejects unknown symbols, stale/unavailable prices, short sales, order notional over USD 1,000, positions above 5 shares, stale/shifted proposals, duplicate approval. Only Alpaca paper API is used; credentials are set locally and the URL is hard-coded to the paper host. The paper approval endpoint is guarded by a private local approval code; other local endpoints are unauthenticated. Never expose ports publicly.

## Evaluation design

25 frozen dated questions test identity, policy, data rules, indicators and evaluation rules. For each of two models test three retrieval conditions: none; Qdrant fixed top 3; agent-chosen Qdrant. Repeat each three times. Script stores every response and latency; calculate strict label-term accuracy, a citation/rationale reasoning-quality proxy, citation presence, and exact normalized response consistency. This produces 450 workflow requests; each triggers several model calls. Check source support with human annotation before claiming reasoning quality. Ensure both models actually call the Qdrant tool in agentic mode by inspecting n8n traces. Use the same local model versions, prompts, embeddings and dated corpus. Rerun with frozen data for a fair comparison. The benchmark stays on the seeded AAPL/MSFT questions by design: the corpus has no cards for other tickers, so extending the evaluation requires adding dated cards for them first.

**Results status:** not measured in this build environment; no local Docker daemon or models are available here. `results/` is intentionally absent. The included evaluator writes the results after the user runs the stack. Never paste illustrative numbers into the final report. If pricing is tested, current Yahoo snapshots cannot recreate a historical point-in-time backtest and should be excluded from the frozen QA comparison.

## Limits and threats to validity

Synthetic classroom policy questions are easier than actual equity research and cannot validate investment conclusions. Term matching can reward wrong answers that include expected words; citations can be present but irrelevant; exact string consistency is harsh. Live Yahoo data may be delayed, interrupted, or subject to personal-use restrictions. For symbols beyond the seeded AAPL/MSFT cards, retrieval returns no ticker-specific evidence, so those runs lean on the live market snapshot and their evidence coverage is weaker. No licensed exchange feed, live news/fundamental provider or realistic commission/slippage model is included. Alpaca paper account and keys are needed before an order can be demonstrated. Because n8n runs natively rather than in Compose, its HTTP Request nodes must target localhost:8000 instead of the Compose-internal api hostname, and its Ollama and Qdrant credentials must use localhost URLs. The n8n workflow JSON was structurally checked off-platform, not run in a live n8n instance in the build environment, so import and end-to-end behavior require the supplied host validation steps before the project can honestly be called runtime-verified.

## Source references

- n8n AI starter kit: https://docs.n8n.io/deploy/host-n8n/deploy-with-the-ai-starter-kit/
- n8n Qdrant tool mode: https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.vectorstoreqdrant/
- n8n Tools Agent: https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/tools-agent/
- yfinance README: https://github.com/ranaroussi/yfinance
