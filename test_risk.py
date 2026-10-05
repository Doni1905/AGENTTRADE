import requests

url_proposal = "http://127.0.0.1:8000/proposal"
url_approve = "http://127.0.0.1:8000/approve"
headers = {"Content-Type": "application/json"}

def test(name, data):
    print(f"\n--- {name} ---")
    res = requests.post(url_proposal, json=data, headers=headers)
    print(f"Proposal Response ({res.status_code}): {res.json()}")
    return res

test("TEST 1: Valid proposal", {"ticker": "AAPL", "side": "BUY", "quantity": 1, "rationale": "test"})
test("TEST 2: >5 shares", {"ticker": "AAPL", "side": "BUY", "quantity": 6, "rationale": "test"})
# AAPL is around $330. 4 shares = $1320.
test("TEST 3: >$1000", {"ticker": "AAPL", "side": "BUY", "quantity": 4, "rationale": "test"})
test("TEST 4: Short selling", {"ticker": "AAPL", "side": "SELL", "quantity": 1, "rationale": "test"})
test("TEST 6: Duplicate", {"ticker": "AAPL", "side": "BUY", "quantity": 1, "rationale": "test"})

