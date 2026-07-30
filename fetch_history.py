#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from src.mt5.account import get_history
from src.mt5.connector import get_connector

c = get_connector()
c.initialize()

print("=" * 70)
print("HISTORICAL TRADES FROM VT MARKETS DEMO ACCOUNT")
print("=" * 70)

history = get_history(deals=100)
if history and not any("error" in h for h in history):
    print(f"\nFound {len(history)} trades\n")
    for i, trade in enumerate(history):
        print(f"{i+1}. Ticket: {trade['ticket']} | {trade['type'].upper():4s} {trade['symbol']} x{trade['volume']} @ {trade['price']:.2f} | P&L: ${trade['profit']:+.2f} | Time: {trade['time']}")
    
    print("\n" + "=" * 70)
    print("TRADE ANALYSIS")
    print("=" * 70)
    
    total_trades = len(history)
    wins = sum(1 for t in history if t['profit'] > 0)
    losses = sum(1 for t in history if t['profit'] < 0)
    breakeven = sum(1 for t in history if t['profit'] == 0)
    total_profit = sum(t['profit'] for t in history)
    total_commission = sum(t.get('commission', 0) for t in history)
    
    print(f"\nTotal trades: {total_trades}")
    print(f"Wins: {wins} ({wins/total_trades*100:.1f}%)")
    print(f"Losses: {losses} ({losses/total_trades*100:.1f}%)")
    print(f"Breakeven: {breakeven}")
    print(f"Total P&L: ${total_profit:.2f}")
    print(f"Total Commission: ${total_commission:.2f}")
    print(f"Net P&L: ${total_profit - total_commission:.2f}")
    print(f"Avg P&L per trade: ${total_profit/total_trades:.2f}")
    
    # Group by symbol
    print("\n" + "=" * 70)
    print("BY SYMBOL")
    print("=" * 70)
    symbols = {}
    for trade in history:
        sym = trade['symbol']
        if sym not in symbols:
            symbols[sym] = {'count': 0, 'pnl': 0, 'trades': []}
        symbols[sym]['count'] += 1
        symbols[sym]['pnl'] += trade['profit']
        symbols[sym]['trades'].append(trade)
    
    for sym, data in sorted(symbols.items()):
        print(f"\n{sym}: {data['count']} trades, P&L: ${data['pnl']:+.2f}, Avg: ${data['pnl']/data['count']:.2f}")

else:
    print("No historical trades found or error occurred")
    if history:
        print(history)
