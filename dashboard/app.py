"""
Trading Bot Dashboard — Production-ready web interface.

Real-time monitoring with self-trading readiness meter.
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
KB_PATH = os.path.join(DATA_DIR, "trading_knowledge.db")
STATUS_PATH = os.path.join(DATA_DIR, "bot_status.json")


# ═══════════════════════════════════════════════════════════════════
# Database helpers
# ═══════════════════════════════════════════════════════════════════

def get_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def safe_query(path: str, query: str, params=(), default=None):
    try:
        if not os.path.exists(path):
            return default
        conn = get_db(path)
        cur = conn.cursor()
        cur.execute(query, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.warning(f"DB query failed: {e}")
        return default


# ═══════════════════════════════════════════════════════════════════
# Readiness calculation
# ═══════════════════════════════════════════════════════════════════

def calculate_readiness() -> dict:
    """
    Calculate how ready the bot is for autonomous trading.
    
    Returns a score from 0-100 and detailed breakdown.
    """
    scores = []
    details = {}
    
    # 1. Historical trades (max 30 points)
    trades = safe_query(DB_PATH, "SELECT COUNT(*) as cnt FROM trades", default=[{"cnt": 0}])
    trade_count = trades[0]["cnt"] if trades else 0
    trade_score = min(trade_count / 30 * 30, 30)
    scores.append(trade_score)
    details["trades"] = {
        "score": round(trade_score, 1),
        "max": 30,
        "value": trade_count,
        "label": "Historical Trades",
        "threshold": "Need 30 closed trades for statistical significance",
    }
    
    # 2. Win rate (max 25 points)
    perf = safe_query(DB_PATH, """
        SELECT 
            SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) as losses
        FROM trades WHERE outcome IN ('win', 'loss')
    """, default=[{"wins": 0, "losses": 0}])
    closed = (perf[0]["wins"] or 0) + (perf[0]["losses"] or 0)
    win_rate = (perf[0]["wins"] / closed * 100) if closed > 0 else 0
    win_score = min(win_rate / 60 * 25, 25) if closed >= 5 else 0
    scores.append(win_score)
    details["win_rate"] = {
        "score": round(win_score, 1),
        "max": 25,
        "value": round(win_rate, 1),
        "label": "Win Rate",
        "threshold": "Need 60% win rate on 5+ closed trades",
    }
    
    # 3. Strategy diversity (max 15 points)
    strategies = safe_query(DB_PATH, """
        SELECT strategy_name, total_trades, winning_trades, losing_trades
        FROM strategy_performance
    """, default=[])
    active_strategies = sum(1 for s in strategies if s["total_trades"] > 0)
    strat_score = min(active_strategies / 5 * 15, 15)
    scores.append(strat_score)
    details["strategies"] = {
        "score": round(strat_score, 1),
        "max": 15,
        "value": active_strategies,
        "label": "Active Strategies",
        "threshold": "Need 5+ strategies with trade history",
    }
    
    # 4. Knowledge base (max 15 points)
    kb = safe_query(KB_PATH, "SELECT COUNT(*) as cnt FROM knowledge_entries", default=[{"cnt": 0}])
    kb_count = kb[0]["cnt"] if kb else 0
    kb_score = min(kb_count / 20 * 15, 15)
    scores.append(kb_score)
    details["knowledge"] = {
        "score": round(kb_score, 1),
        "max": 15,
        "value": kb_count,
        "label": "Knowledge Entries",
        "threshold": "Need 20+ learned knowledge entries",
    }
    
    # 5. Pattern store (max 10 points)
    patterns = safe_query(KB_PATH, "SELECT COUNT(*) as cnt FROM knowledge_entries", default=[{"cnt": 0}])
    pattern_count = patterns[0]["cnt"] if patterns else 0
    pattern_score = min(pattern_count / 10 * 10, 10)
    scores.append(pattern_score)
    details["patterns"] = {
        "score": round(pattern_score, 1),
        "max": 10,
        "value": pattern_count,
        "label": "Pattern History",
        "threshold": "Need 10+ stored patterns",
    }
    
    # 6. Account stability (max 5 points)
    try:
        from src.mt5.connector import get_connector
        c = get_connector()
        if c.is_connected() and not c.in_simulation_mode:
            stability_score = 5
        else:
            stability_score = 0
    except Exception:
        stability_score = 0
    scores.append(stability_score)
    details["connection"] = {
        "score": stability_score,
        "max": 5,
        "value": "Connected" if stability_score > 0 else "Disconnected",
        "label": "MT5 Connection",
        "threshold": "Must be connected to live/demo account",
    }
    
    total = sum(scores)
    percentage = min(total, 100)
    
    # Determine status
    if percentage >= 90:
        status = "READY"
        color = "#3fb950"
    elif percentage >= 70:
        status = "ALMOST READY"
        color = "#d29922"
    elif percentage >= 50:
        status = "LEARNING"
        color = "#58a6ff"
    else:
        status = "TRAINING"
        color = "#f85149"
    
    return {
        "score": round(percentage, 1),
        "status": status,
        "color": color,
        "details": details,
        "summary": f"{percentage:.0f}% ready for autonomous trading",
    }


# ═══════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/readiness")
def api_readiness():
    readiness = calculate_readiness()
    
    # Add live MT5 proof
    try:
        from src.mt5.connector import get_connector
        from src.mt5.account import get_account_info
        from src.mt5.data import get_last_price
        
        c = get_connector()
        c.initialize()
        mt5_connected = c.is_connected() and not c.in_simulation_mode
        
        if mt5_connected:
            acc = get_account_info()
            last = get_last_price("XAUUSD")
            readiness["mt5"] = {
                "connected": True,
                "simulation": False,
                "account": acc,
                "xauusd_last": last,
            }
            # ← FIX: Pass account currency for dashboard
            readiness["account_currency"] = acc.get("currency", "USD") if acc else "USD"
        else:
            readiness["mt5"] = {
                "connected": False,
                "simulation": True,
                "account": None,
                "xauusd_last": None,
            }
            readiness["account_currency"] = "USD"  # Fallback
    except Exception as e:
        readiness["mt5"] = {
            "connected": False,
            "simulation": True,
            "error": str(e),
        }
    
    return jsonify(readiness)


@app.route("/api/trades")
def api_trades():
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
    return jsonify(rows)


@app.route("/api/performance")
def api_performance():
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
    
    strategies = safe_query(DB_PATH, """
        SELECT strategy_name, total_trades, winning_trades, losing_trades,
               total_profit, total_loss, avg_confidence
        FROM strategy_performance
        ORDER BY total_trades DESC
    """, default=[])
    
    for s in strategies:
        s["win_rate"] = round(s["winning_trades"] / max(s["total_trades"], 1) * 100, 2)
        s["profit_factor"] = round(s["total_profit"] / max(abs(s["total_loss"]), 0.001), 2)
    
    return jsonify({
        "overall": overall[0] if overall else {},
        "strategies": strategies,
    })


@app.route("/api/knowledge")
def api_knowledge():
    entries = safe_query(KB_PATH, "SELECT COUNT(*) as cnt FROM knowledge_entries", default=[{"cnt": 0}])
    topics = safe_query(KB_PATH, "SELECT COUNT(DISTINCT topic) as cnt FROM knowledge_entries", default=[{"cnt": 0}])
    pending = safe_query(KB_PATH, "SELECT COUNT(*) as cnt FROM pending_questions WHERE status='pending'", default=[{"cnt": 0}])
    
    topic_breakdown = safe_query(KB_PATH, """
        SELECT topic, COUNT(*) as cnt, AVG(confidence) as avg_conf
        FROM knowledge_entries
        GROUP BY topic
        ORDER BY cnt DESC
    """, default=[])
    
    recent = safe_query(KB_PATH, """
        SELECT id, question, answer, topic, subtopic, confidence, created_at
        FROM knowledge_entries
        ORDER BY id DESC
        LIMIT 20
    """, default=[])
    
    return jsonify({
        "total_entries": entries[0]["cnt"] if entries else 0,
        "total_topics": topics[0]["cnt"] if topics else 0,
        "pending_questions": pending[0]["cnt"] if pending else 0,
        "topics": topic_breakdown,
        "recent_entries": recent,
    })


@app.route("/api/patterns")
def api_patterns():
    try:
        from src.learning.vector_store import PatternVectorStore
        store = PatternVectorStore()
        return jsonify({"pattern_count": store.pattern_count, "status": "ok"})
    except Exception as e:
        return jsonify({"pattern_count": 0, "status": "error", "error": str(e)})


@app.route("/api/cycles")
def api_cycles():
    rows = safe_query(DB_PATH, """
        SELECT timestamp, signal_action, signal_confidence, trade_executed, profit_loss
        FROM trades
        ORDER BY id ASC
    """, default=[])
    return jsonify(rows)


# ═══════════════════════════════════════════════════════════════════
# HTML Template
# ═══════════════════════════════════════════════════════════════════

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Bot Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            background: #0d1117; 
            color: #c9d1d9; 
            padding: 20px;
            min-height: 100vh;
        }
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
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); 
            gap: 15px; 
            margin-bottom: 20px; 
        }
        .card { 
            background: #161b22; 
            border: 1px solid #30363d; 
            border-radius: 8px; 
            padding: 15px; 
        }
        .card h3 { 
            color: #58a6ff; 
            font-size: 13px; 
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .metric { 
            font-size: 28px; 
            font-weight: bold; 
            color: #c9d1d9; 
        }
        .metric small { 
            font-size: 13px; 
            color: #8b949e; 
            display: block;
            margin-top: 4px;
        }
        .positive { color: #3fb950; }
        .negative { color: #f85149; }
        .neutral { color: #d29922; }
        
        /* Readiness Meter */
        .readiness-container {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 25px;
        }
        .readiness-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        .readiness-status {
            font-size: 18px;
            font-weight: bold;
            padding: 6px 16px;
            border-radius: 20px;
            background: #21262d;
        }
        .readiness-meter {
            width: 100%;
            height: 32px;
            background: #21262d;
            border-radius: 16px;
            overflow: hidden;
            position: relative;
            margin-bottom: 15px;
        }
        .readiness-fill {
            height: 100%;
            border-radius: 16px;
            transition: width 0.5s ease, background 0.5s ease;
            position: relative;
        }
        .readiness-fill::after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
            animation: shimmer 2s infinite;
        }
        @keyframes shimmer {
            0% { transform: translateX(-100%); }
            100% { transform: translateX(100%); }
        }
        .readiness-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px;
        }
        .readiness-item {
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 10px;
        }
        .readiness-item-label {
            font-size: 11px;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }
        .readiness-item-value {
            font-size: 16px;
            font-weight: bold;
            color: #c9d1d9;
        }
        .readiness-item-threshold {
            font-size: 11px;
            color: #8b949e;
            margin-top: 2px;
        }
        
        /* Connection Badge */
        .connection-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 10px;
        }
        .connection-badge.live {
            background: #23863633;
            color: #3fb950;
            border: 1px solid #238636;
        }
        .connection-badge.sim {
            background: #d2992233;
            color: #d29922;
            border: 1px solid #d29922;
        }
        .connection-badge.offline {
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
        
        /* Tables */
        table { 
            width: 100%; 
            border-collapse: collapse; 
            font-size: 13px; 
        }
        th, td { 
            text-align: left; 
            padding: 8px; 
            border-bottom: 1px solid #30363d; 
        }
        th { 
            color: #8b949e; 
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        tr:hover { background: #1c2128; }
        
        .badge { 
            display: inline-block; 
            padding: 3px 10px; 
            border-radius: 12px; 
            font-size: 11px; 
            font-weight: 600; 
        }
        .badge-buy { background: #238636; color: white; }
        .badge-sell { background: #da3633; color: white; }
        .badge-hold { background: #6e7681; color: white; }
        .badge-win { background: #238636; color: white; }
        .badge-loss { background: #da3633; color: white; }
        .badge-pending { background: #d29922; color: white; }
        
        .refresh { 
            color: #8b949e; 
            font-size: 12px; 
            margin-top: 10px;
        }
        a { 
            color: #58a6ff; 
            text-decoration: none; 
        }
        a:hover { 
            text-decoration: underline; 
        }
        .section { 
            margin-bottom: 30px; 
        }
        
        .empty-state {
            text-align: center;
            padding: 30px;
            color: #8b949e;
            font-style: italic;
        }
    </style>
</head>
<body>
    <h1>Trading Bot Dashboard</h1>
    <p class="subtitle">Real-time monitoring and self-trading readiness</p>

    <!-- Readiness Meter -->
    <div class="readiness-container">
        <div class="readiness-header">
            <div>
                <div style="font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px;">Self-Trading Readiness</div>
                <div id="readiness-summary" style="font-size: 20px; font-weight: bold;">Loading...</div>
            </div>
            <div id="readiness-badge" class="readiness-status">CALCULATING</div>
        </div>
        <div class="readiness-meter">
            <div id="readiness-fill" class="readiness-fill" style="width: 0%; background: #58a6ff;"></div>
        </div>
        <div id="readiness-details" class="readiness-details">Loading...</div>
    </div>

    <!-- Connection & Account -->
    <div class="grid">
        <div class="card">
            <h3>MT5 Connection</h3>
            <div id="connection">Loading...</div>
        </div>
        <div class="card">
            <h3>Account</h3>
            <div id="account">Loading...</div>
        </div>
        <div class="card">
            <h3>Performance</h3>
            <div id="performance">Loading...</div>
        </div>
        <div class="card">
            <h3>Learning</h3>
            <div id="learning">Loading...</div>
        </div>
    </div>

    <!-- Recent Trades -->
    <div class="section">
        <h2>Recent Trades</h2>
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
                        <th>Size</th>
                        <th>Conf</th>
                        <th>Strategy</th>
                        <th>Outcome</th>
                        <th>P&L</th>
                    </tr>
                </thead>
                <tbody id="trades-table">Loading...</tbody>
            </table>
        </div>
    </div>

    <!-- Strategy Performance -->
    <div class="section">
        <h2>Strategy Performance</h2>
        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th>Strategy</th>
                        <th>Trades</th>
                        <th>Win Rate</th>
                        <th>Profit Factor</th>
                        <th>Avg Confidence</th>
                    </tr>
                </thead>
                <tbody id="strategy-table">Loading...</tbody>
            </table>
        </div>
    </div>

    <!-- Knowledge Base -->
    <div class="section">
        <h2>Knowledge Base</h2>
        <div class="card">
            <table>
                <thead>
                    <tr>
                        <th>Topic</th>
                        <th>Entries</th>
                        <th>Avg Confidence</th>
                    </tr>
                </thead>
                <tbody id="knowledge-topics">Loading...</tbody>
            </table>
        </div>
    </div>

    <script>
        // ← FIX: Dynamic currency symbol
        let accountCurrency = 'USD';
        const currencySymbols = {
            'USD': '$',
            'GBP': '£',
            'EUR': '€',
            'JPY': '¥',
            'CHF': 'CHF',
            'AUD': 'A$',
            'CAD': 'C$',
            'NZD': 'NZ$',
            'ZAR': 'R',
        };
        
        function getCurrencySymbol(currency) {
            return currencySymbols[currency] || '$';
        }
        
        function formatCurrency(val, currency = null) {
            if (val === null || val === undefined) return 'N/A';
            const symbol = getCurrencySymbol(currency || accountCurrency);
            return symbol + parseFloat(val).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }
        
        function formatPercent(val) {
            if (val === null || val === undefined) return 'N/A';
            return parseFloat(val).toFixed(1) + '%';
        }

        async function loadData() {
            try {
                const [readinessRes, tradesRes, perfRes, knowRes, patternsRes] = await Promise.all([
                    fetch('/api/readiness'),
                    fetch('/api/trades'),
                    fetch('/api/performance'),
                    fetch('/api/knowledge'),
                    fetch('/api/patterns'),
                ]);

                const readiness = await readinessRes.json();
                const perf = await perfRes.json();
                const know = await knowRes.json();
                const trades = await tradesRes.json();
                
                // ← FIX: Set account currency from API
                if (readiness.account_currency) {
                    accountCurrency = readiness.account_currency;
                }

                // Readiness Meter
                const score = readiness.score || 0;
                const status = readiness.status || 'UNKNOWN';
                const color = readiness.color || '#58a6ff';
                
                document.getElementById('readiness-fill').style.width = score + '%';
                document.getElementById('readiness-fill').style.background = color;
                document.getElementById('readiness-summary').textContent = readiness.summary || 'Calculating...';
                document.getElementById('readiness-summary').style.color = color;
                
                const badge = document.getElementById('readiness-badge');
                badge.textContent = status;
                badge.style.background = color + '33';
                badge.style.color = color;
                badge.style.border = '1px solid ' + color;
                
                // Readiness details
                const detailsEl = document.getElementById('readiness-details');
                if (readiness.details) {
                    detailsEl.innerHTML = Object.entries(readiness.details).map(([key, d]) => {
                        const scoreColor = d.score >= d.max * 0.8 ? '#3fb950' : 
                                          d.score >= d.max * 0.5 ? '#d29922' : '#f85149';
                        return `
                            <div class="readiness-item">
                                <div class="readiness-item-label">${d.label}</div>
                                <div class="readiness-item-value" style="color: ${scoreColor}">
                                    ${d.score.toFixed(1)} / ${d.max}
                                </div>
                                <div class="readiness-item-threshold">${d.threshold}</div>
                            </div>
                        `;
                    }).join('');
                }

                // Connection
                const connEl = document.getElementById('connection');
                if (readiness.mt5 && readiness.mt5.connected) {
                    connEl.innerHTML = `
                        <div class="connection-badge live">
                            <div class="pulse"></div>
                            LIVE CONNECTION
                        </div>
                        <div style="font-size: 13px; margin-top: 8px;">
                            <div><strong>${readiness.mt5.account?.name || 'N/A'}</strong></div>
                            <div style="color: #8b949e;">Server: ${readiness.mt5.account?.server || 'N/A'}</div>
                            <div style="margin-top: 5px;">
                                <span style="color: #8b949e;">XAUUSD:</span>
                                <span style="color: #3fb950; font-weight: bold;">
                                    ${readiness.mt5.xauusd_last ? formatCurrency(readiness.mt5.xauusd_last.bid) : 'N/A'}
                                </span>
                            </div>
                        </div>
                    `;
                } else if (readiness.mt5 && readiness.mt5.simulation) {
                    connEl.innerHTML = `
                        <div class="connection-badge sim">
                            <div class="pulse"></div>
                            SIMULATION MODE
                        </div>
                        <div style="font-size: 13px; color: #8b949e; margin-top: 8px;">
                            Not connected to live MT5
                        </div>
                    `;
                } else {
                    connEl.innerHTML = `
                        <div class="connection-badge offline">
                            <div class="pulse"></div>
                            OFFLINE
                        </div>
                        <div style="font-size: 13px; color: #8b949e; margin-top: 8px;">
                            ${readiness.mt5?.error || 'Connection error'}
                        </div>
                    `;
                }

                // Account
                const accountEl = document.getElementById('account');
                if (readiness.mt5 && readiness.mt5.account) {
                    const acc = readiness.mt5.account;
                    accountEl.innerHTML = `
                        <div style="font-size: 24px; font-weight: bold; color: #c9d1d9;">
                            ${formatCurrency(acc.balance)}
                        </div>
                        <small style="color: #8b949e;">Balance</small><br>
                        <div style="margin-top: 8px;">
                            <span style="color: #8b949e;">Equity:</span>
                            <span style="color: #c9d1d9; font-weight: bold;">${formatCurrency(acc.equity)}</span>
                        </div>
                        <div>
                            <span style="color: #8b949e;">Leverage:</span>
                            <span style="color: #c9d1d9;">1:${acc.leverage || 'N/A'}</span>
                        </div>
                        <div>
                            <span style="color: #8b949e;">Currency:</span>
                            <span style="color: #c9d1d9;">${acc.currency || 'N/A'}</span>
                        </div>
                    `;
                } else {
                    accountEl.innerHTML = '<div style="color: #8b949e;">No account data</div>';
                }

                // Performance
                const perfEl = document.getElementById('performance');
                const o = perf.overall || {};
                const pnl = parseFloat(o.total_pnl || 0);
                const pnlClass = pnl >= 0 ? 'positive' : 'negative';
                perfEl.innerHTML = `
                    <div class="metric ${pnlClass}">${formatCurrency(pnl)}</div>
                    <small>Total P&L</small><br>
                    <small>${o.total_trades || 0} trades | ${o.wins || 0}W / ${o.losses || 0}L | ${o.pending || 0} pending</small>
                `;

                // Learning
                const learnEl = document.getElementById('learning');
                learnEl.innerHTML = `
                    <div class="metric">${know.total_entries || 0}</div>
                    <small>Knowledge entries</small><br>
                    <small>${know.total_topics || 0} topics | ${know.pending_questions || 0} pending</small>
                `;

                // Trades table
                const tradesTable = document.getElementById('trades-table');
                if (trades.length === 0) {
                    tradesTable.innerHTML = '<tr><td colspan="11" class="empty-state">No trades recorded yet</td></tr>';
                } else {
                    tradesTable.innerHTML = trades.slice(0, 20).map(t => {
                        const actionBadge = t.action === 'buy' ? 'badge-buy' : t.action === 'sell' ? 'badge-sell' : 'badge-hold';
                        const outcomeBadge = t.outcome === 'win' ? 'badge-win' : t.outcome === 'loss' ? 'badge-loss' : 'badge-pending';
                        const pnlClass = parseFloat(t.profit_loss || 0) >= 0 ? 'positive' : 'negative';
                        const ts = t.timestamp ? new Date(t.timestamp).toLocaleString() : 'N/A';
                        return `<tr>
                            <td>${t.id}</td>
                            <td>${ts}</td>
                            <td><span class="badge ${actionBadge}">${t.action || 'N/A'}</span></td>
                            <td>${formatCurrency(t.entry_price)}</td>
                            <td>${formatCurrency(t.stop_loss)}</td>
                            <td>${formatCurrency(t.take_profit)}</td>
                            <td>${parseFloat(t.position_size || 0).toFixed(2)}</td>
                            <td>${parseFloat(t.confidence || 0).toFixed(2)}</td>
                            <td>${t.strategy_used || 'N/A'}</td>
                            <td><span class="badge ${outcomeBadge}">${t.outcome || 'pending'}</span></td>
                            <td class="${pnlClass}">${formatCurrency(t.profit_loss)}</td>
                        </tr>`;
                    }).join('');
                }

                // Strategy table
                const stratTable = document.getElementById('strategy-table');
                if (!perf.strategies || perf.strategies.length === 0) {
                    stratTable.innerHTML = '<tr><td colspan="5" class="empty-state">No strategy data yet</td></tr>';
                } else {
                    stratTable.innerHTML = perf.strategies.map(s => {
                        const wrClass = s.win_rate >= 50 ? 'positive' : 'negative';
                        return `<tr>
                            <td>${s.strategy_name}</td>
                            <td>${s.total_trades}</td>
                            <td class="${wrClass}">${s.win_rate}%</td>
                            <td>${s.profit_factor}</td>
                            <td>${parseFloat(s.avg_confidence || 0).toFixed(2)}</td>
                        </tr>`;
                    }).join('');
                }

                // Knowledge topics
                const knowTopics = document.getElementById('knowledge-topics');
                if (!know.topics || know.topics.length === 0) {
                    knowTopics.innerHTML = '<tr><td colspan="3" class="empty-state">No knowledge yet</td></tr>';
                } else {
                    knowTopics.innerHTML = know.topics.map(t => {
                        return `<tr>
                            <td>${t.topic}</td>
                            <td>${t.cnt}</td>
                            <td>${parseFloat(t.avg_conf || 0).toFixed(2)}</td>
                        </tr>`;
                    }).join('');
                }

            } catch (e) {
                console.error('Failed to load dashboard data:', e);
            }
        }

        loadData();
        setInterval(loadData, 5000);
    </script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("  Trading Bot Dashboard")
    print("=" * 60)
    print("  Open http://localhost:5000 in your browser")
    print("  Press Ctrl+C to stop")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False)
