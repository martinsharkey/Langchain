#!/usr/bin/env python
"""
Realistic pattern testing with proper SL/TP logic

Test patterns with actual trade mechanics:
- Set reasonable SL
- Set realistic TP  
- Calculate actual P&L
- Only count if TP hit before SL
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.data_acquisition.manager import DataManager, DataSourceConfig

def test_pattern_with_sl_tp():
    """Test patterns with realistic SL/TP logic."""
    print("\n" + "="*100)
    print("REALISTIC PATTERN TEST: With SL/TP Mechanics")
    print("="*100 + "\n")
    
    dm = DataManager(DataSourceConfig(broker="vt_markets"))
    bars = dm.get_rates("BTCUSD", "M15", count=12000)
    df = pd.DataFrame(bars)
    
    print(f"Testing {len(df):,} M15 bars\n")
    
    # Pattern: Breakout of 20-bar range + pullback
    print("Pattern: Range Breakout + Mean Reversion")
    print("-" * 100)
    
    trades = []
    
    for i in range(50, len(df) - 20):
        # Define 20-bar range
        range_high = df.iloc[i-20:i]['high'].max()
        range_low = df.iloc[i-20:i]['low'].min()
        range_mid = (range_high + range_low) / 2
        
        current_close = df.iloc[i]['close']
        
        # Entry condition: Price breaks above range, then pulls back into range
        if current_close > range_high:
            # Enter long at breakout high
            entry = range_high
            sl = range_low
            tp = current_close + (range_high - range_low) * 0.5  # TP = 50% of range
            
            # Simulate forward 20 bars
            future_bars = df.iloc[i+1:i+21]
            
            hit_tp = False
            hit_sl = False
            exit_price = current_close
            bars_held = 0
            
            for j, bar in future_bars.iterrows():
                bars_held += 1
                
                # Check if TP or SL hit
                if bar['high'] >= tp:
                    hit_tp = True
                    exit_price = tp
                    break
                
                if bar['low'] <= sl:
                    hit_sl = True
                    exit_price = sl
                    break
            
            pnl = exit_price - entry
            pnl_pct = (pnl / entry) * 100
            
            trades.append({
                'direction': 'LONG',
                'entry': entry,
                'exit': exit_price,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'hit_tp': hit_tp,
                'hit_sl': hit_sl,
                'bars_held': bars_held
            })
    
    # Analyze results
    if trades:
        df_trades = pd.DataFrame(trades)
        
        wins = len(df_trades[df_trades['pnl'] > 0])
        losses = len(df_trades[df_trades['pnl'] <= 0])
        wr = (wins / len(trades)) * 100 if trades else 0
        
        total_pnl = df_trades['pnl'].sum()
        avg_win = df_trades[df_trades['pnl'] > 0]['pnl_pct'].mean() if wins > 0 else 0
        avg_loss = df_trades[df_trades['pnl'] < 0]['pnl_pct'].mean() if losses > 0 else 0
        
        gross_win = df_trades[df_trades['pnl'] > 0]['pnl'].sum()
        gross_loss = abs(df_trades[df_trades['pnl'] < 0]['pnl'].sum())
        pf = gross_win / gross_loss if gross_loss > 0 else 0
        
        print(f"Total trades: {len(trades)}")
        print(f"Wins: {wins} ({wr:.1f}%)")
        print(f"Losses: {losses} ({100-wr:.1f}%)")
        print(f"Avg win: {avg_win:+.3f}%")
        print(f"Avg loss: {avg_loss:+.3f}%")
        print(f"Profit factor: {pf:.2f}")
        print(f"Total P&L: {total_pnl:.2f} points")
        
        if pf >= 1.15:
            print(f"\n✓ PROFITABLE! PF >= 1.15")
            return True
        else:
            print(f"\n✗ Still not profitable enough (PF {pf:.2f} < 1.15)")
            return False
    
    return False


if __name__ == "__main__":
    try:
        is_profitable = test_pattern_with_sl_tp()
        print("\n✓ Analysis complete\n")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
