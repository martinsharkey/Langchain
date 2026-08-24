#!/usr/bin/env python
"""
Bollinger_OsMA Entry vs Exit Analysis - Simplified

Uses the backtester's data pipeline to:
1. Fetch 90 days of BTCUSD M15
2. Apply pattern detection
3. Analyze entry/exit quality
4. Test MACD alignment
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.mt5.broker_adapter import BrokerAdapter
from src.utils.logger import get_logger

logger = get_logger("analysis.entry_exit")

def fetch_and_analyze():
    """Fetch 90 days of data and analyze patterns."""
    print("\n" + "="*80)
    print("BOLLINGER_OSMA ENTRY/EXIT DIAGNOSTIC")
    print("="*80 + "\n")
    
    adapter = BrokerAdapter()
    
    # Fetch M15 data
    print("Fetching BTCUSD data...")
    end_time = datetime.now()
    start_time = end_time - timedelta(days=90)
    
    # Get M15 bars
    bars_m15 = adapter.get_rates("BTCUSD", "M15", start_time, end_time)
    print(f"✓ Fetched {len(bars_m15)} M15 bars")
    
    # Get M1 for MACD
    bars_m1 = adapter.get_rates("BTCUSD", "M1", start_time, end_time)
    print(f"✓ Fetched {len(bars_m1)} M1 bars")
    
    # Get M5 for MACD
    bars_m5 = adapter.get_rates("BTCUSD", "M5", start_time, end_time)
    print(f"✓ Fetched {len(bars_m5)} M5 bars")
    
    # Convert to DataFrames
    df_m15 = pd.DataFrame(bars_m15)
    df_m1 = pd.DataFrame(bars_m1)
    df_m5 = pd.DataFrame(bars_m5)
    
    print(f"\nData ranges:")
    print(f"  M15: {df_m15.iloc[0]['time']} to {df_m15.iloc[-1]['time']} ({len(df_m15)} bars)")
    print(f"  M1: {len(df_m1)} bars")
    print(f"  M5: {len(df_m5)} bars")
    
    # Analyze pattern distribution
    analyze_pattern_distribution(df_m15, df_m1, df_m5)
    
    return df_m15, df_m1, df_m5


def analyze_pattern_distribution(df_m15, df_m1, df_m5):
    """Analyze how often the Bollinger_OsMA pattern occurs."""
    print("\n" + "="*80)
    print("PATTERN DISTRIBUTION ANALYSIS")
    print("="*80 + "\n")
    
    # Calculate indicators
    print("Calculating indicators...")
    
    # Bollinger Bands (20, 2)
    df_m15['sma'] = df_m15['close'].rolling(20).mean()
    df_m15['std'] = df_m15['close'].rolling(20).std()
    df_m15['bb_upper'] = df_m15['sma'] + (2 * df_m15['std'])
    df_m15['bb_lower'] = df_m15['sma'] - (2 * df_m15['std'])
    df_m15['bb_middle'] = df_m15['sma']
    
    # OsMA (12, 26, 9)
    ema12 = df_m15['close'].ewm(span=12).mean()
    ema26 = df_m15['close'].ewm(span=26).mean()
    macd_line = ema12 - ema26
    df_m15['macd_signal'] = macd_line.ewm(span=9).mean()
    df_m15['osma'] = macd_line - df_m15['macd_signal']
    df_m15['osma_prev'] = df_m15['osma'].shift(1)
    df_m15['osma_t2'] = df_m15['osma'].shift(2)
    
    # ATR (14)
    df_m15['tr'] = np.maximum(
        df_m15['high'] - df_m15['low'],
        np.maximum(
            abs(df_m15['high'] - df_m15['close'].shift(1)),
            abs(df_m15['low'] - df_m15['close'].shift(1))
        )
    )
    df_m15['atr'] = df_m15['tr'].rolling(14).mean()
    
    # Calculate M1 and M5 MACD
    print("Calculating MACD M1...")
    ema12_m1 = df_m1['close'].ewm(span=12).mean()
    ema26_m1 = df_m1['close'].ewm(span=26).mean()
    macd_m1 = ema12_m1 - ema26_m1
    signal_m1 = macd_m1.ewm(span=9).mean()
    df_m1['macd_histogram'] = macd_m1 - signal_m1
    
    print("Calculating MACD M5...")
    ema12_m5 = df_m5['close'].ewm(span=12).mean()
    ema26_m5 = df_m5['close'].ewm(span=26).mean()
    macd_m5 = ema12_m5 - ema26_m5
    signal_m5 = macd_m5.ewm(span=9).mean()
    df_m5['macd_histogram'] = macd_m5 - signal_m5
    
    print("✓ Indicators calculated\n")
    
    # Pattern detection
    band_touches = 0
    osma_divergences = 0
    osma_growing = 0
    full_pattern_hits = 0
    
    long_entries = 0
    short_entries = 0
    
    entries_by_hour = {}
    entries_by_session = {"Sydney": 0, "Tokyo": 0, "London": 0, "NewYork": 0, "Off": 0}
    
    for i in range(2, len(df_m15) - 10):
        bar = df_m15.iloc[i]
        
        if pd.isna(bar['bb_upper']) or pd.isna(bar['osma']):
            continue
        
        # Check band touches
        at_upper_band = bar['high'] >= bar['bb_upper']
        at_lower_band = bar['low'] <= bar['bb_lower']
        
        if at_upper_band or at_lower_band:
            band_touches += 1
        
        # Check OsMA divergence (shrinking)
        osma_now = bar['osma']
        osma_prev = bar['osma_prev']
        osma_t2 = bar['osma_t2']
        
        is_shrinking = abs(osma_t2) > abs(osma_prev) > abs(osma_now)
        is_growing = abs(osma_t2) < abs(osma_prev) < abs(osma_now)
        
        if is_shrinking:
            osma_divergences += 1
        if is_growing:
            osma_growing += 1
        
        # Full pattern hit
        if (at_upper_band or at_lower_band) and is_shrinking:
            full_pattern_hits += 1
            
            # Determine entry direction
            if at_lower_band and osma_now > 0:
                long_entries += 1
                direction = "LONG"
            elif at_upper_band and osma_now < 0:
                short_entries += 1
                direction = "SHORT"
            else:
                continue
            
            # Track by hour
            hour = pd.to_datetime(bar['time'], unit='s').hour
            entries_by_hour[hour] = entries_by_hour.get(hour, 0) + 1
            
            # Track by session
            if 22 <= hour or hour < 8:
                entries_by_session["Sydney"] += 1
            elif 8 <= hour < 9:
                entries_by_session["Tokyo"] += 1
            elif 8 <= hour < 17:
                entries_by_session["London"] += 1
            elif 13 <= hour < 21:
                entries_by_session["NewYork"] += 1
            else:
                entries_by_session["Off"] += 1
    
    # Print results
    print(f"Pattern Occurrence Frequency (90 days, {len(df_m15)} M15 bars):")
    print(f"  Band touches only: {band_touches:,} ({band_touches/len(df_m15)*100:.1f}%)")
    print(f"  OsMA shrinking (divergence): {osma_divergences:,} ({osma_divergences/len(df_m15)*100:.1f}%)")
    print(f"  OsMA growing: {osma_growing:,} ({osma_growing/len(df_m15)*100:.1f}%)")
    print(f"  FULL PATTERN (band + shrinking): {full_pattern_hits:,} ({full_pattern_hits/len(df_m15)*100:.1f}%)")
    
    print(f"\nEntry Directions:")
    print(f"  Long entries: {long_entries}")
    print(f"  Short entries: {short_entries}")
    
    print(f"\nEntries by Hour of Day:")
    for hour in sorted(entries_by_hour.keys()):
        count = entries_by_hour[hour]
        print(f"  {hour:02d}:00 - {hour:02d}:45: {count:3d} entries")
    
    print(f"\nEntries by Trading Session:")
    for session, count in entries_by_session.items():
        pct = (count / full_pattern_hits * 100) if full_pattern_hits > 0 else 0
        print(f"  {session:10s}: {count:4d} ({pct:5.1f}%)")
    
    return df_m15, df_m1, df_m5, full_pattern_hits


if __name__ == "__main__":
    try:
        df_m15, df_m1, df_m5 = fetch_and_analyze()
        
        print("\n" + "="*80)
        print("✓ Analysis complete")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
