"""
VECTORBT COMPREHENSIVE DISCOVERY - All indicators via pandas_ta integration
Tests VectorBT built-in (8) + pandas_ta (243) = 251+ indicators
Uses MT5 data via project connector
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import vectorbt as vbt
import pandas as pd
import pandas_ta as ta
import numpy as np
import optuna
from optuna.pruners import MedianPruner
import json
from datetime import datetime
import logging
from pathlib import Path

from src.mt5.data import get_rates
from src.utils.logger import get_logger

logger = get_logger("vectorbt_comprehensive")

class ComprehensiveVectorBTPipeline:
    """VectorBT with full indicator ecosystem (built-in + pandas_ta)"""
    
    def __init__(self, symbol="BTCUSD", timeframe="H1", init_cash=10000):
        self.symbol = symbol
        self.timeframe = timeframe
        self.init_cash = init_cash
        self.discovery_results = []
        self.optimization_results = []
        
    def load_data(self, bars=1000):
        """Load MT5 data"""
        print("Loading MT5 data: {} {}...".format(self.symbol, self.timeframe), end=" ", flush=True)
        try:
            rates = get_rates(symbol=self.symbol, timeframe=self.timeframe, count=bars, lock=True)
            
            if not rates or len(rates) == 0:
                print("FAILED")
                return None
            
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            df.rename(columns={'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}, inplace=True)
            
            # Infer frequency
            df.index = pd.DatetimeIndex(df.index)
            df.index.freq = pd.infer_freq(df.index)
            
            print("OK ({} bars)".format(len(df)))
            return df
            
        except Exception as e:
            print("FAILED: {}".format(str(e)[:80]))
            return None
    
    def discover_all_indicators(self, df):
        """Test ALL VectorBT indicators (built-in + pandas_ta)"""
        print("\nPhase 1: VectorBT Comprehensive Indicator Discovery")
        print("-" * 80)
        
        price = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values
        
        results = []
        
        # VectorBT built-in indicators
        vbt_indicators = [
            ('RSI', 'vectorbt'),
            ('BBANDS', 'vectorbt'),
            ('MACD', 'vectorbt'),
        ]
        
        # Get pandas_ta indicators
        pda_funcs = [x for x in dir(ta) if not x.startswith('_') and x.islower() and callable(getattr(ta, x))]
        pda_indicators = [(name, 'pandas_ta') for name in pda_funcs]
        
        all_indicators = vbt_indicators + pda_indicators
        
        print("Testing {} indicators ({} VectorBT + {} pandas_ta)".format(
            len(all_indicators), len(vbt_indicators), len(pda_indicators)
        ))
        print()
        
        # Test VectorBT indicators
        print("VectorBT Built-in Indicators:")
        for ind_name, ind_type in vbt_indicators:
            print("  Testing {}...".format(ind_name), flush=True)
            try:
                result = self._test_vectorbt_indicator(ind_name, df)
                if result:
                    results.append(result)
                    print("    ✓ PF: {:.2f}".format(result['profit_factor']))
                else:
                    print("    ✗ No viable signals")
            except Exception as e:
                print("    ERROR: {}".format(str(e)[:80]))
        
        # Test pandas_ta indicators
        print("\npandas_ta Indicators ({} total):".format(len(pda_indicators)))
        tested = 0
        failed = 0
        for i, (ind_name, ind_type) in enumerate(pda_indicators):
            if i % 50 == 0:
                print("  Testing {}-{}...".format(i, min(i+50, len(pda_indicators))))
            
            try:
                result = self._test_pandas_ta_indicator(ind_name, df)
                if result:
                    results.append(result)
                    tested += 1
            except Exception as e:
                failed += 1
                logger.debug("pandas_ta {}: {}".format(ind_name, str(e)[:100]))
        
        print("  Tested: {}/{} (Failed: {})".format(tested, len(pda_indicators), failed))
        
        # Sort results
        results = sorted(results, key=lambda x: x['profit_factor'], reverse=True)
        self.discovery_results = results
        
        # Report
        print("\n" + "=" * 80)
        print("DISCOVERY COMPLETE: {} indicators tested".format(len(results)))
        print("=" * 80)
        
        viable = [r for r in results if r['status'] == 'viable']
        print("Viable (PF >= 1.2): {}".format(len(viable)))
        print()
        print("Top 10 Indicators:")
        for i, r in enumerate(results[:10], 1):
            print("  {}. {} ({}) - PF: {:.2f}, WR: {:.0f}%, Trades: {}".format(
                i, r['indicator'].ljust(15), r['type'].ljust(10), 
                r['profit_factor'], r['win_rate']*100, r['trades']
            ))
        
        return results
    
    def _test_vectorbt_indicator(self, ind_name, df):
        """Test VectorBT built-in indicator"""
        price = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        try:
            if ind_name == 'RSI':
                ind = vbt.indicators.RSI.run(price)
                entries = ind.rsi < 30
                exits = ind.rsi > 70
            elif ind_name == 'BBANDS':
                ind = vbt.indicators.BBANDS.run(price)
                entries = price < ind.lower
                exits = price > ind.upper
            elif ind_name == 'MACD':
                ind = vbt.indicators.MACD.run(price)
                entries = ind.macd_crossed_above(ind.signal)
                exits = ind.macd_crossed_below(ind.signal)
            else:
                return None
            
            if entries.sum() < 2:
                return None
            
            # Convert to numpy arrays for portfolio calculation
            price_vals = price.values if hasattr(price, 'values') else price
            entries_vals = entries.values if hasattr(entries, 'values') else entries
            exits_vals = exits.values if hasattr(exits, 'values') else exits
            
            pf = vbt.Portfolio.from_signals(price_vals, entries_vals, exits_vals, init_cash=self.init_cash)
            
            if not pf.trades.count():
                return None
            
            return {
                'indicator': ind_name,
                'type': 'vectorbt',
                'trades': int(pf.trades.count() or 0),
                'win_rate': float(pf.trades.win_rate() or 0),
                'profit_factor': float(pf.trades.profit_factor() or 0),
                'return_pct': float(pf.total_return() * 100 if pf.total_return() else 0),
                'sharpe': float(pf.sharpe_ratio() or 0),
                'status': 'viable' if (pf.trades.profit_factor() or 0) >= 1.2 else 'marginal' if (pf.trades.profit_factor() or 0) >= 1.0 else 'not_viable'
            }
        except Exception as e:
            logger.debug("VectorBT {}: {}".format(ind_name, str(e)[:100]))
            return None
    
    def _test_pandas_ta_indicator(self, ind_name, df):
        """Test pandas_ta indicator"""
        try:
            price = df['close']
            high = df['high']
            low = df['low']
            volume = df['volume']
            
            ind_func = getattr(ta, ind_name)
            result = None
            
            # Try different parameter combinations
            try:
                result = ind_func(price)
            except:
                try:
                    result = ind_func(high, low, price)
                except:
                    try:
                        result = ind_func(price, volume)
                    except:
                        try:
                            result = ind_func(high, low)
                        except:
                            return None
            
            if result is None or not isinstance(result, (pd.Series, pd.DataFrame)):
                return None
            
            # Generate signal
            if isinstance(result, pd.DataFrame):
                signal_data = result.iloc[:, 0]
            else:
                signal_data = result
            
            # Drop NaN values
            signal_data = signal_data.dropna()
            
            if len(signal_data) < 10:
                return None
            
            # Generate entries/exits using simple threshold
            try:
                signal_median = signal_data.median()
                entries = signal_data > signal_median
                exits = signal_data < signal_median
            except:
                return None
            
            if entries.sum() < 2:
                return None
            
            # Align price with signal data (critical: both must have same length and index)
            price_aligned = price.loc[signal_data.index]
            
            # Ensure no NaN in price_aligned
            if price_aligned.isna().sum() > 0:
                return None
            
            pf = vbt.Portfolio.from_signals(
                price_aligned.values,
                entries.values,
                exits.values,
                init_cash=self.init_cash
            )
            
            if not pf.trades.count() or pf.trades.count() < 1:
                return None
            
            return {
                'indicator': ind_name,
                'type': 'pandas_ta',
                'trades': int(pf.trades.count() or 0),
                'win_rate': float(pf.trades.win_rate() or 0),
                'profit_factor': float(pf.trades.profit_factor() or 0),
                'return_pct': float(pf.total_return() * 100 if pf.total_return() else 0),
                'sharpe': float(pf.sharpe_ratio() or 0),
                'status': 'viable' if (pf.trades.profit_factor() or 0) >= 1.2 else 'marginal' if (pf.trades.profit_factor() or 0) >= 1.0 else 'not_viable'
            }
        except Exception as e:
            return None
    
    def validate_best(self, best_ind_name, best_params, df):
        """Phase 3: Walk-forward validation - test on out-of-sample data"""
        print("\nPhase 3: Walk-Forward Validation")
        print("-" * 80)
        print("Validating: {}".format(best_ind_name))
        
        # Split data: 80% in-sample, 20% out-of-sample
        split_idx = int(len(df) * 0.8)
        df_train = df.iloc[:split_idx]
        df_test = df.iloc[split_idx:]
        
        price_train = df_train['close'].values
        price_test = df_test['close'].values
        
        try:
            if best_ind_name == 'RSI':
                period = best_params.get('period', 14)
                thresh_low = best_params.get('thresh_low', 30)
                thresh_high = best_params.get('thresh_high', 70)
                
                # In-sample backtest
                ind_train = vbt.indicators.RSI.run(price_train, window=period)
                entries_train = ind_train < thresh_low
                exits_train = ind_train > thresh_high
                pf_train = vbt.Portfolio.from_signals(price_train, entries_train, exits_train, init_cash=self.init_cash)
                
                # Out-of-sample backtest (no reoptimization)
                ind_test = vbt.indicators.RSI.run(price_test, window=period)
                entries_test = ind_test < thresh_low
                exits_test = ind_test > thresh_high
                pf_test = vbt.Portfolio.from_signals(price_test, entries_test, exits_test, init_cash=self.init_cash)
                
            elif best_ind_name == 'BBANDS':
                period = best_params.get('period', 20)
                alpha = best_params.get('alpha', 2.0)
                
                # In-sample backtest
                ind_train = vbt.indicators.BBANDS.run(price_train, window=period, alpha=alpha)
                entries_train = price_train < ind_train.lower
                exits_train = price_train > ind_train.upper
                pf_train = vbt.Portfolio.from_signals(price_train, entries_train, exits_train, init_cash=self.init_cash)
                
                # Out-of-sample backtest
                ind_test = vbt.indicators.BBANDS.run(price_test, window=period, alpha=alpha)
                entries_test = price_test < ind_test.lower
                exits_test = price_test > ind_test.upper
                pf_test = vbt.Portfolio.from_signals(price_test, entries_test, exits_test, init_cash=self.init_cash)
            else:
                return {'status': 'not_tested', 'reason': 'Indicator not supported for validation'}
            
            # Calculate metrics
            pf_train_val = float(pf_train.trades.profit_factor() or 0)
            pf_test_val = float(pf_test.trades.profit_factor() or 0)
            wr_train = float(pf_train.trades.win_rate() or 0)
            wr_test = float(pf_test.trades.win_rate() or 0)
            
            # Calculate degradation
            if pf_train_val > 0:
                degradation_pct = ((pf_train_val - pf_test_val) / pf_train_val) * 100
            else:
                degradation_pct = 0
            
            # Validation thresholds
            min_pf = 1.3
            min_pf_test = 1.0
            max_degradation = 30
            min_wr = 0.45
            
            # Determine PASS/FAIL
            passed = (pf_train_val >= min_pf and 
                     pf_test_val >= min_pf_test and 
                     degradation_pct <= max_degradation and
                     wr_test >= min_wr)
            
            status = 'PASS' if passed else 'FAIL'
            
            print("In-Sample Metrics:")
            print("  Profit Factor: {:.2f}".format(pf_train_val))
            print("  Win Rate: {:.1f}%".format(wr_train * 100))
            print("  Trades: {}".format(int(pf_train.trades.count() or 0)))
            
            print("\nOut-of-Sample Metrics:")
            print("  Profit Factor: {:.2f}".format(pf_test_val))
            print("  Win Rate: {:.1f}%".format(wr_test * 100))
            print("  Trades: {}".format(int(pf_test.trades.count() or 0)))
            
            print("\nValidation Results:")
            print("  Degradation: {:.1f}%".format(degradation_pct))
            print("  Status: {}".format(status))
            
            val_result = {
                'indicator': best_ind_name,
                'status': status,
                'pf_in_sample': pf_train_val,
                'pf_out_sample': pf_test_val,
                'degradation_pct': degradation_pct,
                'wr_in_sample': wr_train,
                'wr_out_sample': wr_test,
                'trades_in_sample': int(pf_train.trades.count() or 0),
                'trades_out_sample': int(pf_test.trades.count() or 0),
            }
            
            return val_result
            
        except Exception as e:
            logger.error("Validation failed: {}".format(str(e)))
            return {'status': 'ERROR', 'reason': str(e)[:100]}
    
    def optimize_best(self, best_ind_name, df):
        """Optimize best indicator with Optuna"""
        print("\nPhase 2: Optuna Optimization")
        print("-" * 80)
        print("Optimizing: {}".format(best_ind_name))
        
        price = df['close'].values
        split_idx = int(len(price) * 0.7)
        price_train = price[:split_idx]
        
        def objective(trial):
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
                else:
                    return 0
                
                if entries.sum() < 2:
                    return 0
                
                pf = vbt.Portfolio.from_signals(price_train, entries, exits, init_cash=self.init_cash)
                return float(pf.trades.profit_factor() or 0)
            except:
                return 0
        
        # Create studies directory
        studies_dir = Path('data/studies/{}/{}'.format(self.symbol, self.timeframe))
        studies_dir.mkdir(parents=True, exist_ok=True)
        
        # Create persistent study storage
        db_path = studies_dir / '{}.db'.format(best_ind_name)
        storage = optuna.storages.RDBStorage('sqlite:///{}'.format(db_path))
        
        # Create or load existing study
        sampler = optuna.samplers.TPESampler(seed=42)
        study = optuna.create_study(
            direction='maximize',
            sampler=sampler,
            storage=storage,
            study_name=best_ind_name,
            load_if_exists=True
        )
        study.optimize(objective, n_trials=20, show_progress_bar=False)
        
        best = study.best_trial
        
        print("Best Score: {:.4f}".format(best.value))
        print("Best Parameters:")
        for k, v in best.params.items():
            print("  {}: {}".format(k, v))
        
        print("Study persisted to: {}".format(db_path))
        
        opt_result = {
            'indicator': best_ind_name,
            'best_score': float(best.value),
            'best_params': best.params,
            'n_trials': 20,
            'db_path': str(db_path)
        }
        
        self.optimization_results.append(opt_result)
        return opt_result
    
    def run(self):
        """Run complete pipeline"""
        print("\n" + "=" * 80)
        print("COMPREHENSIVE VECTORBT PIPELINE - {} {}".format(self.symbol, self.timeframe))
        print("=" * 80)
        
        df = self.load_data(bars=1000)
        if df is None or len(df) == 0:
            return False
        
        # Phase 1: Discovery
        discovery = self.discover_all_indicators(df)
        if not discovery:
            return False
        
        best_ind = discovery[0]['indicator']
        print("\nSelected for optimization: {}".format(best_ind))
        
        # Phase 2: Optimization
        opt_result = self.optimize_best(best_ind, df)
        
        # Phase 3: Walk-Forward Validation
        if opt_result and 'best_params' in opt_result:
            val_result = self.validate_best(best_ind, opt_result['best_params'], df)
            self.optimization_results.append({'validation': val_result})
        
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
            'total_indicators_tested': len(self.discovery_results),
            'discovery': self.discovery_results,
            'optimization': self.optimization_results
        }
        
        out_file = output_dir / '{}_{}_comprehensive.json'.format(self.symbol, self.timeframe)
        with open(out_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print("\nResults: {}".format(out_file))


if __name__ == '__main__':
    pipeline = ComprehensiveVectorBTPipeline(symbol="BTCUSD", timeframe="H1")
    pipeline.run()
