# AGENTTRADE

Local, educational AI stock research and **paper trading only** for `AAPL` and `MSFT`. No live trading or paid API. Alpaca paper API needs a free paper account. A retrieval agent chooses Qdrant searches, an analyst reasons over evidence, a critic challenges it, and one final pass corrects it. A separate human approval form gates a deterministic Alpaca paper order mirror. Do not use this to make real investment decisions.

## Mac quick start

1. Install Docker Desktop for your Mac from [Docker's official page](https://docs.docker.com/desktop/setup/install/mac-install/); start it, allow the engine to finish. You need disk space for two local models plus embedding model. Apple Silicon runs Ollama here on CPU in Docker; it can be slow. For better speed, you can run Ollama natively on macOS and point n8n/API to `host.docker.internal:11434` (requires compose edits).
2. Download `agenttrade-source.zip` from the repository, unzip it into a new `AGENTTRADE` folder, and `cd AGENTTRADE`. The repository root also contains a readme; the ZIP is the complete source bundle.
3. `cp .env.example .env`; replace `N8N_ENCRYPTION_KEY` with `python3 -c 'import secrets; print(secrets.token_hex(32))'`. Do not commit `.env`.
4. `docker compose up -d --build`; check `docker compose ps`, then `curl http://localhost:8000/health`.
5. Download models: `docker compose exec ollama ollama pull qwen2.5:3b`, `docker compose exec ollama ollama pull llama3.2:3b`, `docker compose exec ollama ollama pull nomic-embed-text`. These downloads can take many minutes. Check with `docker compose exec ollama ollama list`.
6. Register at [Alpaca](https://app.alpaca.markets/signup), open the **paper** account dashboard, create paper API key/secret, and paste them into `.env` locally as `ALPACA_PAPER_KEY_ID` and `ALPACA_PAPER_SECRET_KEY`. Do not send keys in chat, do not use live account credentials. Run `docker compose up -d --force-recreate api` after editing `.env`. The API only connects to `https://paper-api.alpaca.markets`.
7. Seed frozen educational policy cards with `curl -X POST http://localhost:8000/ingest`. The Qdrant collection `agenttrade_evidence` now holds seven dated cards. This corpus is synthetic and cannot establish real fundamentals/news.
8. Open <http://localhost:5678> and create the local n8n owner account. Import **both** `workflows/research.json` and `workflows/approval.json` using *Import from File*. Create Ollama credentials with base URL `http://ollama:11434` and Qdrant credentials with URL `http://qdrant:6333` (no API key for this local instance). Open each model and Qdrant node to select its corresponding credential. The exported credential placeholders are not secrets or preconfigured credentials. Check node parameter compatibility if your n8n version differs from the pinned image.
9. In the research workflow, publish it and send a test request:

```sh
curl -sS http://localhost:5678/webhook/agenttrade-analyze \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the max paper order notional?","ticker":"AAPL","mode":"agentic","model":"qwen2.5:3b","evaluation":true}'
```

For current indicator context use `"evaluation":false` (it fetches current Yahoo data and fails closed if unavailable or stale). `none` supplies no evidence; `fixed` supplies top-3 Qdrant hits chosen by code; `agentic` delegates Qdrant query choice to the retrieval agent. Review the n8n execution trace to verify actual Qdrant tool calls. The final answer is **not** an order.

## Human-gated simulated trade

Use `curl http://localhost:8000/snapshot/AAPL` to inspect as-of date and indicators, then create a bounded proposal, for example:

```sh
curl -sS -X POST http://localhost:8000/proposal -H 'Content-Type: application/json' \
  -d '{"ticker":"AAPL","side":"BUY","quantity":1,"rationale":"Educational example only; review live data and risk before simulation."}'
```

The API returns a proposal ID, reference price, and expiry. Review it with `curl http://localhost:8000/ledger`. Publish the approval workflow and open its Production Form URL shown by the Form Trigger node. **Only the user** enters the proposal ID and explicitly chooses `approve` or `reject`; the API rechecks expiry, price move, position/risk limits and idempotency before submitting an Alpaca **paper** market order. The mirror records the submitted Alpaca order ID, not an asserted fill; confirm fill status and P/L in the Alpaca paper dashboard. No automated analysis path can call the approval endpoint. Do not expose local ports to the internet: a local HTTP approval endpoint is not authenticated; localhost binding is essential. `docker compose down` stops services without deleting state; `docker compose down -v` irreversibly removes ledger/models/workflows.

## Evaluation

`python3 -m pip install -r requirements.txt`, then `python3 app/evaluate.py --repeats 3`. This is **450 local LLM invocations** (25 questions x 3 RAG modes x 2 models x 3 repetitions) plus critic passes, potentially many hours on a laptop. For a smoke test use `--repeats 1` and a subset of questions in a temporary copy; don't label that full evaluation. Outputs `results/raw.csv`, `results/summary.json`, `results/RESULTS.md`. Baseline prompts/model/corpus stay fixed. Accuracy is a labeled-term proxy; reasoning quality is a citation/rationale proxy, not human assessment; consistency is exact normalized answer repetition. Inspect raw output manually for citation correctness. **No measured results are supplied before a real run.** Trading returns are deliberately not substituted for QA metrics.

## Architecture and boundaries

```
client -> n8n research webhook -> Python prepare (validated mode/snapshot/fixed retrieval)
       -> Qdrant retrieval agent (tool permitted only in agentic mode)
       -> analyst -> critic -> one bounded correction -> answer
human -> n8n approval form -> Python risk recheck -> Alpaca PAPER order; SQLite receipt mirror
```

The Python service handles deterministic pricing, indicators, risk, retrieval ingestion, fixed-RAG baseline and Alpaca paper order submissions. n8n handles the three role-separated LLM agents and explicit approval UI. The initial research workflow imports as inactive. n8n credentials are selected in its UI. Data and model snapshots should be frozen for reproducibility; Yahoo Finance is unofficial/delayed and cannot safely represent point-in-time historical research by itself. See `docs/REPORT.md` for rubric mapping and limitations.

## Sources

- [n8n self-hosted AI starter kit](https://docs.n8n.io/deploy/host-n8n/deploy-with-the-ai-starter-kit/)
- [n8n Qdrant tool mode](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.vectorstoreqdrant/)
- [n8n agent tool calling](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/tools-agent/)
- [yfinance](https://github.com/ranaroussi/yfinance)
