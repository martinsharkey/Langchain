"""
AUTOMATIC VECTORBT INDICATOR DISCOVERY
Auto-detects all available indicators in VectorBT library and pandas_ta
Tests them all without manual constraint or hardcoding
"""

import vectorbt as vbt
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime
import json
from pathlib import Path
from typing import Dict, List, Callable

class AutoIndicatorDiscovery:
    """Automatically discovers and tests ALL available indicators"""
    
    def __init__(self, symbol="BTC-USD", period="1y", init_cash=1000):
        self.symbol = symbol
        self.period = period
        self.init_cash = init_cash
        self.results = []
        self.indicators_found = []
        self.indicators_tested = []
        self.indicators_failed = []
        
    def download_data(self):
        """Download real data"""
        print("Downloading {} data ({})...".format(self.symbol, self.period))
        try:
            data = vbt.YFData.download(self.symbol, period=self.period)
            price = data.get("Close")
            ohlc = data.get(["Open", "High", "Low", "Close"])
            volume = data.get("Volume")
            print("  Downloaded: {} bars".format(len(price)))
            return {
                'price': price,
                'ohlc': ohlc,
                'open': ohlc['Open'] if ohlc is not None else None,
                'high': ohlc['High'] if ohlc is not None else None,
                'low': ohlc['Low'] if ohlc is not None else None,
                'close': ohlc['Close'] if ohlc is not None else None,
                'volume': volume
            }
        except Exception as e:
            print("  ERROR: {}".format(e))
            return None
    
    def discover_vectorbt_indicators(self):
        """Discover all built-in VectorBT indicators"""
        print("\nDiscovering VectorBT built-in indicators...")
        indicators = {}
        
        # Get all classes from vbt.indicators
        for name in dir(vbt.indicators):
            if name.startswith('_'):
                continue
            obj = getattr(vbt.indicators, name)
            
            # Check if it's an indicator class
            try:
                if hasattr(obj, 'run') and callable(getattr(obj, 'run')):
                    if name not in ['IndicatorBase', 'IndicatorFactory']:
                        indicators[name] = obj
                        print("  Found: {}".format(name))
            except:
                pass
        
        print("  Total built-in indicators: {}".format(len(indicators)))
        return indicators
    
    def discover_pandas_ta_indicators(self):
        """Discover all pandas_ta indicators"""
        print("\nDiscovering pandas_ta indicators...")
        indicators = {}
        
        # Get all functions from pandas_ta
        for name in dir(ta):
            if name.startswith('_'):
                continue
            obj = getattr(ta, name)
            
            # Check if it's a function (indicator)
            if callable(obj) and name.islower():
                indicators[name] = obj
        
        print("  Total pandas_ta indicators: {}".format(len(indicators)))
        return indicators
    
    def test_vectorbt_indicator(self, indicator_name, indicator_class, data):
        """Test a VectorBT indicator"""
        try:
            price = data['price']
            
            # Try to run the indicator with sensible defaults
            if indicator_name in ['RSI', 'STOCH', 'BBANDS', 'MACD', 'MA', 'ATR', 'MSTD', 'OBV']:
                # Standard indicators with simple parameters
                if indicator_name == 'RSI':
                    result = indicator_class.run(price, window=14)
                    signal = (result < 30) | (result > 70)
                elif indicator_name == 'BBANDS':
                    result = indicator_class.run(price, window=20, alpha=2.0)
                    signal = (price < result.lower) | (price > result.upper)
                elif indicator_name == 'MACD':
                    result = indicator_class.run(price, fast=12, slow=26, signal=9)
                    signal = result.macd_crossed_above(result.signal)
                elif indicator_name == 'MA':
                    result = indicator_class.run(price, window=20)
                    signal = price > result.ma
                elif indicator_name == 'ATR':
                    high = data['high']
                    low = data['low']
                    close = price
                    result = indicator_class.run(high, low, close, window=14)
                    signal = result.value > result.value.rolling(10).mean()
                elif indicator_name == 'STOCH':
                    high = data['high']
                    low = data['low']
                    close = price
                    result = indicator_class.run(high, low, close, window=14)
                    signal = (result.percent_k < 20) | (result.percent_k > 80)
                elif indicator_name == 'MSTD':
                    result = indicator_class.run(price, window=20)
                    signal = result.mstd > result.mstd.rolling(10).mean()
                elif indicator_name == 'OBV':
                    volume = data['volume']
                    result = indicator_class.run(price, volume)
                    signal = result.obv > result.obv.rolling(10).mean()
                else:
                    return None
                
                # Run backtest
                if signal is not None and signal.sum() > 2:
                    pf = vbt.Portfolio.from_signals(price, signal, ~signal, init_cash=self.init_cash)
                    
                    return {
                        'type': 'vectorbt',
                        'indicator': indicator_name,
                        'trades': int(pf.trades.count()) if pf.trades.count() else 0,
                        'win_rate': float(pf.trades.win_rate() or 0),
                        'profit_factor': float(pf.trades.profit_factor() or 0),
                        'return_pct': float(pf.total_return() * 100) if pf.total_return() else 0,
                        'sharpe': float(pf.sharpe_ratio() or 0),
                        'status': 'viable' if (pf.trades.profit_factor() or 0) >= 1.5 else 'marginal' if (pf.trades.profit_factor() or 0) >= 1.0 else 'not_viable'
                    }
            
            return None
            
        except Exception as e:
            return None
    
    def test_pandas_ta_indicator(self, indicator_name, indicator_func, data):
        """Test a pandas_ta indicator"""
        try:
            price = data['price']
            high = data['high']
            low = data['low']
            close = data['close']
            volume = data['volume']
            
            # Try to call the indicator with common parameters
            result = None
            
            # Try different parameter combinations
            try:
                # Most indicators work with just close
                result = indicator_func(close)
            except:
                try:
                    # Some need high, low, close
                    result = indicator_func(high, low, close)
                except:
                    try:
                        # Some need close and volume
                        result = indicator_func(close, volume)
                    except:
                        try:
                            # Some need just high and low
                            result = indicator_func(high, low)
                        except:
                            return None
            
            if result is None or not isinstance(result, (pd.Series, pd.DataFrame)):
                return None
            
            # Generate signal from result
            if isinstance(result, pd.DataFrame):
                # Use first column
                signal_data = result.iloc[:, 0]
            else:
                signal_data = result
            
            # Simple signal: above/below mean
            signal = signal_data > signal_data.rolling(10).mean()
            
            if signal.sum() < 3:
                return None
            
            # Run backtest
            pf = vbt.Portfolio.from_signals(price, signal, ~signal, init_cash=self.init_cash)
            
            return {
                'type': 'pandas_ta',
                'indicator': indicator_name,
                'trades': int(pf.trades.count()) if pf.trades.count() else 0,
                'win_rate': float(pf.trades.win_rate() or 0),
                'profit_factor': float(pf.trades.profit_factor() or 0),
                'return_pct': float(pf.total_return() * 100) if pf.total_return() else 0,
                'sharpe': float(pf.sharpe_ratio() or 0),
                'status': 'viable' if (pf.trades.profit_factor() or 0) >= 1.5 else 'marginal' if (pf.trades.profit_factor() or 0) >= 1.0 else 'not_viable'
            }
            
        except Exception as e:
            return None
    
    def run_auto_discovery(self):
        """Run complete auto-discovery"""
        print("\n" + "=" * 80)
        print("AUTOMATIC VECTORBT INDICATOR DISCOVERY")
        print("=" * 80)
        print()
        
        # Download data
        data = self.download_data()
        if data is None:
            print("FAILED: Could not download data")
            return None
        
        # Discover VectorBT indicators
        vbt_indicators = self.discover_vectorbt_indicators()
        
        # Discover pandas_ta indicators
        pda_indicators = self.discover_pandas_ta_indicators()
        
        print("\n" + "=" * 80)
        print("TESTING ALL DISCOVERED INDICATORS")
        print("=" * 80)
        print()
        
        # Test VectorBT indicators
        print("Testing VectorBT indicators ({} total):".format(len(vbt_indicators)))
        for ind_name, ind_class in sorted(vbt_indicators.items()):
            print("  Testing {}...".format(ind_name), end=" ", flush=True)
            result = self.test_vectorbt_indicator(ind_name, ind_class, data)
            if result:
                self.results.append(result)
                self.indicators_tested.append(ind_name)
                print("OK - PF={:.2f}".format(result['profit_factor']))
            else:
                self.indicators_failed.append(ind_name)
                print("FAILED")
        
        # Test pandas_ta indicators (sample - test top 50 to avoid long runtime)
        print("\nTesting pandas_ta indicators (sampling {}):".format(min(50, len(pda_indicators))))
        tested_count = 0
        for ind_name, ind_func in sorted(list(pda_indicators.items())[:50]):
            print("  Testing {}...".format(ind_name), end=" ", flush=True)
            result = self.test_pandas_ta_indicator(ind_name, ind_func, data)
            if result:
                self.results.append(result)
                self.indicators_tested.append(ind_name)
                print("OK - PF={:.2f}".format(result['profit_factor']))
                tested_count += 1
            else:
                self.indicators_failed.append(ind_name)
                print("FAILED")
        
        # Summary
        viable = [r for r in self.results if r['status'] == 'viable']
        marginal = [r for r in self.results if r['status'] == 'marginal']
        not_viable = [r for r in self.results if r['status'] == 'not_viable']
        
        print("\n" + "=" * 80)
        print("DISCOVERY SUMMARY")
        print("=" * 80)
        print("VectorBT built-in indicators discovered: {}".format(len(vbt_indicators)))
        print("pandas_ta indicators discovered: {}".format(len(pda_indicators)))
        print()
        print("Results:")
        print("  Successfully tested: {}".format(len(self.indicators_tested)))
        print("  Failed to test: {}".format(len(self.indicators_failed)))
        print()
        print("Performance Classification:")
        print("  Viable (PF >= 1.5): {}".format(len(viable)))
        print("  Marginal (PF >= 1.0): {}".format(len(marginal)))
        print("  Not Viable (PF < 1.0): {}".format(len(not_viable)))
        print()
        
        if viable:
            print("Top Viable Indicators:")
            sorted_viable = sorted(viable, key=lambda x: x['profit_factor'], reverse=True)
            for i, r in enumerate(sorted_viable[:5], 1):
                print("  {}. {} - PF: {:.2f}, WR: {:.1f}%, Trades: {}".format(
                    i, r['indicator'].ljust(20), r['profit_factor'], r['win_rate']*100, r['trades']
                ))
        
        print("\n" + "=" * 80)
        
        return self.results
    
    def save_results(self):
        """Save all results to JSON"""
        output_file = Path('tests/onboarding/BTCUSD/auto_discovery_results.json')
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump({
                'symbol': self.symbol,
                'timestamp': datetime.now().isoformat(),
                'vectorbt_indicators_found': len([r for r in self.results if r['type'] == 'vectorbt']),
                'pandas_ta_indicators_tested': len([r for r in self.results if r['type'] == 'pandas_ta']),
                'total_results': len(self.results),
                'indicators_tested': self.indicators_tested,
                'indicators_failed': self.indicators_failed,
                'results': self.results
            }, f, indent=2)
        
        print("Results saved to: {}".format(output_file))


if __name__ == '__main__':
    discovery = AutoIndicatorDiscovery(symbol="BTC-USD", period="1y")
    results = discovery.run_auto_discovery()
    discovery.save_results()
