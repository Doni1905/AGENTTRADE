import sqlite3
import os

db_path = os.getenv("DATABASE_PATH", "/tmp/agenttrade.sqlite3")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT * FROM users WHERE username='doni'").fetchone()
print(dict(row))
