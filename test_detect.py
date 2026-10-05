import sys
from pathlib import Path
import tempfile
import os

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
os.environ["DATABASE_PATH"] = tempfile.mktemp(prefix="agenttrade-smoke-", suffix=".sqlite3")

import main
from fastapi.testclient import TestClient

client = TestClient(main.app)
r = client.post('/detect-stock', json={"question":"What should I buy?"})
print("STATUS:", r.status_code)
print("BODY:", r.json())
