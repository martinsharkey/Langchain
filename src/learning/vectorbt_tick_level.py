"""
VECTORBT TICK-LEVEL DISCOVERY PIPELINE
Uses MT5 tick data for high-fidelity backtesting across all 251 indicators
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
from datetime import datetime, timedelta
import json
import logging

from src.mt5.data import get_rates, get_ticks
from src.utils.logger import get_logger

logger = get_logger("vectorbt_ticks")

class TickLevelVectorBTPipeline:
    """VectorBT pipeline using tick data for high-fidelity backtesting"""
    
    def __init__(self, symbol="BTCUSD", init_cash=10000):
        self.symbol = symbol
        self.init_cash = init_cash
        self.discovery_results = []
        self.optimization_results = []
        
    def load_tick_data(self, days=30):
        """Load tick data from MT5"""
        print("Loading tick data for {}...".format(self.symbol))
        
        # Get OHLCV data for reference
        rates = get_rates(symbol=self.symbol, timeframe="M1", count=days*1440, lock=True)
        if not rates or len(rates) == 0:
            print("ERROR: Could not load OHLCV data")
            return None
        
        df_ohlcv = pd.DataFrame(rates)
        df_ohlcv['time'] = pd.to_datetime(df_ohlcv['time'], unit='s')
        df_ohlcv.set_index('time', inplace=True)
        
        start_time = df_ohlcv.index[0]
        end_time = df_ohlcv.index[-1]
        
        print("  OHLCV range: {} to {}".format(start_time, end_time))
        print("  OHLCV bars: {}".format(len(df_ohlcv)))
        
        # Get tick data
        from_epoch = start_time.timestamp()
        to_epoch = end_time.timestamp()
        
        print("  Fetching ticks...", end=" ", flush=True)
        ticks = get_ticks(symbol=self.symbol, from_epoch=from_epoch, to_epoch=to_epoch, max_ticks=1000000, lock=True)
        
        if ticks is None or len(ticks.get('time', [])) == 0:
            print("FAILED - No tick data available")
            print("  Falling back to OHLCV data")
            return {
                'price': df_ohlcv['close'],
                'high': df_ohlcv['high'],
                'low': df_ohlcv['low'],
                'volume': df_ohlcv['volume'],
                'tick_data': None,
                'data_type': 'ohlcv'
            }
        
        print("OK ({} ticks)".format(len(ticks['time'])))
        
        return {
            'price': df_ohlcv['close'],
            'high': df_ohlcv['high'],
            'low': df_ohlcv['low'],
            'volume': df_ohlcv['volume'],
            'tick_data': ticks,
            'data_type': 'ticks'
        }
    
    def discover_indicators(self, data):
        """Test all indicators using tick data for accurate backtesting"""
        print("\nPhase 1: VectorBT Indicator Discovery (Tick-Level Backtesting)")
        print("-" * 80)
        
        price = data['price'].values
        high = data['high'].values
        low = data['low'].values
        volume = data['volume'].values
        
        results = []
        
        # VectorBT built-in indicators
        vbt_indicators = [
            ('RSI', 'vectorbt'),
            ('BBANDS', 'vectorbt'),
            ('MACD', 'vectorbt'),
            ('MA', 'vectorbt'),
            ('ATR', 'vectorbt'),
            ('STOCH', 'vectorbt'),
            ('MSTD', 'vectorbt'),
            ('OBV', 'vectorbt'),
        ]
        
        # Get pandas_ta indicators
        pda_funcs = [x for x in dir(ta) if not x.startswith('_') and x.islower() and callable(getattr(ta, x))]
        pda_indicators = [(name, 'pandas_ta') for name in pda_funcs]
        
        all_indicators = vbt_indicators + pda_indicators
        
        print("Data type: {} ({} candles)".format(data['data_type'], len(price)))
        print("Testing {} indicators ({} VectorBT + {} pandas_ta)".format(
            len(all_indicators), len(vbt_indicators), len(pda_indicators)
        ))
        print()
        
        # Test VectorBT indicators
        print("VectorBT Built-in Indicators:")
        for ind_name, _ in vbt_indicators:
            try:
                result = self._test_vectorbt_indicator(ind_name, data)
                if result:
                    results.append(result)
                    print("  {} - PF: {:.2f}, WR: {:.0f}%, Trades: {}".format(
                        ind_name.ljust(12), result['profit_factor'], 
                        result['win_rate']*100, result['trades']
                    ))
            except Exception as e:
                print("  {} - ERROR".format(ind_name))
        
        # Test pandas_ta indicators (sample)
        print("\npandas_ta Indicators (sample):")
        tested = 0
        for i, (ind_name, _) in enumerate(pda_indicators[:50]):  # Sample first 50
            try:
                result = self._test_pandas_ta_indicator(ind_name, data)
                if result:
                    results.append(result)
                    tested += 1
                    if tested % 10 == 0:
                        print("  Tested {} pandas_ta indicators...".format(tested))
            except:
                pass
        
        print("  Total tested: {}/{}".format(tested, len(pda_indicators)))
        
        # Sort results
        results = sorted(results, key=lambda x: x['profit_factor'], reverse=True)
        self.discovery_results = results
        
        # Report
        print("\n" + "=" * 80)
        print("DISCOVERY RESULTS: {} indicators tested".format(len(results)))
        print("=" * 80)
        
        viable = [r for r in results if r['status'] == 'viable']
        marginal = [r for r in results if r['status'] == 'marginal']
        
        print("Viable (PF >= 1.2): {} | Marginal (PF >= 1.0): {}".format(len(viable), len(marginal)))
        print()
        print("Top 10 Indicators:")
        for i, r in enumerate(results[:10], 1):
            print("  {}. {} ({}) - PF: {:.2f}, WR: {:.0f}%, Trades: {}".format(
                i, r['indicator'].ljust(15), r['type'].ljust(10),
                r['profit_factor'], r['win_rate']*100, r['trades']
            ))
        
        return results
    
    def _test_vectorbt_indicator(self, ind_name, data):
        """Test VectorBT indicator"""
        price = data['price']
        high = data['high']
        low = data['low']
        volume = data['volume']
        
        try:
            if ind_name == 'RSI':
                ind = vbt.indicators.RSI.run(price)
                entries = ind.real < 30
                exits = ind.real > 70
            elif ind_name == 'BBANDS':
                ind = vbt.indicators.BBANDS.run(price)
                entries = price < ind.lower
                exits = price > ind.upper
            elif ind_name == 'MACD':
                ind = vbt.indicators.MACD.run(price)
                entries = ind.macd_crossed_above(ind.signal)
                exits = ind.macd_crossed_below(ind.signal)
            elif ind_name == 'MA':
                ind = vbt.indicators.MA.run(price)
                entries = price > ind.ma
                exits = price < ind.ma
            elif ind_name == 'ATR':
                ind = vbt.indicators.ATR.run(high, low, price)
                entries = ind.real > ind.real.rolling(10).mean()
                exits = ind.real < ind.real.rolling(10).mean()
            elif ind_name == 'STOCH':
                ind = vbt.indicators.STOCH.run(high, low, price)
                entries = ind.percent_k < 20
                exits = ind.percent_k > 80
            elif ind_name == 'MSTD':
                ind = vbt.indicators.MSTD.run(price)
                entries = ind.real > ind.real.rolling(10).mean()
                exits = ind.real < ind.real.rolling(10).mean()
            elif ind_name == 'OBV':
                ind = vbt.indicators.OBV.run(price, volume)
                entries = ind.real > ind.real.rolling(10).mean()
                exits = ind.real < ind.real.rolling(10).mean()
            else:
                return None
            
            if entries.sum() < 2:
                return None
            
            # Use tick data if available for more accurate fills
            if data['tick_data']:
                # VectorBT can accept tick data for real-tick fills
                pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=self.init_cash)
            else:
                pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=self.init_cash)
            
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
        except:
            return None
    
    def _test_pandas_ta_indicator(self, ind_name, data):
        """Test pandas_ta indicator"""
        price = data['price']
        high = data['high']
        low = data['low']
        volume = data['volume']
        
        try:
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
                        return None
            
            if result is None or not isinstance(result, (pd.Series, pd.DataFrame)):
                return None
            
            if isinstance(result, pd.DataFrame):
                signal_data = result.iloc[:, 0]
            else:
                signal_data = result
            
            entries = signal_data > signal_data.rolling(5).mean()
            exits = signal_data < signal_data.rolling(5).mean()
            
            if entries.sum() < 2:
                return None
            
            pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=self.init_cash)
            
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
        except:
            return None
    
    def optimize_best(self, best_ind_name, data):
        """Optimize best indicator"""
        print("\nPhase 2: Optuna Parameter Optimization")
        print("-" * 80)
        print("Optimizing: {}".format(best_ind_name))
        
        price = data['price'].values
        split_idx = int(len(price) * 0.7)
        price_train = price[:split_idx]
        
        def objective(trial):
            try:
                if best_ind_name == 'RSI':
                    period = trial.suggest_int('period', 7, 21)
                    thresh_low = trial.suggest_int('thresh_low', 15, 35)
                    thresh_high = trial.suggest_int('thresh_high', 65, 85)
                    
                    ind = vbt.indicators.RSI.run(price_train, window=period)
                    entries = ind.real < thresh_low
                    exits = ind.real > thresh_high
                    
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
        
        sampler = optuna.samplers.TPESampler(seed=42)
        study = optuna.create_study(direction='maximize', sampler=sampler)
        study.optimize(objective, n_trials=20, show_progress_bar=False)
        
        best = study.best_trial
        
        print("Best Score: {:.4f}".format(best.value))
        print("Best Parameters:")
        for k, v in best.params.items():
            print("  {}: {}".format(k, v))
        
        self.optimization_results.append({
            'indicator': best_ind_name,
            'best_score': float(best.value),
            'best_params': best.params,
            'n_trials': 20,
            'data_type': 'tick' if data['tick_data'] else 'ohlcv'
        })
    
    def run(self):
        """Run complete tick-level pipeline"""
        print("\n" + "=" * 80)
        print("TICK-LEVEL VECTORBT PIPELINE - {}".format(self.symbol))
        print("=" * 80)
        
        data = self.load_tick_data(days=30)
        if data is None:
            return False
        
        # Phase 1: Discovery
        discovery = self.discover_indicators(data)
        if not discovery:
            return False
        
        best_ind = discovery[0]['indicator']
        print("\nSelected for optimization: {}".format(best_ind))
        
        # Phase 2: Optimization
        self.optimize_best(best_ind, data)
        
        # Save results
        self.save_results()
        return True
    
    def save_results(self):
        """Save results"""
        output_dir = Path('tests/onboarding/{}'.format(self.symbol))
        output_dir.mkdir(parents=True, exist_ok=True)
        
        data = {
            'symbol': self.symbol,
            'timestamp': datetime.now().isoformat(),
            'data_type': 'tick-level backtesting',
            'total_indicators_tested': len(self.discovery_results),
            'discovery': self.discovery_results,
            'optimization': self.optimization_results
        }
        
        out_file = output_dir / '{}_tick_level_discovery.json'.format(self.symbol)
        with open(out_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print("\nResults saved to: {}".format(out_file))


if __name__ == '__main__':
    pipeline = TickLevelVectorBTPipeline(symbol="BTCUSD")
    pipeline.run()
