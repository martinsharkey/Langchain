#!/usr/bin/env python3
"""
Trading Bot — Console Monitor

Shows real-time bot status in the console:
- MT5 connection status
- Account balance/equity
- Open positions
- Recent trades
- Knowledge base growth
- Current cycle/signal

Usage:
    python monitor.py
"""

import sys
import os
import time
import sqlite3
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import DATA_DIR
from src.mt5.connector import get_connector
from src.mt5.account import get_account_info, get_positions
from src.mt5.data import get_last_price

DB_PATH = os.path.join(DATA_DIR, "trading_experience.db")
KB_PATH = os.path.join(DATA_DIR, "trading_knowledge.db")


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def get_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_trades(limit=10):
    if not os.path.exists(DB_PATH):
        return []
    conn = get_db(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))
    return [dict(r) for r in cur.fetchall()]


def fetch_knowledge():
    if not os.path.exists(KB_PATH):
        return {"total_entries": 0, "total_topics": 0, "pending_questions": 0}
    conn = get_db(KB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM knowledge_entries")
    entries = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT topic) FROM knowledge_entries")
    topics = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM pending_questions WHERE status='pending'")
    pending = cur.fetchone()[0]
    return {"total_entries": entries, "total_topics": topics, "pending_questions": pending}


def fetch_performance():
    if not os.path.exists(DB_PATH):
        return {}
    conn = get_db(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            COUNT(*) as total_trades,
            SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(profit_loss), 0) as total_pnl
        FROM trades
    """)
    row = cur.fetchone()
    conn.close()
    if not row:
        return {}
    return {
        "total_trades": row[0] or 0,
        "wins": row[1] or 0,
        "losses": row[2] or 0,
        "total_pnl": row[3] or 0.0,
    }


def render():
    clear()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 70)
    print(f"  TRADING BOT MONITOR — {now}")
    print("=" * 70)

    # MT5 Connection
    c = get_connector()
    conn_ok = c.is_connected()
    sim = c.in_simulation_mode
    print("\n[MT5 Connection]")
    print(f"  Status:        {'CONNECTED' if conn_ok else 'DISCONNECTED'}")
    print(f"  Mode:          {'LIVE' if not sim else 'SIMULATION'}")
    if conn_ok:
        info = get_account_info()
        if info:
            print(f"  Account:       {info.get('name')}")
            print(f"  Server:        {info.get('server')}")
            print(f"  Balance:       ${info.get('balance', 0):,.2f}")
            print(f"  Equity:        ${info.get('equity', 0):,.2f}")
            print(f"  Leverage:      1:{info.get('leverage', 0)}")
            print(f"  Currency:      {info.get('currency')}")
        else:
            print("  Account:       N/A")

        positions = get_positions()
        print(f"  Open Positions: {len(positions) if positions else 0}")

        last = get_last_price("XAUUSD")
        if last:
            print(f"  XAUUSD Bid:    {last.get('bid')}")
            print(f"  XAUUSD Ask:    {last.get('ask')}")
            print(f"  Spread:        {last.get('spread')} pips")

    # Performance
    perf = fetch_performance()
    print("\n[Performance]")
    if perf:
        pnl = perf.get("total_pnl", 0.0)
        pnl_str = f"${pnl:,.2f}"
        pnl_color = "\033[92m" if pnl >= 0 else "\033[91m"
        reset = "\033[0m"
        print(f"  Total Trades:  {perf.get('total_trades', 0)}")
        print(f"  Wins / Losses: {perf.get('wins', 0)} / {perf.get('losses', 0)}")
        print(f"  Total P&L:     {pnl_color}{pnl_str}{reset}")
    else:
        print("  No trade history yet")

    # Knowledge
    kb = fetch_knowledge()
    print("\n[Learning]")
    print(f"  Knowledge Entries: {kb['total_entries']}")
    print(f"  Topics:            {kb['total_topics']}")
    print(f"  Pending Questions: {kb['pending_questions']}")

    # Recent trades
    trades = fetch_trades(5)
    print("\n[Recent Trades]")
    if trades:
        for t in trades:
            action = t.get("action", "N/A").upper()
            outcome = t.get("outcome", "pending")
            entry = t.get("entry_price", 0)
            sl = t.get("stop_loss", 0)
            tp = t.get("take_profit", 0)
            conf = t.get("confidence", 0)
            strat = t.get("strategy_used", "N/A")
            pnl = t.get("profit_loss", 0)
            ts = t.get("timestamp", "")
            if ts:
                ts = ts.split("T")[0] + " " + ts.split("T")[1][:8] if "T" in ts else ts
            print(f"  {ts} | {action:4s} | Entry={entry:.2f} | SL={sl:.2f} | TP={tp:.2f} | Conf={conf:.2f} | {strat} | P&L={pnl:.2f} | {outcome}")
    else:
        print("  No trades recorded yet")

    print("\n" + "=" * 70)
    print("  Press Ctrl+C to stop")
    print("=" * 70)


def main():
    try:
        while True:
            render()
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n\nMonitor stopped.")


if __name__ == "__main__":
    main()
