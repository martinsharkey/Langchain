# Comprehensive Vectorbt Test Report Generator

"""
Generates detailed onboarding reports following workspace structure.
Reports go to: tests/onboarding/symbol/symbol_YYYYMMDD.md|.html
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from test_config import SymbolOnboardingReport, BacktestResult, TRADING_SESSIONS, WEEKDAY_CONFIGS


class OnboardingReportGenerator:
    """Generates comprehensive onboarding reports following workspace structure"""
    
    def __init__(self):
        """Initialize with workspace-compliant path"""
        self.base_dir = Path("tests/onboarding")
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_symbol_dir(self, symbol: str) -> Path:
        """Get or create symbol directory"""
        symbol_dir = self.base_dir / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)
        return symbol_dir
    
    def _get_report_filename(self, symbol: str) -> str:
        """Generate report filename: symbol_YYYYMMDD.ext"""
        date_str = datetime.now().strftime("%Y%m%d")
        return f"{symbol}_{date_str}"
    
    def _analyze_top_combinations(self, report: SymbolOnboardingReport, top_n: int = 10) -> Dict[str, List[Dict]]:
        """Analyze top performing combinations by session and timeframe"""
        combinations = {}
        
        # Group results by session
        for session in report.sessions_tested:
            combinations[session] = {}
            
            # Group by timeframe within session
            for timeframe in report.timeframes_tested:
                session_timeframe_results = [
                    r for r in report.backtest_results 
                    if r.session == session and r.timeframe == timeframe and r.status == "viable"
                ]
                
                # Sort by profit factor (primary), then win rate
                sorted_results = sorted(
                    session_timeframe_results,
                    key=lambda x: (x.profit_factor, x.win_rate),
                    reverse=True
                )
                
                # Store top N
                combinations[session][timeframe] = [
                    {
                        "indicator": r.indicator,
                        "profit_factor": round(r.profit_factor, 2),
                        "win_rate": round(r.win_rate * 100, 1),
                        "trades": r.trades_total,
                        "return_pct": round(r.return_pct, 2),
                        "sharpe_ratio": round(r.sharpe_ratio, 2),
                        "max_drawdown_pct": round(r.max_drawdown_pct * 100, 2),
                    }
                    for r in sorted_results[:top_n]
                ]
        
        return combinations
    
    def _generate_combination_section_md(self, combinations: Dict[str, List[Dict]]) -> str:
        """Generate markdown section with top combinations"""
        md = """---

## 🎯 Multi-Session Trading Solution

Best performing indicator/timeframe combinations for each trading session:

"""
        
        for session, timeframes in combinations.items():
            md += f"### {session} Session\n\n"
            
            for timeframe, results in sorted(timeframes.items()):
                if results:
                    md += f"#### {timeframe} Timeframe\n\n"
                    md += "| Rank | Indicator | P.F. | Win Rate | Trades | Return % | Sharpe | Drawdown |\n"
                    md += "|------|-----------|------|----------|--------|----------|--------|----------|\n"
                    
                    for i, r in enumerate(results, 1):
                        md += f"| {i} | {r['indicator']} | {r['profit_factor']} | {r['win_rate']}% | {r['trades']} | {r['return_pct']}% | {r['sharpe_ratio']} | {r['max_drawdown_pct']}% |\n"
                    
                    md += "\n"
        
        return md
    
    def generate_markdown_report(self, report: SymbolOnboardingReport) -> str:
        """Generate comprehensive markdown report"""
        symbol_dir = self._get_symbol_dir(report.symbol)
        filename = self._get_report_filename(report.symbol)
        filepath = symbol_dir / f"{filename}.md"
        
        md = f"""# {report.symbol} - VectorBT Discovery Report

**Report Date**: {report.report_date}  
**Report Time**: {report.report_timestamp}  
**Data Period**: {report.data_start_date} to {report.data_end_date}  
**Period Coverage**: {report.data_period_coverage}  
**Data Source**: {report.data_source}

---

## 📊 Test Configuration

### Timeframes Tested
{', '.join(f'`{tf}`' for tf in report.timeframes_tested)}

### Trading Sessions Tested
{', '.join(f'`{s}`' for s in report.sessions_tested)}

### Weekday Types
{', '.join(f'`{w}`' for w in report.weekday_types_tested)}

### Total Test Configurations
**5 Indicators × 6 Timeframes × 5 Sessions × 3 Weekday Types = 450 Tests**

---

## 📈 Indicators Tested

"""
        
        for ind in report.indicators_tested:
            md += f"""### {ind.name}
- **Description**: {ind.description}
- **Method**: {ind.method}
- **Custom Model**: {'Yes' if ind.is_custom else 'No'}

"""
        
        md += """---

## 📋 Test Results Summary

"""
        
        md += f"""### Overall Results
| Metric | Count | Percentage |
|--------|-------|-----------|
| Total Tests Run | {report.total_backtests_run} | 100% |
| ✅ Viable | {report.viable_count} | {(report.viable_count/report.total_backtests_run*100):.1f}% |
| ◐ Marginal | {report.marginal_count} | {(report.marginal_count/report.total_backtests_run*100):.1f}% |
| ✗ Not Viable | {report.not_viable_count} | {(report.not_viable_count/report.total_backtests_run*100):.1f}% |

### Quality Metrics
| Metric | Value |
|--------|-------|
| Best Profit Factor | {report.best_profit_factor:.2f} |
| Worst Profit Factor | {report.worst_profit_factor:.2f} |
| Best Win Rate | {report.best_win_rate*100:.1f}% |
| Worst Win Rate | {report.worst_win_rate*100:.1f}% |
| Avg Trades per Config | {report.avg_trades_per_config:.1f} |

---

## 🏆 Recommended Indicators

"""
        
        for i, indicator in enumerate(report.recommended_indicators, 1):
            md += f"{i}. **{indicator}**\n"
        
        md += "\n---\n\n## 📄 Detailed Test Results\n\n"
        
        # Group results by indicator
        by_indicator = {}
        for result in report.backtest_results:
            if result.indicator not in by_indicator:
                by_indicator[result.indicator] = []
            by_indicator[result.indicator].append(result)
        
        for indicator, results in sorted(by_indicator.items()):
            md += f"### {indicator}\n\n"
            
            viable_results = [r for r in results if r.status == "viable"]
            marginal_results = [r for r in results if r.status == "marginal"]
            not_viable_results = [r for r in results if r.status == "not_viable"]
            
            if viable_results:
                md += f"#### Viable Results ({len(viable_results)})\n\n"
                md += "| Session | Timeframe | Weekday | Trades | W.R. | P.F. | Return | Sharpe | Status |\n"
                md += "|---------|-----------|---------|--------|------|------|--------|--------|--------|\n"
                
                for r in viable_results[:10]:  # Show top 10
                    md += f"| {r.session} | {r.timeframe} | {r.weekday_type} | {r.trades_total} | {r.win_rate*100:.1f}% | {r.profit_factor:.2f} | {r.return_pct:.2f}% | {r.sharpe_ratio:.2f} | ✅ |\n"
                
                if len(viable_results) > 10:
                    md += f"\n... and {len(viable_results)-10} more viable results\n"
                
                md += "\n"
            
            if marginal_results:
                md += f"#### Marginal Results ({len(marginal_results)})\n\n"
                md += "| Session | Timeframe | Weekday | Trades | W.R. | P.F. |\n"
                md += "|---------|-----------|---------|--------|------|------|\n"
                
                for r in marginal_results[:5]:  # Show top 5
                    md += f"| {r.session} | {r.timeframe} | {r.weekday_type} | {r.trades_total} | {r.win_rate*100:.1f}% | {r.profit_factor:.2f} |\n"
                
                if len(marginal_results) > 5:
                    md += f"\n... and {len(marginal_results)-5} more marginal results\n"
                
                md += "\n"
        
        # Add top combinations analysis
        combinations = self._analyze_top_combinations(report, top_n=5)
        md += self._generate_combination_section_md(combinations)
        
        md += """---

## 📌 Key Findings

"""
        md += report.notes + "\n\n"
        
        md += """---

## 🚀 Next Steps

"""
        for step in report.next_steps:
            md += f"- {step}\n"
        
        md += """
---

## 📑 Report Metadata

- **Report Type**: VectorBT Discovery Phase
- **Test Framework**: pytest + pandas
- **Generated**: Automated onboarding workflow
- **Location**: tests/onboarding/{symbol}/

"""
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(md)
        
        return str(filepath)
    
    def generate_html_report(self, report: SymbolOnboardingReport) -> str:
        """Generate comprehensive HTML report"""
        symbol_dir = self._get_symbol_dir(report.symbol)
        filename = self._get_report_filename(report.symbol)
        filepath = symbol_dir / f"{filename}.html"
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{report.symbol} - VectorBT Discovery Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f5f5f5;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 30px;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .header .subtitle {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-top: 25px;
        }}
        
        .meta-item {{
            background: rgba(255,255,255,0.1);
            padding: 15px;
            border-radius: 6px;
            border-left: 3px solid rgba(255,255,255,0.5);
        }}
        
        .meta-item .label {{
            font-size: 0.85em;
            opacity: 0.85;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .meta-item .value {{
            font-size: 1.2em;
            font-weight: bold;
            margin-top: 8px;
        }}
        
        .section {{
            background: white;
            padding: 30px;
            margin-bottom: 25px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            border-left: 4px solid #667eea;
        }}
        
        .section h2 {{
            font-size: 1.8em;
            margin-bottom: 20px;
            color: #333;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
        
        .section h3 {{
            font-size: 1.3em;
            margin: 20px 0 15px 0;
            color: #555;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        
        .stat-card {{
            background: #f9f9f9;
            padding: 20px;
            border-radius: 6px;
            border: 1px solid #e0e0e0;
            text-align: center;
        }}
        
        .stat-card .number {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
        }}
        
        .stat-card .label {{
            font-size: 0.9em;
            color: #666;
            margin-top: 8px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
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
        
        .tag {{
            display: inline-block;
            padding: 4px 12px;
            background: #e0e0e0;
            border-radius: 12px;
            font-size: 0.85em;
            margin: 2px;
        }}
        
        .tag.viable {{
            background: #c8e6c9;
            color: #2e7d32;
        }}
        
        .tag.marginal {{
            background: #fff9c4;
            color: #f57f17;
        }}
        
        .tag.not-viable {{
            background: #ffcdd2;
            color: #c62828;
        }}
        
        .indicator-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}
        
        .indicator-card {{
            background: #f9f9f9;
            padding: 15px;
            border-radius: 6px;
            border: 1px solid #e0e0e0;
        }}
        
        .indicator-card h4 {{
            margin-bottom: 10px;
            color: #667eea;
        }}
        
        .params {{
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
            background: white;
            padding: 8px;
            border-radius: 3px;
            border-left: 2px solid #667eea;
        }}
        
        .footer {{
            background: #f0f0f0;
            padding: 20px;
            text-align: center;
            border-radius: 8px;
            font-size: 0.9em;
            color: #666;
            margin-top: 30px;
        }}
    </style>
</head>
<body>
    <div class="container">
        
        <!-- Header -->
        <div class="header">
            <h1>{report.symbol} Discovery Report</h1>
            <div class="subtitle">VectorBT Indicator Discovery Phase</div>
            
            <div class="meta-grid">
                <div class="meta-item">
                    <div class="label">Report Date</div>
                    <div class="value">{report.report_date}</div>
                </div>
                <div class="meta-item">
                    <div class="label">Period Tested</div>
                    <div class="value">{report.data_period_coverage}</div>
                </div>
                <div class="meta-item">
                    <div class="label">Data Source</div>
                    <div class="value">{report.data_source}</div>
                </div>
                <div class="meta-item">
                    <div class="label">Total Tests</div>
                    <div class="value">{report.total_backtests_run}</div>
                </div>
            </div>
        </div>
        
        <!-- Test Configuration Section -->
        <div class="section">
            <h2>Test Configuration</h2>
            
            <h3>Timeframes Tested</h3>
            <p>
                {''.join([f'<span class="tag">{tf}</span>' for tf in report.timeframes_tested])}
            </p>
            
            <h3>Trading Sessions</h3>
            <p>
                {''.join([f'<span class="tag">{s}</span>' for s in report.sessions_tested])}
            </p>
            
            <h3>Weekday Types</h3>
            <p>
                {''.join([f'<span class="tag">{w}</span>' for w in report.weekday_types_tested])}
            </p>
        </div>
        
        <!-- Indicators Section -->
        <div class="section">
            <h2>Indicators Tested</h2>
            
            <div class="indicator-grid">
                {''.join([f'''
                <div class="indicator-card">
                    <h4>{ind.name}</h4>
                    <div>{ind.description}</div>
                    <div class="params">Method: {ind.method} | {'Custom' if ind.is_custom else 'VectorBT'}</div>
                </div>
                ''' for ind in report.indicators_tested])}
            </div>
        </div>
        
        <!-- Results Summary -->
        <div class="section">
            <h2>Test Results Summary</h2>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="number">{report.viable_count}</div>
                    <div class="label">Viable ({report.viable_count/report.total_backtests_run*100:.1f}%)</div>
                </div>
                <div class="stat-card">
                    <div class="number">{report.marginal_count}</div>
                    <div class="label">Marginal ({report.marginal_count/report.total_backtests_run*100:.1f}%)</div>
                </div>
                <div class="stat-card">
                    <div class="number">{report.not_viable_count}</div>
                    <div class="label">Not Viable ({report.not_viable_count/report.total_backtests_run*100:.1f}%)</div>
                </div>
            </div>
            
            <h3>Quality Metrics</h3>
            <table>
                <tr>
                    <th>Metric</th>
                    <th>Value</th>
                </tr>
                <tr>
                    <td>Best Profit Factor</td>
                    <td><strong>{report.best_profit_factor:.2f}</strong></td>
                </tr>
                <tr>
                    <td>Worst Profit Factor</td>
                    <td><strong>{report.worst_profit_factor:.2f}</strong></td>
                </tr>
                <tr>
                    <td>Best Win Rate</td>
                    <td><strong>{report.best_win_rate*100:.1f}%</strong></td>
                </tr>
                <tr>
                    <td>Worst Win Rate</td>
                    <td><strong>{report.worst_win_rate*100:.1f}%</strong></td>
                </tr>
                <tr>
                    <td>Avg Trades per Config</td>
                    <td><strong>{report.avg_trades_per_config:.1f}</strong></td>
                </tr>
            </table>
        </div>
        
        <!-- Recommended Indicators -->
        <div class="section">
            <h2>Recommended Indicators</h2>
            <ol>
                {''.join([f'<li><strong>{ind}</strong></li>' for ind in report.recommended_indicators])}
            </ol>
        </div>
        
        <!-- Sample Results -->
        <div class="section">
            <h2>Sample Backtest Results (First 20)</h2>
            <table>
                <tr>
                    <th>Indicator</th>
                    <th>Session</th>
                    <th>Timeframe</th>
                    <th>Weekday</th>
                    <th>Trades</th>
                    <th>Win Rate</th>
                    <th>Profit Factor</th>
                    <th>Return %</th>
                    <th>Sharpe</th>
                    <th>Status</th>
                </tr>
                {''.join([f'''
                <tr>
                    <td>{r.indicator}</td>
                    <td>{r.session}</td>
                    <td>{r.timeframe}</td>
                    <td>{r.weekday_type}</td>
                    <td>{r.trades_total}</td>
                    <td>{r.win_rate*100:.1f}%</td>
                    <td>{r.profit_factor:.2f}</td>
                    <td>{r.return_pct:.2f}%</td>
                    <td>{r.sharpe_ratio:.2f}</td>
                    <td><span class="tag {r.status}">{r.status}</span></td>
                </tr>
                ''' for r in report.backtest_results[:20]])}
            </table>
        </div>
        
        <!-- Notes & Next Steps -->
        <div class="section">
            <h2>Notes & Recommendations</h2>
            <p>{report.notes}</p>
            
            <h3>Next Steps</h3>
            <ul>
                {''.join([f'<li>{step}</li>' for step in report.next_steps])}
            </ul>
        </div>
        
        <!-- Footer -->
        <div class="footer">
            <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>Location: tests/onboarding/{report.symbol}/</p>
            <p>VectorBT Discovery Phase Report</p>
        </div>
    </div>
</body>
</html>
"""
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
        
        return str(filepath)
    
    def generate_json_report(self, report: SymbolOnboardingReport) -> str:
        """Generate JSON report for machine consumption"""
        symbol_dir = self._get_symbol_dir(report.symbol)
        filename = self._get_report_filename(report.symbol)
        filepath = symbol_dir / f"{filename}.json"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report.to_json())
        
        return str(filepath)
