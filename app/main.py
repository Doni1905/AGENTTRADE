"""Deterministic market data, retrieval ingestion and Alpaca paper-only orders."""
import os, json, sqlite3, time, hashlib, math, re, secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
import httpx
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app = FastAPI(title="AGENTTRADE deterministic service", version="1.0")
DB = os.getenv("DATABASE_PATH", "/tmp/agenttrade.sqlite3")
OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434")
QDRANT = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = "agenttrade_evidence"
ALLOWED = {"AAPL", "MSFT"}
CORPUS = Path(__file__).resolve().parent.parent / "data" / "corpus.json"


def conn():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, ticker TEXT, side TEXT, qty INTEGER, price REAL, rationale TEXT, created TEXT, status TEXT DEFAULT 'pending', reason TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT UNIQUE, alpaca_order_id TEXT, ticker TEXT, side TEXT, qty INTEGER, price REAL, created TEXT)")
    c.commit()
    return c


class Proposal(BaseModel):
    ticker: str
    side: Literal["BUY", "SELL", "HOLD"]
    quantity: int = Field(ge=0, le=10000)
    rationale: str = Field(min_length=10, max_length=2000)
    # Market snapshot computed by server; incoming AI price is ignored.

class Approval(BaseModel):
    proposal_id: str
    decision: Literal["approve", "reject"]
    approval_code: str = ""


def price_data(ticker: str):
    if ticker not in ALLOWED:
        raise HTTPException(400, f"Supported tickers: {sorted(ALLOWED)}")
    try:
        df = yf.download(ticker, period="6mo", interval="1d", progress=False, auto_adjust=True, threads=False, timeout=15)
        if df.empty or len(df) < 30:
            raise ValueError("at least 30 recent daily closes are required")
        close = df["Close"]
        if hasattr(close, "columns"): close = close.iloc[:, 0]
        prices = [float(v) for v in close.dropna().tolist()]
        if len(prices) < 30: raise ValueError("insufficient valid closes")
        last_date = df.index[-1].date().isoformat()
        if (datetime.now(timezone.utc).date() - datetime.fromisoformat(last_date).date()).days > 7:
            raise ValueError("latest daily close is older than seven calendar days")
        deltas = close.diff().dropna(); gains = deltas.clip(lower=0).ewm(alpha=1/14, adjust=False).mean(); losses = (-deltas.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
        loss = float(losses.iloc[-1]); gain = float(gains.iloc[-1]); rsi = 100.0 if loss == 0 and gain > 0 else (50.0 if loss == 0 else 100-100/(1+gain/loss))
        ema12 = close.ewm(span=12, adjust=False).mean(); ema26 = close.ewm(span=26, adjust=False).mean(); macd = ema12-ema26
        return {"ticker":ticker,"as_of":last_date,"retrieved_at":datetime.now(timezone.utc).isoformat(),"currency":"USD", "price":round(prices[-1],2),"sma20":round(sum(prices[-20:])/20,2),"sma50":round(sum(prices[-50:])/50,2) if len(prices)>=50 else None,"rsi14":round(rsi,2),"macd":round(float(macd.iloc[-1]),3),"signal_line":round(float(macd.ewm(span=9,adjust=False).mean().iloc[-1]),3),"data_source":"Yahoo Finance via yfinance; delayed/unofficial, educational use only"}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(503, f"Fresh market data unavailable; trading blocked: {exc}") from exc

@app.get("/",response_class=HTMLResponse)
def dashboard(): return (Path(__file__).parent/"dashboard.html").read_text()

@app.get("/health")
def health(): return {"status":"ok","allowed_tickers":sorted(ALLOWED)}

@app.get("/snapshot/{ticker}")
def snapshot(ticker: str): return price_data(ticker.upper())


def risk(ticker, side, qty, price, db=None):
    if ticker not in ALLOWED: return ["unsupported ticker"]
    if side not in ("BUY", "SELL", "HOLD"): return ["invalid side"]
    if side == "HOLD": return ["HOLD is not an order"]
    errors=[]
    if qty < 1: errors.append("quantity must be positive")
    if not math.isfinite(price) or price <= 0: errors.append("invalid price")
    if qty*price > 1000: errors.append("max order notional USD 1,000")
    if qty > 5: errors.append("max 5 shares per order")
    c = db or conn()
    try:
        bought=c.execute("SELECT COALESCE(SUM(CASE WHEN side='BUY' THEN qty ELSE -qty END),0) FROM trades WHERE ticker=?",(ticker,)).fetchone()[0]
        # Actual holdings are checked against Alpaca at approval, not this local mirror.
        # Alpaca is authoritative for positions; local mirror may lag and is not a risk gate.
    finally:
        if db is None: c.close()
    return errors

@app.post("/proposal")
def create_proposal(p:Proposal):
    ticker=p.ticker.upper(); market=price_data(ticker)
    errors=risk(ticker,p.side,p.quantity,market["price"])
    if errors: raise HTTPException(422,{"risk_errors":errors})
    now=datetime.now(timezone.utc).isoformat()
    digest=hashlib.sha256(f"{now}|{ticker}|{p.side}|{p.quantity}".encode()).hexdigest()[:16]
    with conn() as c:
        c.execute("INSERT INTO proposals(id,ticker,side,qty,price,rationale,created) VALUES(?,?,?,?,?,?,?)",(digest,ticker,p.side,p.quantity,market["price"],p.rationale,now))
    return {"proposal_id":digest,"status":"pending_human_approval","ticker":ticker,"side":p.side,"quantity":p.quantity,"reference_price":market["price"],"as_of":market["as_of"],"rationale":p.rationale,"expires_minutes":30,"paper_only":True}

def alpaca_headers():
    key=os.getenv("ALPACA_PAPER_KEY_ID", "")
    secret=os.getenv("ALPACA_PAPER_SECRET_KEY", "")
    if not key or not secret: raise HTTPException(503,"Alpaca paper keys not configured; no order placed")
    return {"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret}

def alpaca_get(client,path,headers):
    r=client.get("https://paper-api.alpaca.markets"+path,headers=headers)
    if r.status_code>=400: raise HTTPException(503,f"Alpaca paper API status {r.status_code}; no local execution asserted")
    return r.json()

@app.post("/approval")
def approve(a:Approval):
    with conn() as c:
        row=c.execute("SELECT * FROM proposals WHERE id=?",(a.proposal_id,)).fetchone()
    if not row: raise HTTPException(404,"unknown proposal")
    if row["status"] != "pending": return {"proposal_id":a.proposal_id,"status":row["status"],"idempotent":True}
    if (datetime.now(timezone.utc)-datetime.fromisoformat(row["created"])).total_seconds()>1800:
        with conn() as c: c.execute("UPDATE proposals SET status='expired' WHERE id=? AND status='pending'",(a.proposal_id,))
        raise HTTPException(409,"proposal expired")
    code=os.getenv("APPROVAL_CODE", "")
    if not code or not secrets.compare_digest(a.approval_code,code): raise HTTPException(403,"Approval code required")
    if a.decision == "reject":
        with conn() as c: c.execute("UPDATE proposals SET status='rejected' WHERE id=? AND status='pending'",(a.proposal_id,))
        return {"proposal_id":a.proposal_id,"status":"rejected"}
    market=price_data(row["ticker"])
    if abs(market["price"]-row["price"])/row["price"] > 0.02:
        raise HTTPException(409,"reference price moved more than 2%; request a new proposal")
    errors=risk(row["ticker"],row["side"],row["qty"],market["price"])
    if errors: raise HTTPException(409,{"risk_errors":errors})
    headers=alpaca_headers()
    # Use Alpaca's paper endpoint only; client_order_id enables reconciliation on retries.
    with httpx.Client(timeout=25) as client:
        account=alpaca_get(client,"/v2/account",headers)
        if account.get("status") != "ACTIVE": raise HTTPException(409,"Alpaca paper account not active")
        if row["side"] == "BUY" and float(account.get("buying_power",0)) < row["qty"]*market["price"]*1.02:
            raise HTTPException(409,"insufficient Alpaca paper buying power")
        positions=alpaca_get(client,"/v2/positions",headers)
        held=next((float(x.get("qty_available",x.get("qty",0))) for x in positions if x.get("symbol")==row["ticker"]),0)
        if row["side"] == "SELL" and held < row["qty"]: raise HTTPException(409,"insufficient Alpaca paper shares")
        if row["side"] == "BUY" and held + row["qty"] > 5: raise HTTPException(409,"Alpaca paper position would exceed five shares")
        order={"symbol":row["ticker"],"qty":str(row["qty"]),"side":row["side"].lower(),"type":"market","time_in_force":"day","client_order_id":"agenttrade-"+a.proposal_id}
        prior=client.get("https://paper-api.alpaca.markets/v2/orders:by_client_order_id",headers=headers,params={"client_order_id":order["client_order_id"]})
        if prior.status_code == 200: response=prior
        elif prior.status_code == 404: response=client.post("https://paper-api.alpaca.markets/v2/orders",headers=headers,json=order)
        else: raise HTTPException(503,"Unable to reconcile paper order status; check Alpaca dashboard")
        if response.status_code not in (200,201):
            # A timeout or conflict may mean the order did land; reconcile via Alpaca order ID before retrying.
            if response.status_code==422:
                check=client.get("https://paper-api.alpaca.markets/v2/orders:by_client_order_id",headers=headers,params={"client_order_id":order["client_order_id"]})
                if check.status_code==200: response=check
                else: raise HTTPException(409,"Alpaca rejected order; check Alpaca dashboard before retrying")
            else: raise HTTPException(503,f"Alpaca order status {response.status_code}; check dashboard before retrying")
        receipt=response.json()
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        c.execute("INSERT OR IGNORE INTO trades(proposal_id,alpaca_order_id,ticker,side,qty,price,created) VALUES(?,?,?,?,?,?,?)",(a.proposal_id,receipt.get("id"),row["ticker"],row["side"],row["qty"],market["price"],datetime.now(timezone.utc).isoformat()))
        c.execute("UPDATE proposals SET status='submitted_to_alpaca' WHERE id=?",(a.proposal_id,))
    return {"proposal_id":a.proposal_id,"status":"submitted_to_alpaca","paper_only":True,"alpaca_order_id":receipt.get("id"),"alpaca_status":receipt.get("status"),"reference_price":market["price"],"note":"Order may not be filled; check Alpaca paper dashboard."}

@app.get("/ledger")
def ledger():
    with conn() as c: return {"trades":[dict(x) for x in c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 100")],"proposals":[dict(x) for x in c.execute("SELECT * FROM proposals ORDER BY created DESC LIMIT 100")]}

@app.get("/corpus")
def corpus(): return json.loads(CORPUS.read_text())

@app.post("/ingest")
def ingest():
    docs=json.loads(CORPUS.read_text()); vectors=[]
    with httpx.Client(timeout=60) as client:
        for d in docs:
            res=client.post(OLLAMA+"/api/embeddings",json={"model":"nomic-embed-text","prompt":d["text"]});res.raise_for_status()
            vector=res.json()["embedding"]
            vectors.append({"id":int(d["id"]),"vector":vector,"payload":{"content":d["text"],"metadata":{"source":d["source"],"published_at":d["published_at"],"doc_id":d["id"]}}})
        r=client.put(QDRANT+f"/collections/{COLLECTION}",json={"vectors":{"size":len(vectors[0]["vector"]),"distance":"Cosine"}})
        if r.status_code not in (200,409): r.raise_for_status()
        r=client.put(QDRANT+f"/collections/{COLLECTION}/points?wait=true",json={"points":vectors});r.raise_for_status()
    return {"ingested":len(vectors),"collection":COLLECTION}

@app.get("/fixed-rag")
def fixed_rag(question:str):
    with httpx.Client(timeout=45) as client:
        r=client.post(OLLAMA+"/api/embeddings",json={"model":"nomic-embed-text","prompt":question});r.raise_for_status()
        s=client.post(QDRANT+f"/collections/{COLLECTION}/points/search",json={"vector":r.json()["embedding"],"limit":3,"with_payload":True});s.raise_for_status()
    return {"evidence":[{"text":x["payload"]["content"],**x["payload"]["metadata"]} for x in s.json()["result"]]}

class AnalysisInput(BaseModel):
    question: str = Field(min_length=5,max_length=1000)
    ticker: str = "AAPL"
    model: Literal["qwen2.5:3b","llama3.2:3b"] = "qwen2.5:3b"
    mode: Literal["none","fixed","agentic"] = "agentic"
    evaluation: bool = False

@app.post("/prepare")
def prepare(p:AnalysisInput):
    # Evaluation uses only frozen dated source cards to avoid changing answers and future leakage.
    ticker=p.ticker.upper()
    if ticker not in ALLOWED: raise HTTPException(400,"unsupported ticker")
    market=None if p.evaluation else price_data(ticker)
    evidence=[] if p.mode != 'fixed' else fixed_rag(p.question)['evidence']
    return {**p.model_dump(),"snapshot":market,"fixed_evidence":evidence,
            "retrieval_instruction":("DO NOT use the Qdrant tool. No external evidence is available." if p.mode=='none' else
            "DO NOT use the Qdrant tool; only use fixed_evidence supplied here." if p.mode=='fixed' else
            "You MUST choose and call the Qdrant retrieval tool with a query you formulate; inspect the returned source metadata and cite doc IDs. You may reformulate and call again if evidence is insufficient."),
            "warning":"Synthetic corpus provides policy facts only; do not treat these as current financial fundamentals or news."}

@app.post("/research")
def research(p:AnalysisInput):
    try:
        with httpx.Client(timeout=300) as client:
            r=client.post("http://n8n:5678/webhook/agenttrade-analyze",json=p.model_dump())
            r.raise_for_status()
            return r.json()
    except Exception as exc: raise HTTPException(503,f"Local research workflow unavailable: {str(exc)[:140]}")
