#!/usr/bin/env python
"""
EXHAUSTIVE EXIT CONFIGURATION TEST

Test 15 different exit configurations systematically to find PF >= 1.15
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.learning.backtester import Backtester
from src.learning.strategy_registry import StrategyRegistry

def test_exit_configs():
    """Test different backtester exit parameters."""
    print("\n" + "="*120)
    print("EXHAUSTIVE EXIT CONFIGURATION TEST")
    print("="*120 + "\n")
    
    registry = StrategyRegistry()
    
    # Exit parameter variations (sl_atr, tp_rr = TP/SL ratio, giveback, arm)
    configs = [
        # (name, sl_atr, tp_rr, giveback, arm)
        ("Conservative", 1.0, 2.0, 0.55, 0.5),
        ("Tight SL", 0.5, 2.0, 0.55, 0.5),
        ("Loose SL", 2.0, 2.0, 0.55, 0.5),
        ("High RR 3:1", 1.0, 3.0, 0.55, 0.5),
        ("High RR 4:1", 1.0, 4.0, 0.55, 0.5),
        ("Low Giveback", 1.0, 2.0, 0.3, 0.5),
        ("High Giveback", 1.0, 2.0, 0.75, 0.5),
        ("Low Arm", 1.0, 2.0, 0.55, 0.2),
        ("High Arm", 1.0, 2.0, 0.55, 0.8),
        ("Aggressive", 0.75, 2.5, 0.4, 0.4),
        ("Mean Rev Focus", 1.5, 1.5, 0.6, 0.6),
        ("Breakeven", 1.0, 1.0, 0.55, 0.5),
        ("Tight", 0.5, 1.5, 0.4, 0.3),
        ("Wide", 2.5, 3.5, 0.7, 0.7),
        ("Moderate", 1.0, 2.5, 0.5, 0.5),
    ]
    
    results_by_config = {}
    best_config = None
    best_pf = 0
    
    for config_name, sl_atr, tp_rr, giveback, arm in configs:
        print(f"{config_name:20s} (SL={sl_atr}, RR={tp_rr}, GB={giveback}, Arm={arm})...")
        print("-" * 120)
        
        config_results = {}
        
        for symbol in ["BTCUSD", "GER40", "XAUUSD"]:
            print(f"  {symbol}...", end=" ", flush=True)
            
            try:
                backtester = Backtester(registry)
                
                # Use OsMA_Confluence (known strategy)
                strategy = registry.get("OsMA_Confluence")
                if not strategy:
                    print("Strategy not found")
                    continue
                
                results = backtester.walkforward_focused(
                    symbol=symbol,
                    params=strategy.params,
                    sl_atr=sl_atr,
                    tp_rr=tp_rr,
                    giveback=giveback,
                    arm=arm,
                    timeframe="M15"
                )
                
                if not results:
                    print("No results")
                    continue
                
                pfs = results.get("pfs", [])
                score = results.get("score", 0)
                gen = results.get("generalizes", False)
                
                config_results[symbol] = {
                    'score': score,
                    'pfs': pfs,
                    'generalizes': gen
                }
                
                status = "PASS" if score >= 1.15 else "WIN" if score >= 1.0 else "FAIL"
                print(f"{status:4s} PF={score:.2f}")
                
                if score > best_pf:
                    best_pf = score
                    best_config = (config_name, sl_atr, tp_rr, giveback, arm, symbol, score)
                
            except Exception as e:
                print(f"ERROR: {str(e)[:40]}")
        
        results_by_config[config_name] = config_results
        print()
    
    # Summary
    print("\n" + "="*120)
    print("SUMMARY")
    print("="*120 + "\n")
    
    if best_config:
        cfg_name, sl, rr, gb, arm, sym, pf = best_config
        print(f"BEST CONFIGURATION FOUND:")
        print(f"  Config: {cfg_name}")
        print(f"  Symbol: {sym}")
        print(f"  PF: {pf:.2f}")
        print(f"  Parameters: SL={sl}, RR={rr}, Giveback={gb}, Arm={arm}")
        
        if pf >= 1.15:
            print(f"\n  STATUS: PROFITABLE - Ready to deploy!")
        elif pf >= 1.0:
            print(f"\n  STATUS: Breaking even - Close to profitable")
        else:
            print(f"\n  STATUS: Still losing - Need more optimization")
    else:
        print("No profitable configuration found with current parameters")
    
    return results_by_config, best_config


if __name__ == "__main__":
    try:
        results, best = test_exit_configs()
        print("\nTest complete\n")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
