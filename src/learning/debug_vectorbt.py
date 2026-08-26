"""
COMPREHENSIVE VECTORBT PIPELINE - Debug version
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import vectorbt as vbt
import pandas as pd
import pandas_ta as ta
import numpy as np
import optuna
from optuna.pruners import MedianPruner
import json
from datetime import datetime
import logging
import traceback

from src.mt5.data import get_rates
from src.utils.logger import get_logger

logger = get_logger("vectorbt_debug")

# Load data
print("Loading MT5 data...")
rates = get_rates(symbol="BTCUSD", timeframe="H1", count=500, lock=True)
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
df.set_index('time', inplace=True)
df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)

print("Data loaded: {} bars\n".format(len(df)))

price = df['close']
high = df['high']
low = df['low']
volume = df['volume']

results = []

# Test VectorBT RSI
print("Testing RSI...")
try:
    ind = vbt.indicators.RSI.run(price)
    print("  RSI result type: {}".format(type(ind)))
    print("  RSI result: {}".format(ind))
    
    # Try to create entries
    entries = ind < 30
    print("  Entries type: {}".format(type(entries)))
    print("  Entries shape: {}".format(entries.shape if hasattr(entries, 'shape') else len(entries)))
    print("  Entries count: {}".format(entries.sum() if hasattr(entries, 'sum') else np.sum(entries)))
    
except Exception as e:
    print("  ERROR: {}".format(e))
    traceback.print_exc()

print("\nTesting BBANDS...")
try:
    ind = vbt.indicators.BBANDS.run(price)
    print("  BBANDS result type: {}".format(type(ind)))
    
    entries = price < ind.lower
    exits = price > ind.upper
    
    print("  Entries count: {}".format(entries.sum()))
    print("  Exits count: {}".format(exits.sum()))
    
    if entries.sum() > 2:
        pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=10000)
        print("  PF: {:.2f}".format(pf.trades.profit_factor() or 0))
        
except Exception as e:
    print("  ERROR: {}".format(e))
    traceback.print_exc()

print("\nTesting pandas_ta RSI...")
try:
    ind = ta.rsi(price)
    print("  RSI type: {}".format(type(ind)))
    print("  RSI shape: {}".format(ind.shape if hasattr(ind, 'shape') else len(ind)))
    
    entries = ind > ind.rolling(5).mean()
    print("  Entries count: {}".format(entries.sum()))
    
    if entries.sum() > 2:
        pf = vbt.Portfolio.from_signals(price, entries, ~entries, init_cash=10000)
        print("  PF: {:.2f}".format(pf.trades.profit_factor() or 0))
        
except Exception as e:
    print("  ERROR: {}".format(e))
    traceback.print_exc()

print("\nDone")
