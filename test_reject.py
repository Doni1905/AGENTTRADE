import sys
from pathlib import Path
import tempfile
import os

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
os.environ["DATABASE_PATH"] = tempfile.mktemp(prefix="agenttrade-smoke-", suffix=".sqlite3")
os.environ["APPROVAL_CODE"] = "smoke-test-code"

import main
from fastapi.testclient import TestClient

client = TestClient(main.app)

main.alpaca_headers = lambda u="", p="": {"APCA-API-KEY-ID": "fake", "APCA-API-SECRET-KEY": "fake"}
main.alpaca_get = lambda client, url, headers: {"buying_power": "100000", "status": "ACTIVE"} if "account" in url else []

r = client.post("/proposal", json={"ticker": "AAPL", "side": "BUY", "quantity": 1, "rationale": "smoke test proposal one"})
pid1 = r.json()["proposal_id"]

r = client.post("/approval", json={"proposal_id": pid1, "decision": "reject", "approval_code": "smoke-test-code"})
print("STATUS:", r.status_code)
print("BODY:", r.json())
