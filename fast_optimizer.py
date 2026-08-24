#!/usr/bin/env python
"""
FAST BRUTE-FORCE: Test only the best strategies first
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.learning.backtester import Backtester
from src.learning.strategy_registry import StrategyRegistry

def test_fast():
    """Test only top strategies with different exits."""
    print("\n" + "="*100)
    print("FAST OPTIMIZATION: Top Strategies x Exit Configs (BTCUSD)")
    print("="*100 + "\n")
    
    registry = StrategyRegistry()
    backtester = Backtester(registry)
    
    # Test only strategies that showed promise
    test_strategies = [
        "Volume_Breakout",
        "BB_Bounce", 
        "ADX_TrendStrength",
        "EMA_TrendFollow",
        "MACD_Cross",
        "RSI_MeanReversion"
    ]
    
    # Exit configs
    exit_configs = [
        ("Tight", 0.75, 2.0, 0.5, 0.5),
        ("Standard", 1.0, 2.0, 0.55, 0.5),
        ("Wide", 1.5, 2.5, 0.6, 0.6),
        ("Extreme", 2.5, 3.5, 0.7, 0.7),
        ("Scalp", 0.5, 1.5, 0.4, 0.3),
        ("Swing", 2.0, 3.0, 0.7, 0.7),
    ]
    
    winners = []
    
    for strategy in test_strategies:
        print(f"\n{strategy}")
        print("-" * 100)
        
        strat_obj = registry.get(strategy)
        if not strat_obj:
            print("  Not found")
            continue
        
        for cfg_name, sl, rr, gb, arm in exit_configs:
            print(f"  {cfg_name:15s}...", end=" ", flush=True)
            
            try:
                results = backtester.walkforward_focused(
                    symbol="BTCUSD",
                    params=strat_obj.params,
                    sl_atr=sl,
                    tp_rr=rr,
                    giveback=gb,
                    arm=arm,
                    timeframe="M15"
                )
                
                if not results:
                    print("NO RESULTS")
                    continue
                
                pfs = results.get('pfs', [])
                score = results.get('score', 0)
                gen = results.get('generalizes', False)
                wrs = results.get('wrs', [])
                
                if score >= 1.5:
                    status = "WINNER"
                    winners.append({
                        'strategy': strategy,
                        'config': cfg_name,
                        'pf': score,
                        'pfs': pfs,
                        'wr': sum(wrs)/len(wrs) if wrs else 0
                    })
                elif score >= 1.2:
                    status = "GOOD"
                elif score >= 1.0:
                    status = "BREAK"
                else:
                    status = "FAIL"
                
                wr = sum(wrs) / len(wrs) if wrs else 0
                print(f"{status:7s} PF={score:.2f}, WR={wr:.1f}%")
            
            except Exception as e:
                print(f"ERROR: {str(e)[:30]}")
    
    # Summary
    print("\n" + "="*100)
    print("WINNERS (PF >= 1.5)")
    print("="*100 + "\n")
    
    if winners:
        winners.sort(key=lambda x: x['pf'], reverse=True)
        for i, w in enumerate(winners, 1):
            print(f"{i}. {w['strategy']:25s} + {w['config']:10s}: PF={w['pf']:.2f}, WR={w['wr']:.1f}%")
    else:
        print("No winners with PF >= 1.5")
        print("\nTrying wider exit configs...")
        
        # Test with even more extreme exits
        extreme_configs = [
            ("Ultra Wide", 3.0, 4.0, 0.75, 0.75),
            ("Mega", 4.0, 5.0, 0.8, 0.8),
            ("Max", 5.0, 6.0, 0.85, 0.85),
        ]
        
        for strategy in test_strategies[:3]:  # Quick test on top 3
            strat_obj = registry.get(strategy)
            if not strat_obj:
                continue
            
            print(f"\n  {strategy}:")
            for cfg_name, sl, rr, gb, arm in extreme_configs:
                print(f"    {cfg_name:15s}...", end=" ", flush=True)
                
                try:
                    results = backtester.walkforward_focused(
                        symbol="BTCUSD",
                        params=strat_obj.params,
                        sl_atr=sl,
                        tp_rr=rr,
                        giveback=gb,
                        arm=arm,
                        timeframe="M15"
                    )
                    
                    if results:
                        score = results.get('score', 0)
                        wrs = results.get('wrs', [])
                        wr = sum(wrs) / len(wrs) if wrs else 0
                        
                        if score >= 1.5:
                            winners.append({
                                'strategy': strategy,
                                'config': cfg_name,
                                'pf': score,
                                'pfs': results.get('pfs', []),
                                'wr': wr
                            })
                            status = "WINNER"
                        else:
                            status = f"PF={score:.2f}"
                        
                        print(f"{status}, WR={wr:.1f}%")
                except:
                    print("SKIP")
    
    return winners


if __name__ == "__main__":
    try:
        winners = test_fast()
        print("\nDone\n")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
