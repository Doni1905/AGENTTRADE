# AGENTTRADE

AGENTTRADE is a local stock-research tool for US-listed equities. It combines n8n workflows, local Ollama models, Qdrant retrieval, and a Python API to compare research approaches and submit **paper-only** orders through Alpaca after explicit human approval. It is an educational project, not an investment adviser or a live-trading system.

## Features

- Any valid US-listed symbol for research and paper proposals: symbols are validated live against Yahoo Finance, and unknown symbols are rejected with a clear error. For research, dated live evidence cards for the requested symbol are built from Yahoo Finance price history, available statistics and recent headlines, then upserted alongside frozen benchmark cards in Qdrant.
- Each research answer starts with a 2-4 sentence **Simple summary** for readers without a finance background. Technical details follow with a BUY/HOLD/SELL decision where relevant, dated evidence, and brief plain-word explanations of financial terms. An unrelated question gets no forced trading decision.
- Three research modes: no retrieval (`none`), fixed top-3 retrieval (`fixed`), and agent-selected Qdrant retrieval (`agentic`).
- Retrieval and analyst roles, short bull/bear arguments and a critic judge, followed by one bounded correction pass.
- Two-tier local models: `qwen2.5:7b` for analyst and critic judge; `qwen2.5:3b` for retrieval, bull, bear and bounded correction. `llama3.2:3b` remains a single-model benchmark alternative; `nomic-embed-text` handles embeddings.
- Python-calculated market indicators and deterministic proposal/risk checks. Research output cannot place an order.
- A dashboard approval flow for Alpaca paper orders: pending proposals, one-click approve or reject, local approval code, proposal expiry, and duplicate-order checks. An n8n approval form is included as an alternative path.
- A 25-question benchmark comparing three retrieval modes across both models; the evaluator writes raw responses, measured summaries, and the report table after a local run. A dedicated paper portfolio page reads broker positions, historical profit/loss, and recent broker orders/fills.

## Architecture

```text
Native on the host machine:   n8n (workflow orchestration) + Ollama (models)
Docker Compose (containers):  qdrant (evidence store) + api (FastAPI service)

Research request -> n8n research workflow -> Python API (prepare, data, fixed retrieval)
                                        |-> Qdrant + Ollama: retrieval agent (agentic mode)
                                        |-> Ollama: analyst -> bull -> bear -> critic judge -> one correction -> answer

Human -> dashboard approval (or n8n form) -> Python API (risk recheck, SQLite ledger)
                           -> Alpaca paper API (order submission only)
```

Docker Compose runs two services: `qdrant` (evidence store) and `api` (FastAPI dashboard, market data, risk rules, and ledger). Ollama and n8n run natively on the host machine. The API container reaches host Ollama at `http://host.docker.internal:11434`, which Docker Desktop provides on both Mac and Windows. The research workflow does not have an order-submission path. See [the project report](docs/REPORT.md) for the design and evaluation limits.

## Prerequisites

- [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/) or [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/), started with its engine running.
- [Ollama](https://ollama.com/download) installed natively on the host (Mac app or Windows installer), not in Docker.
- [Node.js](https://nodejs.org/) (current LTS) to run n8n with `npx`.
- Git and Python 3. The examples below use `python3` (Mac) and `python` (Windows).
- Enough disk space for three language models and an embedding model. Model downloads can take several minutes.
- Access to this private repository. An [Alpaca paper account](https://app.alpaca.markets/signup) is needed **only** to submit paper orders; research and evaluation do not need Alpaca keys.

## Quick start

Run these commands on the machine hosting the stack. On Windows PowerShell, replace `cp` with `copy`, `python3` with `python`, and `curl` with `curl.exe` (PowerShell aliases `curl` to `Invoke-WebRequest`).

1. Clone the repository and create your local environment file:

   ```sh
   git clone https://github.com/Doni1905/AGENTTRADE.git
   cd AGENTTRADE
   cp .env.example .env
   ```

   In `.env`, replace `APPROVAL_CODE` with a random value. Do not commit `.env` or share the value.

   ```sh
   python3 -c 'import secrets; print(secrets.token_hex(32))'
   ```

2. Install the required models with the native Ollama. Make sure Ollama is running (open the app on Mac, or the Ollama service on Windows):

   ```sh
   ollama pull qwen2.5:7b
   ollama pull qwen2.5:3b
   ollama pull llama3.2:3b
   ollama pull nomic-embed-text
   ollama list
   ```

3. Build and start the two container services, then check the API:

   ```sh
   docker compose up -d --build
   docker compose ps
   curl http://localhost:8000/health
   ```

4. Ingest the included synthetic evidence cards into Qdrant:

   ```sh
   curl -X POST http://localhost:8000/ingest
   ```

5. Start n8n natively (it stays in the foreground; use a second terminal for later commands):

   ```sh
   npx n8n
   ```

   Open [n8n](http://localhost:5678) and create its local owner account. Re-import the updated research workflow after pulling this version; the old imported copy will not update automatically. Use **Import from File** to import both `workflows/research.json` and `workflows/approval.json`. Then:

   - Create Ollama credentials using `http://localhost:11434` and Qdrant credentials using `http://localhost:6333`, and assign them to the matching model, embedding, and Qdrant nodes. If the Qdrant credential form requires an API key, an arbitrary local value is sufficient because Qdrant authentication is disabled in this setup.
   - In each workflow, open the HTTP Request node and change its URL to the host API address: `http://localhost:8000/prepare` in the research workflow and `http://localhost:8000/approval` in the approval workflow. The exported files use the Compose-internal hostname `http://api:8000/...`, which a native n8n process cannot resolve.

   The exported workflows do not include configured credentials. Review any node compatibility warnings against your installed n8n version.

6. Publish the research workflow in n8n before using its production webhook. The dashboard is at [http://localhost:8000](http://localhost:8000).

If the API logs show Ollama connection errors (`docker compose logs api`), native Ollama is bound to `127.0.0.1` by default. Set `OLLAMA_HOST=0.0.0.0` for the Ollama process so the container can reach it through `host.docker.internal`, then restart Ollama.

### Environment variables

Set these in the local `.env` file copied from `.env.example`.

| Variable | Required | Purpose |
| --- | --- | --- |
| `APPROVAL_CODE` | Yes | Private local code required by the paper-order approval endpoint; generate a unique value. |
| `ALPACA_PAPER_KEY_ID` | Paper orders only | Alpaca **paper** account key ID. Leave empty for research-only use. |
| `ALPACA_PAPER_SECRET_KEY` | Paper orders only | Matching Alpaca **paper** secret key. Leave empty for research-only use. |
| `NEWSAPI_KEY` | No | Optional delayed headline feed for local development/testing only; leave empty for Yahoo fallback. |

`APPROVAL_CODE` is required by `compose.yaml` even when no paper order is planned. The API's Ollama and Qdrant service URLs are set in Compose, not in `.env`. Native n8n generates its own credential encryption key on first run, so no encryption-key variable is needed here.

## Usage

### Run research

After publishing the research workflow, send a test request to its production webhook:

```sh
curl -sS http://localhost:5678/webhook/agenttrade-analyze \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the max paper order notional?","ticker":"AAPL","mode":"agentic","model":"qwen2.5:3b","evaluation":true}'
```

`evaluation:true` accepts only AAPL or MSFT and uses frozen educational cards without fetching current prices. Run the benchmark on a clean Qdrant volume before doing live research; live cards already stored in the shared collection could contaminate agentic retrieval. Re-running `/ingest` does not delete live cards. For indicator context, use `evaluation:false`; the API fetches current Yahoo Finance data and fails closed if it is unavailable or stale. Set `mode` to `none`, `fixed`, or `agentic` to compare retrieval behavior. Inspect the n8n execution trace to confirm tool calls in agentic mode. The research form has one natural-language question box: ask "Is TSLA a good buy now?" or "What is your suggestion on Apple?" It detects uppercase tickers or common company names (Apple, Tesla, Microsoft, Nvidia, Google/Alphabet, Amazon, Meta), verifies detected tickers against live Yahoo prices, and immediately starts research without a confirmation tap. A small "Analyzing: Tesla (TSLA)" indicator shows the detected stock while the run starts. If it cannot find one stock, or finds multiple, it asks you to enter a ticker in a fallback field. A valid fallback ticker also starts research immediately. Network or stale-data errors are shown as errors, not mistaken for an unrecognized stock. The separate proposal form still requires a symbol. API clients and the evaluation harness can pass an explicit `ticker` to `/research` and `/prepare`; `/prepare` requires one. The dashboard puts the Simple summary first, then technical details. `/research` returns `simple_summary`, `technical_detail`, and the complete `answer`; if an old n8n import does not supply the required format, it shows an error rather than presenting a jargon-only answer. Re-import and publish the updated `workflows/research.json` after pulling; previous imports do not update automatically. An answer is never an order.

### Two-tier model routing

The dashboard defaults to the split setup. Analyst and critic judge use `qwen2.5:7b`; retrieval, bull, bear and bounded correction use `qwen2.5:3b`. Embeddings stay on `nomic-embed-text`. The Simple summary is produced by the analyst and final correction, not a separate model. Correction remains a 3B generation step and can affect the final answer; a larger analyst/judge is not a guarantee of better results. Measure quality and latency on your Mac before making performance claims.

Requests to `/research`, `/prepare`, or the n8n webhook may omit all model fields to use this default, or set `fast_model` and `smart_model` explicitly. Both tier fields accept `qwen2.5:3b`, `llama3.2:3b`, or `qwen2.5:7b`. A legacy `model` request runs all six chat roles on that one model (`qwen2.5:3b`, `llama3.2:3b`, or `qwen2.5:7b`). Explicit tier fields override the legacy fallback for their tier only. Returned `fast_model` and `smart_model` fields identify the resolved routing; The workflow reports `model` as `two-tier` when no legacy selection was provided (the prepare payload uses null). Unknown model names return a validation error. No model is automatically downloaded or silently substituted if unavailable.

```sh
curl -sS http://localhost:5678/webhook/agenttrade-analyze \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the max paper order notional?","ticker":"AAPL","mode":"agentic","fast_model":"qwen2.5:3b","smart_model":"qwen2.5:7b","evaluation":true}'
```

After pulling this update, run `ollama pull qwen2.5:7b` and `docker compose up -d --build`. Re-import `workflows/research.json` in n8n, reassign local credentials, set its prepare URL to `http://localhost:8000/prepare`, and publish it. Replace or unpublish the old research workflow so only one production webhook uses `agenttrade-analyze`. The old imported workflow will not gain tier routing by rebuilding Docker. The approval workflow is unchanged.

### Submit a human-approved paper order

First add `ALPACA_PAPER_KEY_ID` and `ALPACA_PAPER_SECRET_KEY` from your **paper** account to `.env`, then reload the API container:

```sh
docker compose up -d --force-recreate api
curl http://localhost:8000/snapshot/AAPL
```

Use the research dashboard at [http://localhost:8000](http://localhost:8000). The separate [portfolio page](http://localhost:8000/portfolio) shows Alpaca paper account equity, cash, buying power, current positions, a one-month broker P&L chart, and recent broker orders with filled quantities and prices. Use Refresh to reload. Without paper keys it shows setup guidance rather than invented holdings. The data endpoint is `/api/portfolio`. Neither page has login; keep it local.

To submit a proposal on the research dashboard:

1. In **New trade proposal**, type the symbol (any valid US-listed ticker), choose the side and quantity, and give a rationale. The server takes a fresh price snapshot and applies risk limits. With Alpaca paper keys configured, it checks live account status, available shares before a SELL, and buying power (with a 2% cushion) and the five-share limit before a BUY. Insufficient capacity or a failed account check returns a reason immediately and creates no pending proposal. Without keys, proposals remain local but approval cannot submit an order. A proposal is not an order.
2. In **Pending approval**, review the proposal details. The approval code is pre-filled from your local `.env` by the server; your click is the human gate. Choose **Approve** or **Reject**.
3. Approving re-runs expiry, price-move, risk and paper account capacity checks (positions or buying power can change). Broker rejection messages appear in the dashboard; check Alpaca before retrying an uncertain order. A successful approval sends a market order to `https://paper-api.alpaca.markets`. Rejecting closes the proposal. The **Ledger** section updates after each decision.

Proposals expire 30 minutes after creation. The ledger records submission, not a guaranteed fill; confirm final status in the Alpaca paper dashboard. The pre-filled code is visible to anyone who can open the local page, so keep the ports bound to `127.0.0.1` and never expose them to the internet. Never enter live account credentials.

The n8n approval form remains available as an alternative path: publish `workflows/approval.json` and open the **Production Form URL** displayed by its Form Trigger node. The same proposal IDs, expiry, and approval-code checks apply there.

You can also create a proposal from the terminal instead of the form. The example below is an API request, **not** a recommendation to trade:

```sh
curl -sS -X POST http://localhost:8000/proposal \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"AAPL","side":"BUY","quantity":1,"rationale":"Educational example only; review data and risk before simulation."}'
curl http://localhost:8000/ledger
```

### Evaluate the research workflow

From the repository root, with the research workflow published and both 3B benchmark models available:

```sh
python3 -m pip install -r requirements.txt
python3 app/evaluate.py --repeats 1
```

The evaluator deliberately sends the legacy `model` field, so each benchmark condition uses one model for all roles. It does not measure the two-tier default.

One repeat still runs 150 requests (25 questions x 3 modes x 2 models); use it to check the pipeline, not to claim final results. The full three-repeat comparison runs 450 requests and may take hours on a laptop:

```sh
python3 app/evaluate.py --repeats 3
```

Outputs are written to `results/raw.csv`, `results/summary.json`, and `results/RESULTS.md`, and the measured table replaces the evaluation section of `docs/REPORT.md`. Commit that measured report only after inspecting raw answers and n8n traces. One repeat gives no valid consistency measurement (shown as n/a). The accuracy and reasoning scores are term/citation proxies, not expert review. Check raw answers and citations manually before reporting conclusions.

### Update the automatic stock-detection UI

From your AGENTTRADE folder on Mac or Windows:

```bash
git pull
docker compose up -d --build api
```

Refresh the dashboard (hard refresh if needed). This app-side update does not change either n8n workflow: do not re-import for this change. Research starts automatically after one stock is detected; paper trading still requires explicit approval. Earlier setup instructions about workflow re-import apply only to those earlier workflow changes.

### Run the smoke tests

Offline checks for the API, risk rules, approval gate, and dashboard rendering. They use a temporary database and a fake market snapshot, so no Docker, Ollama, Qdrant, n8n, or Alpaca keys are needed:

```sh
python3 smoke_test.py
```

## Project structure

```text
AGENTTRADE/
├── app/
│   ├── dashboard.html    # Research dashboard
│   ├── portfolio.html    # Separate paper portfolio page
│   ├── evaluate.py       # Benchmark runner
│   └── main.py           # API, ingestion, risk checks, paper-order ledger
├── data/
│   ├── corpus.json       # Synthetic evidence cards
│   └── questions.json    # Frozen benchmark cases
├── docs/
│   └── REPORT.md         # Design, rubric mapping, and validity limits
├── workflows/
│   ├── approval.json     # Human approval form
│   └── research.json     # Research orchestration
├── .env.example          # Local configuration template
├── compose.yaml          # Qdrant and API services
├── Dockerfile            # API image
├── requirements.txt      # Python dependencies
├── smoke_test.py         # Offline API and dashboard checks
└── README.md
```

## Limitations and safety

- Educational and **paper-only**: any valid US-listed symbol is accepted after a live Yahoo Finance check; unknown symbols are rejected with an `Unsupported ticker` error. Alpaca paper accounts trade US-listed securities only. Do not use the output for real investment decisions.
- Live research for every requested valid symbol creates ticker-tagged, dated price, available key-statistics and up to five recent public headline cards; these are embedded and upserted into the same Qdrant collection without deleting the frozen seeds. When news is missing, price and available statistics still work; `evidence_coverage` reports the weaker coverage. The cards are refreshed on each run, not a full article or filings feed. Set optional `NEWSAPI_KEY` in `.env` for local development/testing news only; the NewsAPI free Developer plan is delayed by 24 hours, capped at 100 requests/day, and prohibited in staging/production, including internal production (https://newsapi.org/pricing). Without it, Yahoo Finance headline lookup remains the fallback. The frozen benchmark uses the original 25 AAPL/MSFT questions and needs an uncontaminated Qdrant volume for a fair agentic comparison. To add permanent classroom cards, add dated entries to `data/corpus.json` and run `/ingest`. Historical synthetic policy card 3 mentions an obsolete AAPL/MSFT-only restriction; the live API risk rules, not this old card, define the current scope.
- The evidence corpus is synthetic and cannot establish actual company news or fundamentals. Yahoo Finance data is unofficial or delayed and is not a point-in-time historical feed.
- The n8n workflow JSON was structurally checked, but the stack and workflows were **not run end to end in the build environment**. No measured benchmark results are bundled; import, credential selection, and runtime behavior require validation on your machine.
- The API has unauthenticated local endpoints; the approval endpoint requires the private code. Compose binds exposed ports to `127.0.0.1`. Do not publish them externally.
- `docker compose down` stops the containers without removing named volumes. `docker compose down -v` also deletes Qdrant data and the SQLite ledger. n8n keeps its state in its own host data directory and Ollama stores models outside Compose; neither is removed by `down -v`.

## References

- [n8n self-hosted AI starter kit](https://docs.n8n.io/deploy/host-n8n/deploy-with-the-ai-starter-kit/)
- [n8n Qdrant vector store](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.vectorstoreqdrant/)
- [n8n Tools Agent](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/tools-agent/)
- [yfinance](https://github.com/ranaroussi/yfinance)


### Local-use boundary

The dashboard is designed for one user on localhost. Do not expose it or n8n, Qdrant or Ollama publicly: research and portfolio reads have no login and the approval code is embedded in the local dashboard. Add authentication and secure secret storage before multi-user deployment. The portfolio page reads the broker's recent orders and filled quantities rather than treating ledger submissions as fills. Its chart uses Alpaca paper portfolio-history profit/loss, not a P&L reconstructed from order submissions; verify fills and cash movements at Alpaca. NewsAPI free Developer access is **not a production news license**.
