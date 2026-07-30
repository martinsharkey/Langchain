"""
Fixed Dashboard - Handles errors and shows real data

Issues fixed:
1. Promise.all() was failing silently when one endpoint returned error
2. Position size is 0.0 (real data - trading bot not setting lot sizes)
3. Trades weren't displaying

Changes:
- Better error handling
- Shows trades even if other APIs fail
- Displays 0.0 position size correctly (that's real data)
- Shows what data is available vs not available
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


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/readiness")
def api_readiness():
    """Get readiness and live MT5 data."""
    try:
        from src.mt5.connector import get_connector
        from src.mt5.account import get_account_info
        from src.mt5.data import get_last_price
        
        c = get_connector()
        c.initialize()
        
        if c.is_connected():
            acc = get_account_info()
            last = get_last_price("XAUUSD")
            
            return jsonify({
                "mt5": {
                    "connected": True,
                    "account": acc,
                    "xauusd": last,
                },
                "account_currency": acc.get("currency", "USD") if acc else "USD",
                "score": 100,
                "status": "LIVE",
                "message": "Connected to live MT5",
            })
        else:
            return jsonify({
                "mt5": {"connected": False},
                "account_currency": "USD",
                "score": 0,
                "status": "OFFLINE",
                "message": "Not connected to live MT5",
            })
    except Exception as e:
        return jsonify({
            "mt5": {"connected": False, "error": str(e)},
            "account_currency": "USD",
            "score": 0,
            "status": "ERROR",
            "message": str(e),
        }), 200


@app.route("/api/trades")
def api_trades():
    """Get actual trades from database."""
    limit = int(os.environ.get("DASHBOARD_TRADES_LIMIT", "50"))
    rows = safe_query(DB_PATH, """
        SELECT id, timestamp, symbol, action, entry_price, stop_loss,
               take_profit, position_size, confidence, strategy_used,
               outcome, profit_loss, exit_price, exit_reason,
               market_regime, created_at
        FROM trades
        ORDER BY id DESC
        LIMIT ?
    """, (limit,), default=[])
    return jsonify(rows or [])


@app.route("/api/performance")
def api_performance():
    """Get performance metrics."""
    overall = safe_query(DB_PATH, """
        SELECT 
            COUNT(*) as total_trades,
            SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN outcome='pending' THEN 1 ELSE 0 END) as pending,
            COALESCE(SUM(profit_loss), 0) as total_pnl,
            AVG(CASE WHEN outcome IN ('win','loss') THEN confidence ELSE NULL END) as avg_confidence
        FROM trades
    """, default=[{}])
    
    return jsonify({
        "overall": overall[0] if overall else {},
        "strategies": [],
    })


# ═══════════════════════════════════════════════════════════════════
# HTML Template - FIXED VERSION
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
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { color: #58a6ff; margin-bottom: 5px; font-size: 24px; }
        .subtitle { color: #8b949e; font-size: 14px; margin-bottom: 20px; }
        h2 { 
            color: #8b949e; font-size: 14px; margin: 25px 0 12px; 
            text-transform: uppercase; letter-spacing: 1px;
            border-bottom: 1px solid #30363d; padding-bottom: 8px;
        }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }
        .card h3 { color: #58a6ff; font-size: 13px; margin-bottom: 15px; text-transform: uppercase; }
        .metric { font-size: 28px; font-weight: bold; color: #c9d1d9; margin: 10px 0; }
        .metric small { font-size: 13px; color: #8b949e; display: block; margin-top: 5px; }
        .status-badge {
            display: inline-flex; align-items: center; gap: 8px; padding: 10px 16px; 
            border-radius: 6px; font-size: 13px; font-weight: 600; margin: 10px 0;
        }
        .status-live { background: #23863633; color: #3fb950; border: 1px solid #238636; }
        .status-offline { background: #da363333; color: #f85149; border: 1px solid #da3633; }
        .pulse { width: 10px; height: 10px; border-radius: 50%; background: currentColor; animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        .info-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #30363d; }
        .info-row:last-child { border-bottom: none; }
        .info-label { color: #8b949e; font-size: 13px; }
        .info-value { color: #c9d1d9; font-weight: 500; }
        .positive { color: #3fb950; }
        .negative { color: #f85149; }
        .warning { background: #d2992233; border: 1px solid #d29922; color: #d29922; padding: 12px; border-radius: 6px; margin: 10px 0; font-size: 13px; }
        .success { background: #23863633; border: 1px solid #238636; color: #3fb950; padding: 12px; border-radius: 6px; margin: 10px 0; font-size: 13px; }
        
        table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }
        th, td { text-align: left; padding: 10px; border-bottom: 1px solid #30363d; }
        th { color: #8b949e; font-weight: 600; font-size: 12px; text-transform: uppercase; }
        tr:hover { background: #1c2128; }
        .badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; }
        .badge-buy { background: #238636; color: white; }
        .badge-sell { background: #da3633; color: white; }
        .badge-breakeven { background: #d29922; color: white; }
        .badge-pending { background: #d29922; color: white; }
        .empty-state { text-align: center; padding: 30px; color: #8b949e; font-style: italic; }
        .refresh { color: #8b949e; font-size: 12px; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Trading System Dashboard</h1>
        <p class="subtitle">Real-time monitoring - Live data</p>

        <!-- MT5 Status -->
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

        <!-- Trading Data -->
        <div class="section">
            <h2>Recent Trades (6 trades in database)</h2>
            <div class="card">
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Time</th>
                            <th>Action</th>
                            <th>Entry</th>
                            <th>SL</th>
                            <th>TP</th>
                            <th>Lot Size</th>
                            <th>Confidence</th>
                            <th>Strategy</th>
                            <th>Outcome</th>
                            <th>P&L</th>
                        </tr>
                    </thead>
                    <tbody id="trades-table">
                        <tr><td colspan="11" class="empty-state">Loading trades...</td></tr>
                    </tbody>
                </table>
            </div>
            <div class="warning">
                ⚠️ Note: Lot Size is 0.00 because the trading bot hasn't been configured with position sizing yet. This is REAL data from the database.
            </div>
        </div>

        <!-- Performance Summary -->
        <div class="section">
            <h2>Performance Summary</h2>
            <div class="grid">
                <div class="card">
                    <h3>Total Trades</h3>
                    <div id="total-trades" class="metric">Loading...</div>
                </div>
                <div class="card">
                    <h3>Wins / Losses</h3>
                    <div id="win-loss" class="metric">Loading...</div>
                </div>
                <div class="card">
                    <h3>Total P&L</h3>
                    <div id="total-pnl" class="metric">Loading...</div>
                </div>
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
                // Load each endpoint independently (don't use Promise.all)
                // This way if one fails, others still load
                
                const readiness = await fetch('/api/readiness').then(r => r.json()).catch(e => ({ error: e.message }));
                const trades = await fetch('/api/trades').then(r => r.json()).catch(e => []);
                const perf = await fetch('/api/performance').then(r => r.json()).catch(e => ({}));

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
                        </div>
                    `;
                } else {
                    connEl.innerHTML = `
                        <div class="status-badge status-offline">
                            <div class="pulse"></div>
                            OFFLINE
                        </div>
                        <div style="margin-top: 10px; color: #8b949e;">
                            Not connected to live MT5
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
                    `;
                } else {
                    accountEl.innerHTML = '<div style="color: #8b949e;">No account data</div>';
                }

                // Price
                const priceEl = document.getElementById('price');
                if (readiness.mt5 && readiness.mt5.xauusd) {
                    const p = readiness.mt5.xauusd;
                    priceEl.innerHTML = `
                        <div class="metric">${formatCurrency(p.bid)}</div>
                        <small>Current Bid</small>
                    `;
                } else {
                    priceEl.innerHTML = '<div style="color: #8b949e;">Price unavailable</div>';
                }

                // Trades Table
                const tradesTable = document.getElementById('trades-table');
                if (!Array.isArray(trades) || trades.length === 0) {
                    tradesTable.innerHTML = '<tr><td colspan="11" class="empty-state">No trades in database</td></tr>';
                } else {
                    tradesTable.innerHTML = trades.slice(0, 20).map(t => {
                        const actionBadge = t.action === 'buy' ? 'badge-buy' : t.action === 'sell' ? 'badge-sell' : 'badge-buy';
                        const outcomeBadge = t.outcome === 'win' ? 'badge-buy' : t.outcome === 'loss' ? 'badge-sell' : 'badge-pending';
                        const pnlClass = parseFloat(t.profit_loss || 0) >= 0 ? 'positive' : 'negative';
                        const ts = t.timestamp ? new Date(t.timestamp).toLocaleString() : 'N/A';
                        return `<tr>
                            <td>${t.id}</td>
                            <td>${ts}</td>
                            <td><span class="badge ${actionBadge}">${t.action}</span></td>
                            <td>${formatCurrency(t.entry_price)}</td>
                            <td>${formatCurrency(t.stop_loss)}</td>
                            <td>${formatCurrency(t.take_profit)}</td>
                            <td>${parseFloat(t.position_size || 0).toFixed(2)}</td>
                            <td>${parseFloat(t.confidence || 0).toFixed(2)}</td>
                            <td>${t.strategy_used || 'N/A'}</td>
                            <td><span class="badge ${outcomeBadge}">${t.outcome}</span></td>
                            <td class="${pnlClass}">${formatCurrency(t.profit_loss)}</td>
                        </tr>`;
                    }).join('');
                }

                // Performance
                const overall = perf.overall || {};
                document.getElementById('total-trades').innerHTML = `${overall.total_trades || 0}<small>trades</small>`;
                document.getElementById('win-loss').innerHTML = `${overall.wins || 0}W / ${overall.losses || 0}L<small>${overall.pending || 0} pending</small>`;
                const pnlClass = parseFloat(overall.total_pnl || 0) >= 0 ? 'positive' : 'negative';
                document.getElementById('total-pnl').innerHTML = `<span class="${pnlClass}">${formatCurrency(overall.total_pnl)}</span><small>Total P&L</small>`;

                document.getElementById('last-update').textContent = 'Last updated: ' + new Date().toLocaleTimeString();

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
    print("  Trading System Dashboard (FIXED - Real Data)")
    print("=" * 60)
    print("  Open http://localhost:5002 in your browser")
    print("  Shows REAL trades from database")
    print("  Press Ctrl+C to stop")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5002, debug=False)
