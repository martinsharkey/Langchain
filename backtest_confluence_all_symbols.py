#!/usr/bin/env python
"""
OsMA_Confluence Multi-Symbol Backtest

Tests OsMA_Confluence (old entry strategy) across all available symbols.
Compares against Bollinger_OsMA results.
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

logger = get_logger("backtest.confluence_all_symbols")

# Available symbols from project
SYMBOLS = ["BTCUSD", "EURUSD", "GBPUSD", "GER40", "XAUUSD"]

def run_backtests():
    """Run OsMA_Confluence across all symbols."""
    print("\n" + "="*100)
    print("OsMA_CONFLUENCE MULTI-SYMBOL BACKTEST")
    print("="*100 + "\n")
    
    registry = StrategyRegistry()
    backtester = Backtester(registry)
    
    # Verify OsMA_Confluence is available
    confluence = registry.get("OsMA_Confluence")
    if not confluence:
        print("❌ OsMA_Confluence not found in registry!")
        return
    
    print(f"Strategy: {confluence.name}")
    print(f"Description: {confluence.description}\n")
    
    results_by_symbol = {}
    
    for symbol in SYMBOLS:
        print(f"\nTesting {symbol}...")
        print("-" * 100)
        
        try:
            # Run walk-forward backtest
            results = backtester.walkforward_focused(
                symbol=symbol,
                params=confluence.params,
                timeframe="M15"
            )
            
            if not results:
                print(f"  ❌ No results for {symbol}")
                continue
            
            pfs = results.get("pfs", [])
            wrs = results.get("wrs", [])
            n_total = results.get("n_total", 0)
            generalizes = results.get("generalizes", False)
            score = results.get("score", 0)
            
            results_by_symbol[symbol] = {
                'pfs': pfs,
                'wrs': wrs,
                'n_total': n_total,
                'generalizes': generalizes,
                'score': score,
                'avg_pf': sum(pfs) / len(pfs) if pfs else 0,
                'avg_wr': sum(wrs) / len(wrs) if wrs else 0
            }
            
            # Print per-symbol results
            print(f"  Trades: {n_total:,}")
            print(f"  Generalizes: {'✓ YES' if generalizes else '✗ NO'}")
            print(f"  Min-window PF: {score:.2f}")
            
            for i, (pf, wr) in enumerate(zip(pfs, wrs), 1):
                status = "✓" if pf >= 1.0 else "✗"
                print(f"    Window {i}: PF={pf:.2f} {status}, WR={wr:.1f}%")
        
        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    return results_by_symbol


def print_summary(results_by_symbol):
    """Print comparison summary."""
    print("\n" + "="*100)
    print("SUMMARY: OsMA_CONFLUENCE ACROSS ALL SYMBOLS")
    print("="*100 + "\n")
    
    if not results_by_symbol:
        print("No results to summarize")
        return
    
    # Create comparison table
    data = []
    for symbol, res in results_by_symbol.items():
        data.append({
            'Symbol': symbol,
            'Trades': res['n_total'],
            'Avg PF': res['avg_pf'],
            'Min PF': res['score'],
            'Avg WR': res['avg_wr'],
            'Generalizes': 'Yes' if res['generalizes'] else 'No',
            'Profitable': 'Yes' if res['score'] >= 1.0 else 'No'
        })
    
    df = pd.DataFrame(data)
    
    print(df.to_string(index=False))
    
    # Analysis
    print("\n" + "="*100)
    print("ANALYSIS")
    print("="*100 + "\n")
    
    profitable_symbols = [s for s, r in results_by_symbol.items() if r['score'] >= 1.0]
    generalizes_symbols = [s for s, r in results_by_symbol.items() if r['generalizes']]
    
    print(f"Profitable symbols (PF ≥ 1.0): {len(profitable_symbols)}/{len(results_by_symbol)}")
    if profitable_symbols:
        print(f"  {', '.join(profitable_symbols)}")
    
    print(f"\nGeneralizes across all windows: {len(generalizes_symbols)}/{len(results_by_symbol)}")
    if generalizes_symbols:
        print(f"  {', '.join(generalizes_symbols)}")
    
    print(f"\nBest performer: ", end="")
    best_symbol = max(results_by_symbol.items(), key=lambda x: x[1]['score'])
    print(f"{best_symbol[0]} (PF={best_symbol[1]['score']:.2f})")
    
    print(f"Worst performer: ", end="")
    worst_symbol = min(results_by_symbol.items(), key=lambda x: x[1]['score'])
    print(f"{worst_symbol[0]} (PF={worst_symbol[1]['score']:.2f})")
    
    avg_pf = sum(r['score'] for r in results_by_symbol.values()) / len(results_by_symbol)
    print(f"\nAverage PF across all symbols: {avg_pf:.2f}")
    
    # Comparison note
    print("\n" + "="*100)
    print("COMPARISON TO BOLLINGER_OSMA")
    print("="*100 + "\n")
    
    print("Bollinger_OsMA on BTCUSD M15:")
    print("  PF: 0.89-0.98 (all windows losing)")
    print("  Issue: Exit strategy (capturing only 10% of gains)")
    print()
    
    btcusd_conf = results_by_symbol.get("BTCUSD", {})
    if btcusd_conf:
        print(f"OsMA_Confluence on BTCUSD M15:")
        print(f"  PF: {btcusd_conf['score']:.2f} (min window)")
        print(f"  Avg PF: {btcusd_conf['avg_pf']:.2f}")
        print(f"  Generalizes: {'Yes' if btcusd_conf['generalizes'] else 'No'}")


if __name__ == "__main__":
    try:
        results_by_symbol = run_backtests()
        print_summary(results_by_symbol)
        
        print("\n✓ Analysis complete\n")
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
