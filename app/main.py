"""Deterministic market data, retrieval ingestion and Alpaca paper-only orders."""
import os, json, sqlite3, time, hashlib, math, re, secrets, threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
import httpx
import yfinance as yf
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app = FastAPI(title="AGENTTRADE deterministic service", version="1.3")
DB = os.getenv("DATABASE_PATH", "/tmp/agenttrade.sqlite3")
OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434")
QDRANT = os.getenv("QDRANT_URL", "http://localhost:6333")
# n8n runs natively on the host; the container reaches it via host.docker.internal.
N8N = os.getenv("N8N_URL", "http://host.docker.internal:5678")
COLLECTION = "agenttrade_evidence"
_APPROVAL_LOCK = threading.Lock()
# No fixed ticker whitelist. Symbols are checked by format here and confirmed against
# live Yahoo Finance data in price_data, so any US-listed symbol can be researched
# and paper-traded (Alpaca paper accounts support US-listed securities only).
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
# The frozen synthetic evidence corpus is seeded for these two tickers only.
SEEDED_CORPUS_TICKERS = {"AAPL", "MSFT"}
CORPUS = Path(__file__).resolve().parent.parent / "data" / "corpus.json"


def check_symbol_format(ticker: str) -> bool:
    return bool(SYMBOL_RE.fullmatch(ticker))


def unsupported_ticker(ticker: str) -> HTTPException:
    return HTTPException(400, f"Unsupported ticker '{ticker}'. Provide a valid US-listed symbol, for example AAPL, TSLA or NVDA.")


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
    if not check_symbol_format(ticker):
        raise unsupported_ticker(ticker)
    try:
        df = yf.download(ticker, period="6mo", interval="1d", progress=False, auto_adjust=True, threads=False, timeout=15)
        if df.empty:
            # Yahoo Finance returns no rows for unknown or delisted symbols.
            raise unsupported_ticker(ticker)
        if len(df) < 30:
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
        return {"ticker":ticker,"as_of":last_date,"retrieved_at":datetime.now(timezone.utc).isoformat(),"currency":"USD", "price":round(prices[-1],2),"recent_closes": [round(v,2) for v in prices[-5:]],"sma20":round(sum(prices[-20:])/20,2),"sma50":round(sum(prices[-50:])/50,2) if len(prices)>=50 else None,"rsi14":round(rsi,2),"macd":round(float(macd.iloc[-1]),3),"signal_line":round(float(macd.ewm(span=9,adjust=False).mean().iloc[-1]),3),"data_source":"Yahoo Finance via yfinance; delayed/unofficial, educational use only"}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(503, f"Fresh market data unavailable; trading blocked: {exc}") from exc

@app.get("/",response_class=HTMLResponse)
def dashboard():
    # The approval code is injected so the local dashboard can pre-fill it; the page is bound to localhost only.
    html=(Path(__file__).parent/"dashboard.html").read_text()
    return html.replace("__APPROVAL_CODE__", os.getenv("APPROVAL_CODE",""))

@app.get("/health")
def health(): return {"status":"ok","symbol_universe":"any valid US-listed symbol, validated live via Yahoo Finance","seeded_corpus_tickers":sorted(SEEDED_CORPUS_TICKERS)}

@app.get("/snapshot/{ticker}")
def snapshot(ticker: str): return price_data(ticker.upper())


def risk(ticker, side, qty, price, db=None):
    if not check_symbol_format(ticker): return ["unsupported ticker"]
    if side not in ("BUY", "SELL", "HOLD"): return ["invalid side"]
    if side == "HOLD": return ["HOLD is not an order"]
    errors=[]
    if qty < 1: errors.append("quantity must be positive")
    if not math.isfinite(price) or price <= 0: return errors+["invalid price"]
    if qty*price > 1000: errors.append("max order notional USD 1,000")
    if qty > 5: errors.append("max 5 shares per order")
    return errors

@app.post("/proposal")
def create_proposal(p:Proposal):
    ticker=p.ticker.upper(); market=price_data(ticker)
    errors=risk(ticker,p.side,p.quantity,market["price"])
    if errors: raise HTTPException(422,{"risk_errors":errors})
    # Fail closed on a configured paper account before persisting a proposal.
    if os.getenv("ALPACA_PAPER_KEY_ID") or os.getenv("ALPACA_PAPER_SECRET_KEY"):
        headers=alpaca_headers()
        with httpx.Client(timeout=25) as client:
            account=alpaca_get(client,"/v2/account",headers)
            positions=alpaca_get(client,"/v2/positions",headers)
            check_paper_capacity(ticker,p.side,p.quantity,market["price"],account,positions)
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

def check_paper_capacity(ticker,side,qty,price,account,positions):
    if not isinstance(account,dict) or not isinstance(positions,list):
        raise HTTPException(503,"Alpaca paper account state unavailable; no proposal created")
    if account.get("status") != "ACTIVE": raise HTTPException(409,"Alpaca paper account not active")
    try:
        matches=[x for x in positions if isinstance(x,dict) and x.get("symbol")==ticker]
        held=sum(float(x.get("qty_available",x.get("qty"))) for x in matches)
        if not math.isfinite(held) or held < 0: raise ValueError()
    except (TypeError,ValueError) as exc:
        raise HTTPException(503,"Alpaca paper position unavailable; no proposal created") from exc
    if side == "SELL" and held < qty:
        raise HTTPException(409,f"You hold {held:g} available {ticker} paper shares - cannot sell {qty}")
    if side == "BUY":
        try:
            buying_power=float(account["buying_power"])
            if not math.isfinite(buying_power) or buying_power < 0: raise ValueError()
        except (KeyError,TypeError,ValueError) as exc:
            raise HTTPException(503,"Alpaca paper buying power unavailable; no proposal created") from exc
        required=qty*price*1.02
        if buying_power < required:
            raise HTTPException(409,f"Insufficient Alpaca paper buying power: ${buying_power:,.2f} available; ${required:,.2f} needed including 2% price cushion")
        if held + qty > 5:
            raise HTTPException(409,f"Alpaca paper position would exceed five shares: {held:g} available {ticker} + {qty} proposed")


def broker_error(response):
    try:
        body=response.json()
        if isinstance(body,dict) and isinstance(body.get("message"),str): return body["message"][:500]
    except (ValueError,TypeError): pass
    return f"HTTP {response.status_code} (no broker message available)"


def alpaca_get(client,path,headers):
    r=client.get("https://paper-api.alpaca.markets"+path,headers=headers)
    if r.status_code>=400: raise HTTPException(503,f"Alpaca paper account check failed: {broker_error(r)}; no local execution asserted")
    return r.json()

@app.post("/approval")
def approve(a:Approval):
    # Serialize approval requests in this process; Alpaca client order IDs cover retries.
    with _APPROVAL_LOCK:
        return _approve_locked(a)

def _approve_locked(a:Approval):
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
    headers=alpaca_headers()
    market=price_data(row["ticker"])
    if abs(market["price"]-row["price"])/row["price"] > 0.02:
        raise HTTPException(409,"reference price moved more than 2%; request a new proposal")
    errors=risk(row["ticker"],row["side"],row["qty"],market["price"])
    if errors: raise HTTPException(409,{"risk_errors":errors})
    # Use Alpaca's paper endpoint only; client_order_id enables reconciliation on retries.
    with httpx.Client(timeout=25) as client:
        prior=client.get("https://paper-api.alpaca.markets/v2/orders:by_client_order_id",headers=headers,params={"client_order_id":"agenttrade-"+a.proposal_id})
        if prior.status_code == 200:
            receipt=prior.json()
            with conn() as c:
                c.execute("INSERT OR IGNORE INTO trades(proposal_id,alpaca_order_id,ticker,side,qty,price,created) VALUES(?,?,?,?,?,?,?)",(a.proposal_id,receipt.get("id"),row["ticker"],row["side"],row["qty"],row["price"],datetime.now(timezone.utc).isoformat()))
                c.execute("UPDATE proposals SET status='submitted_to_alpaca' WHERE id=?",(a.proposal_id,))
            return {"proposal_id":a.proposal_id,"status":"submitted_to_alpaca","paper_only":True,"alpaca_order_id":receipt.get("id"),"alpaca_status":receipt.get("status"),"reconciled":True}
        if prior.status_code != 404: raise HTTPException(503,"Unable to reconcile prior paper order; check Alpaca dashboard")
        account=alpaca_get(client,"/v2/account",headers)
        positions=alpaca_get(client,"/v2/positions",headers)
        check_paper_capacity(row["ticker"],row["side"],row["qty"],market["price"],account,positions)
        order={"symbol":row["ticker"],"qty":str(row["qty"]),"side":row["side"].lower(),"type":"market","time_in_force":"day","client_order_id":"agenttrade-"+a.proposal_id}
        response=client.post("https://paper-api.alpaca.markets/v2/orders",headers=headers,json=order)
        if response.status_code not in (200,201):
            # A timeout or conflict may mean the order did land; reconcile via Alpaca order ID before retrying.
            if response.status_code==422:
                check=client.get("https://paper-api.alpaca.markets/v2/orders:by_client_order_id",headers=headers,params={"client_order_id":order["client_order_id"]})
                if check.status_code==200: response=check
                else: raise HTTPException(409,f"Alpaca rejected order: {broker_error(response)}. Check Alpaca dashboard before retrying")
            else: raise HTTPException(503,f"Alpaca order error: {broker_error(response)}. Check Alpaca dashboard before retrying")
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

def live_evidence_cards(ticker: str, market: dict, stock=None):
    """Build bounded, dated public-data cards. News is optional; price/stat cards are not."""
    stock = stock or yf.Ticker(ticker)
    stamp = datetime.now(timezone.utc).isoformat()
    def card(kind, text, source="Yahoo Finance via yfinance", published_at=None):
        # Stable IDs overwrite only this ticker's previous live cards; 1-7 remain frozen.
        uid = int(hashlib.sha256(f"agenttrade-live-v1:{ticker}:{kind}".encode()).hexdigest()[:13], 16) + 1000000
        return {"id": uid, "ticker": ticker, "kind": kind, "source": source,
                "published_at": published_at or stamp, "text": text[:1600], "evidence_type": "live"}
    cards = [card("price", f"{ticker} adjusted daily close on {market['as_of']}: USD {market['price']}. "
                  f"Recent adjusted closes (oldest to newest): {market.get('recent_closes', [market['price']])}. "
                  f"20-day SMA {market['sma20']}; 50-day SMA {market['sma50']}; RSI14 {market['rsi14']}; "
                  f"MACD {market['macd']}, signal {market['signal_line']}. "
                  "Delayed and unofficial market data; indicators describe history, not forecasts.",
                  published_at=market['as_of'])]
    try:
        info = stock.info or {}
        fields = {k: info.get(k) for k in ("shortName", "exchange", "sector", "industry", "marketCap", "trailingPE", "forwardPE", "totalRevenue", "currency") if info.get(k) is not None}
        if fields:
            cards.append(card("stats", f"{ticker} reported Yahoo Finance key statistics retrieved {stamp}: "
                              + json.dumps(fields, ensure_ascii=True, default=str) + ". Figures may be delayed or unavailable."))
    except Exception:
        pass  # A failed optional stats endpoint must not erase the price card.
    try:
        news = stock.news or []
        for index, item in enumerate(news[:5]):
            detail = item.get("content", item)
            if not isinstance(detail, dict): continue
            title = str(detail.get("title") or item.get("title") or "").strip()[:260]
            if not title: continue
            publisher = detail.get("provider") or detail.get("publisher") or item.get("publisher") or "Yahoo Finance news listing"
            if isinstance(publisher, dict): publisher = publisher.get("displayName") or publisher.get("name") or "Yahoo Finance news listing"
            rawtime = detail.get("pubDate") or detail.get("displayTime") or item.get("providerPublishTime")
            try:
                when = datetime.fromtimestamp(rawtime, timezone.utc).isoformat() if isinstance(rawtime, (int,float)) else datetime.fromisoformat(str(rawtime).replace("Z", "+00:00")).isoformat()
            except Exception: continue  # Do not label an undated headline as recent.
            if not -1 <= (datetime.now(timezone.utc) - datetime.fromisoformat(when)).total_seconds()/86400 <= 14: continue
            link = detail.get("canonicalUrl") or detail.get("clickThroughUrl") or item.get("link")
            if isinstance(link, dict): link = link.get("url")
            cards.append(card(f"news-{index}", f"{ticker} public headline: {title}. Publisher: {str(publisher)[:100]}. "
                              f"Published: {when}. Link: {str(link or 'unavailable')[:500]}. "
                              "Headline only, not a verified full article.",
                              source="Yahoo Finance news listing", published_at=when))
    except Exception:
        pass
    coverage = {"ticker": ticker, "news_cards": sum(d['kind'].startswith('news-') for d in cards),
                "stats_available": any(d['kind']=='stats' for d in cards), "price_card": True,
                "quality_note": "Headline coverage unavailable; using price history and available key statistics only." if not any(d['kind'].startswith('news-') for d in cards) else "Headlines are summaries, not full articles; verify important claims at source."}
    return cards, coverage


def upsert_live_evidence(cards):
    """Append/update live cards in the seeded collection; never recreate or delete it."""
    with httpx.Client(timeout=60) as client:
        vectors=[]
        for d in cards:
            r=client.post(OLLAMA+"/api/embeddings",json={"model":"nomic-embed-text","prompt":d['text']}); r.raise_for_status()
            vectors.append({"id":d['id'],"vector":r.json()['embedding'],
                            "payload":{"content":d['text'],"metadata":{k:d[k] for k in ('source','published_at','id','ticker','kind','evidence_type')} | {"doc_id":str(d['id'])}}})
        # /ingest must have been run first so the fixed educational cards survive.
        r=client.get(QDRANT+f"/collections/{COLLECTION}")
        if r.status_code != 200: raise HTTPException(503,"Evidence collection unavailable; run POST /ingest before live research")
        # Clear only reserved IDs for this ticker so old news does not survive a no-news run.
        reserved = [int(hashlib.sha256(f"agenttrade-live-v1:{cards[0]['ticker']}:{kind}".encode()).hexdigest()[:13],16)+1000000
                    for kind in ("price", "stats", *(f"news-{i}" for i in range(5)))]
        r=client.post(QDRANT+f"/collections/{COLLECTION}/points/delete?wait=true",json={"points":reserved}); r.raise_for_status()
        r=client.put(QDRANT+f"/collections/{COLLECTION}/points?wait=true",json={"points":vectors}); r.raise_for_status()
    return len(vectors)


@app.get("/fixed-rag")
def fixed_rag(question:str, ticker:str = None):
    with httpx.Client(timeout=45) as client:
        r=client.post(OLLAMA+"/api/embeddings",json={"model":"nomic-embed-text","prompt":question});r.raise_for_status()
        body={"vector":r.json()["embedding"],"limit":3,"with_payload":True}
        if ticker: body["filter"]={"must":[{"key":"metadata.ticker","match":{"value":ticker}}]}
        s=client.post(QDRANT+f"/collections/{COLLECTION}/points/search",json=body);s.raise_for_status()
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
    if not check_symbol_format(ticker): raise unsupported_ticker(ticker)
    if p.evaluation and ticker not in SEEDED_CORPUS_TICKERS:
        raise HTTPException(400,"Frozen evaluation is limited to AAPL and MSFT")
    market=None if p.evaluation else price_data(ticker)
    coverage=None
    if not p.evaluation and p.mode != 'none':
        cards, coverage=live_evidence_cards(ticker, market)
        try: coverage['cards_ingested']=upsert_live_evidence(cards)
        except HTTPException: raise
        except Exception as exc: raise HTTPException(503,f"Live evidence ingestion unavailable: {str(exc)[:120]}") from exc
    evidence=[] if p.mode != 'fixed' else fixed_rag(p.question, None if p.evaluation else ticker)['evidence']
    seeded=ticker in SEEDED_CORPUS_TICKERS
    return {**p.model_dump(),"snapshot":market,"fixed_evidence":evidence,"ticker_seeded_in_corpus":seeded,"evidence_coverage":coverage,
            "retrieval_instruction":("DO NOT use the Qdrant tool. No external evidence is available." if p.mode=='none' else
            "DO NOT use the Qdrant tool; only use fixed_evidence supplied here." if p.mode=='fixed' else
            "You MUST choose and call the Qdrant retrieval tool with a query you formulate; inspect the returned source metadata and cite doc IDs. You may reformulate and call again if evidence is insufficient."),
            "warning":("Frozen benchmark: educational synthetic cards only; historical policy card 3 is not current trading policy." if p.evaluation else
            "Live cards include delayed public data; news is headline-only. Synthetic policy cards are historical classroom examples and card 3's AAPL/MSFT restriction is obsolete. Cite live sources for current facts. " + (coverage['quality_note'] if coverage else "No retrieval in this mode."))}

@app.post("/research")
def research(p:AnalysisInput):
    try:
        with httpx.Client(timeout=300) as client:
            r=client.post(N8N+"/webhook/agenttrade-analyze",json=p.model_dump())
            r.raise_for_status()
            return r.json()
    except Exception as exc: raise HTTPException(503,f"Local research workflow unavailable at {N8N}: {str(exc)[:140]}")
