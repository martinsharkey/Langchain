#!/usr/bin/env python3
"""
One-shot MT5 Connection Proof Script.

Run this anytime to prove the bot is connected to live MT5:
    python mt5_proof.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.mt5.connector import get_connector
from src.mt5.data import get_rates, get_last_price
from src.mt5.account import get_account_info, get_positions

print("=" * 70)
print("  MT5 LIVE CONNECTION PROOF")
print("=" * 70)

# 1. Initialize connector
c = get_connector()
ok = c.initialize()
print(f"\n[1] Connector.initialize() = {ok}")
print(f"    Connected:     {c.is_connected()}")
print(f"    Simulation:    {c.in_simulation_mode}")

if not ok or c.in_simulation_mode:
    print("\n    ERROR: NOT CONNECTED TO LIVE MT5")
    sys.exit(1)

# 2. Account proof
info = get_account_info()
print(f"\n[2] Account Proof")
print(f"    Name:       {info.get('name')}")
print(f"    Server:     {info.get('server')}")
print(f"    Balance:    ${info.get('balance', 0):,.2f}")
print(f"    Equity:     ${info.get('equity', 0):,.2f}")
print(f"    Leverage:   1:{info.get('leverage', 0)}")
print(f"    Currency:   {info.get('currency')}")

# 3. Live market data proof
print(f"\n[3] Live XAUUSD Market Data (from MT5)")
rates = get_rates("XAUUSD", "H1", 3)
if rates:
    print(f"    Retrieved {len(rates)} live candles:")
    for r in rates:
        print(f"    {r['time']}  O={r['open']:.2f}  H={r['high']:.2f}  L={r['low']:.2f}  C={r['close']:.2f}")
else:
    print("    ERROR: No data received")

last = get_last_price("XAUUSD")
if last:
    print(f"    Bid: {last.get('bid')}  Ask: {last.get('ask')}  Spread: {last.get('spread')} pips")

# 4. Positions
positions = get_positions()
print(f"\n[4] Open Positions: {len(positions) if positions else 0}")

print("\n" + "=" * 70)
print("  RESULT: Bot IS connected to live MT5 demo account")
print("=" * 70)
