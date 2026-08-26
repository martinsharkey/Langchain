#!/usr/bin/env python
"""
BRUTE-FORCE OPTIMIZATION ENGINE

Tests hundreds of combinations of:
- 20+ available entry strategies
- 25+ exit configurations
- Different indicator parameter sets

Goal: Find PF >= 1.8-2.0 on BTCUSD
"""

import sys
from pathlib import Path
import itertools

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.learning.backtester import Backtester
from src.learning.strategy_registry import StrategyRegistry
from src.utils.logger import get_logger

logger = get_logger("optimizer.brute_force")

def get_all_strategies():
    """Get all available strategies to test."""
    registry = StrategyRegistry()
    strategies = [s.name for s in registry.get_all()]
    return strategies

def get_exit_configs():
    """Generate exit parameter configurations to test."""
    configs = [
        # (name, sl_atr, tp_rr, giveback, arm)
        ("Micro SL", 0.3, 2.0, 0.5, 0.5),
        ("Micro+ SL", 0.5, 2.0, 0.5, 0.5),
        ("Tight SL", 0.75, 2.0, 0.5, 0.5),
        ("Standard", 1.0, 2.0, 0.55, 0.5),
        ("Wide SL", 1.5, 2.0, 0.6, 0.5),
        ("Extra Wide", 2.0, 2.0, 0.65, 0.5),
        ("Huge SL", 2.5, 2.0, 0.7, 0.5),
        ("High RR 2.5", 1.0, 2.5, 0.55, 0.5),
        ("High RR 3.0", 1.0, 3.0, 0.55, 0.5),
        ("High RR 4.0", 1.0, 4.0, 0.55, 0.5),
        ("Low Giveback", 1.0, 2.0, 0.3, 0.5),
        ("High Giveback", 1.0, 2.0, 0.75, 0.5),
        ("Low Arm", 1.0, 2.0, 0.5, 0.2),
        ("High Arm", 1.0, 2.0, 0.5, 0.8),
        ("Aggressive", 0.75, 2.5, 0.4, 0.4),
        ("Conservative", 1.5, 1.5, 0.6, 0.6),
        ("Mean Rev 1", 1.5, 1.5, 0.65, 0.65),
        ("Mean Rev 2", 2.0, 2.5, 0.7, 0.7),
        ("Breakout", 2.5, 3.5, 0.7, 0.7),
        ("Extreme", 3.0, 4.0, 0.75, 0.75),
        ("Ultra", 4.0, 5.0, 0.8, 0.8),
        ("Micro Profits", 0.5, 1.2, 0.4, 0.3),
        ("Scalp", 0.25, 1.5, 0.3, 0.2),
        ("Swing", 2.0, 3.0, 0.7, 0.7),
        ("Trend", 3.0, 2.0, 0.8, 0.8),
    ]
    return configs

def test_combination(strategy_name, exit_config, backtester, registry):
    """Test a single strategy + exit config combination."""
    try:
        strategy = registry.get(strategy_name)
        if not strategy:
            return None
        
        cfg_name, sl_atr, tp_rr, giveback, arm = exit_config
        
        results = backtester.walkforward_focused(
            symbol="BTCUSD",
            params=strategy.params,
            sl_atr=sl_atr,
            tp_rr=tp_rr,
            giveback=giveback,
            arm=arm,
            timeframe="M15",
            windows=3
        )
        
        if not results:
            return None
        
        pfs = results.get("pfs", [])
        wrs = results.get("wrs", [])
        score = results.get("score", 0)
        gen = results.get("generalizes", False)
        
        return {
            'strategy': strategy_name,
            'exit_config': cfg_name,
            'sl_atr': sl_atr,
            'tp_rr': tp_rr,
            'giveback': giveback,
            'arm': arm,
            'min_pf': score,
            'pfs': pfs,
            'avg_wr': sum(wrs) / len(wrs) if wrs else 0,
            'generalizes': gen
        }
    
    except Exception as e:
        return None

def run_brute_force():
    """Run exhaustive brute-force optimization."""
    print("\n" + "="*120)
    print("BRUTE-FORCE OPTIMIZATION ENGINE FOR BTCUSD")
    print("="*120 + "\n")
    
    registry = StrategyRegistry()
    backtester = Backtester(registry)
    
    strategies = get_all_strategies()
    exit_configs = get_exit_configs()
    
    print(f"Testing combinations:")
    print(f"  Strategies: {len(strategies)}")
    print(f"  Exit configs: {len(exit_configs)}")
    print(f"  Total combinations: {len(strategies) * len(exit_configs)}")
    print(f"  Target: PF >= 1.8\n")
    
    results = []
    tested = 0
    found_winners = []
    
    for strategy_name in strategies:
        print(f"\n{strategy_name}")
        print("-" * 120)
        
        for exit_config in exit_configs:
            cfg_name = exit_config[0]
            
            print(f"  {cfg_name:20s}...", end=" ", flush=True)
            
            result = test_combination(strategy_name, exit_config, backtester, registry)
            tested += 1
            
            if result:
                results.append(result)
                
                pf = result['min_pf']
                wr = result['avg_wr']
                gen = "GEN" if result['generalizes'] else "ONE"
                
                if pf >= 1.5:
                    status = f"WINNER PF={pf:.2f}"
                    found_winners.append(result)
                elif pf >= 1.2:
                    status = f"CLOSE PF={pf:.2f}"
                elif pf >= 1.0:
                    status = f"GOOD PF={pf:.2f}"
                else:
                    status = f"FAIL PF={pf:.2f}"
                
                print(f"{status}, WR={wr:.1f}%, {gen}")
            else:
                print("SKIP")
    
    # Print summary
    print("\n" + "="*120)
    print("TOP WINNERS (PF >= 1.5)")
    print("="*120 + "\n")
    
    if found_winners:
        # Sort by PF descending
        found_winners.sort(key=lambda x: x['min_pf'], reverse=True)
        
        for i, result in enumerate(found_winners[:10], 1):
            print(f"{i}. {result['strategy']:30s} + {result['exit_config']:15s}")
            print(f"   PF: {result['min_pf']:.2f}, WR: {result['avg_wr']:.1f}%, "
                  f"SL={result['sl_atr']}, RR={result['tp_rr']}, GB={result['giveback']}, Arm={result['arm']}")
            print(f"   Windows: {', '.join([f'{pf:.2f}' for pf in result['pfs']])}")
            print()
    else:
        print("No winners with PF >= 1.5 found yet")
        print("\nTop 10 results so far:")
        
        sorted_results = sorted(results, key=lambda x: x['min_pf'], reverse=True)
        for i, result in enumerate(sorted_results[:10], 1):
            print(f"{i}. {result['strategy']:30s} + {result['exit_config']:15s}: PF={result['min_pf']:.2f}")
    
    print(f"\n\nTotal tested: {tested}")
    print(f"Success rate: {len(found_winners)}/{tested} combinations with PF >= 1.5")
    
    return found_winners


if __name__ == "__main__":
    try:
        winners = run_brute_force()
        print("\nOptimization complete\n")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
