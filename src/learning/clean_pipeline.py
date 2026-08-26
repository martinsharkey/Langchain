"""
CLEAN VECTORBT + OPTUNA PIPELINE - Production Ready
Uses MT5 data loader and VectorBT's native indicator discovery
"""

import sys
from pathlib import Path

# Add project root to path
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

from src.mt5.data import get_rates, TIMEFRAMES
from src.utils.logger import get_logger

logger = get_logger("vectorbt_pipeline")

class CleanVectorBTPipeline:
    """Clean production pipeline using MT5 data and VectorBT auto-discovery"""
    
    def __init__(self, symbol="BTCUSD", timeframe="H1", init_cash=10000):
        self.symbol = symbol
        self.timeframe = timeframe
        self.init_cash = init_cash
        self.discovery_results = []
        self.optimization_results = []
        
    def load_mt5_data(self, bars=1000):
        """Load real MT5 data via project data loader"""
        print("Loading MT5 data: {} {} ({} bars)...".format(self.symbol, self.timeframe, bars), end=" ", flush=True)
        try:
            rates = get_rates(symbol=self.symbol, timeframe=self.timeframe, count=bars, lock=True)
            
            if not rates or len(rates) == 0:
                print("FAILED: No data returned")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            
            # Rename to OHLCV
            df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)
            
            print("OK ({} bars)".format(len(df)))
            return df
            
        except Exception as e:
            print("FAILED: {}".format(str(e)[:100]))
            return None
    
    def vectorbt_discover(self, df):
        """Use VectorBT to test all indicators automatically"""
        print("\nPhase 1: VectorBT Indicator Discovery")
        print("-" * 80)
        
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values
        
        results = []
        
        # Get list of all available VectorBT indicators
        vbt_indicators = [x for x in dir(vbt.indicators) if not x.startswith('_') and x[0].isupper()]
        vbt_indicators = [x for x in vbt_indicators if x not in ['IndicatorBase', 'IndicatorFactory']]
        
        print("Testing {} VectorBT indicators...".format(len(vbt_indicators)))
        print()
        
        for i, ind_name in enumerate(vbt_indicators, 1):
            try:
                ind_class = getattr(vbt.indicators, ind_name)
                
                # Run indicator with standard parameters
                if ind_name == 'RSI':
                    result = ind_class.run(close, window=14)
                    entries = (result < 30)
                    exits = (result > 70)
                    
                elif ind_name == 'BBANDS':
                    result = ind_class.run(close, window=20, alpha=2.0)
                    entries = (close < result.lower)
                    exits = (close > result.upper)
                    
                elif ind_name == 'MACD':
                    result = ind_class.run(close, fast=12, slow=26, signal=9)
                    entries = result.macd_crossed_above(result.signal)
                    exits = result.macd_crossed_below(result.signal)
                    
                elif ind_name == 'MA':
                    result = ind_class.run(close, window=20)
                    entries = (close > result.ma)
                    exits = (close < result.ma)
                    
                elif ind_name == 'ATR':
                    result = ind_class.run(high, low, close, window=14)
                    threshold = result.value.rolling(10).mean()
                    entries = (result.value > threshold * 1.5)
                    exits = (result.value < threshold)
                    
                elif ind_name == 'STOCH':
                    result = ind_class.run(high, low, close, window=14)
                    entries = (result.percent_k < 20)
                    exits = (result.percent_k > 80)
                    
                elif ind_name == 'MSTD':
                    result = ind_class.run(close, window=20)
                    threshold = result.mstd.rolling(10).mean()
                    entries = (result.mstd > threshold * 1.5)
                    exits = (result.mstd < threshold)
                    
                elif ind_name == 'OBV':
                    result = ind_class.run(close, volume)
                    threshold = result.obv.rolling(10).mean()
                    entries = (result.obv > threshold)
                    exits = (result.obv < threshold)
                
                else:
                    continue
                
                # Count signals
                entry_count = np.sum(entries) if hasattr(entries, '__len__') else 0
                if entry_count < 2:
                    continue
                
                # Backtest
                pf = vbt.Portfolio.from_signals(close, entries, exits, init_cash=self.init_cash, freq='1h')
                
                pf_value = float(pf.trades.profit_factor() or 0)
                wr = float(pf.trades.win_rate() or 0)
                
                result_dict = {
                    'indicator': ind_name,
                    'trades': int(pf.trades.count() or 0),
                    'win_rate': wr,
                    'profit_factor': pf_value,
                    'return_pct': float(pf.total_return() * 100 if pf.total_return() else 0),
                    'sharpe': float(pf.sharpe_ratio() or 0),
                    'status': 'viable' if pf_value >= 1.2 else 'marginal' if pf_value >= 1.0 else 'not_viable'
                }
                
                results.append(result_dict)
                
                if (i) % 2 == 0:
                    status_icon = "V" if result_dict['status'] == 'viable' else "M" if result_dict['status'] == 'marginal' else "X"
                    print("  [{}/{}] {} - PF: {:.2f}".format(i, len(vbt_indicators), status_icon, pf_value))
                
            except Exception as e:
                pass
        
        # Sort by profit factor
        results = sorted(results, key=lambda x: x['profit_factor'], reverse=True)
        self.discovery_results = results
        
        print("\n" + "=" * 80)
        print("DISCOVERY RESULTS: {} indicators tested".format(len(results)))
        print("=" * 80)
        
        viable = [r for r in results if r['status'] == 'viable']
        marginal = [r for r in results if r['status'] == 'marginal']
        not_viable = [r for r in results if r['status'] == 'not_viable']
        
        print("Viable: {} | Marginal: {} | Not Viable: {}".format(len(viable), len(marginal), len(not_viable)))
        print()
        print("Top 5 Indicators:")
        for i, r in enumerate(results[:5], 1):
            print("  {}. {} - PF: {:.2f}, WR: {:.1f}%, Trades: {}".format(
                i, r['indicator'].ljust(12), r['profit_factor'], r['win_rate']*100, r['trades']
            ))
        
        return results
    
    def optuna_optimize(self, best_indicator, df):
        """Optimize best indicator with Optuna"""
        print("\nPhase 2: Optuna Parameter Optimization")
        print("-" * 80)
        print("Optimizing: {}".format(best_indicator))
        
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values
        
        # Split: 70% train, 30% test
        split_idx = int(len(close) * 0.7)
        close_train = close[:split_idx]
        high_train = high[:split_idx]
        low_train = low[:split_idx]
        volume_train = volume[:split_idx]
        
        def objective(trial):
            """Optuna objective"""
            try:
                if best_indicator == 'RSI':
                    period = trial.suggest_int('period', 7, 21)
                    thresh_low = trial.suggest_int('thresh_low', 15, 35)
                    thresh_high = trial.suggest_int('thresh_high', 65, 85)
                    
                    rsi = vbt.indicators.RSI.run(close_train, window=period)
                    entries = (rsi < thresh_low)
                    exits = (rsi > thresh_high)
                    
                elif best_indicator == 'BBANDS':
                    period = trial.suggest_int('period', 10, 30)
                    alpha = trial.suggest_float('alpha', 1.5, 3.0)
                    
                    bbands = vbt.indicators.BBANDS.run(close_train, window=period, alpha=alpha)
                    entries = (close_train < bbands.lower)
                    exits = (close_train > bbands.upper)
                    
                elif best_indicator == 'MACD':
                    fast = trial.suggest_int('fast', 8, 15)
                    slow = trial.suggest_int('slow', 20, 30)
                    signal = trial.suggest_int('signal', 7, 12)
                    
                    macd = vbt.indicators.MACD.run(close_train, fast=fast, slow=slow, signal=signal)
                    entries = macd.macd_crossed_above(macd.signal)
                    exits = macd.macd_crossed_below(macd.signal)
                    
                else:
                    return 0
                
                if np.sum(entries) < 2:
                    return 0
                
                pf = vbt.Portfolio.from_signals(close_train, entries, exits, init_cash=self.init_cash)
                pf_val = pf.trades.profit_factor() or 0
                wr = pf.trades.win_rate() or 0
                
                return float(pf_val * (0.5 + wr * 0.5))
                
            except:
                return 0
        
        sampler = optuna.samplers.TPESampler(seed=42)
        pruner = MedianPruner()
        study = optuna.create_study(direction='maximize', sampler=sampler, pruner=pruner)
        study.optimize(objective, n_trials=20, show_progress_bar=False)
        
        best = study.best_trial
        
        print("Best Score: {:.4f}".format(best.value))
        print("Best Parameters:")
        for k, v in best.params.items():
            print("  {}: {}".format(k, v))
        
        opt_result = {
            'indicator': best_indicator,
            'best_score': float(best.value),
            'best_params': best.params,
            'n_trials': 20
        }
        
        self.optimization_results.append(opt_result)
        return opt_result, best.params
    
    def validate_optimized(self, best_indicator, best_params, df):
        """Validate on test set"""
        print("\nPhase 3: Walk-Forward Validation")
        print("-" * 80)
        
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        split_idx = int(len(close) * 0.7)
        close_test = close[split_idx:]
        high_test = high[split_idx:]
        low_test = low[split_idx:]
        
        try:
            if best_indicator == 'RSI':
                rsi = vbt.indicators.RSI.run(close_test, window=best_params['period'])
                entries = (rsi < best_params['thresh_low'])
                exits = (rsi > best_params['thresh_high'])
                
            elif best_indicator == 'BBANDS':
                bbands = vbt.indicators.BBANDS.run(close_test, window=best_params['period'], 
                                                  alpha=best_params['alpha'])
                entries = (close_test < bbands.lower)
                exits = (close_test > bbands.upper)
                
            elif best_indicator == 'MACD':
                macd = vbt.indicators.MACD.run(close_test, fast=best_params['fast'], 
                                             slow=best_params['slow'], signal=best_params['signal'])
                entries = macd.macd_crossed_above(macd.signal)
                exits = macd.macd_crossed_below(macd.signal)
            
            pf = vbt.Portfolio.from_signals(close_test, entries, exits, init_cash=self.init_cash)
            
            val_result = {
                'test_trades': int(pf.trades.count() or 0),
                'test_win_rate': float(pf.trades.win_rate() or 0),
                'test_profit_factor': float(pf.trades.profit_factor() or 0),
                'test_return_pct': float(pf.total_return() * 100 if pf.total_return() else 0),
                'status': 'APPROVED' if (pf.trades.profit_factor() or 0) >= 1.2 else 'NEEDS_REVIEW'
            }
            
            print("Test Set Results:")
            print("  Profit Factor: {:.2f}".format(val_result['test_profit_factor']))
            print("  Win Rate: {:.1f}%".format(val_result['test_win_rate']*100))
            print("  Trades: {}".format(val_result['test_trades']))
            print("  Status: {}".format(val_result['status']))
            
            if self.optimization_results:
                self.optimization_results[0].update(val_result)
            
            return val_result
            
        except Exception as e:
            print("Validation failed: {}".format(e))
            return None
    
    def run_complete_pipeline(self):
        """Run complete end-to-end pipeline"""
        print("\n" + "=" * 80)
        print("CLEAN VECTORBT + OPTUNA PIPELINE")
        print("Symbol: {} | Timeframe: {}".format(self.symbol, self.timeframe))
        print("=" * 80)
        
        # Load MT5 data
        df = self.load_mt5_data(bars=1000)
        if df is None or len(df) == 0:
            print("ERROR: Could not load data")
            return False
        
        # Phase 1: Discovery
        discovery = self.vectorbt_discover(df)
        if not discovery:
            print("ERROR: No indicators tested successfully")
            return False
        
        # Get best indicator
        best_indicator = discovery[0]['indicator']
        print("\nBest indicator for optimization: {}".format(best_indicator))
        
        # Phase 2: Optimization
        opt_result, best_params = self.optuna_optimize(best_indicator, df)
        
        # Phase 3: Validation
        val_result = self.validate_optimized(best_indicator, best_params, df)
        
        # Save results
        self.save_results()
        
        return True
    
    def save_results(self):
        """Save all results"""
        output_dir = Path('tests/onboarding/{}'.format(self.symbol))
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'timestamp': datetime.now().isoformat(),
            'discovery': self.discovery_results,
            'optimization': self.optimization_results
        }
        
        json_file = output_dir / '{}_{}_pipeline_results.json'.format(self.symbol, self.timeframe)
        with open(json_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print("\nResults saved to: {}".format(json_file))


if __name__ == '__main__':
    # Test with BTC on H1 timeframe
    pipeline = CleanVectorBTPipeline(symbol="BTCUSD", timeframe="H1")
    pipeline.run_complete_pipeline()
