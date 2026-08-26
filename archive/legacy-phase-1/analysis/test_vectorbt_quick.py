#!/usr/bin/env python
"""Quick test of vectorbt backtester."""

import sys
sys.path.insert(0, '.')

from src.learning.vectorbt_backtester import VectorbtBacktester

bt = VectorbtBacktester()

print('Testing vectorbt backtester on XAUUSD...')
ohlcv = bt.load_data('XAUUSD', count=4000)
print(f'Loaded {len(ohlcv)} bars')

indicators = bt.calculate_indicators(ohlcv)
print(f'Calculated {len(indicators)} indicators')

entries = bt.test_entry_signal(ohlcv, indicators, 'rsi_bb')
print(f'Generated {int(entries.sum())} entry signals')

result = bt.backtest_vectorized(ohlcv, entries, sl_atr=2.5, tp_rr=3.5)
print()
print(f'Result: PF={result["pf"]:.2f}, WR={result["wr"]*100:.1f}%, Trades={result["trades"]}')
