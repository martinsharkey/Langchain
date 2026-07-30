#!/usr/bin/env python3
"""
MT5 Connection Diagnostic — proves the bot is connected to live MT5.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.mt5.connector import get_connector
from src.mt5.data import get_rates, get_last_price
from src.mt5.account import get_account_info, get_positions

print("=" * 60)
print("MT5 CONNECTION PROOF")
print("=" * 60)

# 1. Connector
c = get_connector()
print("\n1. Connector State")
print(f"   Before init -> connected={c.is_connected()}, simulation={c.in_simulation_mode}")

ok = c.initialize()
print(f"   initialize() -> {ok}")
print(f"   After init  -> connected={c.is_connected()}, simulation={c.in_simulation_mode}")

# 2. Account
info = get_account_info()
print("\n2. Account Information")
if info:
    print(f"   Name:       {info.get('name')}")
    print(f"   Server:     {info.get('server')}")
    print(f"   Balance:    ${info.get('balance', 0):,.2f}")
    print(f"   Equity:     ${info.get('equity', 0):,.2f}")
    print(f"   Leverage:   1:{info.get('leverage', 0)}")
    print(f"   Currency:   {info.get('currency')}")
    print(f"   Simulated:  {info.get('simulated')}")
else:
    print("   ERROR: No account info returned")

# 3. Live market data
print("\n3. Live XAUUSD Market Data")
rates = get_rates("XAUUSD", "H1", 3)
if rates:
    print(f"   Retrieved {len(rates)} candles from MT5:")
    for r in rates[-3:]:
        print(f"   {r['time']}  O={r['open']:.2f}  H={r['high']:.2f}  L={r['low']:.2f}  C={r['close']:.2f}  Vol={r['volume']}")
else:
    print("   ERROR: No rates returned")

last = get_last_price("XAUUSD")
if last:
    print(f"   Last price: Bid={last.get('bid')}  Ask={last.get('ask')}  Spread={last.get('spread')} pips")
else:
    print("   ERROR: No last price returned")

# 4. Positions
positions = get_positions()
print(f"\n4. Open Positions: {len(positions) if positions else 0}")
if positions:
    for p in positions:
        print(f"   {p}")
else:
    print("   No open positions")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
