# Comprehensive Vectorbt Test Report Generator

"""
Generates detailed HTML and JSON reports for symbol onboarding vectorbt discovery
Captures all details: symbol, timeframes, sessions, indicators, parameters, results
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from test_config import SymbolOnboardingReport, BacktestResult, TRADING_SESSIONS, WEEKDAY_CONFIGS

class TestReportGenerator:
    """Generates comprehensive test reports in HTML and JSON formats"""
    
    def __init__(self, output_dir: str = "test-output/reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_html_report(self, report: SymbolOnboardingReport, filename: str = None) -> str:
        """Generate comprehensive HTML report"""
        
        if filename is None:
            filename = f"{report.symbol}_discovery_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        filepath = self.output_dir / filename
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{report.symbol} Discovery Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        
        .header h1 {{
            margin: 0;
            font-size: 2.5em;
        }}
        
        .header-meta {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        
        .meta-item {{
            background: rgba(255,255,255,0.1);
            padding: 15px;
            border-radius: 4px;
        }}
        
        .meta-item label {{
            font-size: 0.9em;
            opacity: 0.9;
        }}
        
        .meta-item value {{
            display: block;
            font-size: 1.3em;
            font-weight: bold;
            margin-top: 5px;
        }}
        
        .section {{
            background: white;
            padding: 25px;
            margin-bottom: 20px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            border-left: 4px solid #667eea;
        }}
        
        .section h2 {{
            margin-top: 0;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
        
        .test-configuration {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin: 15px 0;
        }}
        
        .config-card {{
            background: #f9f9f9;
            padding: 15px;
            border-radius: 4px;
            border: 1px solid #e0e0e0;
        }}
        
        .config-card h4 {{
            margin: 0 0 10px 0;
            color: #667eea;
        }}
        
        .config-card ul {{
            margin: 0;
            padding-left: 20px;
            font-size: 0.9em;
        }}
        
        .config-card li {{
            margin: 5px 0;
        }}
        
        .indicators {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 15px;
            margin: 15px 0;
        }}
        
        .indicator-card {{
            background: #f9f9f9;
            padding: 15px;
            border-radius: 4px;
            border: 1px solid #e0e0e0;
        }}
        
        .indicator-card h4 {{
            margin: 0 0 10px 0;
            color: #333;
        }}
        
        .indicator-params {{
            font-size: 0.85em;
            font-family: monospace;
            background: white;
            padding: 10px;
            border-radius: 3px;
            overflow-x: auto;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        
        th {{
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        
        td {{
            padding: 12px;
            border-bottom: 1px solid #e0e0e0;
        }}
        
        tr:hover {{
            background: #f9f9f9;
        }}
        
        .viable {{
            color: #27ae60;
            font-weight: bold;
        }}
        
        .marginal {{
            color: #f39c12;
            font-weight: bold;
        }}
        
        .not-viable {{
            color: #e74c3c;
            font-weight: bold;
        }}
        
        .metric {{
            display: inline-block;
            background: #f0f0f0;
            padding: 10px 15px;
            margin: 5px;
            border-radius: 4px;
            font-size: 0.9em;
        }}
        
        .metric-value {{
            font-weight: bold;
            color: #667eea;
        }}
        
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 15px 0;
        }}
        
        .summary-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 4px;
            text-align: center;
        }}
        
        .summary-card .number {{
            font-size: 2em;
            font-weight: bold;
        }}
        
        .summary-card .label {{
            font-size: 0.9em;
            opacity: 0.9;
        }}
        
        .recommendations {{
            background: #e8f8f5;
            border: 2px solid #27ae60;
            padding: 15px;
            border-radius: 4px;
            margin: 15px 0;
        }}
        
        .recommendations h4 {{
            color: #27ae60;
            margin-top: 0;
        }}
        
        .recommendations ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}
        
        .recommendations li {{
            margin: 8px 0;
        }}
        
        .footer {{
            text-align: center;
            color: #999;
            font-size: 0.85em;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{report.symbol} Discovery Report</h1>
        <div class="header-meta">
            <div class="meta-item">
                <label>Report Date</label>
                <value>{report.report_date}</value>
            </div>
            <div class="meta-item">
                <label>Data Period</label>
                <value>{report.data_start_date} to {report.data_end_date}</value>
            </div>
            <div class="meta-item">
                <label>Period Coverage</label>
                <value>{report.data_period_coverage}</value>
            </div>
            <div class="meta-item">
                <label>Total Candles</label>
                <value>{report.data_candle_count:,}</value>
            </div>
            <div class="meta-item">
                <label>Data Source</label>
                <value>{report.data_source}</value>
            </div>
        </div>
    </div>
    
    <!-- Test Configuration Section -->
    <div class="section">
        <h2>Test Configuration</h2>
        
        <div class="test-configuration">
            <div class="config-card">
                <h4>Timeframes Tested</h4>
                <ul>
                    {''.join([f'<li>{tf}</li>' for tf in report.timeframes_tested])}
                </ul>
            </div>
            
            <div class="config-card">
                <h4>Sessions Tested</h4>
                <ul>
                    {''.join([f'<li>{s}</li>' for s in report.sessions_tested])}
                </ul>
            </div>
            
            <div class="config-card">
                <h4>Weekday Types</h4>
                <ul>
                    {''.join([f'<li>{w}</li>' for w in report.weekday_types_tested])}
                </ul>
            </div>
        </div>
    </div>
    
    <!-- Indicators Tested Section -->
    <div class="section">
        <h2>Indicators Tested</h2>
        <p>Total Indicators: <strong>{len(report.indicators_tested)}</strong></p>
        
        <div class="indicators">
            {''.join([f'''
            <div class="indicator-card">
                <h4>{ind.name}</h4>
                <p>{ind.description}</p>
                <div class="indicator-params">
                    {json.dumps(ind.parameters, indent=2)}
                </div>
            </div>
            ''' for ind in report.indicators_tested])}
        </div>
    </div>
    
    <!-- Summary Statistics Section -->
    <div class="section">
        <h2>Summary Statistics</h2>
        
        <div class="summary-grid">
            <div class="summary-card">
                <div class="number">{report.total_backtests_run}</div>
                <div class="label">Total Backtests</div>
            </div>
            <div class="summary-card" style="background: linear-gradient(135deg, #27ae60 0%, #229954 100%);">
                <div class="number">{report.viable_count}</div>
                <div class="label">Viable Indicators</div>
            </div>
            <div class="summary-card" style="background: linear-gradient(135deg, #f39c12 0%, #e67e22 100%);">
                <div class="number">{report.marginal_count}</div>
                <div class="label">Marginal Indicators</div>
            </div>
            <div class="summary-card" style="background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);">
                <div class="number">{report.not_viable_count}</div>
                <div class="label">Not Viable</div>
            </div>
        </div>
        
        <div style="margin-top: 20px;">
            <div class="metric">
                <span class="metric-value">{report.best_profit_factor:.2f}</span>
                <span>Best PF</span>
            </div>
            <div class="metric">
                <span class="metric-value">{report.worst_profit_factor:.2f}</span>
                <span>Worst PF</span>
            </div>
            <div class="metric">
                <span class="metric-value">{report.best_win_rate:.1%}</span>
                <span>Best WR</span>
            </div>
            <div class="metric">
                <span class="metric-value">{report.worst_win_rate:.1%}</span>
                <span>Worst WR</span>
            </div>
            <div class="metric">
                <span class="metric-value">{report.avg_trades_per_config:.0f}</span>
                <span>Avg Trades/Config</span>
            </div>
        </div>
    </div>
    
    <!-- Viable Indicators Section -->
    <div class="section">
        <h2>Viable Indicators ({len(report.viable_indicators)})</h2>
        
        <table>
            <thead>
                <tr>
                    <th>Indicator</th>
                    <th>Session</th>
                    <th>Timeframe</th>
                    <th>Weekday</th>
                    <th>Profit Factor</th>
                    <th>Win Rate</th>
                    <th>Return %</th>
                    <th>Trades</th>
                    <th>Max DD%</th>
                </tr>
            </thead>
            <tbody>
                {''.join([f'''
                <tr>
                    <td>{r.get("indicator")}</td>
                    <td>{r.get("session")}</td>
                    <td>{r.get("timeframe")}</td>
                    <td>{r.get("weekday_type")}</td>
                    <td class="viable">{r.get("profit_factor", 0):.2f}</td>
                    <td>{r.get("win_rate", 0):.1%}</td>
                    <td>{r.get("return_pct", 0):.2%}</td>
                    <td>{r.get("trades_total")}</td>
                    <td>{r.get("max_drawdown_pct", 0):.1%}</td>
                </tr>
                ''' for r in report.viable_indicators])}
            </tbody>
        </table>
    </div>
    
    <!-- Recommendations Section -->
    <div class="section">
        <h2>Recommendations</h2>
        
        <div class="recommendations">
            <h4>✅ Recommended Indicators for Next Phase (Optimization)</h4>
            <ul>
                {''.join([f'<li><strong>{ind}</strong> - Ready for Optuna parameter tuning</li>' for ind in report.recommended_indicators])}
            </ul>
        </div>
        
        <h4>Notes:</h4>
        <p>{report.notes}</p>
        
        <h4>Next Steps:</h4>
        <ul>
            {''.join([f'<li>{step}</li>' for step in report.next_steps])}
        </ul>
    </div>
    
    <div class="footer">
        <p>Generated: {report.report_timestamp}</p>
        <p>Symbol Onboarding Discovery Report - VectorBT Analysis</p>
    </div>
</body>
</html>
        """
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
        
        return str(filepath)
    
    def generate_json_report(self, report: SymbolOnboardingReport, filename: str = None) -> str:
        """Generate JSON report for machine consumption"""
        
        if filename is None:
            filename = f"{report.symbol}_discovery_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = self.output_dir / filename
        report.save_json(str(filepath))
        
        return str(filepath)

# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    from test_config import IndicatorConfig
    
    # Create sample report
    report = SymbolOnboardingReport(
        symbol="BTCUSD",
        report_date=datetime.now().strftime("%Y-%m-%d"),
        report_timestamp=datetime.now().isoformat(),
        timeframes_tested=["M1", "M5", "M15", "M30", "H1", "H4"],
        sessions_tested=["Asia", "London", "NewYork", "Overlap_Asia_London", "Overlap_London_NY"],
        weekday_types_tested=["Weekday", "Weekend", "Week"],
        indicators_tested=[
            IndicatorConfig("RSI", 14, "RSI", {"timeperiod": 14}, "Relative Strength Index"),
            IndicatorConfig("MACD", 26, "MACD", {"fast": 12, "slow": 26}, "Moving Average Convergence"),
        ],
        data_start_date="2024-01-01",
        data_end_date="2026-08-25",
        data_candle_count=125000,
        data_source="MT5",
        backtest_results=[],
        viable_indicators=[
            {
                "indicator": "RSI",
                "session": "London",
                "timeframe": "H1",
                "weekday_type": "Weekday",
                "profit_factor": 2.15,
                "win_rate": 0.58,
                "return_pct": 0.45,
                "trades_total": 87,
                "max_drawdown_pct": -0.125,
            }
        ],
        marginal_indicators=[],
        total_backtests_run=150,
        viable_count=1,
        marginal_count=0,
        not_viable_count=149,
        best_profit_factor=2.15,
        worst_profit_factor=0.85,
        best_win_rate=0.58,
        worst_win_rate=0.35,
        avg_trades_per_config=58,
        recommended_indicators=["RSI"],
        notes="Strong RSI signal in London session on hourly timeframe during weekdays.",
        next_steps=[
            "Run Optuna parameter optimization on RSI indicator",
            "Test across additional symbols for robustness",
            "Validate performance on walk-forward data",
        ]
    )
    
    # Generate reports
    generator = TestReportGenerator()
    html_file = generator.generate_html_report(report)
    json_file = generator.generate_json_report(report)
    
    print(f"✅ HTML Report: {html_file}")
    print(f"✅ JSON Report: {json_file}")
