import sqlite3
import sys

db_path = sys.argv[1]
conn = sqlite3.connect(db_path)
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
print("Tables:", tables)

for t in tables:
    table_name = t[0]
    schema = conn.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}';").fetchone()[0]
    print(f"\nSchema for {table_name}: {schema}")
