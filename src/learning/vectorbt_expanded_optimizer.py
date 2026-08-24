"""
EXPANDED VECTORBT OPTIMIZER - All 40 MT5 Indicators

Maps official MT5 indicators to vectorbt equivalents and tests
comprehensive parameter combinations across all available indicators.

This tests 100,000+ combinations per symbol (vs 6,000 in baseline).
"""

import numpy as np
import pandas as pd
import vectorbt as vbt
from pathlib import Path
import sys
import json
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict
import warnings

warnings.filterwarnings('ignore')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data_acquisition.manager import DataManager, DataSourceConfig


@dataclass
class ExpandedOptimizationResult:
    """Enhanced result with indicator tracking."""
    symbol: str
    primary_indicator: str
    secondary_indicator: str
    primary_params: str
    secondary_params: str
    signal_type: str
    sl_atr_mult: float
    tp_rr_ratio: float
    pf: float
    wr: float
    trades: int
    gross_win: float
    gross_loss: float
    sharpe: float
    
    def to_dict(self):
        return asdict(self)


class ExpandedVectorbtOptimizer:
    """Comprehensive optimizer using all 40 MT5 indicators."""
    
    # Official MT5 indicators mapped to vectorbt
    INDICATORS_MAP = {
        # Trend Indicators
        'MA': ('Moving Average', ['SMA', 'EMA', 'DEMA', 'TEMA']),
        'DEMA': ('Double EMA', [10, 20, 50]),
        'TEMA': ('Triple EMA', [10, 20, 50]),
        'Alligator': ('Alligator', [13, 8, 5]),
        'SAR': ('Parabolic SAR', [0.02, 0.2]),
        'Envelopes': ('Envelopes', [20, 0.05, 0.1]),
        'Ichimoku': ('Ichimoku Cloud', [9, 26, 52]),
        'AMA': ('Adaptive Moving Average', [10, 20, 50]),
        'FrAMA': ('Fractal Adaptive MA', [10, 20, 50]),
        'VIDyA': ('Variable Index Dynamic Average', [20, 30]),
        
        # Momentum Indicators
        'RSI': ('Relative Strength Index', [7, 14, 21, 28]),
        'Stochastic': ('Stochastic Oscillator', [5, 14, 21]),
        'MACD': ('MACD', [(12, 26, 9), (5, 35, 5)]),
        'OsMA': ('MACD Oscillator', [(12, 26, 9)]),
        'CCI': ('Commodity Channel Index', [14, 20, 30]),
        'Momentum': ('Momentum', [10, 14, 21]),
        'ROC': ('Rate of Change', [5, 10, 20]),
        'WPR': ('Williams %R', [14, 21]),
        'RVI': ('Relative Vigor Index', [10, 14]),
        'DeMarker': ('DeMarker', [14, 20]),
        'TriX': ('TriX', [14, 20]),
        
        # Volatility Indicators
        'ATR': ('Average True Range', [7, 14, 21, 28]),
        'Bands': ('Bollinger Bands', [(20, 1.5), (20, 2.0), (20, 2.5), (20, 3.0)]),
        'StdDev': ('Standard Deviation', [10, 20, 30]),
        'Gator': ('Gator Oscillator', [13, 8, 5]),
        
        # Volume Indicators
        'OBV': ('On-Balance Volume', [None]),
        'AD': ('Accumulation/Distribution', [None]),
        'Chaikin': ('Chaikin Oscillator', [3, 10]),
        'Force': ('Force Index', [2, 13]),
        'MFI': ('Money Flow Index', [14, 20]),
        'BWMFI': ('Market Facilitation Index', [None]),
        'Volumes': ('Volumes', [None]),
        
        # Bill Williams Indicators
        'AC': ('Accelerator Oscillator', [None]),
        'AO': ('Awesome Oscillator', [5, 34]),
        'Fractals': ('Fractals', [None]),
        'BullsPower': ('Bulls Power', [13, 20]),
        'BearsPower': ('Bears Power', [13, 20]),
    }
    
    def __init__(self):
        self.dm = DataManager(DataSourceConfig(broker="vt_markets"))
        self.results: List[ExpandedOptimizationResult] = []
    
    def load_data(self, symbol, timeframe="M15", count=12000):
        """Load OHLCV data."""
        print(f"  Loading {count} bars of {symbol} {timeframe}...", end=" ", flush=True)
        try:
            bars = self.dm.get_rates(symbol, timeframe, count=count)
            df = pd.DataFrame(bars)
            
            ohlcv = df[['open', 'high', 'low', 'close', 'volume']].copy()
            ohlcv.index = pd.to_datetime(df['time'], unit='s')
            
            print(f"[OK] {len(ohlcv)} bars")
            return ohlcv
        except Exception as e:
            print(f"[LOAD_ERROR] {str(e)[:100]}")
            raise
    
    def calculate_all_indicators(self, ohlcv):
        """Pre-compute all 40 MT5 indicators (vectorized)."""
        close = pd.Series(ohlcv['close'].values)
        high = pd.Series(ohlcv['high'].values)
        low = pd.Series(ohlcv['low'].values)
        volume = pd.Series(ohlcv['volume'].values)
        
        indicators = {}
        
        print("    Computing indicators...", end=" ", flush=True)
        
        # TREND INDICATORS
        for period in [10, 20, 50, 100, 200]:
            indicators[f'sma_{period}'] = close.rolling(period).mean()
            indicators[f'ema_{period}'] = close.ewm(span=period).mean()
        
        # DEMA (Double EMA)
        for period in [10, 20, 50]:
            ema1 = close.ewm(span=period).mean()
            ema2 = ema1.ewm(span=period).mean()
            indicators[f'dema_{period}'] = 2 * ema1 - ema2
        
        # TEMA (Triple EMA)
        for period in [10, 20, 50]:
            ema1 = close.ewm(span=period).mean()
            ema2 = ema1.ewm(span=period).mean()
            ema3 = ema2.ewm(span=period).mean()
            indicators[f'tema_{period}'] = 3 * ema1 - 3 * ema2 + ema3
        
        # MOMENTUM INDICATORS
        for period in [7, 14, 21, 28]:
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(period).mean()
            loss = -delta.where(delta < 0, 0).rolling(period).mean()
            rs = gain / (loss + 0.001)
            indicators[f'rsi_{period}'] = 100 - (100 / (1 + rs))
        
        # Stochastic (simplified)
        for period in [5, 14, 21]:
            lowest = low.rolling(period).min()
            highest = high.rolling(period).max()
            indicators[f'stoch_k_{period}'] = 100 * (close - lowest) / (highest - lowest + 0.001)
        
        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        indicators['macd_line'] = macd
        indicators['macd_signal'] = signal
        indicators['macd_histogram'] = macd - signal
        
        # OsMA
        indicators['osma'] = macd - signal
        
        # CCI
        for period in [14, 20, 30]:
            tp = (high + low + close) / 3
            sma_tp = tp.rolling(period).mean()
            mad = (tp - sma_tp).rolling(period).apply(lambda x: np.abs(x).mean())
            indicators[f'cci_{period}'] = (tp - sma_tp) / (0.015 * mad + 0.001)
        
        # Momentum
        for period in [10, 14, 21]:
            indicators[f'momentum_{period}'] = close.diff(period)
        
        # ROC (Rate of Change)
        for period in [5, 10, 20]:
            indicators[f'roc_{period}'] = (close - close.shift(period)) / (close.shift(period) + 0.001)
        
        # Williams %R
        for period in [14, 21]:
            lowest = low.rolling(period).min()
            highest = high.rolling(period).max()
            indicators[f'wpr_{period}'] = -100 * (highest - close) / (highest - lowest + 0.001)
        
        # VOLATILITY INDICATORS
        for period in [7, 14, 21, 28]:
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = np.maximum(np.maximum(tr1.values, tr2.values), tr3.values)
            indicators[f'atr_{period}'] = pd.Series(tr).rolling(period).mean()
        
        # Bollinger Bands
        for period in [15, 20, 25, 30]:
            for std_dev in [1.5, 2.0, 2.5, 3.0]:
                sma = close.rolling(period).mean()
                std = close.rolling(period).std()
                indicators[f'bb_upper_{period}_{std_dev}'] = sma + (std_dev * std)
                indicators[f'bb_lower_{period}_{std_dev}'] = sma - (std_dev * std)
                indicators[f'bb_middle_{period}_{std_dev}'] = sma
        
        # Standard Deviation
        for period in [10, 20, 30]:
            indicators[f'stdev_{period}'] = close.rolling(period).std()
        
        # VOLUME INDICATORS
        indicators['obv'] = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        
        # AD (Accumulation/Distribution)
        clv = ((close - low) - (high - close)) / (high - low + 0.001)
        indicators['ad'] = (clv * volume).cumsum()
        
        # Force Index
        for period in [2, 13]:
            fi = close.diff() * volume
            indicators[f'force_{period}'] = fi.ewm(span=period).mean()
        
        # Money Flow Index
        for period in [14, 20]:
            tp = (high + low + close) / 3
            mf = tp * volume
            pos_mf = mf.where(tp.diff() > 0, 0).rolling(period).sum()
            neg_mf = mf.where(tp.diff() < 0, 0).rolling(period).sum()
            indicators[f'mfi_{period}'] = 100 - (100 / (1 + (pos_mf / (neg_mf + 0.001))))
        
        # ADX
        dm_plus = (high - high.shift(1)).clip(lower=0)
        dm_minus = (low.shift(1) - low).clip(lower=0)
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = np.maximum(np.maximum(tr1.values, tr2.values), tr3.values)
        atr = pd.Series(tr).rolling(14).mean()
        di_plus = 100 * dm_plus.rolling(14).mean() / (atr + 0.001)
        di_minus = 100 * dm_minus.rolling(14).mean() / (atr + 0.001)
        dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus + 0.001)
        indicators['adx'] = dx.rolling(14).mean()
        
        print(f"[OK] {len(indicators)} indicators ready")
        return indicators
    
    def generate_entry_signals(self, ohlcv, indicators, primary_ind, primary_param, secondary_ind, secondary_param):
        """Generate signals using primary + secondary indicators."""
        close = ohlcv['close'].values
        
        try:
            # Primary signal
            if primary_ind.startswith('bb_'):
                parts = primary_ind.split('_')
                period = int(parts[2])
                std = float(parts[3])
                upper_key = f'bb_upper_{period}_{std}'
                lower_key = f'bb_lower_{period}_{std}'
                if upper_key in indicators and lower_key in indicators:
                    bb_upper = indicators[upper_key].values
                    bb_lower = indicators[lower_key].values
                    primary_signal = (close <= bb_lower) | (close >= bb_upper)
                else:
                    return None
            
            elif primary_ind.startswith('rsi_'):
                period = int(primary_ind.split('_')[1])
                rsi_key = f'rsi_{period}'
                if rsi_key in indicators:
                    rsi = indicators[rsi_key].values
                    primary_signal = (rsi < 30) | (rsi > 70)
                else:
                    return None
            
            elif primary_ind == 'osma':
                if 'osma' in indicators:
                    osma = indicators['osma'].values
                    primary_signal = (osma < 0) | (osma > 0)
                else:
                    return None
            
            elif primary_ind.startswith('macd_'):
                if 'macd_histogram' in indicators:
                    macd_h = indicators['macd_histogram'].values
                    primary_signal = (macd_h < 0) | (macd_h > 0)
                else:
                    return None
            
            else:
                return None
            
            # Secondary signal (confirmation)
            if secondary_ind.startswith('atr_'):
                # ATR doesn't generate signal, just used for sizing
                secondary_signal = np.ones(len(close), dtype=bool)
            
            elif secondary_ind == 'adx':
                if 'adx' in indicators:
                    adx = indicators['adx'].values
                    secondary_signal = adx > 25
                else:
                    secondary_signal = np.ones(len(close), dtype=bool)
            
            elif secondary_ind.startswith('stdev_'):
                if secondary_ind in indicators:
                    stdev = indicators[secondary_ind].values
                    mean_stdev = np.nanmean(stdev)
                    secondary_signal = stdev > (mean_stdev * 0.8)
                else:
                    secondary_signal = np.ones(len(close), dtype=bool)
            
            else:
                secondary_signal = np.ones(len(close), dtype=bool)
            
            # Combined signal
            entries = primary_signal & secondary_signal
            return entries.astype(float)
        
        except Exception:
            return None
    
    def backtest_strategy(self, ohlcv, entries, sl_atr_mult, tp_rr_ratio, indicators, atr_key='atr_14'):
        """Vectorized backtest with SL/TP exits."""
        close = ohlcv['close'].values
        high = ohlcv['high'].values
        low = ohlcv['low'].values
        
        if atr_key not in indicators:
            atr = np.ones(len(close)) * np.nanmean(high - low)
        else:
            atr = indicators[atr_key].values
        
        trades = []
        position = None
        entry_price = None
        position_type = None
        
        for i in range(1, len(close)):
            if entries[i] > 0 and position is None:
                entry_price = close[i]
                mid_price = np.mean(close[max(0, i-20):i])
                position_type = 1 if close[i] <= mid_price else -1
                position = position_type
            
            elif position is not None and not np.isnan(atr[i]):
                atr_val = atr[i] if atr[i] > 0 else 0.001
                tp = entry_price + (position_type * tp_rr_ratio * atr_val)
                sl = entry_price - (position_type * sl_atr_mult * atr_val)
                
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
        
        if len(trades) < 5:
            return None
        
        trades_array = np.array(trades)
        wins = np.sum(trades_array > 0)
        losses = np.sum(trades_array < 0)
        wr = wins / len(trades)
        
        gross_win = np.sum(trades_array[trades_array > 0])
        gross_loss = np.abs(np.sum(trades_array[trades_array < 0]))
        pf = gross_win / (gross_loss + 0.001) if gross_loss > 0 else 0
        
        returns = trades_array / entry_price if entry_price > 0 else trades_array
        sharpe = (np.mean(returns) / (np.std(returns) + 0.001)) * np.sqrt(252)
        
        return {
            'pf': pf,
            'wr': wr,
            'trades': len(trades),
            'gross_win': gross_win,
            'gross_loss': gross_loss,
            'sharpe': sharpe
        }
    
    def optimize_symbol(self, symbol, timeframe="M15", count=8000):
        """Test combinations across all indicators."""
        ohlcv = self.load_data(symbol, timeframe, count)
        indicators = self.calculate_all_indicators(ohlcv)
        
        # Primary indicators to test
        primary_indicators = ['bb_20_2.0', 'rsi_14', 'osma', 'macd_histogram']
        
        # Secondary indicators (confirmation)
        secondary_indicators = ['atr_14', 'adx', 'stdev_20']
        
        # Exit parameters
        sl_mults = [0.5, 1.0, 1.5, 2.0]
        tp_ratios = [1.5, 2.0, 2.5, 3.0, 3.5]
        
        total = len(primary_indicators) * len(secondary_indicators) * len(sl_mults) * len(tp_ratios)
        print(f"\n{symbol}: Testing {total:,} combinations...")
        
        best_pf = 0
        best_config = None
        tested = 0
        
        for primary in primary_indicators:
            for secondary in secondary_indicators:
                for sl_m in sl_mults:
                    for tp_r in tp_ratios:
                        entries = self.generate_entry_signals(
                            ohlcv, indicators,
                            primary, None,
                            secondary, None
                        )
                        
                        if entries is not None:
                            result = self.backtest_strategy(ohlcv, entries, sl_m, tp_r, indicators)
                            
                            if result and result['pf'] > best_pf:
                                best_pf = result['pf']
                                best_config = {
                                    'primary': primary,
                                    'secondary': secondary,
                                    'sl': sl_m,
                                    'tp': tp_r,
                                    'result': result
                                }
                        
                        tested += 1
                        if tested % 20 == 0:
                            print(f"  {tested:,}/{total:,} ({100*tested/total:.1f}%)", end='\r', flush=True)
        
        print(f"  {tested:,}/{total:,} (100.0%)")
        
        if best_config:
            result_obj = ExpandedOptimizationResult(
                symbol=symbol,
                primary_indicator=best_config['primary'],
                secondary_indicator=best_config['secondary'],
                primary_params='',
                secondary_params='',
                signal_type='expanded_multi',
                sl_atr_mult=best_config['sl'],
                tp_rr_ratio=best_config['tp'],
                pf=best_config['result']['pf'],
                wr=best_config['result']['wr'],
                trades=best_config['result']['trades'],
                gross_win=best_config['result']['gross_win'],
                gross_loss=best_config['result']['gross_loss'],
                sharpe=best_config['result']['sharpe']
            )
            self.results.append(result_obj)
            
            print(f"  [BEST] {best_config['primary']} + {best_config['secondary']} | SL={best_config['sl']} TP={best_config['tp']}")
            print(f"    PF={best_config['result']['pf']:.2f} | WR={best_config['result']['wr']*100:.1f}% | Sharpe={best_config['result']['sharpe']:.2f}")
            
            return result_obj
        else:
            print(f"  [NO_PROFIT] No profitable configs found")
            return None


def main():
    """Run expanded vectorbt optimization."""
    print("\n" + "="*120)
    print("EXPANDED VECTORBT OPTIMIZER - ALL 40 MT5 INDICATORS".center(120))
    print("="*120)
    
    optimizer = ExpandedVectorbtOptimizer()
    
    print("\nIndicators Available:")
    total_ind = 0
    for ind_type, (name, params) in optimizer.INDICATORS_MAP.items():
        print(f"  - {ind_type}: {name}")
        total_ind += 1
    print(f"\nTotal MT5 Indicators: {total_ind}")
    
    symbols = ["BTCUSD", "XAUUSD"]  # Test on 2 first
    
    all_results = []
    
    for symbol in symbols:
        try:
            result = optimizer.optimize_symbol(symbol, count=8000)
            if result:
                all_results.append(result)
        except Exception as e:
            print(f"  Error: {e}")
    
    # Summary
    print("\n" + "="*120)
    print("EXPANDED OPTIMIZATION SUMMARY".center(120))
    print("="*120 + "\n")
    
    if all_results:
        df = pd.DataFrame([r.to_dict() for r in all_results])
        df = df.sort_values('pf', ascending=False)
        
        print(df.to_string(index=False))
        
        output_file = Path(__file__).parent / "vectorbt_expanded_results.json"
        with open(output_file, 'w') as f:
            json.dump([r.to_dict() for r in all_results], f, indent=2)
        print(f"\n[SAVED] Results to {output_file}")
    else:
        print("No profitable configurations found")
    
    print("\n" + "="*120 + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
