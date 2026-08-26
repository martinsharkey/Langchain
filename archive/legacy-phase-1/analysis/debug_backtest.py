#!/usr/bin/env python
"""Debug script to inspect Bollinger_OsMA backtest results."""

import sys
import json
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.learning.backtester import Backtester
from src.learning.strategy_registry import StrategyRegistry

registry = StrategyRegistry()
backtester = Backtester(registry)

print("Running walk-forward backtest on BTCUSD M15...")
results = backtester.walkforward_focused(
    symbol="BTCUSD",
    params={},
    timeframe="M15"
)

print("\nRaw results:")
print(json.dumps(results, indent=2))

# Extract and analyze
if results:
    pfs = results.get("pfs", [])
    wrs = results.get("wrs", [])
    n_total = results.get("n_total", 0)
    generalizes = results.get("generalizes", False)
    score = results.get("score", 0)
    
    print(f"\nPFs: {pfs}")
    print(f"WRs: {wrs}")
    print(f"Total trades: {n_total}")
    print(f"Generalizes: {generalizes}")
    print(f"Score: {score}")
