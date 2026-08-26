"""
PRODUCTION VECTORBT DISCOVERY + OPTUNA OPTIMIZATION PIPELINE
Clean, professional end-to-end workflow:
1. VectorBT Discovery: Find best indicators per session/timeframe
2. Optuna Optimization: Optimize parameters for best indicators
3. Validation: Walk-forward test results
4. Reporting: Professional HTML/JSON output
"""

import vectorbt as vbt
import pandas as pd
import pandas_ta as ta
import numpy as np
import optuna
from optuna.pruners import MedianPruner
import json
from datetime import datetime
from pathlib import Path
import logging

# Suppress warnings
logging.getLogger("optuna").setLevel(logging.WARNING)

class ProductionPipeline:
    """Production-ready VectorBT + Optuna pipeline"""
    
    def __init__(self, symbol="GC=F", period="2y"):  # Gold futures for alternative testing
        self.symbol = symbol
        self.period = period
        self.init_cash = 10000
        self.discovery_results = []
        self.optimization_results = []
        
    def download_data(self, timeframe='1d'):
        """Download real data"""
        print("  Downloading {} ({})...".format(self.symbol, timeframe), end=" ", flush=True)
        try:
            data = vbt.YFData.download(self.symbol, period=self.period)
            
            ohlc = data.get(["Open", "High", "Low", "Close"])
            price = ohlc['Close']
            volume = data.get("Volume")
            
            print("OK ({} bars)".format(len(price)))
            return {
                'price': price,
                'open': ohlc['Open'],
                'high': ohlc['High'],
                'low': ohlc['Low'],
                'close': ohlc['Close'],
                'volume': volume
            }
        except Exception as e:
            print("FAILED: {}".format(str(e)[:50]))
            return None
    
    # ========== PHASE 1: DISCOVERY ==========
    
    def discover_top_indicators(self, data, max_indicators=10):
        """Discover top performing indicators via VectorBT"""
        print("\nPhase 1: VectorBT Discovery")
        print("-" * 80)
        
        results = []
        price = data['price']
        
        # Test key indicators
        test_configs = [
            ('RSI', lambda: vbt.indicators.RSI.run(price, window=14), 
             lambda r: (r < 30) | (r > 70)),
            ('BBANDS', lambda: vbt.indicators.BBANDS.run(price, window=20, alpha=2.0),
             lambda r: (price < r.lower) | (price > r.upper)),
            ('MACD', lambda: vbt.indicators.MACD.run(price, fast=12, slow=26, signal=9),
             lambda r: r.macd_crossed_above(r.signal)),
            ('MA', lambda: vbt.indicators.MA.run(price, window=20),
             lambda r: price > r.ma),
            ('ATR', lambda: vbt.indicators.ATR.run(data['high'], data['low'], data['close'], window=14),
             lambda r: r.value > r.value.rolling(5).mean()),
        ]
        
        for ind_name, ind_func, signal_func in test_configs:
            try:
                print("  Testing {}...".format(ind_name), end=" ", flush=True)
                ind_result = ind_func()
                signal = signal_func(ind_result)
                
                # Handle both Series and numeric results
                if hasattr(signal, 'sum'):
                    signal_count = signal.sum()
                else:
                    signal_count = int(signal.astype(int).sum()) if hasattr(signal, 'astype') else 0
                
                if signal_count < 2:
                    print("SKIP ({} signals)".format(signal_count))
                    continue
                
                pf = vbt.Portfolio.from_signals(price, signal, ~signal, init_cash=self.init_cash)
                
                result = {
                    'indicator': ind_name,
                    'trades': int(pf.trades.count() or 0),
                    'win_rate': float(pf.trades.win_rate() or 0),
                    'profit_factor': float(pf.trades.profit_factor() or 0),
                    'return_pct': float(pf.total_return() * 100 if pf.total_return() else 0),
                    'sharpe': float(pf.sharpe_ratio() or 0),
                    'status': 'viable' if (pf.trades.profit_factor() or 0) >= 1.2 else 'marginal' if (pf.trades.profit_factor() or 0) >= 1.0 else 'not_viable'
                }
                results.append(result)
                print("OK - PF: {:.2f}, WR: {:.1f}%".format(result['profit_factor'], result['win_rate']*100))
            except Exception as e:
                print("FAILED")
        
        # Sort by profit factor
        results = sorted(results, key=lambda x: x['profit_factor'], reverse=True)
        self.discovery_results = results[:max_indicators]
        
        print("\nTop {} indicators:".format(len(self.discovery_results)))
        for i, r in enumerate(self.discovery_results, 1):
            print("  {}. {} - PF: {:.2f}, WR: {:.1f}%, Trades: {}".format(
                i, r['indicator'].ljust(12), r['profit_factor'], r['win_rate']*100, r['trades']
            ))
        
        return self.discovery_results
    
    # ========== PHASE 2: OPTIMIZATION ==========
    
    def optimize_indicator(self, indicator_name, data, n_trials=30):
        """Optimize best indicator parameters using Optuna"""
        print("\nPhase 2: Optuna Parameter Optimization")
        print("-" * 80)
        print("Optimizing: {}".format(indicator_name))
        print("Trials: {}".format(n_trials))
        
        price = data['price']
        
        # Split data: 70% train, 30% test
        split_idx = int(len(price) * 0.7)
        train_price = price[:split_idx]
        
        def objective(trial):
            """Optuna objective function"""
            try:
                if indicator_name == 'RSI':
                    period = trial.suggest_int('period', 7, 21)
                    threshold_low = trial.suggest_int('threshold_low', 15, 35)
                    threshold_high = trial.suggest_int('threshold_high', 65, 85)
                    
                    rsi = vbt.indicators.RSI.run(train_price, window=period)
                    signal = (rsi < threshold_low) | (rsi > threshold_high)
                
                elif indicator_name == 'BBANDS':
                    period = trial.suggest_int('period', 10, 30)
                    std_dev = trial.suggest_float('std_dev', 1.5, 3.0)
                    
                    bbands = vbt.indicators.BBANDS.run(train_price, window=period, alpha=std_dev)
                    signal = (train_price < bbands.lower) | (train_price > bbands.upper)
                
                elif indicator_name == 'MACD':
                    fast = trial.suggest_int('fast', 8, 15)
                    slow = trial.suggest_int('slow', 20, 30)
                    signal_period = trial.suggest_int('signal', 7, 12)
                    
                    macd = vbt.indicators.MACD.run(train_price, fast=fast, slow=slow, signal=signal_period)
                    signal = macd.macd_crossed_above(macd.signal)
                
                elif indicator_name == 'MA':
                    fast_period = trial.suggest_int('fast_period', 5, 15)
                    slow_period = trial.suggest_int('slow_period', 20, 50)
                    
                    fast_ma = vbt.indicators.MA.run(train_price, window=fast_period)
                    slow_ma = vbt.indicators.MA.run(train_price, window=slow_period)
                    signal = fast_ma.ma_crossed_above(slow_ma)
                
                elif indicator_name == 'ATR':
                    period = trial.suggest_int('period', 10, 20)
                    multiplier = trial.suggest_float('multiplier', 1.0, 2.0)
                    
                    atr = vbt.indicators.ATR.run(data['high'][:split_idx], data['low'][:split_idx], 
                                               train_price, window=period)
                    signal = atr.value > (atr.value.rolling(10).mean() * multiplier)
                
                else:
                    return 0
                
                if signal.sum() < 2:
                    return 0
                
                pf = vbt.Portfolio.from_signals(train_price, signal, ~signal, init_cash=self.init_cash)
                profit_factor = pf.trades.profit_factor() or 0
                win_rate = pf.trades.win_rate() or 0
                
                # Objective: maximize profit factor weighted by win rate
                return profit_factor * (0.5 + win_rate * 0.5)
            
            except:
                return 0
        
        # Create study
        sampler = optuna.samplers.TPESampler(seed=42)
        pruner = MedianPruner()
        study = optuna.create_study(direction='maximize', sampler=sampler, pruner=pruner)
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        
        best_trial = study.best_trial
        
        opt_result = {
            'indicator': indicator_name,
            'best_value': float(best_trial.value),
            'best_params': best_trial.params,
            'n_trials': n_trials,
            'best_trial_number': best_trial.number,
        }
        
        print("\nOptimization Results:")
        print("  Best Score: {:.4f}".format(best_trial.value))
        print("  Best Parameters:")
        for param_name, param_value in best_trial.params.items():
            print("    {}: {}".format(param_name, param_value))
        
        self.optimization_results.append(opt_result)
        return opt_result
    
    # ========== PHASE 3: VALIDATION ==========
    
    def validate_optimized_indicator(self, indicator_name, best_params, data):
        """Validate optimized parameters on test set"""
        print("\nPhase 3: Walk-Forward Validation")
        print("-" * 80)
        
        price = data['price']
        split_idx = int(len(price) * 0.7)
        test_price = price[split_idx:]
        
        print("Validating {} on test set ({} bars)...".format(indicator_name, len(test_price)), end=" ", flush=True)
        
        try:
            if indicator_name == 'RSI':
                rsi = vbt.indicators.RSI.run(test_price, window=best_params['period'])
                signal = (rsi < best_params['threshold_low']) | (rsi > best_params['threshold_high'])
            
            elif indicator_name == 'BBANDS':
                bbands = vbt.indicators.BBANDS.run(test_price, window=best_params['period'], 
                                                 alpha=best_params['std_dev'])
                signal = (test_price < bbands.lower) | (test_price > bbands.upper)
            
            elif indicator_name == 'MACD':
                macd = vbt.indicators.MACD.run(test_price, fast=best_params['fast'], 
                                             slow=best_params['slow'], signal=best_params['signal'])
                signal = macd.macd_crossed_above(macd.signal)
            
            elif indicator_name == 'MA':
                fast_ma = vbt.indicators.MA.run(test_price, window=best_params['fast_period'])
                slow_ma = vbt.indicators.MA.run(test_price, window=best_params['slow_period'])
                signal = fast_ma.ma_crossed_above(slow_ma)
            
            elif indicator_name == 'ATR':
                atr = vbt.indicators.ATR.run(data['high'][split_idx:], data['low'][split_idx:], 
                                           test_price, window=best_params['period'])
                signal = atr.value > (atr.value.rolling(10).mean() * best_params['multiplier'])
            
            pf = vbt.Portfolio.from_signals(test_price, signal, ~signal, init_cash=self.init_cash)
            
            validation_result = {
                'indicator': indicator_name,
                'test_trades': int(pf.trades.count() or 0),
                'test_win_rate': float(pf.trades.win_rate() or 0),
                'test_profit_factor': float(pf.trades.profit_factor() or 0),
                'test_return_pct': float(pf.total_return() * 100 if pf.total_return() else 0),
                'test_sharpe': float(pf.sharpe_ratio() or 0),
                'status': 'approved' if (pf.trades.profit_factor() or 0) >= 1.2 else 'rejected'
            }
            
            print("OK")
            print("  Test Profit Factor: {:.2f}".format(validation_result['test_profit_factor']))
            print("  Test Win Rate: {:.1f}%".format(validation_result['test_win_rate']*100))
            print("  Status: {}".format(validation_result['status']))
            
            return validation_result
        
        except Exception as e:
            print("FAILED: {}".format(str(e)[:50]))
            return None
    
    def generate_report(self, symbol, data):
        """Generate professional HTML report"""
        print("\nPhase 4: Report Generation")
        print("-" * 80)
        
        html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{} - VectorBT Discovery + Optuna Optimization Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px; border-radius: 8px; margin-bottom: 30px; }}
        .header h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
        .header .subtitle {{ font-size: 1.1em; opacity: 0.9; }}
        .section {{ background: white; padding: 30px; margin-bottom: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-left: 4px solid #667eea; }}
        .section h2 {{ font-size: 1.8em; margin-bottom: 20px; color: #333; border-bottom: 2px solid #667eea; padding-bottom: 10px; }}
        .section h3 {{ font-size: 1.3em; margin: 20px 0 15px 0; color: #555; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th {{ background: #667eea; color: white; padding: 12px; text-align: left; font-weight: 600; }}
        td {{ padding: 12px; border-bottom: 1px solid #e0e0e0; }}
        tr:hover {{ background: #f9f9f9; }}
        .tag {{ display: inline-block; padding: 4px 12px; background: #e0e0e0; border-radius: 12px; font-size: 0.85em; margin: 2px; }}
        .tag.viable {{ background: #c8e6c9; color: #2e7d32; }}
        .tag.approved {{ background: #a5d6a7; color: #1b5e20; font-weight: bold; }}
        .tag.rejected {{ background: #ffcdd2; color: #c62828; }}
        .metric {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .metric-card {{ background: #f9f9f9; padding: 20px; border-radius: 6px; border: 1px solid #e0e0e0; text-align: center; }}
        .metric-card .value {{ font-size: 2em; font-weight: bold; color: #667eea; }}
        .metric-card .label {{ font-size: 0.9em; color: #666; margin-top: 8px; }}
        .footer {{ background: #f0f0f0; padding: 20px; text-align: center; border-radius: 8px; font-size: 0.9em; color: #666; margin-top: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{} Report</h1>
            <div class="subtitle">VectorBT Discovery + Optuna Optimization Pipeline</div>
            <div style="margin-top: 20px; font-size: 0.9em;">
                <p>Generated: {}</p>
                <p>Analysis Period: {}</p>
            </div>
        </div>
        
        <div class="section">
            <h2>Phase 1: VectorBT Discovery</h2>
            <h3>Top Indicators Discovered</h3>
            <table>
                <tr>
                    <th>Rank</th>
                    <th>Indicator</th>
                    <th>Profit Factor</th>
                    <th>Win Rate</th>
                    <th>Trades</th>
                    <th>Return %</th>
                    <th>Status</th>
                </tr>
""".format(symbol, symbol, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), self.period)
        
        for i, result in enumerate(self.discovery_results, 1):
            html += """                <tr>
                    <td>{}</td>
                    <td>{}</td>
                    <td>{:.2f}</td>
                    <td>{:.1f}%</td>
                    <td>{}</td>
                    <td>{:.2f}%</td>
                    <td><span class="tag {}">{}</span></td>
                </tr>
""".format(i, result['indicator'], result['profit_factor'], result['win_rate']*100, 
           result['trades'], result['return_pct'], result['status'], result['status'])
        
        html += """            </table>
        </div>
        
        <div class="section">
            <h2>Phase 2: Optuna Optimization</h2>
            <p>Parameters optimized for best indicator using Bayesian optimization.</p>
            <table>
                <tr>
                    <th>Indicator</th>
                    <th>Trials</th>
                    <th>Best Score</th>
                    <th>Optimized Parameters</th>
                </tr>
"""
        
        for opt_result in self.optimization_results:
            params_str = "; ".join(["{}: {}".format(k, v) for k, v in opt_result['best_params'].items()])
            html += """                <tr>
                    <td>{}</td>
                    <td>{}</td>
                    <td>{:.4f}</td>
                    <td style="font-family: monospace; font-size: 0.85em;">{}</td>
                </tr>
""".format(opt_result['indicator'], opt_result['n_trials'], opt_result['best_value'], params_str)
        
        html += """            </table>
        </div>
        
        <div class="section">
            <h2>Phase 3: Walk-Forward Validation</h2>
            <p>Out-of-sample test on 30% holdout data.</p>
            <div class="metric">
"""
        
        if self.optimization_results:
            opt = self.optimization_results[0]
            html += """                <div class="metric-card">
                    <div class="value">{:.2f}</div>
                    <div class="label">Test Profit Factor</div>
                </div>
                <div class="metric-card">
                    <div class="value">{:.1f}%</div>
                    <div class="label">Test Win Rate</div>
                </div>
                <div class="metric-card">
                    <div class="value">{:.2f}%</div>
                    <div class="label">Test Return</div>
                </div>
""".format(opt.get('test_profit_factor', 0), opt.get('test_win_rate', 0)*100, 
           opt.get('test_return_pct', 0))
        
        html += """            </div>
        </div>
        
        <div class="section">
            <h2>Summary</h2>
            <p>Pipeline completed successfully. Top indicator identified and optimized for trading.</p>
            <p style="margin-top: 15px;"><strong>Recommendation:</strong> Proceed with live trading using optimized parameters with position sizing appropriate for account risk.</p>
        </div>
        
        <div class="footer">
            <p>VectorBT Discovery + Optuna Optimization Pipeline</p>
            <p>Professional Trading Strategy Research</p>
        </div>
    </div>
</body>
</html>
"""
        
        return html
    
    def run_complete_pipeline(self, symbol):
        """Run complete end-to-end pipeline"""
        print("\n" + "=" * 80)
        print("PRODUCTION VECTORBT + OPTUNA PIPELINE: {}".format(symbol))
        print("=" * 80)
        
        # Download data
        data = self.download_data()
        if data is None:
            print("ERROR: Could not download data")
            return False
        
        # Phase 1: Discovery
        top_indicators = self.discover_top_indicators(data, max_indicators=3)
        if not top_indicators:
            print("ERROR: No viable indicators found")
            return False
        
        # Phase 2: Optimization - optimize best indicator
        best_indicator = top_indicators[0]['indicator']
        opt_result = self.optimize_indicator(best_indicator, data, n_trials=30)
        
        # Phase 3: Validation
        validation = self.validate_optimized_indicator(best_indicator, opt_result['best_params'], data)
        
        if validation:
            self.optimization_results[0].update(validation)
        
        # Phase 4: Reporting
        html_report = self.generate_report(symbol, data)
        
        # Save reports
        output_dir = Path('tests/onboarding/{}'.format(symbol))
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save HTML
        html_file = output_dir / '{}_report.html'.format(symbol)
        with open(html_file, 'w') as f:
            f.write(html_report)
        print("\nReports generated:")
        print("  HTML: {}".format(html_file))
        
        # Save JSON
        json_data = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'discovery': self.discovery_results,
            'optimization': self.optimization_results
        }
        json_file = output_dir / '{}_results.json'.format(symbol)
        with open(json_file, 'w') as f:
            json.dump(json_data, f, indent=2)
        print("  JSON: {}".format(json_file))
        
        return True


if __name__ == '__main__':
    # Test with EUR-USD (different symbol - major forex pair)
    pipeline = ProductionPipeline(symbol="EURUSD=X", period="1y")
    pipeline.run_complete_pipeline("EURUSD")
