import sys, tempfile, json
from pathlib import Path
import os
import httpx

ROOT = Path('/Users/doni/.gemini/antigravity-ide/scratch/AGENTTRADE')
sys.path.insert(0, str(ROOT / "app"))
os.environ["DATABASE_PATH"] = tempfile.mktemp(prefix="agenttrade-smoke-", suffix=".sqlite3")

import main
from fastapi.testclient import TestClient
client = TestClient(main.app)

class FakePaperResponse:
    def __init__(self,status,body):self.status_code=status;self.body=body
    def json(self):return self.body
    def raise_for_status(self):
        if self.status_code!=200: raise Exception("fake error")

class PortfolioClient:
    def __init__(self,**kwargs):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def get(self,url,**kwargs):
        print("MOCK GET URL:", url)
        if '/v2/account' in url and '/portfolio/history' not in url:return FakePaperResponse(200,{"cash":"800"})
        if '/v2/positions' in url:return FakePaperResponse(200,[{"symbol":"AAPL","qty":"1","market_value":"250","unrealized_pl":"42"}])
        if '/portfolio/history' in url:return FakePaperResponse(200,{"timestamp":[1,2],"profit_loss":[0,42],"equity":[800,842]})
        if '/v2/orders?' in url:return FakePaperResponse(200,[{"symbol":"AAPL","side":"buy","qty":"2","filled_qty":"2","status":"filled","submitted_at":"2026-09-29T09:00:00Z","filled_at":"2026-09-29T09:01:00Z","filled_avg_price":"250"}])
        print("RAISING ASSERTION ERROR")
        raise AssertionError(url)

main.httpx.Client = PortfolioClient
os.environ['ALPACA_PAPER_KEY_ID']='stub-paper-key'
os.environ['ALPACA_PAPER_SECRET_KEY']='stub-paper-secret'

try:
    r = client.get('/api/portfolio')
    print("STATUS:", r.status_code)
    print("BODY:", r.json())
except Exception as e:
    import traceback
    traceback.print_exc()

