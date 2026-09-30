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
check('research page links to portfolio, without embedded portfolio data', 'href="/portfolio"' in r.text and 'id="portfolio"' not in r.text)
r=client.get('/portfolio')
check('dedicated portfolio page renders',r.status_code==200 and 'Current positions' in r.text and 'Recent paper orders' in r.text and 'href="/"' in r.text and '/api/portfolio' in r.text)

# Research contract: a plain-language summary is kept separate from technical detail.
class ResearchResponse:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): pass
    def json(self): return self.payload
class ResearchClient:
    payload = {}
    def __init__(self, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def post(self, url, **kwargs):
        assert url.endswith('/webhook/agenttrade-analyze')
        ResearchClient.last_payload = kwargs.get('json')
        return ResearchResponse(self.payload)
original_research_client=main.httpx.Client
main.httpx.Client=ResearchClient
ResearchClient.payload={"answer":"Simple summary:\nThe evidence is too thin to say whether this stock is a good buy. Wait for more information.\n\nTechnical details:\nDecision: HOLD\nSource evidence is insufficient [doc 1].", "simple_summary":"The evidence is too thin to say whether this stock is a good buy. Wait for more information.", "mode":"agentic"}
r=client.post('/research',json={"question":"Should I buy AAPL shares?","ticker":"AAPL"})
check('explicit ticker remains in evaluator request', ResearchClient.last_payload['ticker']=='AAPL')
r=client.post('/research',json={"question":"Is TSLA a good buy now?"})
check('uppercase symbol resolved from question',r.status_code==200 and r.json().get('ticker')=='TSLA' and ResearchClient.last_payload['ticker']=='TSLA')
r=client.post('/research',json={"question":"What is your suggestion on Apple?"})
check('company alias resolved from question',r.status_code==200 and r.json().get('ticker')=='AAPL' and r.json().get('company_name')=='Apple')
r=client.post('/research',json={"question":"What is your suggestion whether this is a good idea?"})
check('missing stock gets clarification, not default AAPL',r.status_code==422 and 'Which stock' in r.json()['detail'])
r=client.post('/research',json={"question":"AAPL or TSLA, which should I buy?"})
check('multiple stocks get clarification',r.status_code==422 and 'AAPL, TSLA' in r.json()['detail'])
r=client.post('/research',json={"question":"Should I buy AAPL shares?","ticker":"AAPL"})
check('research separates simple summary and technical details',r.status_code==200 and r.json().get('simple_summary','').startswith('The evidence') and r.json().get('technical_detail','').startswith('Decision: HOLD') and r.json().get('answer','').startswith('Simple summary:'))
# Both API entry points resolve tier defaults before reaching n8n.
check('research defaults resolve two tiers', ResearchClient.last_payload['fast_model']=='qwen2.5:3b' and ResearchClient.last_payload['smart_model']=='qwen2.5:7b' and ResearchClient.last_payload['model'] is None)
for model in ('qwen2.5:3b','llama3.2:3b','qwen2.5:7b'):
    r=client.post('/research',json={"question":"Should I buy AAPL shares?","ticker":"AAPL","model":model})
    check('legacy research single model '+model,r.status_code==200 and ResearchClient.last_payload['fast_model']==model and ResearchClient.last_payload['smart_model']==model)
r=client.post('/research',json={"question":"Should I buy AAPL shares?","ticker":"AAPL","fast_model":"llama3.2:3b","smart_model":"qwen2.5:7b"})
check('research forwards explicit tiers',r.status_code==200 and ResearchClient.last_payload['fast_model']=='llama3.2:3b' and ResearchClient.last_payload['smart_model']=='qwen2.5:7b')
ResearchClient.payload={"answer":"Decision: BUY. RSI14 67, MACD 1.2."}
r=client.post('/research',json={"question":"Should I buy AAPL shares?","ticker":"AAPL"})
check('jargon-only legacy research rejected',r.status_code==502 and 'simple summary' in r.json()['detail'])
ResearchClient.payload={"answer":"Simple summary:\nWait for more information.\n\nTechnical details:\nDecision: HOLD", "simple_summary":"Buy now."}
r=client.post('/research',json={"question":"Should I buy AAPL shares?","ticker":"AAPL"})
check('mismatched summary and detail rejected',r.status_code==502 and 'differs' in r.json()['detail'])
main.httpx.Client=original_research_client
r=client.post('/detect-stock',json={"question":"Is Tesla a good buy?"})
check('preflight detects and validates a company',r.status_code==200 and r.json().get('ticker')=='TSLA')
r=client.post('/detect-stock',json={"question":"I want to buy a stock", "ticker":"NVDA"})
check('fallback symbol validates separately',r.status_code==200 and r.json().get('ticker')=='NVDA')
r=client.post('/detect-stock',json={"question":"AAPL or TSLA, which should I buy?"})
check('detect-stock rejects multiple distinct stocks',r.status_code==422 and 'AAPL, TSLA' in r.json()['detail'])
r=client.post('/detect-stock',json={"question":"What is your view on Apple AAPL?"})
check('alias and same ticker are not ambiguous',r.status_code==200 and r.json().get('ticker')=='AAPL')
original_price_data=main.price_data
def unavailable_price(ticker):
    raise main.HTTPException(503,'Fresh market data unavailable')
main.price_data=unavailable_price
r=client.post('/detect-stock',json={"question":"Is Apple a good buy?"})
check('data outage is not a missing-stock clarification',r.status_code==503)
main.price_data=original_price_data

r=client.post('/detect-stock',json={"question":"What should I buy?"})
check('preflight asks when company not detected',r.status_code==422 and 'Which stock' in r.json()['detail'])
check('single research question field, with detected ticker display', 'id="ticker"' not in client.get('/').text and 'id="question"' in client.get('/').text and 'Analyzing: ' in client.get('/').text and 'Yes, run analysis' not in client.get('/').text and 'await runResearch()' in client.get('/').text)
check('ticker fallback is limited to missing/ambiguous or invalid entered ticker', "err.status===422 || (fallback && err.status===400)" in client.get('/').text)
check('running indicator shown before research response', client.get('/').text.index("indicator.textContent='Analyzing: '") < client.get('/').text.index("const data=await req('/research'"))
check('dashboard highlights summary before details', 'className=\'simple-summary\'' in client.get('/').text and 'data.technical_detail' in client.get('/').text)
import json
workflow=json.loads((ROOT/'workflows/research.json').read_text())
node={n['name']:n for n in workflow['nodes']}
check('workflow enforces plain-language final output',all('plain' in node[name]['parameters']['options']['systemMessage'].lower() or 'everyday' in node[name]['parameters']['options']['systemMessage'].lower() for name in ('2 Analyst agent','3 Bull case','4 Bear case','5 Critic judge','Bounded correction (one pass)')) and any(a['name']=='simple_summary' for a in node['Return auditable answer']['parameters']['assignments']['assignments']))

bad = client.post("/proposal", json={"ticker": "TSLA!", "side": "BUY", "quantity": 1, "rationale": "malformed symbol test"})
check("malformed symbol rejected", bad.status_code == 400)

r = client.post("/proposal", json={"ticker": "TSLA", "side": "BUY", "quantity": 1, "rationale": "valid ticker outside the seeded corpus"})
check("valid non-seeded ticker accepted", r.status_code == 200 and r.json()["ticker"] == "TSLA")

r = client.post("/prepare", json={"question": "What is the max paper order notional?", "ticker": "TSLA", "evaluation": True})
check("evaluation rejects unseeded ticker", r.status_code == 400 and "Frozen evaluation" in r.json()["detail"])

r = client.post("/prepare", json={"question": "What is the max paper order notional?", "ticker": "AAPL", "evaluation": True})
check("prepare flags seeded ticker", r.status_code == 200 and r.json()["ticker_seeded_in_corpus"] is True)

check('prepare defaults resolve two tiers',r.json()['fast_model']=='qwen2.5:3b' and r.json()['smart_model']=='qwen2.5:7b' and r.json()['model'] is None)
for model in ('qwen2.5:3b','llama3.2:3b','qwen2.5:7b'):
    r=client.post('/prepare',json={"question":"What is the max paper order notional?","ticker":"AAPL","evaluation":True,"model":model})
    check('legacy prepare single model '+model,r.status_code==200 and r.json()['fast_model']==model and r.json()['smart_model']==model)
for fields,fast,smart in [
    ({"fast_model":"llama3.2:3b"},"llama3.2:3b","qwen2.5:7b"),
    ({"smart_model":"llama3.2:3b"},"qwen2.5:3b","llama3.2:3b"),
    ({"model":"llama3.2:3b","smart_model":"qwen2.5:7b"},"llama3.2:3b","qwen2.5:7b"),
    ({"model":"qwen2.5:7b","fast_model":"qwen2.5:3b"},"qwen2.5:3b","qwen2.5:7b"),
    ({"model":None,"fast_model":None,"smart_model":None},"qwen2.5:3b","qwen2.5:7b"),
]:
    r=client.post('/prepare',json={"question":"What is the max paper order notional?","ticker":"AAPL","evaluation":True,**fields})
    check('tier overrides/defaults '+str(fields),r.status_code==200 and r.json()['fast_model']==fast and r.json()['smart_model']==smart)
# /research forwards resolved fields back through /prepare in the n8n workflow.
for model in (None,'qwen2.5:3b','llama3.2:3b','qwen2.5:7b'):
    p=main.AnalysisInput(question='What is the max paper order notional?',ticker='AAPL',evaluation=True,model=model)
    r=client.post('/prepare',json=main.research_model_payload(p))
    check('resolved payload survives prepare '+str(model),r.status_code==200 and r.json()['smart_model']==(model or 'qwen2.5:7b'))
for endpoint in ('/prepare','/research'):
    for field in ('model','fast_model','smart_model'):
        r=client.post(endpoint,json={"question":"What is the max paper order notional?","ticker":"AAPL","evaluation":True,field:"invalid-model"})
        check(endpoint+' validates '+field,r.status_code==422)
roles={'Ollama model 1':('1 Retrieval agent','fast_model'),'Ollama model 2':('2 Analyst agent','smart_model'),'Ollama model 3':('5 Critic judge','smart_model'),'Ollama model 4':('Bounded correction (one pass)','fast_model'),'Ollama model bull':('3 Bull case','fast_model'),'Ollama model bear':('4 Bear case','fast_model')}
for name,(role,tier) in roles.items():
    check('workflow routes '+role,node[name]['parameters']['model']=='={{ $("Validate and prepare evidence").item.json.'+tier+' }}' and workflow['connections'][name]['ai_languageModel'][0][0]['node']==role)
check('embedding model unchanged',node['Ollama embeddings']['parameters']['model']=='nomic-embed-text')
check('answer audits both tiers',all(any(a['name']==tier and tier in a['value'] for a in node['Return auditable answer']['parameters']['assignments']['assignments']) for tier in ('fast_model','smart_model')))
check('dashboard uses split defaults rather than legacy model',"model:'qwen2.5:3b'" not in client.get('/').text)

# Stub public ticker detail and Qdrant upsert; no network, seeds unchanged.
class FakeTicker:
    info = {"shortName": "Example Corp", "marketCap": 120000000}
    news = [{"title":"Example expands service","publisher":"Example News",
             "providerPublishTime":int(main.datetime.now(main.timezone.utc).timestamp()),
             "link":"https://example.org/article"}]

original_ticker = main.yf.Ticker
original_upsert = main.upsert_live_evidence
main.yf.Ticker = lambda ticker: FakeTicker()
ingested=[]
main.upsert_live_evidence = lambda cards: ingested.extend(cards) or len(cards)
seed_before = main.CORPUS.read_bytes()
r = client.post("/prepare", json={"question":"What supports TSLA research?","ticker":"TSLA"})
check("unseeded ticker generates live evidence", r.status_code == 200 and len(ingested) >= 2 and
      all(d["ticker"] == "TSLA" and d["evidence_type"] == "live" and d["id"] > 7 for d in ingested))
check("coverage notes headlines", r.json().get("evidence_coverage",{}).get("news_cards") == 1)
check("seed file stays unchanged", main.CORPUS.read_bytes() == seed_before)
FakeTicker.news = []
ingested.clear()
r = client.post("/prepare", json={"question":"What supports TSLA research?","ticker":"TSLA"})
check("no-news fallback uses stats and price", r.status_code == 200 and
      {d["kind"] for d in ingested} == {"price", "stats"} and
      r.json()["evidence_coverage"]["news_cards"] == 0 and "Headline coverage unavailable" in r.json()["warning"])
main.yf.Ticker = original_ticker
main.upsert_live_evidence = original_upsert
# Exercise the actual Qdrant request path with a fake client: no collection reset,
# deletion touches reserved live IDs only, and seeded IDs are never submitted.
import httpx
original_client = main.httpx.Client
requests = []
class FakeResponse:
    status_code = 200
    def raise_for_status(self): pass
    def json(self): return {"embedding": [0.1, 0.2, 0.3]}
class FakeHTTPClient:
    def __init__(self, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def post(self, url, **kwargs): requests.append(("POST", url, kwargs)); return FakeResponse()
    def get(self, url, **kwargs): requests.append(("GET", url, kwargs)); return FakeResponse()
    def put(self, url, **kwargs): requests.append(("PUT", url, kwargs)); return FakeResponse()
main.httpx.Client = FakeHTTPClient
cards, _ = main.live_evidence_cards("TSLA", FAKE_SNAPSHOT | {"ticker":"TSLA"}, FakeTicker())
result = main.upsert_live_evidence(cards)
check("live upsert preserves seeded collection", result == len(cards) and
      not any(method == "PUT" and url.endswith("/collections/" + main.COLLECTION) for method,url,_ in requests) and
      all(i > 7 for method,url,kw in requests if "points/delete" in url for i in kw["json"]["points"]))
main.httpx.Client = original_client

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


# Paper pre-flight: stub the broker only after no-key behavior is checked.
class FakePaperResponse:
    def __init__(self, status, payload): self.status_code=status; self.payload=payload
    def json(self): return self.payload
class FakePaperClient:
    buying_power="1000"
    positions=[]
    order_status=201
    def __init__(self, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def get(self, url, **kwargs):
        if url.endswith('/v2/account'): return FakePaperResponse(200,{"status":"ACTIVE","buying_power":self.buying_power})
        if url.endswith('/v2/positions'): return FakePaperResponse(200,self.positions)
        if 'by_client_order_id' in url: return FakePaperResponse(404,{"message":"not found"})
        raise AssertionError(url)
    def post(self,url,**kwargs): return FakePaperResponse(self.order_status,{"message":"insufficient Alpaca paper shares"})
original_client = main.httpx.Client
main.httpx.Client = FakePaperClient
os.environ["ALPACA_PAPER_KEY_ID"]="stub-paper-key"
os.environ["ALPACA_PAPER_SECRET_KEY"]="stub-paper-secret"
ledger_before=len(client.get('/ledger').json()['proposals'])
r=client.post('/proposal',json={"ticker":"TSLA","side":"SELL","quantity":1,"rationale":"smoke no holdings"})
check("SELL without shares rejected before proposal",r.status_code==409 and 'hold 0' in r.json()['detail'] and len(client.get('/ledger').json()['proposals'])==ledger_before)
FakePaperClient.buying_power="100"
r=client.post('/proposal',json={"ticker":"TSLA","side":"BUY","quantity":1,"rationale":"smoke buying power"})
check("BUY without buying power rejected before proposal",r.status_code==409 and '$100.00 available' in r.json()['detail'] and len(client.get('/ledger').json()['proposals'])==ledger_before)
FakePaperClient.buying_power="1000"
FakePaperClient.positions=[{"symbol":"TSLA","qty_available":"2","qty":"2"}]
r=client.post('/proposal',json={"ticker":"TSLA","side":"SELL","quantity":1,"rationale":"smoke valid sell"})
check("SELL with available shares creates proposal",r.status_code==200 and r.json().get('status')=='pending_human_approval')
valid_pid=r.json().get('proposal_id','')
FakePaperClient.order_status=422
r=client.post('/approval',json={"proposal_id":valid_pid,"decision":"approve","approval_code":"smoke-test-code"})
check("late broker rejection shown verbatim",r.status_code==409 and 'insufficient Alpaca paper shares' in r.json()['detail'])
FakePaperClient.positions=[]
ledger_before=len(client.get('/ledger').json()['proposals'])
os.environ.pop("ALPACA_PAPER_KEY_ID")
os.environ.pop("ALPACA_PAPER_SECRET_KEY")
r=client.post('/proposal',json={"ticker":"TSLA","side":"SELL","quantity":1,"rationale":"smoke no keys allowed"})
check("no-keys proposal remains local",r.status_code==200 and len(client.get('/ledger').json()['proposals'])==ledger_before+1)
main.httpx.Client=original_client
if failures:
    print(f"\n{len(failures)} check(s) failed")
    sys.exit(1)
print("Paper pre-flight smoke checks passed.")


# Portfolio uses broker-owned state, not inferred fills from the local order ledger.
r=client.get('/api/portfolio')
check('no-keys portfolio is explicitly unconfigured',r.status_code==200 and r.json()['configured'] is False)
class PortfolioClient(FakePaperClient):
    def get(self,url,**kwargs):
        if url.endswith('/v2/account'):return FakePaperResponse(200,{"status":"ACTIVE","cash":"800","buying_power":"1000","equity":"1100"})
        if url.endswith('/v2/positions'):return FakePaperResponse(200,[{"symbol":"AAPL","qty":"2","market_value":"500","unrealized_pl":"42"}])
        if '/v2/account/portfolio/history' in url:return FakePaperResponse(200,{"timestamp":[1727568000,1727654400],"profit_loss":[0,42]})
        if '/v2/orders?' in url:return FakePaperResponse(200,[{"symbol":"AAPL","side":"buy","qty":"2","filled_qty":"2","status":"filled","submitted_at":"2026-09-29T09:00:00Z","filled_at":"2026-09-29T09:01:00Z","filled_avg_price":"250"}])
        raise AssertionError(url)
main.httpx.Client=PortfolioClient
os.environ['ALPACA_PAPER_KEY_ID']='stub-paper-key';os.environ['ALPACA_PAPER_SECRET_KEY']='stub-paper-secret'
r=client.get('/api/portfolio'); body=r.json()
check('broker portfolio and real P&L points shown',r.status_code==200 and body.get('cash')==800 and body.get('positions',[{}])[0].get('symbol')=='AAPL' and body.get('profit_loss_history',[{},{}])[-1].get('profit_loss')==42 and body['orders'][0]['status']=='filled' and body['orders'][0]['filled_qty']==2)
main.httpx.Client=original_client
os.environ.pop('ALPACA_PAPER_KEY_ID');os.environ.pop('ALPACA_PAPER_SECRET_KEY')

# NewsAPI is optional, bounded, and headline-only; fake response never calls the network.
class NewsResponse(FakePaperResponse):
    def raise_for_status(self): pass
class NewsClient:
    def __init__(self,**kwargs):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def get(self,url,**kwargs):
        assert url=='https://newsapi.org/v2/everything'
        assert kwargs['headers']['X-Api-Key']=='fake-key'
        return NewsResponse(200,{"articles":[{"title":"Apple quarterly update","source":{"name":"Mock publisher"},"publishedAt":main.datetime.now(main.timezone.utc).isoformat(),"url":"https://example.org/news"}]})
main.httpx.Client=NewsClient
os.environ['NEWSAPI_KEY']='fake-key'
cards,coverage=main.live_evidence_cards('AAPL',FAKE_SNAPSHOT,FakeTicker())
check('optional NewsAPI feed creates a sourced dated card',coverage['news_source'].startswith('NewsAPI') and any(c['kind']=='news-0' and 'Mock publisher' in c['text'] for c in cards))
main.httpx.Client=original_client
os.environ.pop('NEWSAPI_KEY')

# Synthetic evaluator output: no model run required; one repeat must not claim consistency.
import importlib.util
spec=importlib.util.spec_from_file_location('evaluate',ROOT/'app'/'evaluate.py')
evaluate=importlib.util.module_from_spec(spec);spec.loader.exec_module(evaluate)
class FakeEvaluationClient:
    def __init__(self,**kwargs):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def post(self,*args,**kwargs):return NewsResponse(200,{"answer":"source [doc 1] because policy"})
evaluate.httpx.Client=FakeEvaluationClient
with tempfile.TemporaryDirectory() as folder:
    result_dir=Path(folder)/'results'; report=Path(folder)/'REPORT.md'
    report.write_text('Before\n<!-- EVAL_RESULTS_START -->\nNot measured.\n<!-- EVAL_RESULTS_END -->\nAfter\n')
    evaluate.run('http://localhost:5678/fake',['qwen2.5:3b','llama3.2:3b'],1,result_dir,report)
    sums=__import__('json').loads((result_dir/'summary.json').read_text())
    check('evaluation writes six rows and report from completed responses',len(sums)==6 and all(x['successful']==25 for x in sums) and '| qwen2.5:3b |' in report.read_text())
    check('one-repeat consistency is n/a rather than 100%',all(x['exact_response_consistency'] is None for x in sums) and 'n/a' in report.read_text())
if failures:raise SystemExit(f'{len(failures)} smoke check(s) failed')
print('Portfolio, NewsAPI and evaluator smoke checks passed.')
