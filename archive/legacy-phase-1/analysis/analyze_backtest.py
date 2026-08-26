#!/usr/bin/env python
"""Detailed backtest analysis - show trade breakdown."""

import sys
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

if results:
    print("\n" + "="*80)
    print("BOLLINGER_OSMA BACKTEST RESULTS")
    print("="*80)
    
    pfs = results.get("pfs", [])
    wrs = results.get("wrs", [])
    n_total = results.get("n_total", 0)
    generalizes = results.get("generalizes", False)
    score = results.get("score", 0)
    
    print(f"\nWindow Breakdown:")
    for i, (pf, wr) in enumerate(zip(pfs, wrs), 1):
        print(f"  Window {i}: PF={pf:.2f}, WR={wr:.1f}%")
    
    print(f"\nAggregate:")
    print(f"  Total trades: {n_total}")
    print(f"  Generalizes: {generalizes}")
    print(f"  Min-window PF: {score:.2f}")
    
    print(f"\nThreshold Checks:")
    print(f"  All windows PF >= 1.0: {'✓ PASS' if all(pf >= 1.0 for pf in pfs) else '✗ FAIL'}")
    print(f"  Min-window PF >= 1.15: {'✓ PASS' if score >= 1.15 else '✗ FAIL'}")
    
    # Show session breakdown if available
    per_session = results.get("per_session", {})
    if per_session:
        print(f"\nPer-Session Breakdown:")
        for session_name, session_data in per_session.items():
            trades = session_data.get("trades", 0)
            pf = session_data.get("pf", 0)
            wr = session_data.get("wr", 0)
            if trades > 0:
                print(f"  {session_name:12s}: {trades:4d} trades, PF={pf:.2f}, WR={wr:.1f}%")
    
    # Analysis
    print(f"\n" + "="*80)
    if score < 1.0:
        print("❌ STRATEGY IS LOSING MONEY")
        print(f"\nThe fixed divergence check is detecting too few or wrong trades.")
        print(f"Current logic: divergence = abs(t2) > abs(prev) > abs(now)")
        print(f"This requires shrinking momentum which may be too restrictive.")
    else:
        print("✅ STRATEGY IS PROFITABLE")
        print(f"Fixed divergence logic is working correctly.")

