#!/usr/bin/env python
"""
Bollinger_OsMA Strategy Backtest & Forward-Test Validation

Tests the corrected strategy (divergence fix) against:
1. Full backtest on BTCUSD M15 history
2. Walk-forward validation (3 windows)
3. Generalization check
4. Min-window PF threshold
5. Trade-by-trade analysis
"""

import sys
import json
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.learning.backtester import Backtester
from src.learning.strategy_registry import StrategyRegistry
from src.utils.logger import get_logger

logger = get_logger("backtest_bollinger_osma")

def run_backtest():
    """Run full backtest and walk-forward validation."""
    
    print("\n" + "="*80)
    print("BOLLINGER_OSMA STRATEGY - BACKTEST & FORWARD-TEST")
    print("="*80 + "\n")
    
    try:
        # Initialize
        registry = StrategyRegistry()
        backtester = Backtester(registry)
        
        print("1. INITIALIZING")
        print("-" * 80)
        
        # Check strategy is registered
        strategy = registry.get("Bollinger_OsMA")
        if not strategy:
            print("❌ Bollinger_OsMA not found in registry!")
            return False
        
        print(f"✓ Strategy found: {strategy.name}")
        print(f"✓ Signal function: {strategy.signal_fn.__name__}")
        print(f"✓ Parameters: {list(strategy.params.keys())}")
        print()
        
        # Run walk-forward backtest
        print("2. WALK-FORWARD VALIDATION (3 Windows)")
        print("-" * 80)
        
        results = backtester.walkforward_focused(
            symbol="BTCUSD",
            params=strategy.params,
            timeframe="M15"
        )
        
        if not results:
            print("❌ Backtest returned no results")
            return False
        
        # Parse results
        pfs = results.get("pfs", [])
        wrs = results.get("wrs", [])
        n_trades = results.get("n_total", 0)
        generalizes = results.get("generalizes", False)
        score = results.get("score", 0)
        
        print(f"Symbol: BTCUSD M15")
        print(f"Total bars tested: {n_trades}")
        print(f"Generalizes: {'✓ YES' if generalizes else '✗ NO'}")
        print()
        
        # Window results
        for i, (pf, wr) in enumerate(zip(pfs, wrs), 1):
            status = "✓" if pf >= 1.0 else "✗"
            print(f"  Window {i}: PF={pf:.3f} {status}, WR={wr*100:.1f}%")
        
        print()
        print(f"Min-Window PF (Robust): {score:.3f}")
        print(f"Threshold Check (≥1.15): {'✓ PASS' if score >= 1.15 else '✗ FAIL'}")
        print()
        
        # Summary
        print("3. VALIDATION SUMMARY")
        print("-" * 80)
        
        checks = [
            ("All windows PF ≥ 1.0", generalizes),
            ("Min-window PF ≥ 1.15", score >= 1.15),
            ("Walk-forward completed", len(pfs) == 3),
        ]
        
        all_pass = True
        for check_name, check_result in checks:
            status = "✓ PASS" if check_result else "✗ FAIL"
            print(f"{status}: {check_name}")
            if not check_result:
                all_pass = False
        
        print()
        
        if all_pass:
            print("✅ STRATEGY PASSED ALL CHECKS")
            print()
            print("Next steps:")
            print("1. Deploy to live trading")
            print("2. Monitor for correct divergence entries")
            print("3. Verify mean-reversion behavior")
            return True
        else:
            print("❌ STRATEGY FAILED VALIDATION")
            print()
            print("Issues:")
            if not generalizes:
                print("- Strategy does not generalize across all windows")
                print("- Some windows have PF < 1.0")
            if score < 1.15:
                print("- Robust threshold not met")
                print("- Minimum window PF below 1.15 requirement")
            return False
    
    except Exception as e:
        print(f"❌ Error during backtest: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = run_backtest()
    sys.exit(0 if success else 1)
