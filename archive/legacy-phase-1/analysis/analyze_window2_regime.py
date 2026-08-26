#!/usr/bin/env python
"""
Window 2 Market Conditions Analysis

Understand why all strategies collapse in Window 2.
Analyze volatility, trend, consolidation patterns.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.data_acquisition.manager import DataManager, DataSourceConfig
from src.utils.logger import get_logger

logger = get_logger("analysis.window2")

def analyze_regime():
    """Analyze market conditions in each walk-forward window."""
    print("\n" + "="*100)
    print("WINDOW 2 MARKET REGIME ANALYSIS")
    print("="*100 + "\n")
    
    dm = DataManager(DataSourceConfig(broker="vt_markets"))
    
    # Get M15 data
    bars = dm.get_rates("BTCUSD", "M15", count=12000)
    df = pd.DataFrame(bars)
    
    # Calculate window boundaries (3 windows of 4000 bars each)
    window_size = 4000
    windows = {
        'W1': (0, window_size),
        'W2': (window_size, window_size * 2),
        'W3': (window_size * 2, window_size * 3)
    }
    
    results = {}
    
    for window_name, (start, end) in windows.items():
        if end > len(df):
            continue
        
        window_df = df.iloc[start:end].copy()
        
        # Calculate metrics
        returns = window_df['close'].pct_change()
        
        # Volatility
        volatility = returns.std()
        
        # Trend (using SMA slope)
        sma_20 = window_df['close'].rolling(20).mean()
        sma_50 = window_df['close'].rolling(50).mean()
        trend_strength = (sma_20 - sma_50).std()
        
        # ADX-like trend strength (using Wilder's DX)
        high_low = window_df['high'] - window_df['low']
        high_prev = abs(window_df['high'] - window_df['close'].shift(1))
        low_prev = abs(window_df['low'] - window_df['close'].shift(1))
        tr = np.maximum(high_low, np.maximum(high_prev, low_prev))
        atr = tr.rolling(14).mean()
        
        dm_plus = (window_df['high'] - window_df['high'].shift(1)).clip(lower=0)
        dm_minus = (window_df['low'].shift(1) - window_df['low']).clip(lower=0)
        
        di_plus = 100 * dm_plus.rolling(14).mean() / atr
        di_minus = 100 * dm_minus.rolling(14).mean() / atr
        adx_approx = abs(di_plus - di_minus).rolling(14).mean()
        
        # Consolidation metric (Bollinger Band width)
        sma = window_df['close'].rolling(20).mean()
        std = window_df['close'].rolling(20).std()
        bb_width = (4 * std / sma).mean()  # Normalized width
        
        # Range bound
        price_range = (window_df['high'].max() - window_df['low'].min()) / window_df['close'].iloc[0]
        
        # Momentum (RSI)
        delta = window_df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        results[window_name] = {
            'volatility': volatility,
            'trend_strength': trend_strength,
            'adx': adx_approx.iloc[-100:].mean(),
            'bb_width': bb_width,
            'price_range': price_range,
            'rsi_mean': rsi.mean(),
            'bars': len(window_df),
            'price_start': window_df['close'].iloc[0],
            'price_end': window_df['close'].iloc[-1],
            'price_change': (window_df['close'].iloc[-1] / window_df['close'].iloc[0] - 1) * 100
        }
    
    # Print analysis
    print(f"{'Metric':<30} {'W1':<20} {'W2':<20} {'W3':<20}")
    print("-" * 90)
    
    metrics = ['volatility', 'trend_strength', 'adx', 'bb_width', 'price_range', 'rsi_mean']
    for metric in metrics:
        row = f"{metric:<30}"
        for window in ['W1', 'W2', 'W3']:
            if window in results:
                val = results[window].get(metric, 0)
                row += f" {val:<20.4f}"
            else:
                row += f" {'N/A':<20}"
        print(row)
    
    print("\n" + "="*100)
    print("INTERPRETATION")
    print("="*100 + "\n")
    
    for window in ['W1', 'W2', 'W3']:
        if window not in results:
            continue
        
        r = results[window]
        print(f"\n{window}:")
        print(f"  Price: {r['price_start']:.2f} → {r['price_end']:.2f} ({r['price_change']:+.2f}%)")
        print(f"  Volatility: {r['volatility']:.6f}")
        print(f"  Trend strength (ADX-like): {r['adx']:.2f}")
        print(f"  BB Width (consolidation): {r['bb_width']:.4f}")
        print(f"  Price range: {r['price_range']:.2f} ({r['price_range']*100:.1f}%)")
        print(f"  RSI mean: {r['rsi_mean']:.2f}")
        
        # Classify regime
        is_trending = r['adx'] > 30
        is_consolidating = r['bb_width'] < 0.02
        is_volatile = r['volatility'] > 0.001
        
        regime = []
        if is_trending:
            regime.append("TRENDING")
        if is_consolidating:
            regime.append("CONSOLIDATING")
        if is_volatile:
            regime.append("VOLATILE")
        
        if not regime:
            regime.append("NORMAL")
        
        print(f"  → Regime: {', '.join(regime)}")
    
    # Window 2 specific analysis
    print("\n" + "="*100)
    print("WHY WINDOW 2 FAILS")
    print("="*100 + "\n")
    
    if 'W2' in results:
        w2 = results['W2']
        print(f"Window 2 Characteristics:")
        print(f"  Volatility: {w2['volatility']:.6f}", end="")
        if w2['volatility'] < results['W1']['volatility']:
            print(" (LOWER than W1 - less volatile)")
        else:
            print(" (Higher than W1)")
        
        print(f"  Trend strength: {w2['adx']:.2f}", end="")
        if w2['adx'] < 25:
            print(" (WEAK trend - consolidating!)")
        else:
            print(" (Reasonable trend)")
        
        print(f"  BB Width: {w2['bb_width']:.4f}", end="")
        if w2['bb_width'] < 0.02:
            print(" (TIGHT - strong consolidation)")
        else:
            print(" (Normal)")
        
        print(f"\n  → Window 2 is likely RANGE-BOUND/CONSOLIDATING")
        print(f"    Mean-reversion strategies fail in consolidation because:")
        print(f"    - Price bounces off levels but doesn't follow through")
        print(f"    - False signals spike, drawdown increases")
        print(f"    - Need to SKIP entries or use different exit in W2")


if __name__ == "__main__":
    try:
        analyze_regime()
        print("\n✓ Analysis complete\n")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
