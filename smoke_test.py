"""Offline smoke tests for the AGENTTRADE API and dashboard.

Run from the repository root:

    python3 smoke_test.py          # Mac
    python smoke_test.py           # Windows

Uses a temporary SQLite database and a fake market snapshot, so no
network, Docker, Ollama, Qdrant, n8n, or Alpaca keys are required.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

os.environ["DATABASE_PATH"] = tempfile.mktemp(prefix="agenttrade-smoke-", suffix=".sqlite3")
os.environ["APPROVAL_CODE"] = "smoke-test-code"
os.environ.pop("ALPACA_PAPER_KEY_ID", None)
os.environ.pop("ALPACA_PAPER_SECRET_KEY", None)

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FAKE_SNAPSHOT = {
    "ticker": "AAPL", "as_of": "2026-09-28", "retrieved_at": "2026-09-29T00:00:00+00:00",
    "currency": "USD", "price": 250.0, "sma20": 248.0, "sma50": 240.0,
    "rsi14": 55.0, "macd": 1.2, "signal_line": 1.0, "data_source": "smoke test fake",
}
def _fake_price_data(ticker):
    # Mirrors the real checks: malformed symbols fail offline; unknown symbols would
    # fail against live market data, which these tests never touch.
    if not main.check_symbol_format(ticker):
        raise main.unsupported_ticker(ticker)
    return {**FAKE_SNAPSHOT, "ticker": ticker}


main.price_data = _fake_price_data

client = TestClient(main.app)
failures = []


def check(name, condition):
    print(("PASS" if condition else "FAIL"), "-", name)
    if not condition:
        failures.append(name)


r = client.get("/health")
check("health endpoint", r.status_code == 200 and r.json()["status"] == "ok")
check("health reports seeded corpus", r.json()["seeded_corpus_tickers"] == ["AAPL", "MSFT"])

r = client.get("/")
check("dashboard renders", r.status_code == 200 and "Pending approval" in r.text)
check("approval code injected into dashboard", "smoke-test-code" in r.text)

bad = client.post("/proposal", json={"ticker": "TSLA!", "side": "BUY", "quantity": 1, "rationale": "malformed symbol test"})
check("malformed symbol rejected", bad.status_code == 400)

r = client.post("/proposal", json={"ticker": "TSLA", "side": "BUY", "quantity": 1, "rationale": "valid ticker outside the seeded corpus"})
check("valid non-seeded ticker accepted", r.status_code == 200 and r.json()["ticker"] == "TSLA")

r = client.post("/prepare", json={"question": "What is the max paper order notional?", "ticker": "TSLA", "evaluation": True})
check("prepare flags unseeded ticker", r.status_code == 200 and r.json()["ticker_seeded_in_corpus"] is False and "No seeded evidence cards" in r.json()["warning"])

r = client.post("/prepare", json={"question": "What is the max paper order notional?", "ticker": "AAPL", "evaluation": True})
check("prepare flags seeded ticker", r.status_code == 200 and r.json()["ticker_seeded_in_corpus"] is True)

bad = client.post("/proposal", json={"ticker": "AAPL", "side": "BUY", "quantity": 10, "rationale": "too many shares for the limit"})
check("risk limit rejects 10 shares", bad.status_code == 422)

r = client.post("/proposal", json={"ticker": "AAPL", "side": "BUY", "quantity": 1, "rationale": "smoke test proposal one"})
check("proposal created", r.status_code == 200 and r.json()["status"] == "pending_human_approval")
pid1 = r.json().get("proposal_id", "")

r = client.post("/approval", json={"proposal_id": pid1, "decision": "approve", "approval_code": "wrong"})
check("wrong approval code rejected", r.status_code == 403)

r = client.post("/approval", json={"proposal_id": pid1, "decision": "reject", "approval_code": "smoke-test-code"})
check("reject works with code", r.status_code == 200 and r.json()["status"] == "rejected")

r = client.post("/approval", json={"proposal_id": pid1, "decision": "approve", "approval_code": "smoke-test-code"})
check("decision is idempotent after reject", r.status_code == 200 and r.json().get("idempotent"))

r = client.post("/proposal", json={"ticker": "MSFT", "side": "BUY", "quantity": 1, "rationale": "smoke test proposal two"})
pid2 = r.json().get("proposal_id", "")
r = client.post("/approval", json={"proposal_id": pid2, "decision": "approve", "approval_code": "smoke-test-code"})
check("approve without Alpaca keys places no order", r.status_code == 503)

r = client.get("/ledger")
body = r.json()
check("ledger lists proposals", r.status_code == 200 and len(body["proposals"]) >= 2)
check("ledger has no trades after failed approval", len(body["trades"]) == 0)

if failures:
    print(f"\n{len(failures)} check(s) failed")
    sys.exit(1)
print("\nAll smoke checks passed.")
