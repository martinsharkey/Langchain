"""
Trading Dashboard — REAL DATA ONLY.

Every value shown is sourced from one of:
  * Live MT5 account (balance, equity, positions, deal history, prices)
  * bot_status.json written by the ScalpEngine (mode, cycle, open trades,
    Algo Trading status, per-symbol prices, learning progress)
  * The experience DB (closed trades, per-strategy performance)
  * The knowledge DB (research topics/entries)

If a source is unavailable it is reported as "unavailable" — never faked.

Run standalone:  python -m flask --app dashboard.app run --port 5000
Or via app.py (imports `app` from here).
"""

import os
import json
import sqlite3
from datetime import datetime, timezone

from flask import Flask, jsonify, request

from src import config
from src.utils.logger import get_logger

logger = get_logger("dashboard")
app = Flask(__name__)

DATA_DIR = config.DATA_DIR
EXPERIENCE_DB = os.path.join(DATA_DIR, "trading_experience.db")
KNOWLEDGE_DB = os.path.join(DATA_DIR, "trading_knowledge.db")
STATUS_PATH = os.path.join(DATA_DIR, "bot_status.json")


# ─────────────────────────── helpers ───────────────────────────
def _query(db_path, sql, params=(), default=None):
    if not os.path.exists(db_path):
        return default if default is not None else []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.warning(f"query failed on {db_path}: {e}")
        return default if default is not None else []


def _read_status():
    if not os.path.exists(STATUS_PATH):
        return None
    try:
        with open(STATUS_PATH) as f:
            return json.load(f)
    except Exception:
        return None


# ─────────────────────────── API ───────────────────────────
@app.route("/api/status")
def api_status():
    """Engine + Algo Trading + account snapshot (from bot_status.json)."""
    status = _read_status()
    if not status:
        # fall back to live MT5 read so the dashboard still shows account/algo
        try:
            from src.mt5.broker_adapter import get_algo_status
            from src.mt5.account import get_account_info
            algo = get_algo_status()
            acct = get_account_info()
            return jsonify({
                "engine_running": False,
                "mode": config.TRADING_MODE,
                "note": "Engine not running — showing live MT5 only",
                "algo_trading": {
                    "can_trade": algo.can_trade,
                    "terminal_trade_allowed": algo.terminal_trade_allowed,
                    "account_trade_allowed": algo.account_trade_allowed,
                    "connected": algo.connected,
                    "reason": algo.reason,
                },
                "account": acct if isinstance(acct, dict) else {},
                "trades_opened": 0, "trades_closed": 0,
                "target_trades": config.SCALP_TARGET_TRADES,
                "open_positions": [], "symbols": [],
            })
        except Exception as e:
            return jsonify({"error": str(e), "engine_running": False})
    status["engine_running"] = status.get("running", False)
    return jsonify(status)


@app.route("/api/trading_state")
def api_trading_state():
    """
    The REAL reason trading is or isn't happening (#30) — so the dashboard never
    shows a misleading 'algo blocked' when the true cause is a governor pause,
    risk halt, closed market, or simply no signal. Precedence: algo/connection
    -> risk halt -> per-symbol (market closed / governor paused / eligible).
    """
    status = _read_status() or {}
    algo = status.get("algo_trading", {})
    risk = status.get("risk", {})
    gov = status.get("symbol_governance", {})
    symbols = status.get("symbols", [])

    if not algo.get("can_trade", True):
        state = {"state": "ALGO_DISABLED",
                 "reason": f"MT5 algo trading not permitted: {algo.get('reason','unknown')}"}
    elif risk.get("halted"):
        state = {"state": "RISK_HALTED", "reason": risk.get("reason", "risk manager halted trading")}
    else:
        per_symbol = {}
        eligible = 0
        for s in symbols:
            base = s.get("base")
            g = (gov.get(base) or {})
            if not s.get("open", True):
                per_symbol[base] = "market_closed"
            elif g.get("status") in ("paused", "failed"):
                per_symbol[base] = f"governor_{g.get('status')} (advisory)" \
                    if not config.__dict__.get("GOVERNOR_PAUSE_BLOCKS_ENTRIES", False) else f"governor_{g.get('status')}"
                eligible += 1  # advisory -> still eligible
            else:
                per_symbol[base] = "eligible"
                eligible += 1
        state = {"state": "TRADING" if eligible else "IDLE",
                 "reason": ("eligible symbols present; entries occur when a signal clears the confidence gate"
                            if eligible else "no eligible symbols right now (markets closed)"),
                 "per_symbol": per_symbol}
    state["algo_can_trade"] = algo.get("can_trade")
    state["mode"] = status.get("mode")
    return jsonify(state)


@app.route("/api/control", methods=["GET", "POST"])
def api_control():
    """
    Dashboard control channel (#19). GET returns the current control request;
    POST writes one to data/control.json which the engine reads each cycle and
    applies (trading mode, pause/resume, scalping toggle, per-symbol disable).
    File-based so it survives restarts and works if dashboard/engine are separated.
    """
    import json as _json
    path = os.path.join(config.DATA_DIR, "control.json")
    if request.method == "GET":
        try:
            if os.path.exists(path):
                with open(path) as f:
                    return jsonify(_json.load(f))
        except Exception as e:
            return jsonify({"error": str(e)})
        return jsonify({})
    try:
        req = request.get_json(force=True) or {}
    except Exception:
        req = {}
    allowed = {}
    if str(req.get("mode", "")).upper() in ("OBSERVE", "PAPER", "LIVE_MICRO", "LIVE"):
        allowed["mode"] = str(req["mode"]).upper()
    if "paused" in req:
        allowed["paused"] = bool(req["paused"])
    if "scalping" in req:
        allowed["scalping"] = bool(req["scalping"])
    if isinstance(req.get("disabled_symbols"), list):
        allowed["disabled_symbols"] = [str(s).upper() for s in req["disabled_symbols"]]
    if not allowed:
        return jsonify({"error": "no valid control fields",
                        "accepts": ["mode", "paused", "scalping", "disabled_symbols"]}), 400
    import time as _t
    allowed["requested_at"] = _t.time()
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            _json.dump(allowed, f, indent=2)
        os.replace(tmp, path)
        logger.info(f"dashboard control request: {allowed}")
        return jsonify({"ok": True, "applied_request": allowed,
                        "note": "engine applies this on its next cycle"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/trades/history")
def api_trades_history():
    """REAL executed deals from the live MT5 account history."""
    try:
        from src.mt5.connector import get_connector
        from src.mt5.account import get_history
        c = get_connector()
        if not c.is_connected():
            c.initialize()
        deals = get_history(deals=100)
        if isinstance(deals, dict):
            return jsonify({"error": deals.get("error", "unavailable"), "deals": []})
        rows = []
        for d in deals or []:
            ts = d.get("time")
            try:
                ts = datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                ts = str(ts)
            profit = float(d.get("profit") or 0)
            comm = float(d.get("commission") or 0)
            swap = float(d.get("swap") or 0)
            rows.append({
                "ticket": d.get("ticket"), "time": ts, "symbol": d.get("symbol"),
                "type": d.get("type"), "volume": float(d.get("volume") or 0),
                "price": float(d.get("price") or 0),
                "net": round(profit + comm + swap, 2),
                "comment": d.get("comment", ""),
            })
        rows.reverse()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e), "deals": []})


@app.route("/api/trades/bot")
def api_trades_bot():
    """Trades the BOT placed and recorded (experience DB), with real outcomes."""
    rows = _query(EXPERIENCE_DB, """
        SELECT id, timestamp, symbol, action, entry_price, stop_loss, take_profit,
               position_size, confidence, strategy_used, strategy_combination,
               outcome, profit_loss, exit_price, exit_reason
        FROM trades ORDER BY id DESC LIMIT 100
    """)
    return jsonify(rows)


@app.route("/api/strategies")
def api_strategies():
    """Per-strategy performance from real closed trades + which symbols each traded."""
    perf = _query(EXPERIENCE_DB, """
        SELECT strategy_name, total_trades, winning_trades, losing_trades,
               total_profit, total_loss, avg_confidence
        FROM strategy_performance ORDER BY total_trades DESC
    """)
    for s in perf:
        tt = s.get("total_trades") or 0
        wins = s.get("winning_trades") or 0
        s["win_rate"] = round(wins / tt * 100, 1) if tt else 0.0
        s["net_profit"] = round((s.get("total_profit") or 0) - (s.get("total_loss") or 0), 2)

    # which symbols each strategy has traded + best strategy per symbol (real closed trades)
    by_symbol = _query(EXPERIENCE_DB, """
        SELECT symbol, strategy_used,
               COUNT(*) as trades,
               SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) as losses,
               COALESCE(SUM(profit_loss),0) as pnl
        FROM trades
        WHERE outcome IN ('win','loss','breakeven')
        GROUP BY symbol, strategy_used
        ORDER BY symbol, pnl DESC
    """)
    return jsonify({"performance": perf, "by_symbol": by_symbol})


@app.route("/api/learning")
def api_learning():
    """Learning progress: closed-trade counts, symbols learned, knowledge base."""
    counts = _query(EXPERIENCE_DB, """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN outcome='breakeven' THEN 1 ELSE 0 END) as breakeven,
            SUM(CASE WHEN outcome='pending' THEN 1 ELSE 0 END) as pending,
            COALESCE(SUM(profit_loss),0) as net_pnl
        FROM trades
    """, default=[{}])
    c = counts[0] if counts else {}
    closed = (c.get("wins") or 0) + (c.get("losses") or 0) + (c.get("breakeven") or 0)

    symbols = _query(EXPERIENCE_DB, """
        SELECT symbol, COUNT(*) as trades,
               SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) as losses,
               COALESCE(SUM(profit_loss),0) as pnl
        FROM trades GROUP BY symbol ORDER BY trades DESC
    """)

    kb_entries = _query(KNOWLEDGE_DB, "SELECT COUNT(*) as n FROM knowledge_entries", default=[{"n": 0}])
    kb_topics = _query(KNOWLEDGE_DB, "SELECT name as topic_name, entry_count as n FROM topics ORDER BY entry_count DESC",
                       default=[])
    pending_q = _query(KNOWLEDGE_DB, "SELECT COUNT(*) as n FROM pending_questions", default=[{"n": 0}])

    target = config.SCALP_TARGET_TRADES
    return jsonify({
        "closed_trades": closed,
        "target_trades": target,
        "progress_pct": round(min(closed / target * 100, 100), 1) if target else 0,
        "wins": c.get("wins") or 0,
        "losses": c.get("losses") or 0,
        "breakeven": c.get("breakeven") or 0,
        "pending": c.get("pending") or 0,
        "net_pnl": round(c.get("net_pnl") or 0, 2),
        "win_rate": round((c.get("wins") or 0) / closed * 100, 1) if closed else 0.0,
        "symbols_learned": symbols,
        "knowledge_entries": kb_entries[0]["n"] if kb_entries else 0,
        "knowledge_topics": kb_topics,
        "pending_questions": pending_q[0]["n"] if pending_q else 0,
    })


@app.route("/api/research")
def api_research():
    """Research status + topics (knowledge base is the persistent research store)."""
    topics = _query(KNOWLEDGE_DB, """
        SELECT name as topic_name, description, entry_count
        FROM topics ORDER BY entry_count DESC LIMIT 25
    """, default=[])
    recent = _query(KNOWLEDGE_DB, """
        SELECT question as title, topic as category, created_at
        FROM knowledge_entries ORDER BY id DESC LIMIT 15
    """, default=[])
    # News/research availability (honest, granular):
    # RSS (Yahoo/CoinDesk/Investing) needs NO key; central banks + geopolitical
    # scrape public sites; only the NewsAPI aggregator needs NEWSAPI_KEY.
    newsapi = bool(os.getenv("NEWSAPI_KEY"))
    rss_items = []
    rss_ok = False
    # Cache RSS with a TTL so an auto-refreshing dashboard tab does NOT hammer the
    # live feeds (and flood the logs) on every ~4s poll. Refetch at most every 5 min.
    import time as _t
    global _RSS_CACHE
    now = _t.time()
    cached = globals().get("_RSS_CACHE")
    if cached and (now - cached["ts"] < 300):
        rss_items = cached["items"]
        rss_ok = bool(rss_items)
    else:
        try:
            from src.data_sources.rss_news import RSSNewsSource
            rss = RSSNewsSource()
            rss_items = rss.fetch()[:15]
            rss_ok = bool(rss_items)
            globals()["_RSS_CACHE"] = {"ts": now, "items": rss_items}
        except Exception as e:
            logger.debug(f"rss news skip: {e}")

    if rss_ok or newsapi:
        news_status = "available (live headlines)"
    else:
        news_status = "unavailable"
    return jsonify({
        "news_status": news_status,
        "newsapi_configured": newsapi,
        "rss_available": rss_ok,
        "headlines": rss_items,
        "topics": topics,
        "recent_entries": recent,
    })


@app.route("/api/readiness")
def api_readiness():
    """Trading readiness score based on REAL closed trades + connection + learning."""
    learning = api_learning().get_json()
    status = _read_status() or {}
    algo = status.get("algo_trading", {})

    closed = learning["closed_trades"]
    win_rate = learning["win_rate"]
    target = learning["target_trades"]

    scores, details = [], {}

    # connection + algo (20)
    conn_ok = algo.get("can_trade", False)
    conn_score = 20 if conn_ok else 0
    scores.append(conn_score)
    # accurate label: distinguish "algo disabled in MT5" from "connected/OK". The
    # real not-trading reasons (governor pause, closed market, no signal) live in
    # /api/trading_state, so we don't mislabel those as 'algo blocked' here.
    algo_label = "Algo trading enabled" if conn_ok else "Algo trading NOT permitted by MT5"
    details["connection"] = {"label": algo_label, "score": conn_score, "max": 20,
                             "value": algo.get("reason", "unknown")}

    # sample size (40) — driving toward target
    sample_score = min(closed / target * 40, 40) if target else 0
    scores.append(sample_score)
    details["sample"] = {"label": f"Closed trades ({closed}/{target})", "score": round(sample_score, 1),
                         "max": 40, "value": closed}

    # win rate (40) — only meaningful with >=20 closed
    wr_score = min(win_rate / 60 * 40, 40) if closed >= 20 else 0
    scores.append(wr_score)
    details["win_rate"] = {"label": "Win rate (needs 20+ trades)", "score": round(wr_score, 1),
                           "max": 40, "value": f"{win_rate}%"}

    total = round(sum(scores), 1)
    if total >= 80:
        status_txt, color = "READY", "#3fb950"
    elif total >= 50:
        status_txt, color = "LEARNING", "#d29922"
    else:
        status_txt, color = "TRAINING", "#58a6ff"

    return jsonify({"score": total, "status": status_txt, "color": color,
                    "details": details,
                    "summary": f"{total}% — {status_txt} ({closed}/{target} trades, {win_rate}% win)"})


@app.route("/api/equity")
def api_equity():
    """Cumulative P&L curve from real closed trades (for the hero chart)."""
    rows = _query(EXPERIENCE_DB, """
        SELECT id, timestamp, profit_loss, outcome
        FROM trades
        WHERE outcome IN ('win','loss','breakeven')
        ORDER BY id ASC
    """)
    curve, cum = [], 0.0
    for r in rows:
        cum += float(r.get("profit_loss") or 0)
        curve.append({"t": (r.get("timestamp") or "")[:19].replace("T", " "),
                      "cum": round(cum, 2)})
    return jsonify(curve)


@app.route("/api/cryptorti")
def api_cryptorti():
    """Live CryptoRTI whale signals (from the signal client's state file)."""
    path = os.path.join(DATA_DIR, "cryptorti_signals.json")
    if not os.path.exists(path):
        return jsonify({"connected": False, "count": 0, "signals": []})
    try:
        with open(path) as f:
            data = json.load(f)
        # compact view for the dashboard
        rows = []
        for s in data.get("signals", []):
            wt = s.get("whale_transfer") or {}
            rows.append({
                "signal_id": s.get("signal_id"),
                "stage": s.get("stage"),
                "status": s.get("signal_status"),
                "exchange": wt.get("exchange"),
                "amount_btc": wt.get("amount_btc"),
                "amount_usd": wt.get("amount_usd"),
                "detected_at": s.get("detected_at"),
            })
        # stale if older than 2 minutes
        return jsonify({
            "connected": data.get("connected", False),
            "updated_at": data.get("updated_at"),
            "count": len(rows),
            "signals": rows[-15:],
        })
    except Exception as e:
        return jsonify({"connected": False, "error": str(e), "signals": []})


@app.route("/")
def index():
    tpl = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
    with open(tpl, encoding="utf-8") as f:
        return f.read()


@app.after_request
def _no_cache(resp):
    """Prevent the browser from serving a stale cached dashboard/endpoints."""
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp
