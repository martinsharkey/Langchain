"""
Experience Database — Persistent Storage of Trade Outcomes for Learning.

This module provides a lightweight SQLite-based database for storing
trade outcomes alongside the market conditions at the time of the trade.
It complements the vector store by providing:
1. Structured querying (by date, strategy, outcome)
2. Performance analytics per strategy
3. Trade journal with full context
4. Learning data for the meta-strategy agent

The experience DB is the "long-term memory" of the trading bot.
Every trade outcome is stored here and used to improve future decisions.
"""

import os
import json
import sqlite3
import logging
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger("learning.experience_db")


class ExperienceDatabase:
    """
    SQLite-backed experience database for trade learning.
    
    Stores every trade with full market context, enabling the bot to
    learn from experience and improve over time.
    
    Usage:
        db = ExperienceDatabase()
        
        # Record a trade
        db.record_trade(signal, indicators, outcome, profit_loss)
        
        # Get performance stats
        stats = db.get_performance_stats()
        
        # Get learning insights
        insights = db.get_learning_insights()
    """
    
    DB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data",
        "trading_experience.db",
    )
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the experience database.
        
        Args:
            db_path: Override the default database path.
        """
        self.db_path = db_path or self.DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                entry_price REAL,
                stop_loss REAL,
                take_profit REAL,
                position_size REAL,
                confidence REAL,
                strategy_used TEXT,
                strategy_combination TEXT,
                outcome TEXT,
                profit_loss REAL,
                exit_price REAL,
                exit_reason TEXT,
                market_regime TEXT,
                indicators_snapshot TEXT,
                rsi_value REAL,
                trend TEXT,
                atr_value REAL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                total_profit REAL DEFAULT 0.0,
                total_loss REAL DEFAULT 0.0,
                avg_confidence REAL DEFAULT 0.0,
                last_updated TEXT DEFAULT (datetime('now')),
                UNIQUE(strategy_name)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_conditions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                price REAL,
                regime TEXT,
                volatility TEXT,
                trend_strength REAL,
                pattern_id TEXT,
                trade_id INTEGER,
                FOREIGN KEY (trade_id) REFERENCES trades(id)
            )
        """)
        
        conn.commit()
        conn.close()
        
        # Lightweight migrations (add columns if missing)
        self._migrate()

        # #21: the currently-connected account; stats/writes scope to it when set.
        # {"login": int, "server": str, "trade_mode": "DEMO"|"REAL"|...}
        self.current_account = None

        logger.info(f"Experience database initialized at {self.db_path}")

    def set_current_account(self, login=None, server=None, trade_mode=None):
        """#21: set the connected account so writes stamp it and stats filter by it."""
        self.current_account = {"login": login, "server": server, "trade_mode": trade_mode}
        return self.current_account

    def _account_clause(self, alias: str = ""):
        """Return (sql_fragment, params) to scope a query to the current account.
        Empty when no account is set (back-compat). alias like 't.' if joined."""
        acct = getattr(self, "current_account", None)
        if not acct or acct.get("login") in (None, 0):
            return "", []
        col_login = f"{alias}account_login"
        col_server = f"{alias}account_server"
        return (f" AND {col_login}=? AND {col_server}=?",
                [acct["login"], acct.get("server")])

    def backfill_account(self, login: int, server: str, trade_mode: str = "DEMO") -> int:
        """One-shot: stamp existing NULL-account rows with a known account (#21)."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("UPDATE trades SET account_login=?, account_server=?, account_trade_mode=? "
                    "WHERE account_login IS NULL", (login, server, trade_mode))
        n = cur.rowcount
        conn.commit(); conn.close()
        logger.info(f"backfilled {n} trades to account {login}/{server}/{trade_mode}")
        return n

    def _migrate(self):
        """Add newer columns to existing DBs without dropping data."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(trades)")
        cols = {r[1] for r in cur.fetchall()}
        adds = []
        if "mgmt_variant" not in cols:
            adds.append("ALTER TABLE trades ADD COLUMN mgmt_variant TEXT")
        if "timeframe" not in cols:
            adds.append("ALTER TABLE trades ADD COLUMN timeframe TEXT")
        if "mt5_ticket" not in cols:
            adds.append("ALTER TABLE trades ADD COLUMN mt5_ticket INTEGER")
        # #21: per-account scoping so demo/live and different demo accounts never
        # blend. Backfilled to the current account or 'unknown_account' below.
        if "account_login" not in cols:
            adds.append("ALTER TABLE trades ADD COLUMN account_login INTEGER")
        if "account_server" not in cols:
            adds.append("ALTER TABLE trades ADD COLUMN account_server TEXT")
        if "account_trade_mode" not in cols:
            adds.append("ALTER TABLE trades ADD COLUMN account_trade_mode TEXT")
        for sql in adds:
            try:
                cur.execute(sql)
            except Exception as e:
                logger.debug(f"migrate skip: {e}")
        # index for account-scoped stats
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_account "
                        "ON trades(account_login, account_server, symbol, outcome)")
        except Exception as e:
            logger.debug(f"account index skip: {e}")
        conn.commit()
        conn.close()

    def get_symbol_profitability(self) -> dict:
        """
        Score each symbol by how quickly/reliably it makes money — so the bot can
        learn which symbol is 'easiest' to trade and lean into it (while still
        sampling others for 24/7 coverage).

        Returns {symbol: {trades, win_rate, net_pnl, avg_pnl, pnl_per_trade,
        avg_minutes, pnl_per_hour}} using real closed trades. pnl_per_hour is the
        'fastest return' proxy the trader asked for.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT symbol,
                    COUNT(*) trades,
                    SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) wins,
                    COALESCE(SUM(profit_loss),0) net,
                    COALESCE(AVG(profit_loss),0) avg_pnl
                FROM trades
                WHERE outcome IN ('win','loss','breakeven')
                GROUP BY symbol
            """).fetchall()
            conn.close()
            out = {}
            for r in rows:
                d = dict(r); t = d["trades"] or 0; w = d["wins"] or 0
                out[d["symbol"]] = {
                    "trades": t,
                    "win_rate": round(w / t * 100, 1) if t else 0.0,
                    "net_pnl": round(d["net"] or 0, 2),
                    "avg_pnl": round(d["avg_pnl"] or 0, 4),
                    "pnl_per_trade": round((d["net"] or 0) / t, 4) if t else 0.0,
                }
            return out
        except Exception as e:
            logger.warning(f"get_symbol_profitability failed: {e}")
            return {}

    def get_variant_performance(self, symbol: Optional[str] = None) -> dict:
        """
        Per-management-variant performance from real closed trades.

        Returns {symbol: {variant: {trades, wins, win_rate, net_pnl}}} — the data
        the TradeManager uses to bias variant selection toward what works.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            q = """
                SELECT symbol, mgmt_variant,
                    COUNT(*) trades,
                    SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) wins,
                    SUM(CASE WHEN outcome='loss' THEN 1 ELSE 0 END) losses,
                    COALESCE(SUM(profit_loss),0) net
                FROM trades
                WHERE outcome IN ('win','loss','breakeven') AND mgmt_variant IS NOT NULL
            """
            if symbol:
                q += " AND symbol = ?"
            q += " GROUP BY symbol, mgmt_variant"
            rows = conn.execute(q, (symbol,) if symbol else ()).fetchall()
            conn.close()
            out: dict = {}
            for r in rows:
                d = dict(r)
                sym = d["symbol"]; var = d["mgmt_variant"]
                t = d["trades"] or 0; w = d["wins"] or 0
                out.setdefault(sym, {})[var] = {
                    "trades": t, "wins": w, "losses": d["losses"] or 0,
                    "win_rate": round(w / t * 100, 1) if t else 0.0,
                    "net_pnl": round(d["net"] or 0, 2),
                }
            return out
        except Exception as e:
            logger.warning(f"get_variant_performance failed: {e}")
            return {}
    
    # ─── Trade Recording ─────────────────────────────────────
    
    def record_trade(
        self,
        signal: dict,
        indicators: dict,
        outcome: str = "pending",
        profit_loss: float = 0.0,
        exit_price: Optional[float] = None,
        exit_reason: Optional[str] = None,
        strategy_combination: Optional[str] = None,
        mgmt_variant: Optional[str] = None,
        timeframe: Optional[str] = None,
        mt5_ticket: Optional[int] = None,
    ):
        """
        Record a trade in the experience database.
        
        Args:
            signal: Dict with action, price, sl, tp, confidence, strategy_used.
            indicators: Dict of technical indicators at time of trade.
            outcome: "pending", "win", "loss", or "breakeven".
            profit_loss: P&L in dollars.
            exit_price: Price at which the trade was closed.
            exit_reason: Why the trade was closed (sl, tp, manual).
            strategy_combination: Comma-separated strategy names if ensemble.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp = datetime.now().isoformat()
        indicators_snapshot = json.dumps({
            k: v for k, v in indicators.items()
            if isinstance(v, (int, float, str, bool, list))
        }, default=str)
        
        cursor.execute("""
            INSERT INTO trades (
                timestamp, symbol, action, entry_price, stop_loss,
                take_profit, position_size, confidence, strategy_used,
                strategy_combination, outcome, profit_loss, exit_price,
                exit_reason, market_regime, indicators_snapshot,
                rsi_value, trend, atr_value, mgmt_variant, timeframe, mt5_ticket,
                account_login, account_server, account_trade_mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp,
            signal.get("symbol", "XAUUSD"),
            signal.get("action", "hold"),
            signal.get("price", 0),
            signal.get("stop_loss", 0),
            signal.get("take_profit", 0),
            signal.get("position_size", 0),
            signal.get("confidence", 0),
            signal.get("strategy_used", "unknown"),
            strategy_combination or "",
            outcome,
            profit_loss,
            exit_price,
            exit_reason,
            indicators.get("trend", "unknown"),
            indicators_snapshot,
            indicators.get("rsi"),
            indicators.get("trend"),
            indicators.get("atr"),
            mgmt_variant,
            timeframe,
            mt5_ticket,
            (self.current_account or {}).get("login"),
            (self.current_account or {}).get("server"),
            (self.current_account or {}).get("trade_mode"),
        ))
        
        trade_id = cursor.lastrowid
        
        # Update strategy performance
        strategy = signal.get("strategy_used", "unknown")
        cursor.execute("""
            INSERT INTO strategy_performance (strategy_name, total_trades, last_updated)
            VALUES (?, 0, datetime('now'))
            ON CONFLICT(strategy_name) DO UPDATE SET last_updated = datetime('now')
        """, (strategy,))
        
        if outcome != "pending":
            if outcome == "win":
                cursor.execute("""
                    UPDATE strategy_performance SET
                        total_trades = total_trades + 1,
                        winning_trades = winning_trades + 1,
                        total_profit = total_profit + ?,
                        avg_confidence = (avg_confidence * (total_trades - 1) + ?) / total_trades
                    WHERE strategy_name = ?
                """, (profit_loss, signal.get("confidence", 0), strategy))
            elif outcome == "loss":
                cursor.execute("""
                    UPDATE strategy_performance SET
                        total_trades = total_trades + 1,
                        losing_trades = losing_trades + 1,
                        total_loss = total_loss + abs(?),
                        avg_confidence = (avg_confidence * (total_trades - 1) + ?) / total_trades
                    WHERE strategy_name = ?
                """, (profit_loss, signal.get("confidence", 0), strategy))
        
        conn.commit()
        conn.close()
        
        logger.info(
            f"Recorded trade #{trade_id}: {signal.get('action')} "
            f"${signal.get('price', 0):.2f} → {outcome} "
            f"(${profit_loss:.2f}) using {strategy}"
        )
        
        return trade_id
    
    def update_trade_outcome(
        self,
        trade_id: int,
        outcome: str,
        profit_loss: float,
        exit_price: Optional[float] = None,
        exit_reason: Optional[str] = None,
    ):
        """
        Update a trade's outcome after it closes.
        
        Args:
            trade_id: The trade ID to update.
            outcome: "win", "loss", or "breakeven".
            profit_loss: Final P&L.
            exit_price: Exit price.
            exit_reason: Why the trade was closed.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE trades SET
                outcome = ?,
                profit_loss = ?,
                exit_price = ?,
                exit_reason = ?
            WHERE id = ?
        """, (outcome, profit_loss, exit_price, exit_reason, trade_id))
        
        # Also update strategy performance
        cursor.execute("SELECT strategy_used, confidence FROM trades WHERE id = ?", (trade_id,))
        row = cursor.fetchone()
        if row:
            strategy, confidence = row
            if outcome == "win":
                cursor.execute("""
                    UPDATE strategy_performance SET
                        avg_confidence = (avg_confidence * total_trades + ?) / (total_trades + 1),
                        total_trades = total_trades + 1,
                        winning_trades = winning_trades + 1,
                        total_profit = total_profit + ?
                    WHERE strategy_name = ?
                """, (confidence, profit_loss, strategy))
            elif outcome == "loss":
                cursor.execute("""
                    UPDATE strategy_performance SET
                        avg_confidence = (avg_confidence * total_trades + ?) / (total_trades + 1),
                        total_trades = total_trades + 1,
                        losing_trades = losing_trades + 1,
                        total_loss = total_loss + abs(?)
                    WHERE strategy_name = ?
                """, (confidence, profit_loss, strategy))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Updated trade #{trade_id}: {outcome} (${profit_loss:.2f})")

    def get_pending_trades(self) -> list[dict]:
        """All trades still marked pending (for DB-driven reconciliation)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            "SELECT id, symbol, action, entry_price, position_size, mt5_ticket, "
            "timestamp, created_at FROM trades WHERE outcome='pending'"
        ).fetchall()]
        conn.close()
        return rows

    def get_open_trade_id_by_ticket(self, ticket: int) -> Optional[int]:
        """
        Return the id of an existing NON-closed trade row for this MT5 ticket, if
        any. Prevents duplicate rows when a bot-opened position is later adopted
        (e.g. after a restart) — one real trade must map to exactly one DB row.
        """
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT id FROM trades WHERE mt5_ticket=? AND outcome='pending' "
            "ORDER BY id ASC LIMIT 1", (ticket,)
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def set_ticket(self, trade_id: int, ticket: int):
        """Attach an MT5 ticket to a trade row (so it can be reconciled later)."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE trades SET mt5_ticket=? WHERE id=?", (ticket, trade_id))
        conn.commit(); conn.close()

    def mark_unknown(self, trade_id: int, reason: str = "unresolved"):
        """
        Mark an old pending trade whose outcome can't be found as 'unknown' so it
        stops skewing win/loss stats (which filter on win/loss/breakeven).
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE trades SET outcome='unknown', exit_reason=? WHERE id=?",
                     (reason, trade_id))
        conn.commit(); conn.close()
        logger.info(f"Trade #{trade_id} marked unknown ({reason})")
    
    # ─── Querying ────────────────────────────────────────────
    
    def get_recent_trades(self, limit: int = 20) -> list[dict]:
        """Get the most recent trades."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM trades ORDER BY id DESC LIMIT ?
        """, (limit,))
        
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    
    def get_trades_by_strategy(self, strategy_name: str, limit: int = 50) -> list[dict]:
        """Get trades for a specific strategy."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM trades WHERE strategy_used = ? ORDER BY id DESC LIMIT ?
        """, (strategy_name, limit))
        
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    
    def get_trades_by_date(self, days: int = 7) -> list[dict]:
        """Get trades from the last N days."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        since = (datetime.now() - timedelta(days=days)).isoformat()
        cursor.execute("""
            SELECT * FROM trades WHERE timestamp > ? ORDER BY id DESC
        """, (since,))
        
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    
    # ─── Performance Analytics ───────────────────────────────
    
    def get_performance_stats(self) -> dict:
        """Get overall performance statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN outcome = 'pending' THEN 1 ELSE 0 END) as pending,
                COALESCE(SUM(profit_loss), 0) as total_pnl,
                AVG(CASE WHEN outcome IN ('win', 'loss') THEN confidence ELSE NULL END) as avg_confidence
            FROM trades
        """)
        
        row = cursor.fetchone()
        total = row[0] or 0
        wins = row[1] or 0
        losses = row[2] or 0
        pending = row[3] or 0
        total_pnl = row[4] or 0.0
        avg_confidence = row[5] or 0.0
        
        # Get best and worst trades
        cursor.execute("SELECT profit_loss, strategy_used, action FROM trades WHERE outcome IN ('win', 'loss') ORDER BY profit_loss DESC LIMIT 1")
        best_trade = cursor.fetchone()
        
        cursor.execute("SELECT profit_loss, strategy_used, action FROM trades WHERE outcome IN ('win', 'loss') ORDER BY profit_loss ASC LIMIT 1")
        worst_trade = cursor.fetchone()
        
        conn.close()
        
        closed_trades = wins + losses
        
        return {
            "total_trades": total,
            "closed_trades": closed_trades,
            "winning_trades": wins,
            "losing_trades": losses,
            "pending_trades": pending,
            "win_rate": round(wins / max(closed_trades, 1) * 100, 2),
            "total_profit_loss": round(total_pnl, 2),
            "average_confidence": round(avg_confidence, 3),
            "best_trade": {
                "profit": round(best_trade[0], 2) if best_trade else 0,
                "strategy": best_trade[1] if best_trade else "N/A",
                "action": best_trade[2] if best_trade else "N/A",
            } if best_trade else None,
            "worst_trade": {
                "profit": round(worst_trade[0], 2) if worst_trade else 0,
                "strategy": worst_trade[1] if worst_trade else "N/A",
                "action": worst_trade[2] if worst_trade else "N/A",
            } if worst_trade else None,
        }
    
    def get_strategy_performance_table(self) -> list[dict]:
        """
        Performance breakdown from the strategy_performance table (list form).
        Used by get_learning_insights. NOTE: the live weight-adaptation path uses
        get_strategy_performance() (dict form, reads the trades table) instead.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM strategy_performance ORDER BY total_trades DESC
        """)
        
        rows = []
        for row in cursor.fetchall():
            d = dict(row)
            d["win_rate"] = round(
                d["winning_trades"] / max(d["total_trades"], 1) * 100, 2
            )
            d["profit_factor"] = round(
                d["total_profit"] / max(abs(d["total_loss"]), 0.001), 2
            )
            rows.append(d)
        
        conn.close()
        return rows
    
    def get_learning_insights(self) -> list[str]:
        """
        Generate learning insights from trade history.
        
        These insights are used by the meta-strategy agent to
        improve decision-making over time.
        """
        insights = []
        stats = self.get_performance_stats()
        
        if stats["total_trades"] == 0:
            insights.append("No trade history yet — building experience database")
            return insights
        
        # Overall performance
        if stats["win_rate"] >= 60:
            insights.append(f"Overall win rate is strong: {stats['win_rate']:.1f}%")
        elif stats["win_rate"] >= 40:
            insights.append(f"Overall win rate is moderate: {stats['win_rate']:.1f}%")
        else:
            insights.append(f"Overall win rate needs improvement: {stats['win_rate']:.1f}%")
        
        insights.append(f"Total P&L: ${stats['total_profit_loss']:.2f} across {stats['closed_trades']} closed trades")
        
        # Strategy-specific insights
        strategy_perf = self.get_strategy_performance_table()
        for sp in strategy_perf[:3]:  # Top 3 strategies
            if sp["total_trades"] >= 3:
                insights.append(
                    f"Strategy '{sp['strategy_name']}': {sp['win_rate']:.1f}% win rate "
                    f"({sp['winning_trades']}W/{sp['losing_trades']}L, "
                    f"profit factor: {sp['profit_factor']:.2f})"
                )
        
        # Best/worst trade insights
        if stats.get("best_trade"):
            insights.append(
                f"Best trade: +${stats['best_trade']['profit']} using "
                f"{stats['best_trade']['strategy']} ({stats['best_trade']['action']})"
            )
        if stats.get("worst_trade"):
            insights.append(
                f"Worst trade: ${stats['worst_trade']['profit']} using "
                f"{stats['worst_trade']['strategy']} ({stats['worst_trade']['action']})"
            )
        
        return insights
    
    def get_trade_count(self) -> int:
        """Get total number of recorded trades."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM trades")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    # ← FIX #4: GET STRATEGY PERFORMANCE
    def get_strategy_performance(self, strategy_name: str = None) -> dict:
        """
        Get historical performance metrics for strategies.
        
        Args:
            strategy_name: If provided, get metrics for specific strategy.
                          If None, get metrics for all strategies.
        
        Returns:
            Dict with {strategy_name: {win_rate, avg_profit, loss_count, ...}}
        """
        try:
            query = """
                SELECT 
                    strategy_used,
                    COUNT(*) as trade_count,
                    SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as win_count,
                    SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as loss_count,
                    ROUND(100.0 * SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) 
                          / NULLIF(COUNT(*), 0), 2) as win_rate,
                    ROUND(AVG(profit_loss), 2) as avg_profit,
                    ROUND(SUM(profit_loss), 2) as total_profit,
                    ROUND(MAX(profit_loss), 2) as max_profit,
                    ROUND(MIN(profit_loss), 2) as max_loss
                FROM trades
                WHERE outcome IN ('win', 'loss')
            """
            
            if strategy_name:
                query += f" AND strategy_used = '{strategy_name}'"
            
            query += " GROUP BY strategy_used ORDER BY win_rate DESC"
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
            
            if not rows:
                return {}
            
            performance = {}
            for row in rows:
                strategy = row[0]
                performance[strategy] = {
                    "trade_count": row[1],
                    "win_count": row[2],
                    "loss_count": row[3],
                    "win_rate": row[4],  # Percentage
                    "avg_profit": row[5],
                    "total_profit": row[6],
                    "max_profit": row[7],
                    "max_loss": row[8],
                }
            
            logger.info(f"Retrieved performance for {len(performance)} strategies")
            return performance
        
        except Exception as e:
            logger.error(f"Error getting strategy performance: {e}")
            return {}
    
    def clear(self):
        """Clear all data (for testing)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM trades")
        cursor.execute("DELETE FROM strategy_performance")
        cursor.execute("DELETE FROM market_conditions")
        conn.commit()
        conn.close()
        logger.info("Cleared all experience data")
