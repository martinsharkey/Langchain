import sqlite3
import os

db_path = r"C:\Users\MartinSharkey\Documents\Langchain\langchain\data\trading_experience.db"

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check if trades table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables in database:")
for table in tables:
    print(f"  - {table[0]}")

# Check trades table schema
print("\nTrades table schema:")
cursor.execute("PRAGMA table_info(trades)")
columns = cursor.fetchall()
for col in columns:
    print(f"  {col[1]}: {col[2]}")

# Count trades
cursor.execute("SELECT COUNT(*) FROM trades")
count = cursor.fetchone()[0]
print(f"\nTotal trades in database: {count}")

# Get sample trade
if count > 0:
    cursor.execute("SELECT * FROM trades LIMIT 1")
    row = cursor.fetchone()
    print(f"\nSample trade:")
    col_names = [description[0] for description in cursor.description]
    for name, value in zip(col_names, row):
        print(f"  {name}: {value}")
else:
    print("\nNo trades in database")

conn.close()
