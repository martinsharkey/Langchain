#!/usr/bin/env python3
"""
Cleaned Dashboard - Only Real Data

This dashboard shows ONLY:
✅ Real MT5 connection status
✅ Real account information
✅ Real live XAUUSD price
✅ Readiness score (calculated from real data)

Removed:
❌ Empty trades table (no trades executed yet)
❌ Empty strategy table (no strategies executed yet)
❌ Empty knowledge table (learning not enabled yet)

Run with:
    python dashboard_clean.py
"""

import os
import sys
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, render_template_string, jsonify

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DATA_DIR

logger = logging.getLogger("dashboard")
app = Flask(__name__)

DB_PATH = os.path.join(DATA_DIR, "trading_experience.db")


def safe_query(path: str, query: str, params=(), default=None):
    """Safe database query with error handling."""
    try:
        if not os.path.exists(path):
            return default
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.warning(f"DB query failed: {e}")
        return default


def calculate_readiness() -> dict:
    """Calculate readiness based on REAL data only."""
    
    # 1. MT5 Connection (only real metric right now)
    try:
        from src.mt5.connector import get_connector
        c = get_connector()
        if c.is_connected():
            connection_score = 100
            connection_status = "LIVE"
        else:
            connection_score = 0
            connection_status = "OFFLINE"
    except Exception:
        connection_score = 0
        connection_status = "ERROR"
    
    return {
        "score": connection_score,
        "status": connection_status,
        "color": "#3fb950" if connection_score > 0 else "#f85149",
        "message": "System connected to live MT5" if connection_score > 0 else "System offline",
    }


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/readiness")
def api_readiness():
    """Get readiness and live MT5 data."""
    readiness = calculate_readiness()
    
    try:
        from src.mt5.connector import get_connector
        from src.mt5.account import get_account_info
        from src.mt5.data import get_last_price
        
        c = get_connector()
        c.initialize()
        
        if c.is_connected():
            acc = get_account_info()
            last = get_last_price("XAUUSD")
            
            readiness["mt5"] = {
                "connected": True,
                "account": acc,
                "xauusd": last,
            }
            readiness["account_currency"] = acc.get("currency", "USD") if acc else "USD"
        else:
            readiness["mt5"] = {
                "connected": False,
                "account": None,
                "xauusd": None,
            }
            readiness["account_currency"] = "USD"
    except Exception as e:
        readiness["mt5"] = {
            "connected": False,
            "error": str(e),
        }
    
    return jsonify(readiness)


@app.route("/api/research")
def api_research():
    """Get research system status (real data only)."""
    try:
        from src.orchestration import get_orchestrator
        
        orchestrator = get_orchestrator()
        research = orchestrator.get_research_context_for_trading()
        scheduler_status = orchestrator.scheduler.get_status()
        
        return jsonify({
            "has_research": research.get("has_research", False),
            "scheduler_running": scheduler_status.get("is_running", False),
            "trigger_time": scheduler_status.get("trigger_time"),
            "next_run": scheduler_status.get("next_run"),
            "cycle_count": scheduler_status.get("run_count", 0),
            "research": research.get("analysis", {}),
        })
    except Exception as e:
        return jsonify({
            "has_research": False,
            "error": str(e),
        })


# ═══════════════════════════════════════════════════════════════════
# HTML Template - Clean, Real Data Only
# ═══════════════════════════════════════════════════════════════════

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading System - Real Data Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: #0d1117; 
            color: #c9d1d9; 
            padding: 20px;
            min-height: 100vh;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { 
            color: #58a6ff; 
            margin-bottom: 5px;
            font-size: 24px;
        }
        .subtitle {
            color: #8b949e;
            font-size: 14px;
            margin-bottom: 20px;
        }
        h2 { 
            color: #8b949e; 
            font-size: 14px; 
            margin: 25px 0 12px; 
            text-transform: uppercase; 
            letter-spacing: 1px;
            border-bottom: 1px solid #30363d;
            padding-bottom: 8px;
        }
        .grid { 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); 
            gap: 15px; 
            margin-bottom: 20px; 
        }
        .card { 
            background: #161b22; 
            border: 1px solid #30363d; 
            border-radius: 8px; 
            padding: 20px; 
        }
        .card h3 { 
            color: #58a6ff; 
            font-size: 13px; 
            margin-bottom: 15px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .metric { 
            font-size: 28px; 
            font-weight: bold; 
            color: #c9d1d9; 
            margin: 10px 0;
        }
        .metric small { 
            font-size: 13px; 
            color: #8b949e; 
            display: block;
            margin-top: 5px;
        }
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 10px 16px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            margin: 10px 0;
        }
        .status-live {
            background: #23863633;
            color: #3fb950;
            border: 1px solid #238636;
        }
        .status-offline {
            background: #da363333;
            color: #f85149;
            border: 1px solid #da3633;
        }
        .pulse {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: currentColor;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }
        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #30363d;
        }
        .info-row:last-child { border-bottom: none; }
        .info-label {
            color: #8b949e;
            font-size: 13px;
        }
        .info-value {
            color: #c9d1d9;
            font-weight: 500;
        }
        .positive { color: #3fb950; }
        .negative { color: #f85149; }
        .neutral { color: #d29922; }
        .section { margin-bottom: 30px; }
        .refresh {
            color: #8b949e;
            font-size: 12px;
            margin-top: 10px;
        }
        .warning {
            background: #d2992233;
            border: 1px solid #d29922;
            color: #d29922;
            padding: 12px;
            border-radius: 6px;
            margin: 10px 0;
            font-size: 13px;
        }
        .success {
            background: #23863633;
            border: 1px solid #238636;
            color: #3fb950;
            padding: 12px;
            border-radius: 6px;
            margin: 10px 0;
            font-size: 13px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Trading System Dashboard</h1>
        <p class="subtitle">Real-time monitoring - Live data only</p>

        <!-- MT5 Connection Status -->
        <div class="section">
            <h2>System Status</h2>
            <div class="grid">
                <div class="card">
                    <h3>MT5 Connection</h3>
                    <div id="connection">Loading...</div>
                </div>
                <div class="card">
                    <h3>Account Information</h3>
                    <div id="account">Loading...</div>
                </div>
                <div class="card">
                    <h3>XAUUSD Market Data</h3>
                    <div id="price">Loading...</div>
                </div>
            </div>
        </div>

        <!-- Research System Status -->
        <div class="section">
            <h2>Research Intelligence System</h2>
            <div class="grid">
                <div class="card">
                    <h3>Daily Research Scheduler</h3>
                    <div id="research">Loading...</div>
                </div>
                <div class="card">
                    <h3>Market Analysis</h3>
                    <div id="analysis">Loading...</div>
                </div>
            </div>
        </div>

        <!-- System Readiness -->
        <div class="section">
            <h2>System Readiness</h2>
            <div class="card">
                <h3>Integration Status</h3>
                <div id="readiness">Loading...</div>
            </div>
        </div>

        <!-- Legend -->
        <div class="section">
            <h2>Data Sources</h2>
            <div class="card">
                <div class="success">✅ Real data pulled from MetaTrader 5 API</div>
                <div class="success">✅ Real data from research intelligence system</div>
                <div class="warning">⚠️ No trade history yet (trading not executed)</div>
                <div class="warning">⚠️ This is a live monitoring dashboard for real data only</div>
            </div>
        </div>

        <div class="refresh" id="last-update">Last updated: --</div>
    </div>

    <script>
        let accountCurrency = 'USD';
        
        function formatCurrency(val, currency = null) {
            if (val === null || val === undefined) return 'N/A';
            const symbols = {
                'USD': '$', 'GBP': '£', 'EUR': '€', 'JPY': '¥',
                'CHF': 'CHF', 'AUD': 'A$', 'CAD': 'C$', 'NZD': 'NZ$'
            };
            const symbol = symbols[currency || accountCurrency] || '$';
            return symbol + parseFloat(val).toLocaleString(undefined, 
                {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }

        async function loadData() {
            try {
                const [readinessRes, researchRes] = await Promise.all([
                    fetch('/api/readiness'),
                    fetch('/api/research'),
                ]);

                const readiness = await readinessRes.json();
                const research = await researchRes.json();

                // Set currency
                if (readiness.account_currency) {
                    accountCurrency = readiness.account_currency;
                }

                // Connection Status
                const connEl = document.getElementById('connection');
                if (readiness.mt5 && readiness.mt5.connected) {
                    connEl.innerHTML = `
                        <div class="status-badge status-live">
                            <div class="pulse"></div>
                            LIVE CONNECTION
                        </div>
                        <div style="margin-top: 10px;">
                            <div class="info-row">
                                <span class="info-label">Status</span>
                                <span class="info-value positive">Connected</span>
                            </div>
                            <div class="info-row">
                                <span class="info-label">Server</span>
                                <span class="info-value">${readiness.mt5.account?.server || 'N/A'}</span>
                            </div>
                            <div class="info-row">
                                <span class="info-label">Account Type</span>
                                <span class="info-value">${readiness.mt5.account?.type || 'N/A'}</span>
                            </div>
                        </div>
                    `;
                } else {
                    connEl.innerHTML = `
                        <div class="status-badge status-offline">
                            <div class="pulse"></div>
                            OFFLINE
                        </div>
                        <div style="margin-top: 10px; color: #8b949e;">
                            ${readiness.mt5?.error || 'Not connected to live MT5'}
                        </div>
                    `;
                }

                // Account Information
                const accountEl = document.getElementById('account');
                if (readiness.mt5 && readiness.mt5.account) {
                    const acc = readiness.mt5.account;
                    accountEl.innerHTML = `
                        <div class="info-row">
                            <span class="info-label">Account Name</span>
                            <span class="info-value">${acc.name || 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Balance</span>
                            <span class="info-value">${formatCurrency(acc.balance)}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Equity</span>
                            <span class="info-value">${formatCurrency(acc.equity)}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Leverage</span>
                            <span class="info-value">1:${acc.leverage || 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Currency</span>
                            <span class="info-value">${acc.currency || 'N/A'}</span>
                        </div>
                    `;
                } else {
                    accountEl.innerHTML = '<div style="color: #8b949e;">No account data available</div>';
                }

                // XAUUSD Price
                const priceEl = document.getElementById('price');
                if (readiness.mt5 && readiness.mt5.xauusd) {
                    const price = readiness.mt5.xauusd;
                    priceEl.innerHTML = `
                        <div class="metric">${formatCurrency(price.bid)}</div>
                        <small>Current Bid Price</small>
                        <div class="info-row" style="margin-top: 10px;">
                            <span class="info-label">Ask</span>
                            <span class="info-value">${formatCurrency(price.ask)}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Bid</span>
                            <span class="info-value">${formatCurrency(price.bid)}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Spread</span>
                            <span class="info-value">${((price.ask - price.bid) * 100).toFixed(1)} cents</span>
                        </div>
                    `;
                } else {
                    priceEl.innerHTML = '<div style="color: #8b949e;">Price data unavailable</div>';
                }

                // Research Status
                const researchEl = document.getElementById('research');
                if (research.scheduler_running) {
                    researchEl.innerHTML = `
                        <div class="success" style="margin: 0;">
                            ✅ Scheduler running
                        </div>
                        <div class="info-row">
                            <span class="info-label">Trigger Time</span>
                            <span class="info-value">${research.trigger_time}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Next Run</span>
                            <span class="info-value">${research.next_run || 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Cycles Completed</span>
                            <span class="info-value">${research.cycle_count}</span>
                        </div>
                    `;
                } else {
                    researchEl.innerHTML = `
                        <div class="warning" style="margin: 0;">
                            ⚠️ Scheduler not running
                        </div>
                    `;
                }

                // Analysis
                const analysisEl = document.getElementById('analysis');
                if (research.has_research && research.research) {
                    const r = research.research;
                    analysisEl.innerHTML = `
                        <div class="info-row">
                            <span class="info-label">Market Bias</span>
                            <span class="info-value">${r.net_bias || 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Confidence</span>
                            <span class="info-value">${r.confidence ? (r.confidence * 100).toFixed(0) + '%' : 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Volatility Risk</span>
                            <span class="info-value">${r.volatility_risk || 'N/A'}</span>
                        </div>
                        <div class="info-row">
                            <span class="info-label">Recommendation</span>
                            <span class="info-value">${r.recommendation || 'N/A'}</span>
                        </div>
                    `;
                } else {
                    analysisEl.innerHTML = '<div style="color: #8b949e;">No analysis available yet (runs daily)</div>';
                }

                // Readiness
                const readinessEl = document.getElementById('readiness');
                readinessEl.innerHTML = `
                    <div class="info-row">
                        <span class="info-label">Status</span>
                        <span class="info-value ${readiness.score > 0 ? 'positive' : 'negative'}">
                            ${readiness.status}
                        </span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Message</span>
                        <span class="info-value">${readiness.message}</span>
                    </div>
                `;

                // Update timestamp
                document.getElementById('last-update').textContent = 
                    'Last updated: ' + new Date().toLocaleTimeString();

            } catch (e) {
                console.error('Load error:', e);
            }
        }

        loadData();
        setInterval(loadData, 5000);
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    print("=" * 60)
    print("  Trading System Dashboard (Real Data Only)")
    print("=" * 60)
    print("  Open http://localhost:5001 in your browser")
    print("  Shows only REAL data from MT5 and research system")
    print("  Press Ctrl+C to stop")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5001, debug=False)
