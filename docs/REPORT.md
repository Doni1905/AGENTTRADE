# AGENTTRADE mini-project report

## Problem and scope

A single chatbot can invent current stock news or leap from weak evidence to an order. AGENTTRADE separates retrieval, analysis, critique and deterministic risk. The only execution is in a Alpaca paper account after a user's explicit form approval. The project accepts any valid US-listed ticker, confirmed against live market data, while the frozen classroom corpus stays seeded for AAPL and MSFT only. It is not a predictive trading product. A frozen, labeled classroom corpus makes retrieval evaluation reproducible; it is **not** real company financial data. The two-ticker restriction in synthetic policy card 3 was a historical classroom scope; it is now annotated as obsolete in the card text and is superseded by live API risk rules.

## Architecture and justification

n8n coordinates a retrieval agent, analyst, short bull and bear cases, a critic judge, and a single bounded correction pass. The debate is deliberately limited to two short arguments per side for 3B local models. The retrieval agent uses Qdrant as a tool and chooses query terms; fixed RAG is implemented separately in the Python service to isolate retrieval policy. Three roles help trace evidence, proposed judgment, and failure checks. Ollama defaults to Qwen2.5 7B for the analyst and critic judge and Qwen2.5 3B for retrieval, bull, bear and bounded correction. Llama3.2 3B remains a supported alternative. Embeddings use nomic-embed-text; Qdrant stores frozen synthetic case cards alongside ticker-tagged live price, available statistics and headline cards generated on demand; Python computes RSI14, SMA20/50, MACD and deterministic position/order limits. SQLite stores proposals and Alpaca order receipt IDs, while Alpaca paper account owns order status and positions. A single agent would make it harder to separate missing evidence from speculative judgment. The agent output does not authorize paper API submissions. Deployment is split: Docker Compose runs only the Qdrant and Python API containers, while n8n and Ollama run natively on the host machine. The API container reaches host Ollama at http://host.docker.internal:11434 and host n8n at http://host.docker.internal:5678.

## Plain-language research output

The final correction pass begins with a 2-4 sentence Simple summary for a reader without a finance background. Technical detail follows with the supported BUY/HOLD/SELL decision, evidence, dated citations and inline explanations of any financial terms. The analyst and both debate agents prepare readable claims; the critic checks for a missing or misleading summary and unsupported valuation. For unrelated questions, the output says the decision is not applicable. The API rejects a missing or mismatched summary rather than silently showing a jargon-only answer; the dashboard highlights it above the detail. This is a communication-quality design choice, not a measured readability result. Small local models can still miss the instructions, so inspect real runs on the target machine.

## Core capabilities

- **Tool use and agentic RAG:** agent-chosen Qdrant tool query; source IDs and publication dates in retrieved payloads. No-RAG and fixed top-3 RAG are controlled baselines routed around the tool-connected agent. In agentic mode the prompt requires retrieval, but model behavior must be checked in execution logs.
- **Memory:** persistent Qdrant source-card store and SQLite proposal/trade history. This is external state, not conversational personal memory; no claim of long-term autonomous learning.
- **Reflection:** independent critic checks freshness, claims and risk; bounded one-pass revision prevents unconstrained self-talk.
- **Collaboration/HITL:** three agents collaborate; a separate form requires human choice for Alpaca paper orders.
- **Safety:** service validates tickers by format and against live market data and rejects unknown symbols, stale/unavailable prices, short sales, order notional over USD 1,000, positions above 5 shares, stale/shifted proposals, duplicate approval. With paper keys configured, proposal creation checks live account status, available shares for SELL, and buying power with a 2% cushion plus five-share exposure for BUY; unavailable broker state fails closed without a proposal. Without keys, proposals remain local and approval cannot submit an order. Approval repeats capacity checks because state may change, and broker rejection messages reach the dashboard. Only Alpaca paper API is used; credentials are set locally and the URL is hard-coded to the paper host. The paper approval endpoint is guarded by a private local approval code; other local endpoints are unauthenticated. Never expose ports publicly.

## Evaluation design

25 frozen dated questions test identity, policy, data rules, indicators and evaluation rules. For each of two models test three retrieval conditions: none; Qdrant fixed top 3; agent-chosen Qdrant. Repeat each three times. Script stores every response and latency; calculate strict label-term accuracy, a citation/rationale reasoning-quality proxy, citation presence, and exact normalized response consistency. This produces 450 workflow requests; each triggers several model calls. Check source support with human annotation before claiming reasoning quality. Ensure both models actually call the Qdrant tool in agentic mode by inspecting n8n traces. Use the same local model versions, prompts, embeddings and dated corpus. Rerun with frozen data for a fair comparison. The benchmark stays on the seeded AAPL/MSFT questions by design. Live cards persist in the same Qdrant collection, so run the benchmark on a clean collection before live research; `/ingest` does not clear previously added live points. Extending the frozen benchmark requires adding dated case cards and questions first.

**Results status:** not measured in this build environment; no local Docker daemon or models are available here. Run `python3 app/evaluate.py --repeats 1` as a pipeline smoke check, then `python3 app/evaluate.py --repeats 3` on a fresh Qdrant collection before live research. The evaluator writes actual responses to `results/` and replaces only the bounded section below with measured tables. Never paste illustrative numbers into the final report.

<!-- EVAL_RESULTS_START -->
# Evaluation results

Run began (UTC): 2026-10-03T16:24:59.631855+00:00.
25 frozen questions, 3 repeat(s) per model and retrieval mode.

| Model | RAG mode | Successful / attempted | Accuracy | Reasoning proxy | Citation rate | Exact consistency | Errors |
|---|---|---:|---:|---:|---:|---:|---:|
| qwen2.5:3b | none | 75 / 75 | 0.307 | 0.000 | 0.013 | 0.000 | 0 |
| qwen2.5:3b | fixed | 75 / 75 | 0.707 | 0.000 | 0.000 | 0.000 | 0 |
| qwen2.5:3b | agentic | 75 / 75 | 0.640 | 0.013 | 0.053 | 0.000 | 0 |
| llama3.2:3b | none | 75 / 75 | 0.293 | 0.000 | 0.000 | 0.000 | 0 |
| llama3.2:3b | fixed | 75 / 75 | 0.893 | 0.000 | 0.000 | 0.000 | 0 |
| llama3.2:3b | agentic | 75 / 75 | 0.747 | 0.027 | 0.027 | 0.000 | 0 |

Scores exclude failed requests and show their counts explicitly; a row with no successful requests is n/a.
Accuracy is strict labeled-term matching, not expert judgment. Reasoning is a citation/rationale proxy.
With one repeat, consistency is n/a; use three or more repeats for a consistency comparison.
Inspect raw.csv and n8n traces for actual source support and tool calls. No trading performance inference.
<!-- EVAL_RESULTS_END --> If pricing is tested, current Yahoo snapshots cannot recreate a historical point-in-time backtest and should be excluded from the frozen QA comparison.

## Limits and threats to validity

Synthetic classroom policy questions are easier than actual equity research and cannot validate investment conclusions. Term matching can reward wrong answers that include expected words; citations can be present but irrelevant; exact string consistency is harsh. Live Yahoo data may be delayed, interrupted, or subject to personal-use restrictions. NewsAPI is an optional local development-only source; its free Developer plan has a 24-hour delay and cannot be used in staging or production, even internally (https://newsapi.org/pricing). When the key is absent or that feed fails, Yahoo headline retrieval is attempted. All researched tickers receive dated live price cards in the same collection, with available key statistics and recent Yahoo Finance headlines. No news yields a flagged price/stat fallback; a headline is not a verified full article and source coverage varies by ticker. The old synthetic policy card 3 originally asserted an obsolete two-ticker limit; the card now includes an explicit OBSOLETE annotation and must not be applied to live trading rules. No licensed exchange feed, verified full-article news/filings provider or realistic commission/slippage model is included. Alpaca paper account and keys are needed before an order can be demonstrated. Because n8n runs natively rather than in Compose, its HTTP Request nodes must target localhost:8000 instead of the Compose-internal api hostname, and its Ollama and Qdrant credentials must use localhost URLs. The n8n workflow JSON was structurally checked off-platform, not run in a live n8n instance in the build environment, so import and end-to-end behavior require the supplied host validation steps before the project can honestly be called runtime-verified. API warnings and debug output are written to `agenttrade.log` (rotating RotatingFileHandler, 5 MB × 3 backups) rather than a static `debug.log`.

## Source references

- n8n AI starter kit: https://docs.n8n.io/deploy/host-n8n/deploy-with-the-ai-starter-kit/
- n8n Qdrant tool mode: https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.vectorstoreqdrant/
- n8n Tools Agent: https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/tools-agent/
- yfinance README: https://github.com/ranaroussi/yfinance


## Portfolio

The research dashboard (`/`) handles research, approvals, and the local submission ledger. A separate portfolio page (`/portfolio`) reads `/api/portfolio` for Alpaca paper equity, cash, buying power, positions, one-month broker portfolio-history profit/loss, and the 20 most recent broker orders with filled quantities, fill price and status. Refresh reloads broker data. Without keys it shows an unconfigured state, not simulated holdings. The local ledger records submissions, not fill-confirmed P&L; it cannot establish a return series. The broker chart can be empty on a new account. Confirm fills and any cash-flow effects in Alpaca.

## Production boundary

This is a local paper research tool, not a production financial service. No login protects the dashboard or research endpoints; approval code is rendered into the localhost page. Keep Docker ports bound to 127.0.0.1, do not expose the dashboard, n8n, Ollama or Qdrant publicly, and add authentication, secret handling, rate limits, data rights and operational monitoring before any multi-user deployment. Never use real-trading keys.


### Natural-language research input

The dashboard takes a single question rather than a separate ticker. The service extracts explicit uppercase tickers or a small, extensible common-name alias map and checks candidates against Yahoo before sending a resolved ticker to the unchanged n8n workflow. No stock or multiple distinct stocks prompts a fallback ticker field, not a guessed recommendation. One detected stock starts analysis immediately without a confirmation tap. A small "Analyzing: Apple (AAPL)" indicator labels the company and ticker as research starts; a valid fallback ticker also starts immediately. Market-data outages are shown as errors rather than prompting for a different ticker. Trading still requires explicit human approval; the benchmark retains its explicit-ticker API path. This detection is deliberately narrow: unfamiliar company names need a ticker.


## Two-tier routing update

The dashboard omits legacy `model` selection and uses the API defaults: `fast_model=qwen2.5:3b`, `smart_model=qwen2.5:7b`. The `/prepare` response resolves both names; the n8n analyst and critic model nodes use `smart_model`, and the other four chat nodes use `fast_model`. Explicit legacy `model` requests still use a single model for every chat role unless a tier override is supplied. Both resolved names are returned for audit. Embeddings are unchanged. The Simple summary is part of analyst/correction output, not a separate node.

The existing Qwen3B vs Llama3B evaluation intentionally remains single-model for comparability; its results cannot establish two-tier quality or speed. Bounded correction still uses 3B and can change the final wording and decision. No latency or quality improvement has been measured for the split setup. Offline API tests and structural workflow checks do not replace importing and testing on the host with all required models installed.
