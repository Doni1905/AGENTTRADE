# AGENTTRADE

AGENTTRADE is a local stock-research prototype for `AAPL` and `MSFT`. It combines n8n workflows, local Ollama models, Qdrant retrieval, and a Python API to compare research approaches and submit **paper-only** orders through Alpaca after explicit human approval. It is an educational project, not an investment adviser or a live-trading system.

## Features

- Three research modes: no retrieval (`none`), fixed top-3 retrieval (`fixed`), and agent-selected Qdrant retrieval (`agentic`).
- Separate retrieval, analyst, and critic roles, followed by one bounded correction pass.
- Local models: `qwen2.5:3b` and `llama3.2:3b`; `nomic-embed-text` for embeddings.
- Python-calculated market indicators and deterministic proposal/risk checks. Research output cannot place an order.
- A separate n8n approval form for Alpaca paper orders, with a local approval code, proposal expiry, and duplicate-order checks.
- A 25-question benchmark comparing three retrieval modes across both models; raw responses and summary scores are written locally.

## Architecture

```text
Research request -> n8n research workflow -> Python API (prepare, data, fixed retrieval)
                                        |-> Qdrant + Ollama: retrieval agent (agentic mode)
                                        |-> Ollama: analyst -> critic -> one correction -> answer

Human -> n8n approval form -> Python API (risk recheck, SQLite ledger)
                           -> Alpaca paper API (order submission only)
```

Docker Compose runs four local services: `n8n` (workflow orchestration), `ollama` (models), `qdrant` (evidence store), and `api` (FastAPI dashboard, market data, risk rules, and ledger). The research workflow does not have an order-submission path. See [the project report](docs/REPORT.md) for the design and evaluation limits.

## Prerequisites

- [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/), started with its engine running, or a working Docker Engine with Compose on another platform.
- Git and Python 3 on the host; `curl` for the examples below.
- Enough disk space for two language models and an embedding model. Model downloads can take several minutes. Docker-hosted Ollama can be slower on a Mac than a native Metal-backed installation; switching to native Ollama requires changing the service URLs in Compose and n8n.
- Access to this private repository. An [Alpaca paper account](https://app.alpaca.markets/signup) is needed **only** to submit paper orders; research and evaluation do not need Alpaca keys.

## Quick start

Run these commands from a terminal on the machine hosting Docker.

1. Clone the repository and create your local environment file:

   ```sh
   git clone https://github.com/Doni1905/AGENTTRADE.git
   cd AGENTTRADE
   cp .env.example .env
   ```

   In `.env`, replace `N8N_ENCRYPTION_KEY` and `APPROVAL_CODE` with **different** random values. Run the following command twice, then put one result in each field. Do not commit `.env` or share the values.

   ```sh
   python3 -c 'import secrets; print(secrets.token_hex(32))'
   ```

2. Build and start the four services, then check the API:

   ```sh
   docker compose up -d --build
   docker compose ps
   curl http://localhost:8000/health
   ```

3. Download the required models into the Ollama container:

   ```sh
   docker compose exec ollama ollama pull qwen2.5:3b
   docker compose exec ollama ollama pull llama3.2:3b
   docker compose exec ollama ollama pull nomic-embed-text
   docker compose exec ollama ollama list
   ```

4. Ingest the included synthetic evidence cards into Qdrant:

   ```sh
   curl -X POST http://localhost:8000/ingest
   ```

5. Open [n8n](http://localhost:5678) and create its local owner account. Use **Import from File** to import both `workflows/research.json` and `workflows/approval.json`. Create Ollama credentials using `http://ollama:11434` and Qdrant credentials using `http://qdrant:6333`, then assign them to the matching model and Qdrant nodes. If the Qdrant credential form requires an API key, an arbitrary local value is sufficient for this Compose setup because Qdrant authentication is disabled. The exported workflows do not include configured credentials. Review any node compatibility warnings against the pinned n8n version in `compose.yaml`.

6. Publish the research workflow in n8n before using its production webhook. The dashboard is at [http://localhost:8000](http://localhost:8000).

### Environment variables

Set these in the local `.env` file copied from `.env.example`.

| Variable | Required | Purpose |
| --- | --- | --- |
| `N8N_ENCRYPTION_KEY` | Yes | Encrypts local n8n credentials; generate a unique value. |
| `APPROVAL_CODE` | Yes | Private local code required by the paper-order approval endpoint; generate a separate value. |
| `ALPACA_PAPER_KEY_ID` | Paper orders only | Alpaca **paper** account key ID. Leave empty for research-only use. |
| `ALPACA_PAPER_SECRET_KEY` | Paper orders only | Matching Alpaca **paper** secret key. Leave empty for research-only use. |

The first two variables are required by `compose.yaml` even when no paper order is planned. The API's Ollama and Qdrant service URLs are set in Compose, not in `.env`.

## Usage

### Run research

After publishing the research workflow, send a test request to its production webhook:

```sh
curl -sS http://localhost:5678/webhook/agenttrade-analyze \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the max paper order notional?","ticker":"AAPL","mode":"agentic","model":"qwen2.5:3b","evaluation":true}'
```

`evaluation:true` uses the frozen educational corpus without fetching current prices. For indicator context, use `evaluation:false`; the API fetches current Yahoo Finance data and fails closed if it is unavailable or stale. Set `mode` to `none`, `fixed`, or `agentic` to compare retrieval behavior. Inspect the n8n execution trace to confirm tool calls in agentic mode. An answer is never an order.

### Submit a human-approved paper order

First add `ALPACA_PAPER_KEY_ID` and `ALPACA_PAPER_SECRET_KEY` from your **paper** account to `.env`, then reload the API container:

```sh
docker compose up -d --force-recreate api
curl http://localhost:8000/snapshot/AAPL
```

Create a proposal only after checking the data and risk. The example below is an API request, **not** a recommendation to trade:

```sh
curl -sS -X POST http://localhost:8000/proposal \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"AAPL","side":"BUY","quantity":1,"rationale":"Educational example only; review data and risk before simulation."}'
curl http://localhost:8000/ledger
```

Publish `workflows/approval.json` in n8n and open the **Production Form URL** displayed by its Form Trigger node. Review the returned proposal ID and details in the ledger; the human operator enters the ID, chooses `approve` or `reject`, and supplies the private approval code. Approval triggers another expiry, price-move, and risk check before a market order is sent to `https://paper-api.alpaca.markets`. The ledger records submission, not a guaranteed fill. Confirm final status in the Alpaca paper dashboard. Never enter live account credentials or expose these localhost ports to the internet.

### Evaluate the research workflow

From the repository root, with the research workflow published and both models available:

```sh
python3 -m pip install -r requirements.txt
python3 app/evaluate.py --repeats 1
```

One repeat still runs 150 requests (25 questions × 3 modes × 2 models); use it to check the pipeline, not to claim final results. The full three-repeat comparison runs 450 requests and may take hours on a laptop:

```sh
python3 app/evaluate.py --repeats 3
```

Outputs are written to `results/raw.csv`, `results/summary.json`, and `results/RESULTS.md`. The accuracy and reasoning scores are term/citation proxies, not expert review. Check raw answers and citations manually before reporting conclusions.

## Project structure

```text
AGENTTRADE/
├── app/
│   ├── dashboard.html    # Research dashboard
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
├── compose.yaml          # Four-service stack
├── Dockerfile            # API image
├── requirements.txt      # Python dependencies
└── README.md
```

## Limitations and safety

- Educational and **paper-only**: supported symbols are `AAPL` and `MSFT`. Do not use the output for real investment decisions.
- The evidence corpus is synthetic and cannot establish actual company news or fundamentals. Yahoo Finance data is unofficial or delayed and is not a point-in-time historical feed.
- The n8n workflow JSON was structurally checked, but the stack and workflows were **not run end to end in the build environment**. No measured benchmark results are bundled; import, credential selection, and runtime behavior require validation on your machine.
- The API has unauthenticated local endpoints; the approval endpoint requires the private code. Compose binds exposed ports to `127.0.0.1`. Do not publish them externally.
- `docker compose down` stops the stack without removing named volumes. `docker compose down -v` also deletes saved n8n state, Ollama models, Qdrant data, and the SQLite ledger.

## References

- [n8n self-hosted AI starter kit](https://docs.n8n.io/deploy/host-n8n/deploy-with-the-ai-starter-kit/)
- [n8n Qdrant vector store](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.vectorstoreqdrant/)
- [n8n Tools Agent](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/tools-agent/)
- [yfinance](https://github.com/ranaroussi/yfinance)
