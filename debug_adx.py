#!/usr/bin/env python
"""Debug: Check what ADX values are actually being passed to strategies."""

import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.data_acquisition.manager import DataManager, DataSourceConfig
from src.strategies.indicators import compute_indicator_series

print("\nChecking ADX values in backtest data...\n")

dm = DataManager(DataSourceConfig(broker="vt_markets"))
bars = dm.get_rates("BTCUSD", "M15", count=12000)
df = pd.DataFrame(bars)

# Calculate indicators
print("Calculating indicators...")
ind_params = {
    'bb_period': 20,
    'bb_std': 2,
    'adx_period': 14,
    'atr_period': 14,
    'rsi_period': 14,
}

indicators_list = compute_indicator_series(df, ind_params)

print(f"Total bars with indicators: {len(indicators_list)}")
print()

# Check ADX across windows
window_size = 4000
for window_name, (start, end) in [("W1", (0, 4000)), ("W2", (4000, 8000)), ("W3", (8000, 12000))]:
    if end > len(indicators_list):
        continue
    
    adx_values = [ind.get('adx', 0) for ind in indicators_list[start:end]]
    
    print(f"{window_name} (bars {start:,}-{end:,}):")
    print(f"  Mean ADX: {sum(adx_values)/len(adx_values):.2f}")
    print(f"  Min ADX: {min(adx_values):.2f}")
    print(f"  Max ADX: {max(adx_values):.2f}")
    print(f"  ADX < 20 (consolidation): {sum(1 for a in adx_values if a < 20)/len(adx_values)*100:.1f}%")
    print(f"  ADX >= 20 (trending): {sum(1 for a in adx_values if a >= 20)/len(adx_values)*100:.1f}%")
    print()

# Check a few sample bars
print("Sample bar ADX values:")
for i in [100, 500, 1000, 4100, 4500, 8100, 8500]:
    if i < len(indicators_list):
        ind = indicators_list[i]
        print(f"  Bar {i:,}: ADX={ind.get('adx', 0):.2f}, "
              f"BB_upper={ind.get('bb_upper', 0):.2f}, "
              f"OSsMA={ind.get('osma', 0):.4f}")
