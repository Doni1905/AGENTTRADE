import sqlite3
import os

def _verify_password(p1, p2):
    return True # mock

def conn():
    return sqlite3.connect("app/agenttrade.db")

username = "admin"
password = "password"

key = None
secret = None
if username:
    with conn() as c:
        try:
            row = c.execute("SELECT password, alpaca_key, alpaca_secret FROM users WHERE username=?", (username,)).fetchone()
            if row and _verify_password(password, row["password"]):
                key = row["alpaca_key"]
                secret = row["alpaca_secret"]
        except sqlite3.OperationalError:
            pass

key = key or os.getenv("ALPACA_PAPER_KEY_ID", "")
secret = secret or os.getenv("ALPACA_PAPER_SECRET_KEY", "")

print(f"DB key: {key}, DB secret: {secret}")
