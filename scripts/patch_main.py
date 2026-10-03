import re
with open("app/main.py", "r") as f:
    code = f.read()

replacement = """
    user_owns_stock = False
    if not p.evaluation and (os.getenv("ALPACA_PAPER_KEY_ID") and os.getenv("ALPACA_PAPER_SECRET_KEY")):
        try:
            with httpx.Client(timeout=10) as client:
                positions = alpaca_get(client, "/v2/positions", alpaca_headers())
                for pos in positions:
                    if pos.get("symbol") == ticker and float(pos.get("qty", 0)) > 0:
                        user_owns_stock = True
                        break
        except Exception:
            pass

    return {**research_model_payload(p),"input":p.question,"snapshot":market,"fixed_evidence":evidence,"ticker_seeded_in_corpus":seeded,"evidence_coverage":coverage, "user_owns_stock": user_owns_stock,
"""

code = code.replace(
    'return {**research_model_payload(p),"input":p.question,"snapshot":market,"fixed_evidence":evidence,"ticker_seeded_in_corpus":seeded,"evidence_coverage":coverage,',
    replacement
)

with open("app/main.py", "w") as f:
    f.write(code)
