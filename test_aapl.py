import requests
url = "http://127.0.0.1:8000/research"
payload = {"question": "Analyze AAPL and determine the current research view, including the bullish case, bearish case, risks, evidence and final decision."}
res = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
print(res.json())
