"""
VECTORBT WITH SESSION FILTERING
Tests strategy combinations separately for Asian, London, and New York sessions
Allows identifying which strategies work best in each market session
"""

import numpy as np
import pandas as pd
from pathlib import Path
import sys
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
import warnings

warnings.filterwarnings('ignore')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data_acquisition.manager import DataManager, DataSourceConfig


@dataclass
class SessionStrategyResult:
    """Result broken down by trading session."""
    session_name: str
    primary_ind: str
    secondary_ind: str
    sl_mult: float
    tp_ratio: float
    pf: float
    wr: float
    trades: int
    sharpe: float
    session_filter: str
    
    def to_dict(self):
        return asdict(self)


class SessionFilterOptimizer:
    """Vectorbt optimizer with session-based filtering."""
    
    # Market sessions (UTC time, 5-minute bars = 300-second intervals)
    # Note: BTCUSD trades 24/7 including weekends (Fri 21:00 UTC - Sun 21:00 UTC)
    SESSIONS = {
        'asian': {
            'name': 'Asian (Tokyo, Hong Kong, Singapore)',
            'start_hour': 0,      # 00:00 UTC = 09:00 JST
            'end_hour': 8,        # 08:00 UTC = 17:00 JST
            'weekday': None,      # All weekdays
            'description': 'Tokyo open 00:00-08:00 UTC'
        },
        'london': {
            'name': 'London (European)',
            'start_hour': 8,      # 08:00 UTC = 08:00 GMT
            'end_hour': 16,       # 16:00 UTC = 16:00 GMT
            'weekday': None,      # All weekdays
            'description': 'London open 08:00-16:00 UTC'
        },
        'newyork': {
            'name': 'New York (American)',
            'start_hour': 13,     # 13:00 UTC = 08:00 EST
            'end_hour': 21,       # 21:00 UTC = 16:00 EST
            'weekday': None,      # All weekdays
            'description': 'New York open 13:00-21:00 UTC'
        },
        'overlap_london_ny': {
            'name': 'London-NY Overlap',
            'start_hour': 13,     # 13:00 UTC = 08:00 EST (NY opens)
            'end_hour': 16,       # 16:00 UTC = 16:00 GMT (London closes)
            'weekday': None,      # All weekdays
            'description': 'Highest volatility overlap 13:00-16:00 UTC'
        },
        'weekend_trading': {
            'name': 'Weekend Trading (Crypto-Only)',
            'start_hour': None,   # All hours
            'end_hour': None,
            'weekday': [5, 6],    # Friday (5) + Saturday (6) + Sunday (6)
            'description': 'Friday 21:00 UTC - Sunday 21:00 UTC (retail/news driven)'
        },
        'friday_evening': {
            'name': 'Friday Evening (Transition)',
            'start_hour': 21,     # 21:00 UTC = 16:00 EST
            'end_hour': 24,       # Midnight UTC
            'weekday': [4],       # Friday only
            'description': 'Friday evening 21:00 UTC - 00:00 UTC (market close + weekend opener)'
        },
        'weekend_saturday': {
            'name': 'Saturday Trading',
            'start_hour': 0,      # All day Saturday
            'end_hour': 24,
            'weekday': [5],       # Saturday (in ISO: 5=Saturday, 6=Sunday)
            'description': 'Full Saturday 00:00-24:00 UTC'
        },
        'sunday_trading': {
            'name': 'Sunday Trading',
            'start_hour': 0,      # All day Sunday until NY close
            'end_hour': 21,       # 21:00 UTC = 16:00 EST
            'weekday': [6],       # Sunday
            'description': 'Sunday 00:00-21:00 UTC (before NY close)'
        }
    }
    
    def __init__(self):
        self.dm = DataManager(DataSourceConfig(broker="vt_markets"))
        self.results: List[SessionStrategyResult] = []
    
    def load_data(self, symbol="BTCUSD", timeframe="M15", count=12000):
        """Load OHLCV data with UTC timestamps."""
        print(f"\n[LOADING] {symbol} {timeframe} ({count} bars)...", end=" ", flush=True)
        try:
            bars = self.dm.get_rates(symbol, timeframe, count=count)
            df = pd.DataFrame(bars)
            
            ohlcv = df[['open', 'high', 'low', 'close', 'volume']].copy()
            # Convert Unix timestamp to UTC datetime
            ohlcv.index = pd.to_datetime(df['time'], unit='s', utc=True)
            
            print(f"OK ({len(ohlcv)} bars, {ohlcv.index[0]} to {ohlcv.index[-1]})")
            return ohlcv
        except Exception as e:
            print(f"ERROR: {str(e)[:100]}")
            raise
    
    def filter_by_session(self, ohlcv: pd.DataFrame, session_key: str) -> pd.DataFrame:
        """Filter OHLCV data to specific trading session."""
        session = self.SESSIONS[session_key]
        
        # Create base mask for all rows
        mask = pd.Series([True] * len(ohlcv), index=ohlcv.index)
        
        # Apply hour filter if specified
        if session['start_hour'] is not None and session['end_hour'] is not None:
            start_hour = session['start_hour']
            end_hour = session['end_hour']
            hours = ohlcv.index.hour
            
            if start_hour < end_hour:
                # Normal range (e.g., 0-8)
                hour_mask = (hours >= start_hour) & (hours < end_hour)
            else:
                # Wrap around midnight (e.g., 21-24)
                hour_mask = (hours >= start_hour) | (hours < end_hour)
            
            mask = mask & hour_mask
        
        # Apply weekday filter if specified
        if session.get('weekday') is not None:
            weekdays = session['weekday']
            # ISO weekday: Monday=0, Tuesday=1, ..., Saturday=5, Sunday=6
            weekday_mask = ohlcv.index.weekday.isin(weekdays)
            mask = mask & weekday_mask
        
        filtered = ohlcv[mask].copy()
        return filtered
    
    def calculate_indicators_for_session(self, session_ohlcv: pd.DataFrame) -> Dict:
        """Calculate indicators for session data."""
        if len(session_ohlcv) < 50:
            return {}  # Not enough data
        
        close = pd.Series(session_ohlcv['close'].values)
        high = pd.Series(session_ohlcv['high'].values)
        low = pd.Series(session_ohlcv['low'].values)
        
        indicators = {}
        
        # RSI
        for period in [14, 21]:
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(period).mean()
            loss = -delta.where(delta < 0, 0).rolling(period).mean()
            rs = gain / (loss + 0.001)
            indicators[f'rsi_{period}'] = 100 - (100 / (1 + rs))
        
        # Bollinger Bands
        for period in [20]:
            for std_dev in [2.0, 2.5, 3.0]:
                sma = close.rolling(period).mean()
                std = close.rolling(period).std()
                indicators[f'bb_upper_{period}_{std_dev}'] = sma + (std_dev * std)
                indicators[f'bb_lower_{period}_{std_dev}'] = sma - (std_dev * std)
        
        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        indicators['osma'] = macd - signal
        
        # ATR
        for period in [14]:
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = np.maximum(np.maximum(tr1.values, tr2.values), tr3.values)
            indicators[f'atr_{period}'] = pd.Series(tr).rolling(period).mean()
        
        # Standard Deviation
        indicators['stdev_20'] = close.rolling(20).std()
        
        return indicators
    
    def generate_signal(self, session_ohlcv, indicators, primary, secondary):
        """Generate entry signals."""
        if not indicators:
            return None
        
        close = session_ohlcv['close'].values
        
        try:
            # Primary signal
            if primary == 'rsi_14':
                if 'rsi_14' in indicators:
                    rsi = indicators['rsi_14'].values
                    signal = (rsi < 30) | (rsi > 70)
                else:
                    return None
            
            elif primary == 'bb_20_2.0':
                if 'bb_upper_20_2.0' in indicators:
                    bb_upper = indicators['bb_upper_20_2.0'].values
                    bb_lower = indicators['bb_lower_20_2.0'].values
                    signal = (close <= bb_lower) | (close >= bb_upper)
                else:
                    return None
            
            elif primary == 'osma':
                if 'osma' in indicators:
                    osma = indicators['osma'].values
                    signal = (osma > 0) | (osma < 0)
                else:
                    return None
            
            else:
                return None
            
            # Secondary filter
            if secondary == 'none':
                confirmation = np.ones(len(close), dtype=bool)
            elif secondary == 'adx' and 'stdev_20' in indicators:
                stdev = indicators['stdev_20'].values
                mean_stdev = np.nanmean(stdev)
                confirmation = stdev > (mean_stdev * 0.7)
            else:
                confirmation = np.ones(len(close), dtype=bool)
            
            combined = signal & confirmation
            return combined.astype(float)
        
        except Exception:
            return None
    
    def backtest_session(self, session_ohlcv, entries, sl_mult, tp_ratio, indicators):
        """Backtest on session data."""
        close = session_ohlcv['close'].values
        high = session_ohlcv['high'].values
        low = session_ohlcv['low'].values
        
        if 'atr_14' not in indicators:
            atr = np.ones(len(close)) * np.mean(high - low)
        else:
            atr = indicators['atr_14'].values
        
        trades = []
        position = None
        entry_price = None
        position_type = None
        
        for i in range(1, len(close)):
            if entries[i] > 0 and position is None and not np.isnan(atr[i]):
                entry_price = close[i]
                mid = np.mean(close[max(0, i-10):i])
                position_type = 1 if close[i] <= mid else -1
                position = position_type
            
            elif position is not None and not np.isnan(atr[i]):
                atr_val = max(atr[i], 0.001)
                tp = entry_price + (position_type * tp_ratio * atr_val)
                sl = entry_price - (position_type * sl_mult * atr_val)
                
                exit_price = None
                
                if position_type == 1:
                    if high[i] >= tp or low[i] <= sl:
                        exit_price = tp if high[i] >= tp else sl
                else:
                    if low[i] <= tp or high[i] >= sl:
                        exit_price = tp if low[i] <= tp else sl
                
                if exit_price:
                    pnl = (exit_price - entry_price) * position_type
                    trades.append(pnl)
                    position = None
        
        if len(trades) < 3:
            return None
        
        trades_arr = np.array(trades)
        wins = np.sum(trades_arr > 0)
        pf = np.sum(trades_arr[trades_arr > 0]) / (np.abs(np.sum(trades_arr[trades_arr < 0])) + 0.001)
        wr = wins / len(trades)
        
        returns = trades_arr / entry_price if entry_price > 0 else trades_arr
        sharpe = (np.mean(returns) / (np.std(returns) + 0.001)) * np.sqrt(252)
        
        return {
            'pf': pf,
            'wr': wr,
            'trades': len(trades),
            'sharpe': sharpe
        }
    
    def optimize_all_sessions(self, symbol="BTCUSD"):
        """Test all strategy combinations across all sessions."""
        ohlcv = self.load_data(symbol)
        
        # Strategy combinations to test
        primary_signals = ['rsi_14', 'bb_20_2.0', 'osma']
        secondary_filters = ['none', 'adx']
        sl_mults = [0.5, 1.0, 1.5]
        tp_ratios = [2.0, 3.0, 4.0]
        
        print("\n" + "="*120)
        print(f"SESSION-BASED OPTIMIZATION FOR {symbol}".center(120))
        print("="*120 + "\n")
        
        for session_key, session_info in self.SESSIONS.items():
            print(f"\n[SESSION] {session_info['name']}")
            print(f"  Time: {session_info['description']}")
            
            # Filter data for this session
            session_data = self.filter_by_session(ohlcv, session_key)
            print(f"  Bars in session: {len(session_data)}", end="")
            
            if len(session_data) < 100:
                print(f" [INSUFFICIENT_DATA] (need 100+)")
                continue
            
            print(f" [OK]")
            
            # Calculate indicators for this session
            indicators = self.calculate_indicators_for_session(session_data)
            
            if not indicators:
                print(f"  [INDICATOR_CALC_FAILED] Could not calculate indicators")
                continue
            
            total_combos = len(primary_signals) * len(secondary_filters) * len(sl_mults) * len(tp_ratios)
            print(f"  Testing {total_combos:,} combinations...")
            
            best_pf = 0
            best_config = None
            
            for primary in primary_signals:
                for secondary in secondary_filters:
                    for sl_m in sl_mults:
                        for tp_r in tp_ratios:
                            entries = self.generate_signal(session_data, indicators, primary, secondary)
                            
                            if entries is not None:
                                result = self.backtest_session(session_data, entries, sl_m, tp_r, indicators)
                                
                                if result and result['pf'] > best_pf:
                                    best_pf = result['pf']
                                    best_config = {
                                        'primary': primary,
                                        'secondary': secondary,
                                        'sl': sl_m,
                                        'tp': tp_r,
                                        'result': result
                                    }
            
            if best_config:
                print(f"  [BEST] {best_config['primary']} + {best_config['secondary']} | SL={best_config['sl']} TP={best_config['tp']}")
                print(f"    PF={best_config['result']['pf']:.2f} | WR={best_config['result']['wr']*100:.1f}% | Trades={best_config['result']['trades']} | Sharpe={best_config['result']['sharpe']:.2f}")
                
                result_obj = SessionStrategyResult(
                    session_name=session_info['name'],
                    primary_ind=best_config['primary'],
                    secondary_ind=best_config['secondary'],
                    sl_mult=best_config['sl'],
                    tp_ratio=best_config['tp'],
                    pf=best_config['result']['pf'],
                    wr=best_config['result']['wr'],
                    trades=best_config['result']['trades'],
                    sharpe=best_config['result']['sharpe'],
                    session_filter=session_key
                )
                self.results.append(result_obj)
            else:
                print(f"  [NO_PROFIT] No profitable combinations found")
        
        return self.results


def main():
    """Run session-filtered optimization."""
    optimizer = SessionFilterOptimizer()
    results = optimizer.optimize_all_sessions("BTCUSD")
    
    if results:
        print("\n" + "="*120)
        print("SESSION COMPARISON SUMMARY".center(120))
        print("="*120 + "\n")
        
        df = pd.DataFrame([r.to_dict() for r in results])
        print(df.to_string(index=False))
        
        print("\n\nKEY INSIGHTS:")
        print(f"  Best Session: {df.loc[df['pf'].idxmax(), 'session_name']} (PF={df['pf'].max():.2f})")
        print(f"  Most Trades:  {df.loc[df['trades'].idxmax(), 'session_name']} ({df['trades'].max()} trades)")
        print(f"  Best WR:      {df.loc[df['wr'].idxmax(), 'session_name']} ({df['wr'].max()*100:.1f}%)")
        
        print("\n" + "="*120 + "\n")
    else:
        print("\nNo results found\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] {e}\n")
        import traceback
        traceback.print_exc()
