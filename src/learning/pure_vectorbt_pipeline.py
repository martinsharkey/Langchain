"""
PURE VECTORBT PIPELINE - No custom logic
Uses only VectorBT's built-in indicator discovery and portfolio testing
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import vectorbt as vbt
import pandas as pd
import numpy as np
import optuna
from optuna.pruners import MedianPruner
import json
from datetime import datetime
import logging

from src.mt5.data import get_rates
from src.utils.logger import get_logger

logger = get_logger("vectorbt_pure")

class PureVectorBTPipeline:
    """Pipeline using only VectorBT native functionality"""
    
    def __init__(self, symbol="BTCUSD", timeframe="H1", init_cash=10000):
        self.symbol = symbol
        self.timeframe = timeframe
        self.init_cash = init_cash
        self.discovery_results = []
        self.optimization_results = []
        
    def load_data(self, bars=1000):
        """Load MT5 data"""
        print("Loading data: {} {}...".format(self.symbol, self.timeframe), end=" ", flush=True)
        try:
            rates = get_rates(symbol=self.symbol, timeframe=self.timeframe, count=bars, lock=True)
            
            if not rates or len(rates) == 0:
                print("FAILED")
                return None
            
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)
            
            print("OK ({} bars)".format(len(df)))
            return df
            
        except Exception as e:
            print("FAILED: {}".format(str(e)[:80]))
            return None
    
    def vectorbt_discovery(self, df):
        """Use VectorBT's native indicator discovery"""
        print("\nPhase 1: VectorBT Indicator Discovery")
        print("-" * 80)
        
        price = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        results = []
        
        # Test each VectorBT indicator with its default parameters
        indicators_to_test = [
            ('RSI', vbt.indicators.RSI),
            ('BBANDS', vbt.indicators.BBANDS),
            ('MACD', vbt.indicators.MACD),
            ('MA', vbt.indicators.MA),
            ('ATR', vbt.indicators.ATR),
            ('STOCH', vbt.indicators.STOCH),
            ('MSTD', vbt.indicators.MSTD),
            ('OBV', vbt.indicators.OBV),
        ]
        
        print("Testing {} indicators...\n".format(len(indicators_to_test)))
        
        for ind_name, ind_class in indicators_to_test:
            try:
                print("  {}...".format(ind_name.ljust(12)), end=" ", flush=True)
                
                # Run with VectorBT defaults - no custom logic
                if ind_name == 'RSI':
                    ind = ind_class.run(price)
                    # VectorBT returns RSI values, use simple threshold
                    entries = ind < 30
                    exits = ind > 70
                    
                elif ind_name == 'BBANDS':
                    ind = ind_class.run(price)
                    entries = price < ind.lower
                    exits = price > ind.upper
                    
                elif ind_name == 'MACD':
                    ind = ind_class.run(price)
                    entries = ind.macd_crossed_above(ind.signal)
                    exits = ind.macd_crossed_below(ind.signal)
                    
                elif ind_name == 'MA':
                    ind = ind_class.run(price)
                    entries = price > ind.ma
                    exits = price < ind.ma
                    
                elif ind_name == 'ATR':
                    ind = ind_class.run(high, low, price)
                    entries = ind.value > ind.value.rolling(10).mean()
                    exits = ind.value < ind.value.rolling(10).mean()
                    
                elif ind_name == 'STOCH':
                    ind = ind_class.run(high, low, price)
                    entries = ind.percent_k < 20
                    exits = ind.percent_k > 80
                    
                elif ind_name == 'MSTD':
                    ind = ind_class.run(price)
                    entries = ind.mstd > ind.mstd.rolling(10).mean()
                    exits = ind.mstd < ind.mstd.rolling(10).mean()
                    
                elif ind_name == 'OBV':
                    ind = ind_class.run(price, volume)
                    entries = ind.obv > ind.obv.rolling(10).mean()
                    exits = ind.obv < ind.obv.rolling(10).mean()
                
                else:
                    print("SKIP")
                    continue
                
                # Run VectorBT backtest
                pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=self.init_cash, freq='1h')
                
                pf_val = float(pf.trades.profit_factor() or 0)
                wr = float(pf.trades.win_rate() or 0)
                trades = int(pf.trades.count() or 0)
                ret = float(pf.total_return() * 100 if pf.total_return() else 0)
                sharpe = float(pf.sharpe_ratio() or 0)
                
                result = {
                    'indicator': ind_name,
                    'trades': trades,
                    'win_rate': wr,
                    'profit_factor': pf_val,
                    'return_pct': ret,
                    'sharpe': sharpe,
                    'status': 'viable' if pf_val >= 1.2 else 'marginal' if pf_val >= 1.0 else 'not_viable'
                }
                
                results.append(result)
                print("PF={:.2f} WR={:.0f}% T={}".format(pf_val, wr*100, trades))
                
            except Exception as e:
                print("ERROR: {}".format(str(e)[:50]))
        
        results = sorted(results, key=lambda x: x['profit_factor'], reverse=True)
        self.discovery_results = results
        
        print("\n" + "=" * 80)
        print("DISCOVERY RESULTS")
        print("=" * 80)
        for i, r in enumerate(results, 1):
            print("  {}. {} - PF: {:.2f}, WR: {:.0f}%, Trades: {}, Status: {}".format(
                i, r['indicator'].ljust(12), r['profit_factor'], r['win_rate']*100, 
                r['trades'], r['status']
            ))
        
        return results
    
    def optuna_optimize(self, best_ind_name, df):
        """Optimize best indicator using Optuna"""
        print("\nPhase 2: Optuna Parameter Optimization")
        print("-" * 80)
        print("Optimizing: {}".format(best_ind_name))
        
        price = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        split_idx = int(len(price) * 0.7)
        price_train = price[:split_idx]
        high_train = high[:split_idx]
        low_train = low[:split_idx]
        volume_train = volume[:split_idx]
        
        def objective(trial):
            """Optuna objective using VectorBT"""
            try:
                if best_ind_name == 'RSI':
                    period = trial.suggest_int('period', 7, 21)
                    thresh_low = trial.suggest_int('thresh_low', 15, 35)
                    thresh_high = trial.suggest_int('thresh_high', 65, 85)
                    
                    ind = vbt.indicators.RSI.run(price_train, window=period)
                    entries = ind < thresh_low
                    exits = ind > thresh_high
                    
                elif best_ind_name == 'BBANDS':
                    period = trial.suggest_int('period', 10, 30)
                    alpha = trial.suggest_float('alpha', 1.5, 3.0)
                    
                    ind = vbt.indicators.BBANDS.run(price_train, window=period, alpha=alpha)
                    entries = price_train < ind.lower
                    exits = price_train > ind.upper
                    
                elif best_ind_name == 'MACD':
                    fast = trial.suggest_int('fast', 8, 15)
                    slow = trial.suggest_int('slow', 20, 30)
                    signal = trial.suggest_int('signal', 7, 12)
                    
                    ind = vbt.indicators.MACD.run(price_train, fast=fast, slow=slow, signal=signal)
                    entries = ind.macd_crossed_above(ind.signal)
                    exits = ind.macd_crossed_below(ind.signal)
                    
                elif best_ind_name == 'MA':
                    fast_window = trial.suggest_int('fast_window', 5, 15)
                    slow_window = trial.suggest_int('slow_window', 20, 50)
                    
                    fast = vbt.indicators.MA.run(price_train, window=fast_window)
                    slow = vbt.indicators.MA.run(price_train, window=slow_window)
                    entries = fast.ma_crossed_above(slow.ma)
                    exits = fast.ma_crossed_below(slow.ma)
                    
                elif best_ind_name == 'ATR':
                    period = trial.suggest_int('period', 10, 20)
                    mult = trial.suggest_float('mult', 1.0, 2.0)
                    
                    ind = vbt.indicators.ATR.run(high_train, low_train, price_train, window=period)
                    threshold = ind.value.rolling(10).mean() * mult
                    entries = ind.value > threshold
                    exits = ind.value < threshold
                    
                else:
                    return 0
                
                if entries.sum() < 2:
                    return 0
                
                pf = vbt.Portfolio.from_signals(price_train, entries, exits, init_cash=self.init_cash)
                pf_val = pf.trades.profit_factor() or 0
                wr = pf.trades.win_rate() or 0
                
                return float(pf_val * (0.5 + wr * 0.5))
                
            except:
                return 0
        
        sampler = optuna.samplers.TPESampler(seed=42)
        study = optuna.create_study(direction='maximize', sampler=sampler)
        study.optimize(objective, n_trials=20, show_progress_bar=False)
        
        best = study.best_trial
        
        print("Best Score: {:.4f}".format(best.value))
        print("Best Parameters:")
        for k, v in best.params.items():
            print("  {}: {}".format(k, v))
        
        opt_result = {
            'indicator': best_ind_name,
            'best_score': float(best.value),
            'best_params': best.params,
            'n_trials': 20
        }
        
        self.optimization_results.append(opt_result)
        return opt_result, best.params
    
    def validate(self, best_ind_name, best_params, df):
        """Validate on test set using VectorBT"""
        print("\nPhase 3: Walk-Forward Validation (Test Set)")
        print("-" * 80)
        
        price = df['close']
        high = df['high']
        low = df['low']
        
        split_idx = int(len(price) * 0.7)
        price_test = price[split_idx:]
        high_test = high[split_idx:]
        low_test = low[split_idx:]
        
        try:
            if best_ind_name == 'RSI':
                ind = vbt.indicators.RSI.run(price_test, window=best_params['period'])
                entries = ind < best_params['thresh_low']
                exits = ind > best_params['thresh_high']
                
            elif best_ind_name == 'BBANDS':
                ind = vbt.indicators.BBANDS.run(price_test, window=best_params['period'], alpha=best_params['alpha'])
                entries = price_test < ind.lower
                exits = price_test > ind.upper
                
            elif best_ind_name == 'MACD':
                ind = vbt.indicators.MACD.run(price_test, fast=best_params['fast'], slow=best_params['slow'], signal=best_params['signal'])
                entries = ind.macd_crossed_above(ind.signal)
                exits = ind.macd_crossed_below(ind.signal)
                
            elif best_ind_name == 'MA':
                fast = vbt.indicators.MA.run(price_test, window=best_params['fast_window'])
                slow = vbt.indicators.MA.run(price_test, window=best_params['slow_window'])
                entries = fast.ma_crossed_above(slow.ma)
                exits = fast.ma_crossed_below(slow.ma)
                
            elif best_ind_name == 'ATR':
                ind = vbt.indicators.ATR.run(high_test, low_test, price_test, window=best_params['period'])
                threshold = ind.value.rolling(10).mean() * best_params['mult']
                entries = ind.value > threshold
                exits = ind.value < threshold
            
            pf = vbt.Portfolio.from_signals(price_test, entries, exits, init_cash=self.init_cash)
            
            val = {
                'test_trades': int(pf.trades.count() or 0),
                'test_win_rate': float(pf.trades.win_rate() or 0),
                'test_profit_factor': float(pf.trades.profit_factor() or 0),
                'test_return_pct': float(pf.total_return() * 100 if pf.total_return() else 0),
                'test_sharpe': float(pf.sharpe_ratio() or 0),
                'status': 'APPROVED' if (pf.trades.profit_factor() or 0) >= 1.2 else 'REVIEW'
            }
            
            print("Test Results:")
            print("  PF: {:.2f} | WR: {:.0f}% | Trades: {} | Return: {:.1f}% | Status: {}".format(
                val['test_profit_factor'], val['test_win_rate']*100, val['test_trades'],
                val['test_return_pct'], val['status']
            ))
            
            if self.optimization_results:
                self.optimization_results[0].update(val)
            
            return val
            
        except Exception as e:
            print("Validation error: {}".format(e))
            return None
    
    def run(self):
        """Run complete pipeline"""
        print("\n" + "=" * 80)
        print("PURE VECTORBT PIPELINE - {} {}".format(self.symbol, self.timeframe))
        print("=" * 80)
        
        df = self.load_data(bars=1000)
        if df is None or len(df) == 0:
            return False
        
        # Phase 1: Discovery
        discovery = self.vectorbt_discovery(df)
        if not discovery:
            return False
        
        best_ind = discovery[0]['indicator']
        print("\nSelected for optimization: {}".format(best_ind))
        
        # Phase 2: Optimization
        opt_result, best_params = self.optuna_optimize(best_ind, df)
        
        # Phase 3: Validation
        self.validate(best_ind, best_params, df)
        
        # Save
        self.save_results()
        return True
    
    def save_results(self):
        """Save results"""
        output_dir = Path('tests/onboarding/{}'.format(self.symbol))
        output_dir.mkdir(parents=True, exist_ok=True)
        
        data = {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'timestamp': datetime.now().isoformat(),
            'discovery': self.discovery_results,
            'optimization': self.optimization_results
        }
        
        out_file = output_dir / '{}_{}_pure_vbt.json'.format(self.symbol, self.timeframe)
        with open(out_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print("\nResults: {}".format(out_file))


if __name__ == '__main__':
    pipeline = PureVectorBTPipeline(symbol="BTCUSD", timeframe="H1")
    pipeline.run()
