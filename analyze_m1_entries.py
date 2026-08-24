#!/usr/bin/env python
"""
Bollinger_OsMA M1 Entry Analysis

Fetches 90 days of BTCUSD M1, applies pattern detection,
analyzes entry quality and exit effectiveness,
tests MACD M1/M5 alignment filter.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.mt5.broker_adapter import BrokerAdapter
from src.data_acquisition.manager import DataManager
from src.utils.logger import get_logger

logger = get_logger("analysis.m1_entries")

def fetch_data():
    """Fetch M1 data from data manager."""
    print("\n" + "="*80)
    print("BOLLINGER_OSMA M1 ENTRY ANALYSIS")
    print("="*80 + "\n")
    
    print("Initializing data manager...")
    # Create data manager with vt_markets broker
    from src.data_acquisition.manager import DataSourceConfig
    config = DataSourceConfig(broker="vt_markets")
    dm = DataManager(config)
    
    print(f"Fetching BTCUSD M1 data...")
    bars_m1 = dm.get_rates("BTCUSD", "M1", count=129600)  # 90 days of M1
    print(f"✓ Fetched {len(bars_m1)} M1 bars")
    
    print(f"Fetching BTCUSD M5 data...")
    bars_m5 = dm.get_rates("BTCUSD", "M5", count=25920)  # 90 days of M5
    print(f"✓ Fetched {len(bars_m5)} M5 bars")
    
    df_m1 = pd.DataFrame(bars_m1)
    df_m5 = pd.DataFrame(bars_m5)
    
    return df_m1, df_m5


def calculate_indicators(df_m1, df_m5):
    """Calculate all required indicators."""
    print("\nCalculating indicators...")
    
    # M1 Bollinger Bands (20, 2)
    df_m1['sma'] = df_m1['close'].rolling(20).mean()
    df_m1['std'] = df_m1['close'].rolling(20).std()
    df_m1['bb_upper'] = df_m1['sma'] + (2 * df_m1['std'])
    df_m1['bb_lower'] = df_m1['sma'] - (2 * df_m1['std'])
    df_m1['bb_middle'] = df_m1['sma']
    
    # M1 OsMA (12, 26, 9)
    ema12 = df_m1['close'].ewm(span=12).mean()
    ema26 = df_m1['close'].ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()
    df_m1['osma'] = macd_line - signal_line
    df_m1['osma_prev'] = df_m1['osma'].shift(1)
    df_m1['osma_t2'] = df_m1['osma'].shift(2)
    df_m1['macd_histogram'] = df_m1['osma']
    
    # M1 ATR (14)
    df_m1['tr'] = np.maximum(
        df_m1['high'] - df_m1['low'],
        np.maximum(
            abs(df_m1['high'] - df_m1['close'].shift(1)),
            abs(df_m1['low'] - df_m1['close'].shift(1))
        )
    )
    df_m1['atr'] = df_m1['tr'].rolling(14).mean()
    
    # M5 MACD for alignment check
    ema12_m5 = df_m5['close'].ewm(span=12).mean()
    ema26_m5 = df_m5['close'].ewm(span=26).mean()
    macd_m5 = ema12_m5 - ema26_m5
    signal_m5 = macd_m5.ewm(span=9).mean()
    df_m5['macd_histogram'] = macd_m5 - signal_m5
    
    print("✓ Indicators calculated")
    return df_m1, df_m5


def detect_entries(df_m1, df_m5):
    """Detect all M1 entry signals."""
    print("\nDetecting M1 entries...")
    
    entries = []
    
    for i in range(2, len(df_m1) - 10):
        bar = df_m1.iloc[i]
        
        if pd.isna(bar['bb_upper']) or pd.isna(bar['osma']):
            continue
        
        # Band touches
        at_upper = bar['high'] >= bar['bb_upper']
        at_lower = bar['low'] <= bar['bb_lower']
        
        # OsMA divergence (shrinking)
        osma_now = abs(bar['osma'])
        osma_prev = abs(bar['osma_prev'])
        osma_t2 = abs(bar['osma_t2'])
        
        is_shrinking = osma_t2 > osma_prev > osma_now
        is_growing = osma_t2 < osma_prev < osma_now
        
        # Entry condition: band touch + shrinking
        if (at_upper or at_lower) and is_shrinking:
            entry_time_ms = bar.get('time')
            entry_price = bar['close']
            
            # Determine direction
            if at_lower and bar['osma'] > 0:
                direction = "LONG"
            elif at_upper and bar['osma'] < 0:
                direction = "SHORT"
            else:
                continue
            
            # Look ahead 10 bars for exit analysis
            future_closes = df_m1.iloc[i+1:i+11]['close'].values
            
            if len(future_closes) < 10:
                continue
            
            exit_price = future_closes[-1]
            max_price = future_closes.max()
            min_price = future_closes.min()
            
            # Calculate P&L
            if direction == "LONG":
                pnl = exit_price - entry_price
                max_gain = (max_price - entry_price) / entry_price * 100 if entry_price > 0 else 0
                max_loss = (min_price - entry_price) / entry_price * 100 if entry_price > 0 else 0
            else:  # SHORT
                pnl = entry_price - exit_price
                max_gain = (entry_price - min_price) / entry_price * 100 if entry_price > 0 else 0
                max_loss = (entry_price - max_price) / entry_price * 100 if entry_price > 0 else 0
            
            pnl_pct = (pnl / entry_price * 100) if entry_price > 0 else 0
            
            # Get MACD from nearest M5 bar (simple index-based lookup)
            m5_idx = i // 5  # Approximate M5 index
            if m5_idx < len(df_m5):
                macd_m5 = df_m5.iloc[m5_idx].get('macd_histogram', 0)
            else:
                macd_m5 = 0
            
            # Check alignment
            macd_m1 = bar['macd_histogram']
            aligned = (direction == "LONG" and macd_m1 > 0 and macd_m5 > 0) or \
                     (direction == "SHORT" and macd_m1 < 0 and macd_m5 < 0)
            
            # Extract hour from timestamp
            hour = 0
            if isinstance(entry_time_ms, (int, float)):
                import datetime as dt
                entry_dt = dt.datetime.fromtimestamp(entry_time_ms / 1000, tz=dt.timezone.utc)
                hour = entry_dt.hour
            
            entries.append({
                'time': entry_time_ms,
                'hour': hour,
                'direction': direction,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'max_price': max_price,
                'min_price': min_price,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'max_gain': max_gain,
                'max_loss': max_loss,
                'macd_m1': macd_m1,
                'macd_m5': macd_m5,
                'aligned': aligned,
                'growing': is_growing
            })
    
    print(f"✓ Detected {len(entries)} M1 entry signals")
    return entries


def analyze_results(entries):
    """Analyze entry quality and exit effectiveness."""
    print("\n" + "="*80)
    print("ENTRY ANALYSIS RESULTS")
    print("="*80 + "\n")
    
    if not entries:
        print("❌ No entries found!")
        return
    
    df_entries = pd.DataFrame(entries)
    
    # Overall stats
    total = len(entries)
    wins = len(df_entries[df_entries['pnl'] > 0])
    losses = len(df_entries[df_entries['pnl'] <= 0])
    wr = (wins / total * 100) if total > 0 else 0
    
    print(f"Total M1 entries: {total:,}")
    print(f"  Wins: {wins} ({wins/total*100:.1f}%)")
    print(f"  Losses: {losses} ({losses/total*100:.1f}%)")
    print(f"  Win rate: {wr:.1f}%\n")
    
    avg_win = df_entries[df_entries['pnl'] > 0]['pnl_pct'].mean() if wins > 0 else 0
    avg_loss = abs(df_entries[df_entries['pnl'] < 0]['pnl_pct'].mean()) if losses > 0 else 0
    
    print(f"  Avg win: +{avg_win:.3f}%")
    print(f"  Avg loss: -{avg_loss:.3f}%")
    
    profit_factor = abs(df_entries[df_entries['pnl'] > 0]['pnl'].sum() / 
                        df_entries[df_entries['pnl'] < 0]['pnl'].sum()) if losses > 0 else 0
    total_pnl = df_entries['pnl'].sum()
    
    print(f"  Profit factor: {profit_factor:.2f}")
    print(f"  Total P&L: {total_pnl:.2f}\n")
    
    # Entry vs Exit quality
    print(f"{'='*80}")
    print("ENTRY vs EXIT QUALITY")
    print(f"{'='*80}\n")
    
    df_entries['exit_quality'] = df_entries['pnl_pct'] / df_entries['max_gain'].abs()
    avg_exit_quality = df_entries['exit_quality'].mean()
    
    print(f"Average max gain potential: {df_entries['max_gain'].mean():.3f}%")
    print(f"Average realized P&L: {df_entries['pnl_pct'].mean():.3f}%")
    print(f"Exit quality ratio: {avg_exit_quality:.1%}")
    
    if avg_exit_quality < 0.4:
        print(f"\n⚠️  SEVERE EXIT PROBLEM DETECTED")
        print(f"   Exits only capturing {avg_exit_quality:.1%} of available gains")
    elif avg_exit_quality < 0.7:
        print(f"\n⚠️  ENTRY/EXIT IMBALANCE")
        print(f"   Exit quality is {avg_exit_quality:.1%}")
    else:
        print(f"\n✓ Exit quality is good ({avg_exit_quality:.1%})")
    
    # MACD alignment analysis
    print(f"\n{'='*80}")
    print("MACD M1/M5 ALIGNMENT ANALYSIS")
    print(f"{'='*80}\n")
    
    aligned = df_entries[df_entries['aligned'] == True]
    misaligned = df_entries[df_entries['aligned'] == False]
    
    print(f"Aligned with M1+M5: {len(aligned)} ({len(aligned)/total*100:.1f}%)")
    print(f"Misaligned: {len(misaligned)} ({len(misaligned)/total*100:.1f}%)\n")
    
    if len(aligned) > 0:
        aligned_wr = len(aligned[aligned['pnl'] > 0]) / len(aligned) * 100
        aligned_avg = aligned['pnl_pct'].mean()
        aligned_pf = abs(aligned[aligned['pnl'] > 0]['pnl'].sum() / 
                         aligned[aligned['pnl'] < 0]['pnl'].sum()) if len(aligned[aligned['pnl'] < 0]) > 0 else 0
        print(f"ALIGNED trades:")
        print(f"  WR: {aligned_wr:.1f}%")
        print(f"  Avg P&L: {aligned_avg:+.3f}%")
        print(f"  PF: {aligned_pf:.2f}")
    
    if len(misaligned) > 0:
        misaligned_wr = len(misaligned[misaligned['pnl'] > 0]) / len(misaligned) * 100
        misaligned_avg = misaligned['pnl_pct'].mean()
        misaligned_pf = abs(misaligned[misaligned['pnl'] > 0]['pnl'].sum() / 
                            misaligned[misaligned['pnl'] < 0]['pnl'].sum()) if len(misaligned[misaligned['pnl'] < 0]) > 0 else 0
        print(f"\nMISALIGNED trades:")
        print(f"  WR: {misaligned_wr:.1f}%")
        print(f"  Avg P&L: {misaligned_avg:+.3f}%")
        print(f"  PF: {misaligned_pf:.2f}")
    
    # Distribution by hour
    print(f"\n{'='*80}")
    print("ENTRY DISTRIBUTION BY HOUR")
    print(f"{'='*80}\n")
    
    by_hour = df_entries.groupby('hour').agg({
        'pnl': ['count', 'sum'],
        'pnl_pct': 'mean'
    }).round(3)
    
    for hour in sorted(df_entries['hour'].unique()):
        hour_data = df_entries[df_entries['hour'] == hour]
        count = len(hour_data)
        avg_pnl = hour_data['pnl_pct'].mean()
        pnl_sum = hour_data['pnl'].sum()
        wr = len(hour_data[hour_data['pnl'] > 0]) / count * 100 if count > 0 else 0
        print(f"  {hour:02d}:xx: {count:4d} trades, WR {wr:5.1f}%, Avg {avg_pnl:+.3f}%, Total {pnl_sum:+.2f}")
    
    # Recommendation
    print(f"\n{'='*80}")
    print("RECOMMENDATION")
    print(f"{'='*80}\n")
    
    improvement_with_macd = 0
    if len(aligned) > 0 and len(misaligned) > 0:
        aligned_avg_pf = abs(aligned[aligned['pnl'] > 0]['pnl'].sum() / 
                             aligned[aligned['pnl'] < 0]['pnl'].sum()) if len(aligned[aligned['pnl'] < 0]) > 0 else 0
        misaligned_avg_pf = abs(misaligned[misaligned['pnl'] > 0]['pnl'].sum() / 
                                misaligned[misaligned['pnl'] < 0]['pnl'].sum()) if len(misaligned[misaligned['pnl'] < 0]) > 0 else 0
        improvement_with_macd = aligned_avg_pf - misaligned_avg_pf
    
    if avg_exit_quality < 0.5:
        print("PRIMARY ISSUE: EXIT STRATEGY")
        print("  → The strategy finds good entries but exits too early or at wrong times")
        print("  → Focus on TP (take-profit) at middle band or based on different logic")
        print("  → Consider time-based exits or SL/PnL ratio exits")
    elif improvement_with_macd > 0.2:
        print("RECOMMENDATION: ADD MACD M1/M5 FILTER")
        print(f"  → MACD-aligned trades show {improvement_with_macd:.2f} higher PF")
        print("  → Filter entries to only those aligned with M1+M5 MACD")
        print("  → Expected improvement: ~{:.0f}% higher PF".format(improvement_with_macd * 50))
    else:
        print("RECOMMENDATION: INVESTIGATE ENTRY CONDITIONS")
        print("  → Current entry pattern may not be strong enough")
        print("  → Consider additional filters or stricter pattern requirements")


if __name__ == "__main__":
    try:
        df_m1, df_m5 = fetch_data()
        df_m1, df_m5 = calculate_indicators(df_m1, df_m5)
        entries = detect_entries(df_m1, df_m5)
        analyze_results(entries)
        
        print("\n✓ Analysis complete\n")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
