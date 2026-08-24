#!/usr/bin/env python
"""
Brute-force pattern discovery: What price patterns actually make money?

Skip indicators, skip complex logic. Just find what works in raw OHLC.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.data_acquisition.manager import DataManager, DataSourceConfig
from src.utils.logger import get_logger

logger = get_logger("pattern.discovery")

def test_simple_patterns():
    """Test ultra-simple patterns to find what works."""
    print("\n" + "="*100)
    print("PATTERN DISCOVERY: What Actually Makes Money?")
    print("="*100 + "\n")
    
    dm = DataManager(DataSourceConfig(broker="vt_markets"))
    bars = dm.get_rates("BTCUSD", "M15", count=12000)
    df = pd.DataFrame(bars)
    
    print(f"Analyzing {len(df):,} M15 bars\n")
    
    results = {}
    
    # Pattern 1: Simple reversal (price makes new low/high then reverses)
    print("Testing Pattern 1: Price Reversal After New Extreme")
    print("-" * 100)
    
    reversals = []
    for i in range(10, len(df) - 10):
        # Check if price made a new 10-bar low then reversed up
        recent_low = df.iloc[i-10:i]['low'].min()
        current_low = df.iloc[i]['low']
        
        if current_low < recent_low:  # New low
            # Did it reverse up in next 5 bars?
            future_prices = df.iloc[i+1:i+6]['close'].values
            if len(future_prices) > 0:
                peak = future_prices.max()
                entry = df.iloc[i]['close']
                pnl = peak - entry
                pnl_pct = (pnl / entry) * 100
                
                if pnl_pct > 0:
                    reversals.append(pnl_pct)
    
    if reversals:
        avg_reversal = sum(reversals) / len(reversals)
        win_count = sum(1 for r in reversals if r > 0)
        wr = (win_count / len(reversals)) * 100
        
        print(f"  New lows: {len(reversals)}")
        print(f"  Win rate: {wr:.1f}%")
        print(f"  Avg gain when it wins: +{avg_reversal:.3f}%")
        results['reversal'] = {
            'count': len(reversals),
            'wr': wr,
            'avg_gain': avg_reversal
        }
    
    # Pattern 2: Big candle followed by reversal
    print("\nTesting Pattern 2: Large Range Candle Reversal")
    print("-" * 100)
    
    big_candles = []
    for i in range(5, len(df) - 5):
        # Large range candle?
        candle_range = df.iloc[i]['high'] - df.iloc[i]['low']
        avg_range = df.iloc[i-5:i]['high'].values - df.iloc[i-5:i]['low'].values
        avg_range = np.mean(avg_range)
        
        if candle_range > avg_range * 1.5:  # 50% larger than average
            # Did price reverse in next 3 bars?
            next_close = df.iloc[i+1]['close']
            entry = df.iloc[i]['close']
            
            # Enter opposite direction of candle
            if entry > df.iloc[i]['open']:  # Up candle, go short
                future_low = df.iloc[i+1:i+4]['low'].min()
                pnl = entry - future_low
            else:  # Down candle, go long
                future_high = df.iloc[i+1:i+4]['high'].max()
                pnl = future_high - entry
            
            pnl_pct = (pnl / entry) * 100
            if pnl_pct > 0:
                big_candles.append(pnl_pct)
    
    if big_candles:
        avg_big = sum(big_candles) / len(big_candles)
        win_big = sum(1 for b in big_candles if b > 0)
        wr_big = (win_big / len(big_candles)) * 100
        
        print(f"  Large candles found: {len(big_candles)}")
        print(f"  Win rate: {wr_big:.1f}%")
        print(f"  Avg gain: +{avg_big:.3f}%")
        results['big_candle'] = {
            'count': len(big_candles),
            'wr': wr_big,
            'avg_gain': avg_big
        }
    
    # Pattern 3: Breakout (price breaks above/below recent range)
    print("\nTesting Pattern 3: Range Breakout")
    print("-" * 100)
    
    breakouts = []
    for i in range(20, len(df) - 5):
        recent_high = df.iloc[i-20:i]['high'].max()
        recent_low = df.iloc[i-20:i]['low'].min()
        
        current_high = df.iloc[i]['high']
        current_low = df.iloc[i]['low']
        
        # Breakout up?
        if current_high > recent_high:
            future_high = df.iloc[i+1:i+5]['high'].max()
            entry = recent_high
            pnl = future_high - entry
            pnl_pct = (pnl / entry) * 100
            if pnl_pct > 0:
                breakouts.append(pnl_pct)
        
        # Breakout down?
        if current_low < recent_low:
            future_low = df.iloc[i+1:i+5]['low'].min()
            entry = recent_low
            pnl = entry - future_low
            pnl_pct = (pnl / entry) * 100
            if pnl_pct > 0:
                breakouts.append(pnl_pct)
    
    if breakouts:
        avg_bo = sum(breakouts) / len(breakouts)
        win_bo = sum(1 for b in breakouts if b > 0)
        wr_bo = (win_bo / len(breakouts)) * 100
        
        print(f"  Breakouts found: {len(breakouts)}")
        print(f"  Win rate: {wr_bo:.1f}%")
        print(f"  Avg gain: +{avg_bo:.3f}%")
        results['breakout'] = {
            'count': len(breakouts),
            'wr': wr_bo,
            'avg_gain': avg_bo
        }
    
    # Pattern 4: Volume spike + price move
    print("\nTesting Pattern 4: Volume Spike Continuation")
    print("-" * 100)
    
    vol_spikes = []
    for i in range(10, len(df) - 5):
        current_vol = df.iloc[i]['volume']
        avg_vol = df.iloc[i-10:i]['volume'].mean()
        
        if current_vol > avg_vol * 1.5:  # Volume spike
            # Does price continue in direction of high volume candle?
            candle_dir = 1 if df.iloc[i]['close'] > df.iloc[i]['open'] else -1
            
            if candle_dir > 0:  # Up volume, go long
                future_high = df.iloc[i+1:i+5]['high'].max()
                entry = df.iloc[i]['close']
                pnl = future_high - entry
            else:  # Down volume, go short
                future_low = df.iloc[i+1:i+5]['low'].min()
                entry = df.iloc[i]['close']
                pnl = entry - future_low
            
            pnl_pct = (pnl / entry) * 100
            if pnl_pct > 0:
                vol_spikes.append(pnl_pct)
    
    if vol_spikes:
        avg_vol = sum(vol_spikes) / len(vol_spikes)
        win_vol = sum(1 for v in vol_spikes if v > 0)
        wr_vol = (win_vol / len(vol_spikes)) * 100
        
        print(f"  Volume spikes: {len(vol_spikes)}")
        print(f"  Win rate: {wr_vol:.1f}%")
        print(f"  Avg gain: +{avg_vol:.3f}%")
        results['volume_spike'] = {
            'count': len(vol_spikes),
            'wr': wr_vol,
            'avg_gain': avg_vol
        }
    
    # Summary
    print("\n" + "="*100)
    print("SUMMARY: Which Pattern Works Best?")
    print("="*100 + "\n")
    
    best_pattern = None
    best_wr = 0
    
    for pattern_name, pattern_data in results.items():
        wr = pattern_data['wr']
        avg = pattern_data['avg_gain']
        count = pattern_data['count']
        pf_est = 1.0 + (wr/100 - 0.5) * 2  # Rough estimate
        
        print(f"{pattern_name:20s}: {count:4d} signals, WR {wr:5.1f}%, "
              f"Avg gain {avg:+.3f}%, Est PF {pf_est:.2f}")
        
        if wr > best_wr:
            best_wr = wr
            best_pattern = pattern_name
    
    print()
    if best_pattern:
        print(f"✓ BEST PATTERN: {best_pattern} ({best_wr:.1f}% WR)")
        print(f"  This could be the foundation for a profitable strategy")
    
    return results, best_pattern


if __name__ == "__main__":
    try:
        results, best = test_simple_patterns()
        print("\n✓ Analysis complete\n")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
