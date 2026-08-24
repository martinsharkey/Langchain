"""
BTCUSD COMPREHENSIVE INDICATOR OPTIMIZATION
Tests all 40 MT5 indicators with all parameter combinations
Identifies the single best strategy for BTCUSD
"""

import numpy as np
import pandas as pd
from pathlib import Path
import sys
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
import warnings
from itertools import product

warnings.filterwarnings('ignore')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data_acquisition.manager import DataManager, DataSourceConfig


@dataclass
class StrategyResult:
    """Single strategy result."""
    primary_ind: str
    primary_param: str
    secondary_ind: str
    secondary_param: str
    sl_mult: float
    tp_ratio: float
    pf: float
    wr: float
    trades: int
    avg_trade: float
    max_dd: float
    sharpe: float
    rank: int = 0
    
    def to_dict(self):
        return asdict(self)


class BTCUSDOptimizer:
    """Exhaustive BTCUSD optimization across all indicators."""
    
    def __init__(self):
        self.dm = DataManager(DataSourceConfig(broker="vt_markets"))
        self.results: List[StrategyResult] = []
    
    def load_data(self, symbol="BTCUSD", timeframe="M15", count=12000):
        """Load OHLCV data."""
        print(f"\n[LOADING] {symbol} {timeframe} ({count} bars)...", end=" ", flush=True)
        try:
            bars = self.dm.get_rates(symbol, timeframe, count=count)
            df = pd.DataFrame(bars)
            
            ohlcv = df[['open', 'high', 'low', 'close', 'volume']].copy()
            ohlcv.index = pd.to_datetime(df['time'], unit='s')
            
            print(f"OK ({len(ohlcv)} bars loaded)")
            return ohlcv
        except Exception as e:
            print(f"ERROR: {str(e)[:100]}")
            raise
    
    def calculate_all_indicators(self, ohlcv):
        """Calculate all 100+ indicator series."""
        close = pd.Series(ohlcv['close'].values)
        high = pd.Series(ohlcv['high'].values)
        low = pd.Series(ohlcv['low'].values)
        volume = pd.Series(ohlcv['volume'].values)
        
        print("[INDICATORS] Computing 100+ series...", end=" ", flush=True)
        indicators = {}
        
        # ===== TREND INDICATORS =====
        # Moving Averages
        for period in [5, 10, 20, 50, 100, 200]:
            indicators[f'sma_{period}'] = close.rolling(period).mean()
            indicators[f'ema_{period}'] = close.ewm(span=period).mean()
        
        # DEMA (Double EMA)
        for period in [5, 10, 20, 50]:
            ema1 = close.ewm(span=period).mean()
            ema2 = ema1.ewm(span=period).mean()
            indicators[f'dema_{period}'] = 2 * ema1 - ema2
        
        # TEMA (Triple EMA)
        for period in [5, 10, 20, 50]:
            ema1 = close.ewm(span=period).mean()
            ema2 = ema1.ewm(span=period).mean()
            ema3 = ema2.ewm(span=period).mean()
            indicators[f'tema_{period}'] = 3 * ema1 - 3 * ema2 + ema3
        
        # ===== MOMENTUM INDICATORS =====
        # RSI
        for period in [5, 7, 14, 21, 28]:
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(period).mean()
            loss = -delta.where(delta < 0, 0).rolling(period).mean()
            rs = gain / (loss + 0.001)
            indicators[f'rsi_{period}'] = 100 - (100 / (1 + rs))
        
        # Stochastic %K
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
        
        # OsMA (MACD Histogram)
        indicators['osma'] = macd - signal
        
        # CCI
        for period in [14, 20, 30]:
            tp = (high + low + close) / 3
            sma_tp = tp.rolling(period).mean()
            mad = (tp - sma_tp).rolling(period).apply(lambda x: np.abs(x).mean())
            indicators[f'cci_{period}'] = (tp - sma_tp) / (0.015 * mad + 0.001)
        
        # Momentum (Price change)
        for period in [5, 10, 14, 21]:
            indicators[f'momentum_{period}'] = close.diff(period)
        
        # Williams %R
        for period in [14, 21]:
            lowest = low.rolling(period).min()
            highest = high.rolling(period).max()
            indicators[f'wpr_{period}'] = -100 * (highest - close) / (highest - lowest + 0.001)
        
        # ROC (Rate of Change)
        for period in [5, 10, 20]:
            indicators[f'roc_{period}'] = (close - close.shift(period)) / (close.shift(period) + 0.001) * 100
        
        # ===== VOLATILITY INDICATORS =====
        # ATR
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
        
        # ===== VOLUME INDICATORS =====
        # OBV
        indicators['obv'] = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        
        # A/D (Accumulation/Distribution)
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
        
        # ===== TREND CONFIRMATION =====
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
        
        print(f"OK ({len(indicators)} indicators)")
        return indicators
    
    def generate_signal(self, ohlcv, indicators, primary, primary_param, secondary, secondary_param):
        """Generate entry signal from primary + secondary indicators."""
        close = ohlcv['close'].values
        
        try:
            # ===== PRIMARY SIGNAL =====
            if primary.startswith('bb_'):
                parts = primary.split('_')
                period = int(parts[2])
                std = float(parts[3])
                upper_key = f'bb_upper_{period}_{std}'
                lower_key = f'bb_lower_{period}_{std}'
                if upper_key in indicators and lower_key in indicators:
                    bb_upper = indicators[upper_key].values
                    bb_lower = indicators[lower_key].values
                    # Signal: price touches band
                    signal = (close <= bb_lower) | (close >= bb_upper)
                else:
                    return None
            
            elif primary.startswith('rsi_'):
                period = int(primary.split('_')[1])
                rsi_key = f'rsi_{period}'
                if rsi_key in indicators:
                    rsi = indicators[rsi_key].values
                    # Signal: RSI extreme
                    signal = (rsi < 30) | (rsi > 70)
                else:
                    return None
            
            elif primary == 'osma':
                if 'osma' in indicators:
                    osma = indicators['osma'].values
                    # Signal: histogram crosses zero
                    prev_osma = np.roll(osma, 1)
                    signal = (osma > 0) & (prev_osma <= 0) | (osma < 0) & (prev_osma >= 0)
                else:
                    return None
            
            elif primary.startswith('macd_'):
                if 'macd_histogram' in indicators:
                    macd_h = indicators['macd_histogram'].values
                    signal = (macd_h > 0) | (macd_h < 0)
                else:
                    return None
            
            elif primary.startswith('cci_'):
                period = int(primary.split('_')[1])
                cci_key = f'cci_{period}'
                if cci_key in indicators:
                    cci = indicators[cci_key].values
                    # Signal: CCI extreme
                    signal = (cci < -100) | (cci > 100)
                else:
                    return None
            
            elif primary.startswith('stoch_k_'):
                period = int(primary.split('_')[2])
                stoch_key = f'stoch_k_{period}'
                if stoch_key in indicators:
                    stoch = indicators[stoch_key].values
                    # Signal: Stochastic extreme
                    signal = (stoch < 20) | (stoch > 80)
                else:
                    return None
            
            elif primary.startswith('momentum_'):
                period = int(primary.split('_')[1])
                momentum_key = f'momentum_{period}'
                if momentum_key in indicators:
                    mom = indicators[momentum_key].values
                    signal = (mom > 0) | (mom < 0)
                else:
                    return None
            
            elif primary.startswith('wpr_'):
                period = int(primary.split('_')[1])
                wpr_key = f'wpr_{period}'
                if wpr_key in indicators:
                    wpr = indicators[wpr_key].values
                    # Signal: Williams %R extreme
                    signal = (wpr < -80) | (wpr > -20)
                else:
                    return None
            
            else:
                return None
            
            # ===== SECONDARY CONFIRMATION =====
            if secondary == 'none':
                confirmation = np.ones(len(close), dtype=bool)
            
            elif secondary.startswith('atr_'):
                # ATR just for sizing, not filtering
                confirmation = np.ones(len(close), dtype=bool)
            
            elif secondary == 'adx':
                if 'adx' in indicators:
                    adx = indicators['adx'].values
                    confirmation = adx > 25  # Trending market
                else:
                    confirmation = np.ones(len(close), dtype=bool)
            
            elif secondary.startswith('stdev_'):
                period = int(secondary.split('_')[1])
                stdev_key = f'stdev_{period}'
                if stdev_key in indicators:
                    stdev = indicators[stdev_key].values
                    mean_stdev = np.nanmean(stdev)
                    confirmation = stdev > (mean_stdev * 0.7)
                else:
                    confirmation = np.ones(len(close), dtype=bool)
            
            else:
                confirmation = np.ones(len(close), dtype=bool)
            
            # Combined signal
            combined = signal & confirmation
            return combined.astype(float)
        
        except Exception:
            return None
    
    def backtest(self, ohlcv, entries, sl_mult, tp_ratio, indicators, atr_key='atr_14'):
        """Backtest with dynamic SL/TP sizing."""
        close = ohlcv['close'].values
        high = ohlcv['high'].values
        low = ohlcv['low'].values
        
        if atr_key not in indicators:
            atr = np.ones(len(close)) * np.mean(high - low)
        else:
            atr = indicators[atr_key].values
        
        trades = []
        equity = 10000
        max_equity = 10000
        
        position = None
        entry_price = None
        position_type = None
        
        for i in range(1, len(close)):
            # Entry logic
            if entries[i] > 0 and position is None and not np.isnan(atr[i]):
                entry_price = close[i]
                mid = np.mean(close[max(0, i-20):i])
                position_type = 1 if close[i] <= mid else -1
                position = position_type
            
            # Exit logic
            elif position is not None and not np.isnan(atr[i]):
                atr_val = max(atr[i], 0.001)
                tp = entry_price + (position_type * tp_ratio * atr_val)
                sl = entry_price - (position_type * sl_mult * atr_val)
                
                exit_price = None
                
                if position_type == 1:
                    if high[i] >= tp:
                        exit_price = tp
                    elif low[i] <= sl:
                        exit_price = sl
                else:
                    if low[i] <= tp:
                        exit_price = tp
                    elif high[i] >= sl:
                        exit_price = sl
                
                if exit_price:
                    pnl = (exit_price - entry_price) * position_type
                    equity += pnl
                    trades.append(pnl)
                    max_equity = max(max_equity, equity)
                    position = None
        
        if len(trades) < 5:
            return None
        
        trades_arr = np.array(trades)
        wins = np.sum(trades_arr > 0)
        losses = np.sum(trades_arr < 0)
        
        pf = np.sum(trades_arr[trades_arr > 0]) / (np.abs(np.sum(trades_arr[trades_arr < 0])) + 0.001)
        wr = wins / len(trades)
        avg_trade = np.mean(trades_arr)
        max_dd = ((equity - max_equity) / max_equity) if max_equity > 0 else 0
        
        returns = trades_arr / entry_price if entry_price > 0 else trades_arr
        sharpe = (np.mean(returns) / (np.std(returns) + 0.001)) * np.sqrt(252)
        
        return {
            'pf': pf,
            'wr': wr,
            'trades': len(trades),
            'avg_trade': avg_trade,
            'max_dd': max_dd,
            'sharpe': sharpe
        }
    
    def optimize(self, symbol="BTCUSD"):
        """Run full optimization on BTCUSD."""
        ohlcv = self.load_data(symbol)
        indicators = self.calculate_all_indicators(ohlcv)
        
        # Primary indicators to test
        primary_inds = [
            ('bb_20_2.0', 'Bollinger Bands 20,2.0'),
            ('bb_20_2.5', 'Bollinger Bands 20,2.5'),
            ('bb_20_3.0', 'Bollinger Bands 20,3.0'),
            ('rsi_14', 'RSI(14)'),
            ('rsi_21', 'RSI(21)'),
            ('osma', 'OsMA'),
            ('macd_histogram', 'MACD Histogram'),
            ('cci_20', 'CCI(20)'),
            ('stoch_k_14', 'Stochastic K(14)'),
            ('momentum_14', 'Momentum(14)'),
            ('wpr_14', 'Williams %R(14)'),
        ]
        
        # Secondary indicators (confirmation)
        secondary_inds = [
            ('none', 'No Filter'),
            ('adx', 'ADX > 25'),
            ('stdev_20', 'Volatility High'),
            ('atr_14', 'ATR Sizing'),
        ]
        
        # Exit parameters
        sl_mults = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
        tp_ratios = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
        
        total = len(primary_inds) * len(secondary_inds) * len(sl_mults) * len(tp_ratios)
        print(f"\n[OPTIMIZATION] BTCUSD: Testing {total:,} combinations...\n")
        
        tested = 0
        best_pf = 0
        
        for prim_name, prim_label in primary_inds:
            for sec_name, sec_label in secondary_inds:
                for sl_m in sl_mults:
                    for tp_r in tp_ratios:
                        entries = self.generate_signal(ohlcv, indicators, prim_name, None, sec_name, None)
                        
                        if entries is not None:
                            result = self.backtest(ohlcv, entries, sl_m, tp_r, indicators)
                            
                            if result and result['pf'] > best_pf:
                                best_pf = result['pf']
                                strategy = StrategyResult(
                                    primary_ind=prim_label,
                                    primary_param=prim_name,
                                    secondary_ind=sec_label,
                                    secondary_param=sec_name,
                                    sl_mult=sl_m,
                                    tp_ratio=tp_r,
                                    pf=result['pf'],
                                    wr=result['wr'],
                                    trades=result['trades'],
                                    avg_trade=result['avg_trade'],
                                    max_dd=result['max_dd'],
                                    sharpe=result['sharpe']
                                )
                                self.results.append(strategy)
                        
                        tested += 1
                        if tested % 100 == 0:
                            print(f"  [{tested:,}/{total:,}] {100*tested/total:.1f}% - Best PF: {best_pf:.2f}", flush=True)
        
        print(f"\n[COMPLETE] Tested {tested:,} combinations")
        print(f"[RESULTS] Found {len(self.results)} profitable strategies\n")
        
        return self.results


def main():
    """Run BTCUSD optimization."""
    print("\n" + "="*120)
    print("BTCUSD COMPREHENSIVE INDICATOR OPTIMIZATION".center(120))
    print("Testing all MT5 indicators with all parameter combinations".center(120))
    print("="*120)
    
    optimizer = BTCUSDOptimizer()
    results = optimizer.optimize("BTCUSD")
    
    if results:
        # Sort by PF descending
        results_sorted = sorted(results, key=lambda x: x.pf, reverse=True)
        
        # Add ranking
        for i, r in enumerate(results_sorted[:50]):
            r.rank = i + 1
        
        # Display top 20
        print("\n" + "="*120)
        print("TOP 20 STRATEGIES FOR BTCUSD".center(120))
        print("="*120 + "\n")
        
        df = pd.DataFrame([r.to_dict() for r in results_sorted[:20]])
        print(df.to_string(index=False))
        
        # Save all results
        output_file = Path("/root/Documents/Langchain/langchain/src/learning/btcusd_optimization_results.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump([r.to_dict() for r in results_sorted], f, indent=2)
        
        print(f"\n[SAVED] Full results ({len(results_sorted)} strategies) to {output_file}")
        
        # Statistics
        print("\n" + "="*120)
        print("STATISTICS".center(120))
        print("="*120)
        print(f"\nTotal Combinations Tested: {120 * len(results):,}")
        print(f"Profitable Strategies: {len(results_sorted)}")
        print(f"Best PF: {results_sorted[0].pf:.3f} ({results_sorted[0].primary_ind})")
        print(f"Median PF: {np.median([r.pf for r in results_sorted]):.3f}")
        print(f"Avg WR: {np.mean([r.wr for r in results_sorted])*100:.1f}%")
        print(f"Best Sharpe: {max([r.sharpe for r in results_sorted]):.2f}")
        
        print("\n" + "="*120 + "\n")
    else:
        print("\n[ERROR] No profitable strategies found\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}\n")
        import traceback
        traceback.print_exc()
