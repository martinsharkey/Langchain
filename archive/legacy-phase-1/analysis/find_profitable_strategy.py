#!/usr/bin/env python
"""
Test strategies that showed historical profitability

From edge_weights.py comments:
- Volume_Breakout: PF 1.32 on XAUUSD
- BB_Bounce: PF 1.54 in RANGING, profitable in specific regimes
- ADX_TrendStrength, EMA_TrendFollow: Showed edge
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.learning.backtester import Backtester
from src.learning.strategy_registry import StrategyRegistry
from src.utils.logger import get_logger

logger = get_logger("backtest.profitable_strategies")

# Test individual strategies that showed historical profitability
TEST_CONFIGS = [
    ("XAUUSD", "M15", ["Volume_Breakout", "BB_Bounce", "ADX_TrendStrength", "EMA_TrendFollow"]),
    ("GER40", "M5", ["ADX_TrendStrength", "EMA_TrendFollow", "MACD_Cross"]),
    ("BTCUSD", "M15", ["Volume_Breakout", "BB_Bounce"]),
]

def test_profitable_strategies():
    """Test strategies one by one to find winners."""
    print("\n" + "="*120)
    print("SEARCHING FOR PROFITABLE STRATEGIES")
    print("="*120 + "\n")
    
    registry = StrategyRegistry()
    backtester = Backtester(registry)
    
    winners = []
    
    for symbol, timeframe, strategies in TEST_CONFIGS:
        print(f"\n{symbol} {timeframe}")
        print("-" * 120)
        
        for strategy_name in strategies:
            strategy = registry.get(strategy_name)
            if not strategy:
                print(f"  ❌ {strategy_name}: Not in registry")
                continue
            
            print(f"  Testing {strategy_name}...", end=" ", flush=True)
            
            try:
                # Run simplified backtest on single window first
                results = backtester.walkforward_focused(
                    symbol=symbol,
                    params=strategy.params,
                    timeframe=timeframe,
                    windows=3
                )
                
                if not results:
                    print("❌ No results")
                    continue
                
                pfs = results.get("pfs", [])
                wrs = results.get("wrs", [])
                score = results.get("score", 0)
                generalizes = results.get("generalizes", False)
                n_total = results.get("n_total", 0)
                
                # Check if profitable
                if score >= 1.0:
                    status = "✓ PROFITABLE"
                    winners.append((symbol, strategy_name, timeframe, score, pfs, n_total))
                elif score >= 0.95:
                    status = "~ CLOSE (0.95-1.0)"
                else:
                    status = "✗ Losing"
                
                gen_str = "GEN" if generalizes else "ONE-WINDOW"
                print(f"{status}: PF={score:.2f} ({gen_str}), Trades={n_total}")
                
            except Exception as e:
                print(f"❌ Error: {str(e)[:40]}")
    
    print("\n" + "="*120)
    print("WINNERS FOUND")
    print("="*120 + "\n")
    
    if winners:
        print(f"Found {len(winners)} profitable configuration(s):\n")
        for symbol, strategy_name, tf, pf, pfs, trades in winners:
            print(f"✓ {symbol} {tf} using {strategy_name}")
            print(f"    Min PF (robust): {pf:.2f}")
            print(f"    Windows: {', '.join([f'{p:.2f}' for p in pfs])}")
            print(f"    Trades: {trades}")
            print()
    else:
        print("❌ No profitable configs found")
        print("\nTrying alternative approach: Test ALL available strategies...")
    
    return winners


if __name__ == "__main__":
    try:
        winners = test_profitable_strategies()
        
        if not winners:
            print("\n⚠️  Need to try broader search or develop new strategy")
        
        print("\n✓ Complete\n")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
