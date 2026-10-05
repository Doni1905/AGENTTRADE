# AGENTTRADE Report

## Problem and scope

A single chatbot can invent current stock news or leap from weak evidence to an order. AGENTTRADE separates retrieval, analysis, critique and deterministic risk. The only execution is in a Alpaca paper account after a user's explicit form approval. The project accepts any valid US-listed ticker, confirmed against live market data, while the frozen evaluation corpus stays seeded for AAPL and MSFT only. It is not a predictive trading product. A frozen, labeled evaluation corpus makes retrieval evaluation reproducible; it is **not** real company financial data. The two-ticker restriction in synthetic policy card 3 was a historical evaluation scope; it is now annotated as obsolete in the card text and is superseded by live API risk rules.


## Stakeholders

1. **Retail Investor:** Seeks transparent, understandable insights and risk-controlled execution without needing deep financial modeling skills.
2. **Financial Analyst:** Requires traceable evidence, technical indicator validation, and clear logic paths to augment their own research.
3. **Portfolio Manager:** Needs robust deterministic risk constraints (max quantity, max notional, no short selling) to ensure safe execution boundaries.
4. **Risk Manager / Compliance Officer:** Relies on deterministic validation (RSI, SMA, MACD constraints, explicit human approval) that cannot be bypassed by LLM hallucinations.
5. **Broker / Paper-Trading Platform:** Interacts securely with the system via isolated API endpoints (e.g. Alpaca Paper Trading).
6. **Market Data & Financial Information Providers:** Provide the critical pricing and headline data (e.g. Yahoo Finance) used for grounding.
7. **System Administrator:** Requires clear Docker-based deployment boundaries, isolated credentials, and reliable local execution.

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


## EXPERIMENTAL EVALUATION AND RESULTS

### A. Technical Indicator Verification
We verified the deterministic Python market calculations against an independent test harness.
| Indicator | Test Case | Expected | Actual | Result |
|---|---|---|---|---|
| SMA20 | 100 days linear (100 to 200) | 190.40 | 190.40 | PASS |
| SMA50 | 100 days linear (100 to 200) | 175.25 | 175.25 | PASS |
| RSI14 | Constant gain (linear) | 100.0 | 100.0 | PASS |
| MACD | Linear upward trend | 7.065 | 7.065 | PASS |
| Insufficient Data | 20 days data | ValueError | ValueError | PASS |
| Missing Values (NaN) | 60 days with 1 missing | 129.24 (valid) | 129.24 | PASS |

### B. Risk-Control Verification
All risk rules were executed and confirmed to block or allow orders appropriately.
| Risk Test | Input | Expected | Actual | Result |
|---|---|---|---|---|
| Quantity <= 5 | Qty=5, Price=150 | ALLOW / Keys err | ALLOW / Keys err | PASS |
| Quantity > 5 | Qty=6, Price=150 | BLOCK (422) | BLOCK (422) | PASS |
| Notional <= $1,000 | Qty=5, Price=150 | ALLOW / Keys err | ALLOW / Keys err | PASS |
| Notional > $1,000 | Qty=5, Price=250 | BLOCK (422) | BLOCK (422) | PASS |
| Short selling | Qty=1, Side=SELL | BLOCK (400) | BLOCK (400) | PASS |

### C. Human-Approval and Paper-Execution Verification
- **PATH A (No human approval):** Attempting an Alpaca paper order directly from a proposal without explicit user interaction in the UI is BLOCKED. The execution requires the private approval code and a separate POST request.
- **PATH B (Explicit human approval):** Executing the AAPL workflow with paper credentials creates a local proposal. Using the UI to explicitly approve it submits the order successfully to the Alpaca PAPER API (as verified in end-to-end testing). 
- **Live Trading Endpoint:** It is explicitly confirmed that the implementation uses the `paper-api.alpaca.markets` endpoint. No live-money endpoints are configured or used.

### D. Retrieval and Debate Workflow Reliability
The multi-agent debate (Retrieval -> Analyst -> Bull -> Bear -> Critic -> Correction) successfully executes and synthesizes financial context.
- **Bull/Bear Generation:** Both cases are generated reliably from the identical context.
- **Critic & Correction:** The Critic reliably identifies unsupported claims, and the single-pass Correction incorporates these insights to qualify claims.
- **End-to-End Success:** The pipeline executed fully on AAPL without crashes, although latency is subject to the speed of the local Ollama processes.
- *Note: Latency was not independently measured in the final verification due to environment variability.*
- *Note: Retrieval metrics (Precision/Recall) and prediction accuracy were not measured. This is a decision-support prototype, not a predictive trading oracle.*

### E. Existing RAG Benchmark
*(The following benchmark is preserved from the original evaluation run. It evaluates retrieval/model behavior, not investment profitability or expert financial accuracy.)*
<!-- EVAL_RESULTS_START -->
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
<!-- EVAL_RESULTS_END --> If pricing is tested, current Yahoo snapshots cannot recreate a historical point-in-time backtest and should be excluded from the frozen QA comparison.

## Limits and threats to validity

Synthetic benchmark policy questions are easier than actual equity research and cannot validate investment conclusions. Term matching can reward wrong answers that include expected words; citations can be present but irrelevant; exact string consistency is harsh. Live Yahoo data may be delayed, interrupted, or subject to personal-use restrictions. NewsAPI is an optional local development-only source; its free Developer plan has a 24-hour delay and cannot be used in staging or production, even internally (https://newsapi.org/pricing). When the key is absent or that feed fails, Yahoo headline retrieval is attempted. All researched tickers receive dated live price cards in the same collection, with available key statistics and recent Yahoo Finance headlines. No news yields a flagged price/stat fallback; a headline is not a verified full article and source coverage varies by ticker. The old synthetic policy card 3 originally asserted an obsolete two-ticker limit; the card now includes an explicit OBSOLETE annotation and must not be applied to live trading rules. No licensed exchange feed, verified full-article news/filings provider or realistic commission/slippage model is included. Alpaca paper account and keys are needed before an order can be demonstrated. Because n8n runs natively rather than in Compose, its HTTP Request nodes must target localhost:8000 instead of the Compose-internal api hostname, and its Ollama and Qdrant credentials must use localhost URLs. The final implementation was validated locally using FastAPI, n8n, Ollama, Qdrant and Alpaca Paper Trading. An AAPL request was executed end-to-end through evidence retrieval, multi-agent analysis, proposal generation, deterministic risk validation, human approval and paper-order submission. API warnings and debug output are written to `agenttrade.log` (rotating RotatingFileHandler, 5 MB × 3 backups) rather than a static `debug.log`.

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


### Final System Validation

| Component/Test | Expected | Observed | Status |
|---|---|---|---|
| FastAPI | Backend available | Verified | PASS |
| n8n | Workflow executes | Verified | PASS |
| Ollama | Model inference | Verified | PASS |
| Qdrant | Evidence retrieval | Verified | PASS |
| AAPL research | Complete analysis | Verified | PASS |
| Bull/Bear debate | Both cases generated | Verified | PASS |
| Critic | Final synthesis | Verified | PASS |
| Risk engine | Constraints enforced | Verified | PASS |
| Human approval | Required | Verified | PASS |
| Alpaca | Paper order | Verified | PASS |
