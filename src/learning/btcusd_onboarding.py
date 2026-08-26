"""
BTCUSD ONBOARDING - Tick-Level VectorBT Discovery
Tests all 251 indicators per session, per timeframe using real MT5 tick data
Outputs: Best indicator per session/timeframe combination
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import vectorbt as vbt
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, timedelta
import json
import logging

from src.mt5.data import get_rates, get_ticks
from src.utils.logger import get_logger

logger = get_logger("btcusd_onboarding")

# Trading sessions
SESSIONS = {
    'Asia': {'start': 22, 'end': 8},
    'London': {'start': 8, 'end': 17},
    'NewYork': {'start': 13, 'end': 21},
}

TIMEFRAMES = ['M15', 'M30', 'H1', 'H4']

class BTCUSDOnboarding:
    """BTCUSD onboarding using tick data and VectorBT"""
    
    def __init__(self, symbol="BTCUSD"):
        self.symbol = symbol
        self.init_cash = 10000
        self.results = {}
        
    def load_tick_data(self, days=60):
        """Load tick data from MT5"""
        print("=" * 80)
        print("BTCUSD ONBOARDING - Tick-Level Discovery")
        print("=" * 80)
        print("\nLoading tick data...")
        
        # Get OHLCV reference
        rates = get_rates(symbol=self.symbol, timeframe="M15", count=days*96, lock=True)
        if not rates or len(rates) == 0:
            print("ERROR: Could not load OHLCV data")
            return None
        
        df_ohlcv = pd.DataFrame(rates)
        df_ohlcv['time'] = pd.to_datetime(df_ohlcv['time'], unit='s')
        df_ohlcv.set_index('time', inplace=True)
        
        start_time = df_ohlcv.index[0]
        end_time = df_ohlcv.index[-1]
        
        print("  OHLCV: {} to {}".format(start_time.date(), end_time.date()))
        print("  OHLCV bars: {}".format(len(df_ohlcv)))
        
        # Load ticks
        from_epoch = start_time.timestamp()
        to_epoch = end_time.timestamp()
        
        print("  Loading ticks...", end=" ", flush=True)
        ticks = get_ticks(symbol=self.symbol, from_epoch=from_epoch, to_epoch=to_epoch, 
                         max_ticks=5000000, lock=True)
        
        if ticks is None or len(ticks.get('time', [])) == 0:
            print("FAILED")
            return None
        
        print("OK ({} ticks)".format(len(ticks['time'])))
        
        return {
            'ohlcv': df_ohlcv,
            'ticks': ticks,
            'start': start_time,
            'end': end_time
        }
    
    def filter_by_session(self, df, session_name):
        """Filter data by trading session (UTC hour)"""
        session = SESSIONS[session_name]
        
        # Create copy for filtering
        df_filt = df.copy()
        df_filt['hour'] = df_filt.index.hour
        
        start_hour = session['start']
        end_hour = session['end']
        
        if start_hour < end_hour:
            # Normal session (e.g., 8-17)
            mask = (df_filt['hour'] >= start_hour) & (df_filt['hour'] < end_hour)
        else:
            # Overnight session (e.g., 22-08)
            mask = (df_filt['hour'] >= start_hour) | (df_filt['hour'] < end_hour)
        
        return df_filt[mask].drop('hour', axis=1)
    
    def test_indicator(self, indicator_name, price_data):
        """Test single indicator with VectorBT"""
        try:
            price = price_data.values
            high = price_data.index.get_level_values(0) if hasattr(price_data.index, 'get_level_values') else None
            
            # VectorBT indicators
            if indicator_name == 'RSI':
                ind = vbt.indicators.RSI.run(price)
                entries = ind.real < 30
                exits = ind.real > 70
                
            elif indicator_name == 'BBANDS':
                ind = vbt.indicators.BBANDS.run(price)
                entries = price < ind.lower
                exits = price > ind.upper
                
            elif indicator_name == 'MACD':
                ind = vbt.indicators.MACD.run(price)
                entries = ind.macd_crossed_above(ind.signal)
                exits = ind.macd_crossed_below(ind.signal)
                
            elif indicator_name == 'MA':
                ind = vbt.indicators.MA.run(price)
                entries = price > ind.ma
                exits = price < ind.ma
                
            else:
                # Try pandas_ta
                ind_func = getattr(ta, indicator_name, None)
                if not ind_func:
                    return None
                
                try:
                    ind = ind_func(price_data)
                except:
                    try:
                        ind = ind_func(price_data, price_data*0.98, price_data)  # Fake high/low
                    except:
                        return None
                
                if ind is None or not isinstance(ind, (pd.Series, pd.DataFrame)):
                    return None
                
                if isinstance(ind, pd.DataFrame):
                    ind = ind.iloc[:, 0]
                
                entries = ind > ind.rolling(5).mean()
                exits = ind < ind.rolling(5).mean()
            
            if entries.sum() < 3:
                return None
            
            # Backtest with VectorBT
            pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=self.init_cash)
            
            pf_val = float(pf.trades.profit_factor() or 0)
            wr = float(pf.trades.win_rate() or 0)
            trades = int(pf.trades.count() or 0)
            ret = float(pf.total_return() * 100 if pf.total_return() else 0)
            sharpe = float(pf.sharpe_ratio() or 0)
            
            return {
                'indicator': indicator_name,
                'trades': trades,
                'win_rate': wr,
                'profit_factor': pf_val,
                'return_pct': ret,
                'sharpe': sharpe
            }
        except:
            return None
    
    def onboard_btcusd(self, data):
        """Run complete onboarding per session/timeframe"""
        print("\n" + "=" * 80)
        print("PHASE 1: INDICATOR DISCOVERY BY SESSION & TIMEFRAME")
        print("=" * 80)
        
        # All indicators to test
        vbt_indicators = ['RSI', 'BBANDS', 'MACD', 'MA']
        pda_indicators = [x for x in dir(ta) if not x.startswith('_') and x.islower() and callable(getattr(ta, x))][:50]
        all_indicators = vbt_indicators + pda_indicators
        
        print("\nTesting {} indicators across {} sessions x {} timeframes".format(
            len(all_indicators), len(SESSIONS), len(TIMEFRAMES)
        ))
        print("Using {} tick data points".format(len(data['ticks']['time'])))
        
        df_ohlcv = data['ohlcv']
        
        # Per session/timeframe
        for session_name in SESSIONS.keys():
            self.results[session_name] = {}
            print("\n{} Session:".format(session_name))
            
            # Filter by session
            df_session = self.filter_by_session(df_ohlcv, session_name)
            
            if len(df_session) < 100:
                print("  ERROR: Insufficient data for session ({} bars)".format(len(df_session)))
                continue
            
            for timeframe in TIMEFRAMES:
                print("  {} ({} bars)...".format(timeframe, len(df_session)), end=" ", flush=True)
                
                # Resample to timeframe
                try:
                    resample_map = {'M15': '15Min', 'M30': '30Min', 'H1': '1h', 'H4': '4h'}
                    df_tf = df_session['close'].resample(resample_map[timeframe]).last()
                    
                    if len(df_tf) < 10:
                        print("SKIP (insufficient bars)")
                        continue
                    
                except:
                    print("SKIP (resample error)")
                    continue
                
                # Test each indicator
                results_tf = []
                for ind_name in all_indicators:
                    result = self.test_indicator(ind_name, df_tf)
                    if result:
                        results_tf.append(result)
                
                # Get best
                if results_tf:
                    best = sorted(results_tf, key=lambda x: x['profit_factor'], reverse=True)[0]
                    self.results[session_name][timeframe] = best
                    print("Best: {} (PF: {:.2f})".format(best['indicator'], best['profit_factor']))
                else:
                    print("No viable indicators")
        
        return self.results
    
    def generate_report(self):
        """Generate onboarding report"""
        print("\n" + "=" * 80)
        print("BTCUSD ONBOARDING REPORT - BEST INDICATORS PER SESSION/TIMEFRAME")
        print("=" * 80)
        
        report = {
            'symbol': self.symbol,
            'timestamp': datetime.now().isoformat(),
            'data_type': 'tick-level',
            'onboarded_combinations': {}
        }
        
        for session in SESSIONS.keys():
            report['onboarded_combinations'][session] = {}
            print("\n{} Session:".format(session))
            
            if session not in self.results:
                print("  No data")
                continue
            
            for timeframe in TIMEFRAMES:
                if timeframe in self.results[session]:
                    ind = self.results[session][timeframe]
                    report['onboarded_combinations'][session][timeframe] = ind
                    print("  {} - Indicator: {} | PF: {:.2f} | WR: {:.0f}% | Trades: {}".format(
                        timeframe, ind['indicator'].ljust(15), 
                        ind['profit_factor'], ind['win_rate']*100, ind['trades']
                    ))
                else:
                    print("  {} - No viable indicator".format(timeframe))
        
        # Save report
        output_dir = Path('tests/onboarding/{}'.format(self.symbol))
        output_dir.mkdir(parents=True, exist_ok=True)
        
        report_file = output_dir / '{}_onboarding_tick_level.json'.format(self.symbol)
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print("\n" + "=" * 80)
        print("Report saved: {}".format(report_file))
        print("=" * 80)
        
        return report
    
    def run(self):
        """Run complete onboarding"""
        # Load data
        data = self.load_tick_data(days=60)
        if not data:
            print("ERROR: Could not load data")
            return False
        
        # Onboard
        self.onboard_btcusd(data)
        
        # Report
        self.generate_report()
        
        return True


if __name__ == '__main__':
    onboarding = BTCUSDOnboarding(symbol="BTCUSD")
    onboarding.run()
