"""
Execution Service Core Engine

Manages live trading execution and trade management.
"""

import json
import sqlite3
from typing import Dict, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class TradeStatus(Enum):
    """Trade status values."""
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class Trade:
    """Live trade record."""
    trade_id: str
    strategy_id: str
    symbol: str
    entry_price: float
    entry_time: str
    size: float
    direction: str  # long, short
    status: str  # pending, open, closed, cancelled, error
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@dataclass
class StrategyExecution:
    """Strategy execution state."""
    strategy_id: str
    symbol: str
    session: str
    status: str  # idle, active, error
    trades_open: int
    trades_closed: int
    total_pnl: float
    win_rate: float
    last_trade_time: Optional[str] = None
    error_message: Optional[str] = None


class ExecutionEngine:
    """Core execution engine for live trading."""
    
    def __init__(self, db_path: str = "./execution.db"):
        """
        Initialize Execution Engine.
        
        Args:
            db_path: SQLite database path
        """
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Trades table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    size REAL NOT NULL,
                    direction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    exit_price REAL,
                    exit_time TEXT,
                    pnl REAL,
                    pnl_percent REAL,
                    stop_loss REAL,
                    take_profit REAL
                )
            """)
            
            # Strategy execution state table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS executions (
                    strategy_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    session TEXT NOT NULL,
                    status TEXT NOT NULL,
                    trades_open INTEGER NOT NULL,
                    trades_closed INTEGER NOT NULL,
                    total_pnl REAL NOT NULL,
                    win_rate REAL NOT NULL,
                    last_trade_time TEXT,
                    error_message TEXT
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info(f"Execution database initialized: {self.db_path}")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
    
    async def open_trade(
        self,
        trade_id: str,
        strategy_id: str,
        symbol: str,
        entry_price: float,
        size: float,
        direction: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Trade:
        """
        Open a new trade.
        
        Args:
            trade_id: Unique trade identifier
            strategy_id: Strategy placing trade
            symbol: Trading symbol
            entry_price: Entry price
            size: Trade size
            direction: long or short
            stop_loss: Stop loss price
            take_profit: Take profit price
        
        Returns:
            Trade object
        """
        logger.info(
            f"Opening trade: {trade_id} ({symbol} {direction} {size} @ {entry_price})"
        )
        
        trade = Trade(
            trade_id=trade_id,
            strategy_id=strategy_id,
            symbol=symbol,
            entry_price=entry_price,
            entry_time=datetime.now(timezone.utc).isoformat(),
            size=size,
            direction=direction,
            status=TradeStatus.OPEN.value,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        
        try:
            self._save_trade(trade)
            logger.info(f"Trade opened: {trade_id}")
            return trade
        except Exception as e:
            logger.error(f"Trade opening error: {e}")
            trade.status = TradeStatus.ERROR.value
            return trade
    
    async def close_trade(
        self,
        trade_id: str,
        exit_price: float
    ) -> Optional[Trade]:
        """
        Close an open trade.
        
        Args:
            trade_id: Trade to close
            exit_price: Exit price
        
        Returns:
            Closed Trade or None
        """
        logger.info(f"Closing trade: {trade_id} @ {exit_price}")
        
        try:
            trade = self._load_trade(trade_id)
            if not trade:
                logger.warning(f"Trade not found: {trade_id}")
                return None
            
            trade.exit_price = exit_price
            trade.exit_time = datetime.now(timezone.utc).isoformat()
            trade.status = TradeStatus.CLOSED.value
            
            # Calculate P&L
            pnl = exit_price - trade.entry_price
            if trade.direction == "short":
                pnl = -pnl
            
            trade.pnl = pnl * trade.size
            trade.pnl_percent = (pnl / trade.entry_price) * 100
            
            self._save_trade(trade)
            logger.info(f"Trade closed: {trade_id} (PnL: {trade.pnl})")
            return trade
        except Exception as e:
            logger.error(f"Trade closing error: {e}")
            return None
    
    async def update_trade_stops(
        self,
        trade_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Optional[Trade]:
        """
        Update trade stop loss and take profit.
        
        Args:
            trade_id: Trade to update
            stop_loss: New stop loss price
            take_profit: New take profit price
        
        Returns:
            Updated Trade or None
        """
        try:
            trade = self._load_trade(trade_id)
            if not trade:
                return None
            
            if stop_loss is not None:
                trade.stop_loss = stop_loss
            if take_profit is not None:
                trade.take_profit = take_profit
            
            self._save_trade(trade)
            logger.info(f"Trade stops updated: {trade_id}")
            return trade
        except Exception as e:
            logger.error(f"Trade update error: {e}")
            return None
    
    async def get_open_trades(self, strategy_id: str) -> List[Trade]:
        """Get all open trades for a strategy."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM trades WHERE strategy_id = ? AND status = ?",
                (strategy_id, TradeStatus.OPEN.value)
            )
            rows = cursor.fetchall()
            conn.close()
            
            trades = []
            for row in rows:
                trades.append(Trade(*row))
            
            return trades
        except Exception as e:
            logger.error(f"Get open trades error: {e}")
            return []
    
    async def get_strategy_execution(self, strategy_id: str) -> Optional[StrategyExecution]:
        """Get strategy execution state."""
        return self._load_execution(strategy_id)
    
    async def update_strategy_execution(
        self,
        strategy_id: str,
        symbol: str,
        session: str
    ) -> Optional[StrategyExecution]:
        """
        Update strategy execution state (stats).
        
        Args:
            strategy_id: Strategy ID
            symbol: Symbol
            session: Session
        
        Returns:
            Updated StrategyExecution
        """
        try:
            # Get current trades
            open_trades = await self.get_open_trades(strategy_id)
            
            # Get closed trades for stats
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM trades WHERE strategy_id = ? AND status = ?",
                (strategy_id, TradeStatus.CLOSED.value)
            )
            closed_rows = cursor.fetchall()
            conn.close()
            
            closed_trades = [Trade(*row) for row in closed_rows]
            
            # Calculate stats
            total_pnl = sum(t.pnl for t in closed_trades if t.pnl)
            winning_trades = len([t for t in closed_trades if t.pnl and t.pnl > 0])
            total_closed = len(closed_trades)
            win_rate = winning_trades / total_closed if total_closed > 0 else 0
            
            execution = StrategyExecution(
                strategy_id=strategy_id,
                symbol=symbol,
                session=session,
                status="active",
                trades_open=len(open_trades),
                trades_closed=total_closed,
                total_pnl=total_pnl,
                win_rate=win_rate,
                last_trade_time=closed_trades[-1].exit_time if closed_trades else None
            )
            
            self._save_execution(execution)
            logger.info(f"Execution state updated: {strategy_id}")
            return execution
        except Exception as e:
            logger.error(f"Execution update error: {e}")
            return None
    
    def _save_trade(self, trade: Trade):
        """Save trade to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO trades
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade.trade_id,
            trade.strategy_id,
            trade.symbol,
            trade.entry_price,
            trade.entry_time,
            trade.size,
            trade.direction,
            trade.status,
            trade.exit_price,
            trade.exit_time,
            trade.pnl,
            trade.pnl_percent,
            trade.stop_loss,
            trade.take_profit
        ))
        
        conn.commit()
        conn.close()
    
    def _load_trade(self, trade_id: str) -> Optional[Trade]:
        """Load trade from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,))
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            return Trade(*row)
        except Exception as e:
            logger.error(f"Load trade error: {e}")
            return None
    
    def _save_execution(self, execution: StrategyExecution):
        """Save execution state to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO executions
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            execution.strategy_id,
            execution.symbol,
            execution.session,
            execution.status,
            execution.trades_open,
            execution.trades_closed,
            execution.total_pnl,
            execution.win_rate,
            execution.last_trade_time,
            execution.error_message
        ))
        
        conn.commit()
        conn.close()
    
    def _load_execution(self, strategy_id: str) -> Optional[StrategyExecution]:
        """Load execution state from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM executions WHERE strategy_id = ?", (strategy_id,))
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            return StrategyExecution(*row)
        except Exception as e:
            logger.error(f"Load execution error: {e}")
            return None


__all__ = ['ExecutionEngine', 'Trade', 'StrategyExecution', 'TradeStatus']
