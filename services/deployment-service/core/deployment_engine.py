"""
Deployment Service Core Engine

Manages live trading state, snapshots, and strategy deployment to live trading.
"""

import json
import sqlite3
from typing import Dict, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class StrategyState:
    """Live strategy state."""
    strategy_id: str
    strategy_name: str
    symbol: str
    session: str
    timeframe: str
    status: str  # active, paused, stopped, error
    floor_value: float
    deployed_at: str
    last_updated: str
    metrics: Dict
    error_message: Optional[str] = None


@dataclass
class StateSnapshot:
    """Point-in-time snapshot of strategy state."""
    snapshot_id: str
    strategy_id: str
    timestamp: str
    state_data: Dict
    reason: str  # pre_optimization, pre_tuning, backup, etc.


class DeploymentEngine:
    """Core deployment engine for live trading state management."""
    
    def __init__(self, db_path: str = "./deployment.db"):
        """
        Initialize Deployment Engine.
        
        Args:
            db_path: SQLite database path for state persistence
        """
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Strategies table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategies (
                    strategy_id TEXT PRIMARY KEY,
                    strategy_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    session TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    status TEXT NOT NULL,
                    floor_value REAL NOT NULL,
                    deployed_at TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    metrics TEXT NOT NULL,
                    error_message TEXT
                )
            """)
            
            # State snapshots table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    state_data TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    FOREIGN KEY (strategy_id) REFERENCES strategies(strategy_id)
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info(f"Deployment database initialized: {self.db_path}")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
    
    async def deploy_strategy(
        self,
        strategy_id: str,
        strategy_name: str,
        symbol: str,
        session: str,
        timeframe: str,
        floor_value: float,
        initial_metrics: Dict
    ) -> StrategyState:
        """
        Deploy a validated strategy to live trading.
        
        Args:
            strategy_id: Unique strategy identifier
            strategy_name: Name of strategy
            symbol: Trading symbol
            session: Trading session
            timeframe: Timeframe
            floor_value: Optimized floor value
            initial_metrics: Initial backtest metrics
        
        Returns:
            StrategyState for deployed strategy
        """
        logger.info(f"Deploying strategy: {strategy_id} ({symbol}/{session}/{timeframe})")
        
        state = StrategyState(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            symbol=symbol,
            session=session,
            timeframe=timeframe,
            status="active",
            floor_value=floor_value,
            deployed_at=datetime.now(timezone.utc).isoformat(),
            last_updated=datetime.now(timezone.utc).isoformat(),
            metrics=initial_metrics
        )
        
        try:
            self._save_strategy_state(state)
            logger.info(f"Strategy deployed: {strategy_id}")
            return state
        except Exception as e:
            logger.error(f"Deployment error: {e}")
            state.status = "error"
            state.error_message = str(e)
            return state
    
    async def snapshot_strategy(
        self,
        strategy_id: str,
        reason: str
    ) -> Optional[StateSnapshot]:
        """
        Create point-in-time snapshot of strategy state.
        
        Args:
            strategy_id: Strategy to snapshot
            reason: Snapshot reason (pre_optimization, pre_tuning, etc.)
        
        Returns:
            StateSnapshot or None if failed
        """
        logger.info(f"Snapshotting strategy: {strategy_id} (reason: {reason})")
        
        try:
            state = self._load_strategy_state(strategy_id)
            if not state:
                logger.warning(f"Strategy not found: {strategy_id}")
                return None
            
            snapshot = StateSnapshot(
                snapshot_id=f"snap_{strategy_id}_{int(datetime.now(timezone.utc).timestamp())}",
                strategy_id=strategy_id,
                timestamp=datetime.now(timezone.utc).isoformat(),
                state_data=asdict(state),
                reason=reason
            )
            
            self._save_snapshot(snapshot)
            logger.info(f"Snapshot created: {snapshot.snapshot_id}")
            return snapshot
        except Exception as e:
            logger.error(f"Snapshot error: {e}")
            return None
    
    async def restore_strategy(
        self,
        snapshot_id: str
    ) -> Optional[StrategyState]:
        """
        Restore strategy state from snapshot.
        
        Args:
            snapshot_id: Snapshot to restore from
        
        Returns:
            Restored StrategyState or None if failed
        """
        logger.info(f"Restoring strategy from snapshot: {snapshot_id}")
        
        try:
            snapshot = self._load_snapshot(snapshot_id)
            if not snapshot:
                logger.warning(f"Snapshot not found: {snapshot_id}")
                return None
            
            state_dict = snapshot.state_data
            state = StrategyState(**state_dict)
            state.last_updated = datetime.now(timezone.utc).isoformat()
            
            self._save_strategy_state(state)
            logger.info(f"Strategy restored from snapshot: {snapshot_id}")
            return state
        except Exception as e:
            logger.error(f"Restore error: {e}")
            return None
    
    async def update_strategy_metrics(
        self,
        strategy_id: str,
        new_metrics: Dict
    ) -> Optional[StrategyState]:
        """
        Update strategy live trading metrics.
        
        Args:
            strategy_id: Strategy to update
            new_metrics: Updated metrics
        
        Returns:
            Updated StrategyState or None
        """
        logger.info(f"Updating metrics for strategy: {strategy_id}")
        
        try:
            state = self._load_strategy_state(strategy_id)
            if not state:
                return None
            
            state.metrics.update(new_metrics)
            state.last_updated = datetime.now(timezone.utc).isoformat()
            
            self._save_strategy_state(state)
            logger.info(f"Metrics updated for strategy: {strategy_id}")
            return state
        except Exception as e:
            logger.error(f"Metrics update error: {e}")
            return None
    
    async def pause_strategy(self, strategy_id: str) -> Optional[StrategyState]:
        """Pause live strategy."""
        return await self._change_strategy_status(strategy_id, "paused")
    
    async def resume_strategy(self, strategy_id: str) -> Optional[StrategyState]:
        """Resume paused strategy."""
        return await self._change_strategy_status(strategy_id, "active")
    
    async def stop_strategy(self, strategy_id: str) -> Optional[StrategyState]:
        """Stop live strategy."""
        return await self._change_strategy_status(strategy_id, "stopped")
    
    async def _change_strategy_status(
        self,
        strategy_id: str,
        new_status: str
    ) -> Optional[StrategyState]:
        """Change strategy status."""
        try:
            state = self._load_strategy_state(strategy_id)
            if not state:
                return None
            
            old_status = state.status
            state.status = new_status
            state.last_updated = datetime.now(timezone.utc).isoformat()
            
            self._save_strategy_state(state)
            logger.info(f"Strategy status changed: {strategy_id} {old_status} -> {new_status}")
            return state
        except Exception as e:
            logger.error(f"Status change error: {e}")
            return None
    
    async def get_strategy_state(self, strategy_id: str) -> Optional[StrategyState]:
        """Get current strategy state."""
        return self._load_strategy_state(strategy_id)
    
    async def list_strategies(self, symbol: Optional[str] = None) -> List[StrategyState]:
        """List all deployed strategies."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if symbol:
                cursor.execute("SELECT * FROM strategies WHERE symbol = ?", (symbol,))
            else:
                cursor.execute("SELECT * FROM strategies")
            
            rows = cursor.fetchall()
            conn.close()
            
            states = []
            for row in rows:
                state = StrategyState(*row)
                state.metrics = json.loads(state.metrics)
                states.append(state)
            
            return states
        except Exception as e:
            logger.error(f"List strategies error: {e}")
            return []
    
    def _save_strategy_state(self, state: StrategyState):
        """Save strategy state to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO strategies
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            state.strategy_id,
            state.strategy_name,
            state.symbol,
            state.session,
            state.timeframe,
            state.status,
            state.floor_value,
            state.deployed_at,
            state.last_updated,
            json.dumps(state.metrics),
            state.error_message
        ))
        
        conn.commit()
        conn.close()
    
    def _load_strategy_state(self, strategy_id: str) -> Optional[StrategyState]:
        """Load strategy state from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM strategies WHERE strategy_id = ?", (strategy_id,))
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            state = StrategyState(*row)
            state.metrics = json.loads(state.metrics)
            return state
        except Exception as e:
            logger.error(f"Load state error: {e}")
            return None
    
    def _save_snapshot(self, snapshot: StateSnapshot):
        """Save snapshot to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO snapshots
            VALUES (?, ?, ?, ?, ?)
        """, (
            snapshot.snapshot_id,
            snapshot.strategy_id,
            snapshot.timestamp,
            json.dumps(snapshot.state_data),
            snapshot.reason
        ))
        
        conn.commit()
        conn.close()
    
    def _load_snapshot(self, snapshot_id: str) -> Optional[StateSnapshot]:
        """Load snapshot from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM snapshots WHERE snapshot_id = ?", (snapshot_id,))
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            snapshot = StateSnapshot(*row)
            snapshot.state_data = json.loads(snapshot.state_data)
            return snapshot
        except Exception as e:
            logger.error(f"Load snapshot error: {e}")
            return None


__all__ = ['DeploymentEngine', 'StrategyState', 'StateSnapshot']
