#!/usr/bin/env python
"""
Comprehensive Strategy Optimization Test

Tests multiple variations:
1. Original OsMA_Confluence
2. Bollinger_OsMA (growing momentum)
3. Bollinger_OsMA (shrinking momentum/divergence)
4. Enhanced OsMA (regime detection + improved exits)

Runs full walk-forward backtest on BTCUSD to identify best approach.
"""

import sys
from pathlib import Path
import pandas as pd
from datetime import datetime

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.learning.backtester import Backtester
from src.learning.strategy_registry import StrategyRegistry
from src.utils.logger import get_logger

logger = get_logger("backtest.optimization")

STRATEGIES = [
    "OsMA_Confluence",
    "Bollinger_OsMA"
]

SYMBOLS = ["BTCUSD", "GER40", "XAUUSD"]

def run_strategy_tests():
    """Run all strategy variations."""
    print("\n" + "="*120)
    print("COMPREHENSIVE STRATEGY OPTIMIZATION TEST")
    print("="*120 + "\n")
    
    registry = StrategyRegistry()
    backtester = Backtester(registry)
    
    all_results = {}
    
    for strategy_name in STRATEGIES:
        print(f"\n{'='*120}")
        print(f"TESTING: {strategy_name}")
        print(f"{'='*120}\n")
        
        strategy = registry.get(strategy_name)
        if not strategy:
            print(f"❌ {strategy_name} not found\n")
            continue
        
        print(f"Description: {strategy.description}\n")
        
        strategy_results = {}
        
        for symbol in SYMBOLS:
            print(f"  {symbol}...", end=" ", flush=True)
            
            try:
                results = backtester.walkforward_focused(
                    symbol=symbol,
                    params=strategy.params,
                    timeframe="M15"
                )
                
                if not results:
                    print("❌ No results")
                    continue
                
                pfs = results.get("pfs", [])
                wrs = results.get("wrs", [])
                n_total = results.get("n_total", 0)
                generalizes = results.get("generalizes", False)
                score = results.get("score", 0)
                
                strategy_results[symbol] = {
                    'pfs': pfs,
                    'wrs': wrs,
                    'n_total': n_total,
                    'generalizes': generalizes,
                    'score': score,
                    'avg_pf': sum(pfs) / len(pfs) if pfs else 0,
                    'avg_wr': sum(wrs) / len(wrs) if wrs else 0,
                    'window_details': ', '.join([f"W{i+1}:{pf:.2f}" for i, pf in enumerate(pfs)])
                }
                
                # Print compact result
                status = "✓" if score >= 1.15 else "✗"
                print(f"{status} PF={score:.2f} (avg {strategy_results[symbol]['avg_pf']:.2f}), "
                      f"Trades={n_total}, Gen={'Y' if generalizes else 'N'}")
                
            except Exception as e:
                print(f"❌ Error: {str(e)[:50]}")
        
        all_results[strategy_name] = strategy_results
    
    # Print summary
    print_summary(all_results)
    return all_results


def print_summary(all_results):
    """Print comparison summary."""
    print("\n" + "="*120)
    print("SUMMARY COMPARISON")
    print("="*120 + "\n")
    
    # Build comparison table
    print(f"{'Strategy':<25} {'Symbol':<12} {'Min PF':<10} {'Avg PF':<10} {'Trades':<10} {'Generalizes':<12} {'Status':<10}")
    print("-" * 120)
    
    best_overall = None
    best_pf = 0
    
    for strategy_name, symbols_data in all_results.items():
        for symbol, data in symbols_data.items():
            min_pf = data['score']
            avg_pf = data['avg_pf']
            trades = data['n_total']
            generalizes = data['generalizes']
            status = "✓ PASS" if min_pf >= 1.15 else "✗ FAIL"
            
            if min_pf > best_pf:
                best_pf = min_pf
                best_overall = (strategy_name, symbol)
            
            print(f"{strategy_name:<25} {symbol:<12} {min_pf:<10.2f} {avg_pf:<10.2f} {trades:<10d} "
                  f"{'Yes' if generalizes else 'No':<12} {status:<10}")
    
    # Overall stats
    print("\n" + "="*120)
    print("ANALYSIS")
    print("="*120 + "\n")
    
    total_configs = sum(len(s) for s in all_results.values())
    passing_configs = sum(1 for s in all_results.values() for d in s.values() if d['score'] >= 1.15)
    
    print(f"Total configurations tested: {total_configs}")
    print(f"Passing configurations (PF ≥ 1.15): {passing_configs}/{total_configs}")
    
    if best_overall:
        best_strat, best_sym = best_overall
        best_data = all_results[best_strat][best_sym]
        print(f"\nBest performer: {best_strat} on {best_sym}")
        print(f"  Min PF: {best_data['score']:.2f}")
        print(f"  Avg PF: {best_data['avg_pf']:.2f}")
        print(f"  Windows: {best_data['window_details']}")
        print(f"  Trades: {best_data['n_total']}")
        print(f"  Generalizes: {'Yes' if best_data['generalizes'] else 'No'}")
    else:
        print("\n❌ No configurations meet minimum threshold (PF ≥ 1.15)")
        print("   All strategies need improvement")
    
    # Recommendations
    print("\n" + "="*120)
    print("RECOMMENDATIONS")
    print("="*120 + "\n")
    
    if passing_configs == 0:
        print("1. PRIMARY: Implement regime detection (skip consolidation)")
        print("2. Improve exit logic (use momentum reversal or ATR-based TP)")
        print("3. Add Win Rate filters (skip low-probability entry patterns)")
        print("4. Consider tighter entry filters (require stronger signals)")
    elif passing_configs < total_configs / 2:
        print("1. Regime detection is partially working")
        print("2. Focus on improving exit logic for better risk/reward")
        print("3. Optimize parameters per symbol (different regimes)")
    else:
        print("1. Current configuration is viable")
        print("2. Fine-tune parameters for better consistency")
        print("3. Test on live data for final validation")


if __name__ == "__main__":
    try:
        results = run_strategy_tests()
        
        print("\n" + "="*120)
        print("✓ All tests complete")
        print("="*120 + "\n")
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
