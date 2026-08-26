"""
BTCUSD Per-Session Discovery Results
Session-filtered indicator discovery for London, Tokyo, New York

This test runs the discovery pipeline separately for each trading session
and generates per-session performance breakdowns.
"""

import sys
from pathlib import Path
import json
from datetime import datetime
import pandas as pd
import numpy as np

# Set working directory
import os
os.chdir(Path(__file__).parent.parent.parent)
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import vectorbt as vbt
import pandas_ta as ta
import talib

from src.mt5.data import get_rates
from src.utils.logger import get_logger

logger = get_logger("btcusd_session_discovery")

# Session definitions (UTC hours)
SESSIONS = {
    'Tokyo': {'start': 23, 'end': 8},      # 23:00-08:00 UTC (Fri 23:00 - Sat 08:00)
    'London': {'start': 8, 'end': 17},     # 08:00-17:00 UTC
    'New York': {'start': 13, 'end': 22},  # 13:00-22:00 UTC
}

class SessionAwareDiscovery:
    def __init__(self, symbol='BTCUSD', timeframe='H1'):
        self.symbol = symbol
        self.timeframe = timeframe
        self.init_cash = 10000
        self.results_by_session = {}
        
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
    
    def filter_by_session(self, df, session_name):
        """Filter data to only include bars from specified session"""
        session = SESSIONS[session_name]
        start_hour = session['start']
        end_hour = session['end']
        
        # Extract hour from datetime index
        hours = df.index.hour
        
        if start_hour < end_hour:
            # Normal case: e.g., 8-17 (London)
            mask = (hours >= start_hour) & (hours < end_hour)
        else:
            # Overnight case: e.g., 23-8 (Tokyo)
            mask = (hours >= start_hour) | (hours < end_hour)
        
        filtered_df = df[mask]
        return filtered_df
    
    def test_indicators_for_session(self, df, session_name):
        """Test all indicators for a specific session"""
        if len(df) < 50:
            return []
        
        price = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values
        
        results = []
        
        # Test VectorBT indicators
        vbt_indicators = ['RSI', 'BBANDS', 'MACD']
        for ind_name in vbt_indicators:
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
                    continue
                
                if entries.sum() < 2:
                    continue
                
                pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=self.init_cash)
                
                if pf.trades.count():
                    results.append({
                        'indicator': ind_name,
                        'type': 'vectorbt',
                        'trades': int(pf.trades.count() or 0),
                        'win_rate': float(pf.trades.win_rate() or 0),
                        'profit_factor': float(pf.trades.profit_factor() or 0),
                        'return_pct': float(pf.total_return() * 100 if pf.total_return() else 0),
                        'sharpe': float(pf.sharpe_ratio() or 0),
                    })
            except:
                pass
        
        # Test ta-lib indicators (sample key ones)
        talib_indicators = ['RSI', 'BBANDS', 'MACD', 'ADX', 'CCI', 'ROC', 'STOCH']
        for ind_name in talib_indicators:
            try:
                talib_func = getattr(talib, ind_name, None)
                if not talib_func:
                    continue
                
                result = None
                try:
                    result = talib_func(price)
                except:
                    try:
                        result = talib_func(high, low, price)
                    except:
                        try:
                            result = talib_func(price, volume)
                        except:
                            continue
                
                if result is None:
                    continue
                
                # Handle result (could be tuple or array)
                if isinstance(result, tuple):
                    signal_data = np.array(result[0]) if len(result) > 0 else None
                else:
                    signal_data = np.array(result)
                
                if signal_data is None:
                    continue
                
                signal_data = signal_data[~np.isnan(signal_data)]
                if len(signal_data) < 5:
                    continue
                
                signal_median = np.median(signal_data)
                entries = signal_data > signal_median
                exits = signal_data < signal_median
                
                if entries.sum() < 2:
                    continue
                
                # Align price
                if len(price) > len(entries):
                    price_aligned = price[:len(entries)]
                else:
                    price_aligned = price
                
                pf = vbt.Portfolio.from_signals(price_aligned, entries, exits, init_cash=self.init_cash)
                
                if pf.trades.count():
                    results.append({
                        'indicator': ind_name + '_talib',
                        'type': 'talib',
                        'trades': int(pf.trades.count() or 0),
                        'win_rate': float(pf.trades.win_rate() or 0),
                        'profit_factor': float(pf.trades.profit_factor() or 0),
                        'return_pct': float(pf.total_return() * 100 if pf.total_return() else 0),
                        'sharpe': float(pf.sharpe_ratio() or 0),
                    })
            except:
                pass
        
        # Test pandas_ta indicators (sample key ones)
        pandas_ta_indicators = ['rsi', 'bbands', 'macd', 'adx', 'cci', 'roc', 'stoch']
        for ind_name in pandas_ta_indicators:
            try:
                ind_func = getattr(ta, ind_name, None)
                if not ind_func:
                    continue
                
                result = None
                try:
                    result = ind_func(price)
                except:
                    try:
                        result = ind_func(high, low, price)
                    except:
                        try:
                            result = ind_func(price, volume)
                        except:
                            continue
                
                if result is None or not isinstance(result, (pd.Series, pd.DataFrame)):
                    continue
                
                if isinstance(result, pd.DataFrame):
                    signal_data = result.iloc[:, 0].values
                else:
                    signal_data = result.values
                
                signal_data = signal_data[~np.isnan(signal_data)]
                if len(signal_data) < 5:
                    continue
                
                signal_median = np.median(signal_data)
                entries = signal_data > signal_median
                exits = signal_data < signal_median
                
                if entries.sum() < 2:
                    continue
                
                if len(price) > len(entries):
                    price_aligned = price[:len(entries)]
                else:
                    price_aligned = price
                
                pf = vbt.Portfolio.from_signals(price_aligned, entries, exits, init_cash=self.init_cash)
                
                if pf.trades.count():
                    results.append({
                        'indicator': ind_name + '_pandas_ta',
                        'type': 'pandas_ta',
                        'trades': int(pf.trades.count() or 0),
                        'win_rate': float(pf.trades.win_rate() or 0),
                        'profit_factor': float(pf.trades.profit_factor() or 0),
                        'return_pct': float(pf.total_return() * 100 if pf.total_return() else 0),
                        'sharpe': float(pf.sharpe_ratio() or 0),
                    })
            except:
                pass
        
        return results
    
    def run_all_sessions(self):
        """Run discovery for all sessions"""
        df = self.load_data(bars=1000)
        if df is None:
            return False
        
        print("\n" + "=" * 80)
        print("BTCUSD SESSION-AWARE DISCOVERY")
        print("=" * 80)
        print("Data range: {} to {}".format(df.index[0], df.index[-1]))
        print("Total bars: {}".format(len(df)))
        print()
        
        for session_name in ['London', 'Tokyo', 'New York']:
            print("[{}] Running discovery...".format(session_name))
            filtered_df = self.filter_by_session(df, session_name)
            print("  Bars in session: {}".format(len(filtered_df)))
            
            results = self.test_indicators_for_session(filtered_df, session_name)
            
            # Sort by profit factor
            results = sorted(results, key=lambda x: x['profit_factor'], reverse=True)
            self.results_by_session[session_name] = results
            
            print("  Viable indicators: {}".format(len(results)))
            if results:
                print("  Top indicator: {} (PF: {:.2f})".format(
                    results[0]['indicator'], results[0]['profit_factor']
                ))
            print()
        
        return True
    
    def generate_report(self):
        """Generate comprehensive report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'sessions': {}
        }
        
        print("\n" + "=" * 80)
        print("BTCUSD DISCOVERY RESULTS - PER SESSION BREAKDOWN")
        print("=" * 80)
        print()
        
        for session_name, results in self.results_by_session.items():
            session_data = {
                'total_viable': len(results),
                'indicators': results[:10]  # Top 10
            }
            report['sessions'][session_name] = session_data
            
            print("[{}] - {} viable indicators".format(session_name, len(results)))
            if results:
                print("  Top 5 Indicators:")
                for i, r in enumerate(results[:5], 1):
                    print("    {}. {} ({}) - PF: {:.2f}, WR: {:.1f}%, Trades: {}".format(
                        i, r['indicator'].ljust(20), r['type'].ljust(10),
                        r['profit_factor'], r['win_rate']*100, r['trades']
                    ))
            else:
                print("  No viable indicators found")
            print()
        
        # Save report
        report_path = Path('tests/onboarding/BTCUSD/BTCUSD_session_breakdown.json')
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        print("Report saved to: {}".format(report_path))
        print()
        
        return report

if __name__ == '__main__':
    discovery = SessionAwareDiscovery('BTCUSD', 'H1')
    if discovery.run_all_sessions():
        discovery.generate_report()
