#!/usr/bin/env python
"""
Test OsMA_RegimeAdaptive strategy

Tests the new regime-aware strategy with:
- ADX-based consolidation detection
- Higher profit targets (ATR * 2.0)
- Stronger entry filters
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.learning.backtester import Backtester
from src.learning.strategy_registry import StrategyRegistry
from src.utils.logger import get_logger

logger = get_logger("backtest.regime_adaptive")

SYMBOLS = ["BTCUSD", "GER40", "XAUUSD"]

def test_regime_adaptive():
    """Test OsMA_RegimeAdaptive strategy."""
    print("\n" + "="*100)
    print("TESTING: OsMA_RegimeAdaptive (Regime-Aware with ADX Filtering)")
    print("="*100 + "\n")
    
    registry = StrategyRegistry()
    backtester = Backtester(registry)
    
    strategy = registry.get("OsMA_RegimeAdaptive")
    if not strategy:
        print("❌ OsMA_RegimeAdaptive not found\n")
        return
    
    print(f"Description: {strategy.description}\n")
    
    results = {}
    
    for symbol in SYMBOLS:
        print(f"  {symbol}...", end=" ", flush=True)
        
        try:
            bt_results = backtester.walkforward_focused(
                symbol=symbol,
                params=strategy.params,
                timeframe="M15"
            )
            
            if not bt_results:
                print("❌ No results")
                continue
            
            pfs = bt_results.get("pfs", [])
            wrs = bt_results.get("wrs", [])
            n_total = bt_results.get("n_total", 0)
            generalizes = bt_results.get("generalizes", False)
            score = bt_results.get("score", 0)
            
            results[symbol] = {
                'pfs': pfs,
                'wrs': wrs,
                'n_total': n_total,
                'generalizes': generalizes,
                'score': score,
                'avg_pf': sum(pfs) / len(pfs) if pfs else 0,
                'avg_wr': sum(wrs) / len(wrs) if wrs else 0,
            }
            
            status = "✓" if score >= 1.15 else "✗"
            print(f"{status} PF={score:.2f} (avg {results[symbol]['avg_pf']:.2f}), "
                  f"Trades={n_total}, Gen={'Y' if generalizes else 'N'}")
            
            # Print window breakdown
            for i, (pf, wr) in enumerate(zip(pfs, wrs), 1):
                w_status = "✓" if pf >= 1.0 else "✗"
                print(f"       W{i}: PF={pf:.2f} {w_status}, WR={wr:.1f}%")
        
        except Exception as e:
            print(f"❌ Error: {str(e)[:60]}")
            import traceback
            traceback.print_exc()
    
    print_analysis(results)
    return results


def print_analysis(results):
    """Print analysis of results."""
    print("\n" + "="*100)
    print("ANALYSIS")
    print("="*100 + "\n")
    
    if not results:
        print("No results to analyze")
        return
    
    passing = sum(1 for r in results.values() if r['score'] >= 1.15)
    total = len(results)
    
    print(f"Symbols tested: {total}")
    print(f"Passing (PF ≥ 1.15): {passing}/{total}")
    
    for symbol, data in results.items():
        print(f"\n{symbol}:")
        print(f"  Min PF (robust): {data['score']:.2f}")
        print(f"  Avg PF: {data['avg_pf']:.2f}")
        print(f"  Avg WR: {data['avg_wr']:.1f}%")
        print(f"  Total trades: {data['n_total']}")
        print(f"  Generalizes: {'Yes' if data['generalizes'] else 'No'}")
    
    if passing > 0:
        print(f"\n✅ SUCCESS: {passing} symbols are profitable!")
        print("Next: Run comprehensive comparison with other strategies")
    else:
        print(f"\n❌ No symbols meet threshold")
        print("Options:")
        print("  1. Increase TP multiplier further (ATR * 3.0)")
        print("  2. Tighten SL (ATR * 1.0)")
        print("  3. Adjust ADX threshold (try 15 instead of 20)")
        print("  4. Add additional entry filters (RSI, volume)")


if __name__ == "__main__":
    try:
        results = test_regime_adaptive()
        print("\n✓ Test complete\n")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
