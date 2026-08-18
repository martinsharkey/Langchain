"""Per-symbol edge report from trading_experience.db.
Read-only. No dashboard data."""
import sqlite3, os
from collections import defaultdict

DB = r"C:\Users\MartinSharkey\Documents\Langchain\langchain\data\trading_experience.db"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

sql = """
SELECT symbol, outcome, profit_loss, timestamp
FROM trades
WHERE outcome IN ('win','loss')
  AND (exit_reason IS NULL OR exit_reason <> 'pre_rebuild_synthetic')
  AND (data_source IS NULL OR data_source NOT LIKE '%SIMULATED%')
ORDER BY timestamp ASC
"""
rows = [dict(r) for r in conn.execute(sql).fetchall()]
conn.close()

print(f"Total closed trades (real data): {len(rows)}")
print()

by_sym = defaultdict(list)
for r in rows:
    by_sym[r["symbol"]].append(r)

summary = []
for sym, trades in by_sym.items():
    wins = [t for t in trades if t["outcome"] == 'win']
    losses = [t for t in trades if t["outcome"] == 'loss']
    n = len(trades)
    wr = len(wins) / n * 100 if n else 0
    gw = sum(t["profit_loss"] for t in wins)
    gl = abs(sum(t["profit_loss"] for t in losses))
    pf = gw / gl if gl else float('inf')
    net = sum(t["profit_loss"] for t in trades)
    avg_win = gw / len(wins) if wins else 0
    avg_loss = gl / len(losses) if losses else 0
    exp = net / n if n else 0
    summary.append((sym, n, len(wins), len(losses), wr, pf, net, avg_win, avg_loss, exp))

summary.sort(key=lambda x: x[6], reverse=True)

header = f"{'Symbol':<14} {'N':>5} {'W':>5} {'L':>5} {'WR%':>6} {'PF':>6} {'NetPnL':>10} {'AvgWin':>9} {'AvgLoss':>9} {'Expect':>9}"
print(header)
print("-" * len(header))
for s in summary:
    print(f"{s[0]:<14} {s[1]:>5} {s[2]:>5} {s[3]:>5} {s[4]:>6.1f} {s[5]:>6.2f} {s[6]:>10.2f} {s[7]:>9.2f} {s[8]:>9.2f} {s[9]:>9.2f}")

print()
print("=== Recent 50-trade window per focus symbol ===")
for sym in ["XAUUSD-ECN", "GER40.", "BTCUSD"]:
    if sym not in by_sym:
        continue
    t = by_sym[sym][-50:]
    wins = [x for x in t if x["outcome"] == 'win']
    losses = [x for x in t if x["outcome"] == 'loss']
    n = len(t)
    wr = len(wins) / n * 100 if n else 0
    gw = sum(x["profit_loss"] for x in wins)
    gl = abs(sum(x["profit_loss"] for x in losses))
    pf = gw / gl if gl else float('inf')
    net = sum(x["profit_loss"] for x in t)
    print(f"{sym}: last {n} trades | WR {wr:.1f}% | PF {pf:.2f} | Net {net:.2f}")
