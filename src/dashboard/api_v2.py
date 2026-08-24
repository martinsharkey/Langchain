"""
Dashboard API v2 - Analytics-focused REST API for strategy performance and optimization tracking.

This module provides endpoints for:
  1. Strategy analytics (backtest, live, vectorbt metrics)
  2. Backtest result analysis (walk-forward, equity curves)
  3. Optuna optimization tracking (trials, convergence)
  4. Vectorbt edge discovery (validated pockets, regime edges)
  5. Live account state

Uses existing data sources:
  - trading_experience.db (trades, strategy performance)
  - Optuna study databases (optimization history)
  - data/edge_weights.json (vectorbt discoveries)
  - bot_status.json (live account state)
  - data/strategy_config.json (strategy metadata)

No database modifications - read-only aggregation and analysis.
"""

import os
import json
import sqlite3
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from functools import lru_cache

_log = logging.getLogger("dashboard_api_v2")


# ── Type definitions ──

@dataclass
class WalkForwardWindow:
    """Single walk-forward validation window."""
    window: int
    profit_factor: float
    win_rate: float
    trades: int
    sharpe: float
    min_window_pf: float  # For robustness


@dataclass
class BacktestMetrics:
    """Backtest performance metrics."""
    profit_factor: float
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    avg_win: float
    avg_loss: float
    consecutive_wins: int
    consecutive_losses: int
    total_trades: int
    gross_profit: float
    gross_loss: float


@dataclass
class StrategyBacktest:
    """Backtest results for a strategy."""
    symbol: str
    strategy_name: str
    timeframe: str
    validated_at: str  # ISO8601
    walk_forward_windows: List[WalkForwardWindow]
    metrics: BacktestMetrics
    generalizes: bool  # All windows PF >= 1.0
    min_window_pf: float  # Robust threshold


@dataclass
class StrategyLive:
    """Live trading performance for a strategy."""
    symbol: str
    strategy_name: str
    total_trades: int
    win_count: int
    loss_count: int
    win_rate: float
    total_pnl: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    last_trade_time: Optional[str]  # ISO8601


@dataclass
class RegimeEdge:
    """Regime-specific edge weight for a strategy."""
    regime: str
    multiplier: float
    sample_size: int


@dataclass
class Strategy:
    """Complete strategy analytics."""
    symbol: str
    name: str
    enabled: bool
    rank: int
    
    # Backtest
    backtest: Optional[StrategyBacktest]
    
    # Live performance
    live: Optional[StrategyLive]
    
    # Vectorbt discovery
    validated: bool
    vectorbt_pf: Optional[float]
    regime_edges: List[RegimeEdge]
    
    # Optuna (if available)
    optuna_study: Optional[str]
    optuna_trials: int
    optuna_best_value: Optional[float]
    optuna_improvement_pct: Optional[float]
    last_optimized: Optional[str]


class DashboardAPIv2:
    """Analytics API backend."""
    
    def __init__(self, db_path: str, config_dir: str):
        """Initialize API.
        
        Args:
            db_path: Path to trading_experience.db
            config_dir: Path to data/ directory (edge_weights.json, strategy_config.json)
        """
        self.db_path = db_path
        self.config_dir = config_dir
        self._strategies_cache = {}
        self._edge_weights_cache = {}
        self._strategy_config_cache = {}
        self._load_configs()
    
    def _load_configs(self):
        """Load configuration files."""
        # Load edge_weights.json (vectorbt discoveries)
        edge_path = os.path.join(self.config_dir, "edge_weights.json")
        if os.path.exists(edge_path):
            try:
                with open(edge_path) as f:
                    self._edge_weights_cache = json.load(f)
                _log.info(f"Loaded edge_weights.json")
            except Exception as e:
                _log.warning(f"Failed to load edge_weights.json: {e}")
        
        # Load strategy_config.json (data-driven config)
        config_path = os.path.join(self.config_dir, "strategy_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    self._strategy_config_cache = json.load(f)
                _log.info(f"Loaded strategy_config.json with {len(self._strategy_config_cache.get('strategies', {}))} symbols")
            except Exception as e:
                _log.warning(f"Failed to load strategy_config.json: {e}")
    
    def list_strategies(self, symbol: Optional[str] = None) -> List[Strategy]:
        """List all strategies with analytics.
        
        Args:
            symbol: Optional filter by symbol
        
        Returns:
            List of Strategy objects with metrics.
        """
        strategies = []
        
        # Get all configured symbols
        symbols_config = self._strategy_config_cache.get("strategies", {})
        
        for sym, strat_list in symbols_config.items():
            if symbol and symbol.upper() != sym.upper():
                continue
            
            for strat_entry in strat_list:
                try:
                    strat = self._build_strategy_object(sym, strat_entry)
                    strategies.append(strat)
                except Exception as e:
                    _log.warning(f"Error building strategy {strat_entry.get('strategy')} for {sym}: {e}")
        
        # Sort by symbol, then rank
        strategies.sort(key=lambda s: (s.symbol, s.rank))
        return strategies
    
    def _build_strategy_object(self, symbol: str, config_entry: Dict) -> Strategy:
        """Build Strategy object from config and live data.
        
        Args:
            symbol: Symbol (e.g., "XAUUSD")
            config_entry: Strategy config entry from strategy_config.json
        
        Returns:
            Populated Strategy object.
        """
        strategy_name = config_entry.get("strategy")
        
        # Backtest metrics from config
        backtest_data = config_entry.get("performance", {})
        backtest = None
        if backtest_data.get("vectorbt_pf"):
            backtest = StrategyBacktest(
                symbol=symbol,
                strategy_name=strategy_name,
                timeframe="M15",  # Default from config
                validated_at=backtest_data.get("last_validated", ""),
                walk_forward_windows=[],  # Would need to expand from config
                metrics=BacktestMetrics(
                    profit_factor=backtest_data.get("vectorbt_pf", 0),
                    win_rate=backtest_data.get("vectorbt_wr", 0),
                    sharpe_ratio=backtest_data.get("vectorbt_sharpe", 0),
                    max_drawdown=0,  # Not in config
                    avg_win=0,
                    avg_loss=0,
                    consecutive_wins=0,
                    consecutive_losses=0,
                    total_trades=backtest_data.get("trades_tested", 0),
                    gross_profit=0,
                    gross_loss=0
                ),
                generalizes=True,  # Assumed if in config
                min_window_pf=backtest_data.get("vectorbt_pf", 0)
            )
        
        # Live performance from database
        live = self._get_live_performance(symbol, strategy_name)
        
        # Vectorbt metrics
        vectorbt_pf = backtest_data.get("vectorbt_pf")
        regime_edges = self._get_regime_edges(symbol, strategy_name)
        
        # Optuna tracking
        optuna_study = config_entry.get("optuna_study")
        optuna_trials = 0
        optuna_best_value = None
        optuna_improvement = None
        last_optimized = None
        
        if optuna_study:
            optuna_stats = self._get_optuna_stats(optuna_study)
            optuna_trials = optuna_stats.get("trial_count", 0)
            optuna_best_value = optuna_stats.get("best_value")
            optuna_improvement = optuna_stats.get("improvement_pct")
            last_optimized = optuna_stats.get("last_trial_time")
        
        return Strategy(
            symbol=symbol,
            name=strategy_name,
            enabled=config_entry.get("enabled", True),
            rank=config_entry.get("rank", 999),
            backtest=backtest,
            live=live,
            validated=backtest is not None and backtest.generalizes,
            vectorbt_pf=vectorbt_pf,
            regime_edges=regime_edges,
            optuna_study=optuna_study,
            optuna_trials=optuna_trials,
            optuna_best_value=optuna_best_value,
            optuna_improvement_pct=optuna_improvement,
            last_optimized=last_optimized
        )
    
    def _get_live_performance(self, symbol: str, strategy_name: str) -> Optional[StrategyLive]:
        """Get live performance metrics from trading_experience.db."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Query trades for this symbol/strategy
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN outcome = 'BREAKEVEN' THEN 1 ELSE 0 END) as breakeven,
                    AVG(CASE WHEN outcome = 'WIN' THEN profit_loss ELSE NULL END) as avg_win,
                    AVG(CASE WHEN outcome = 'LOSS' THEN ABS(profit_loss) ELSE NULL END) as avg_loss,
                    SUM(profit_loss) as total_pnl,
                    MAX(timestamp) as last_trade_time
                FROM trades
                WHERE symbol = ? AND strategy_used = ? AND outcome IN ('WIN', 'LOSS', 'BREAKEVEN')
            """, (symbol, strategy_name))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row or row['total_trades'] == 0:
                return None
            
            total_trades = row['total_trades']
            wins = row['wins'] or 0
            losses = row['losses'] or 0
            
            # Calculate profit factor
            gross_win = sum([row['avg_win'] * wins if row['avg_win'] else 0])
            gross_loss = sum([row['avg_loss'] * losses if row['avg_loss'] else 0])
            pf = gross_win / gross_loss if gross_loss > 0 else 0
            
            return StrategyLive(
                symbol=symbol,
                strategy_name=strategy_name,
                total_trades=total_trades,
                win_count=wins,
                loss_count=losses,
                win_rate=wins / total_trades if total_trades > 0 else 0,
                total_pnl=row['total_pnl'] or 0,
                profit_factor=pf,
                avg_win=row['avg_win'] or 0,
                avg_loss=row['avg_loss'] or 0,
                last_trade_time=row['last_trade_time']
            )
        
        except Exception as e:
            _log.warning(f"Error getting live performance for {symbol}/{strategy_name}: {e}")
            return None
    
    def _get_regime_edges(self, symbol: str, strategy_name: str) -> List[RegimeEdge]:
        """Extract regime edge weights from edge_weights.json."""
        edges = []
        
        try:
            regime_data = self._edge_weights_cache.get("regime_edge", {}).get(symbol, {})
            strat_regimes = regime_data.get(strategy_name, {})
            
            for regime, multiplier in strat_regimes.items():
                edges.append(RegimeEdge(
                    regime=regime,
                    multiplier=multiplier,
                    sample_size=0  # Not in current schema
                ))
            
            return sorted(edges, key=lambda e: -e.multiplier)
        
        except Exception as e:
            _log.warning(f"Error getting regime edges for {symbol}/{strategy_name}: {e}")
            return []
    
    def _get_optuna_stats(self, study_name: str) -> Dict[str, Any]:
        """Get Optuna study statistics.
        
        This is a placeholder - full implementation would query Optuna DB.
        """
        return {
            "trial_count": 0,
            "best_value": None,
            "improvement_pct": None,
            "last_trial_time": None
        }
    
    def get_backtest_results(self, symbol: Optional[str] = None, 
                           strategy: Optional[str] = None) -> List[Dict]:
        """Get backtest results with walk-forward validation.
        
        Args:
            symbol: Optional filter by symbol
            strategy: Optional filter by strategy name
        
        Returns:
            List of backtest result dictionaries.
        """
        results = []
        
        strategies = self.list_strategies(symbol)
        for strat in strategies:
            if strategy and strat.name != strategy:
                continue
            
            if strat.backtest:
                results.append({
                    "symbol": strat.symbol,
                    "strategy": strat.name,
                    "profit_factor": strat.backtest.metrics.profit_factor,
                    "win_rate": strat.backtest.metrics.win_rate,
                    "sharpe": strat.backtest.metrics.sharpe_ratio,
                    "trades": strat.backtest.metrics.total_trades,
                    "generalizes": strat.backtest.generalizes,
                    "min_window_pf": strat.backtest.min_window_pf,
                    "validated_at": strat.backtest.validated_at
                })
        
        return results
    
    def get_vectorbt_discovery(self) -> Dict[str, Any]:
        """Get vectorbt edge discovery results."""
        try:
            meta = self._edge_weights_cache.get("meta", {})
            symbols_data = meta.get("symbols", {})
            
            return {
                "swept_at": meta.get("swept_at"),
                "min_pf_threshold": meta.get("min_pf"),
                "timeframe": meta.get("timeframe"),
                "symbols": symbols_data
            }
        
        except Exception as e:
            _log.warning(f"Error getting vectorbt discovery: {e}")
            return {}
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """Get dashboard summary statistics."""
        strategies = self.list_strategies()
        
        # Calculate aggregates
        validated_count = sum(1 for s in strategies if s.validated)
        avg_pf = sum([s.vectorbt_pf or 0 for s in strategies]) / len(strategies) if strategies else 0
        
        # Best/worst strategy
        best_strat = max((s for s in strategies if s.vectorbt_pf), 
                        key=lambda s: s.vectorbt_pf, default=None)
        worst_strat = min((s for s in strategies if s.vectorbt_pf), 
                         key=lambda s: s.vectorbt_pf, default=None)
        
        return {
            "total_strategies": len(strategies),
            "validated_strategies": validated_count,
            "avg_profit_factor": round(avg_pf, 2),
            "best_strategy": {
                "name": best_strat.name if best_strat else None,
                "symbol": best_strat.symbol if best_strat else None,
                "pf": best_strat.vectorbt_pf if best_strat else None
            } if best_strat else None,
            "worst_strategy": {
                "name": worst_strat.name if worst_strat else None,
                "symbol": worst_strat.symbol if worst_strat else None,
                "pf": worst_strat.vectorbt_pf if worst_strat else None
            } if worst_strat else None
        }


# Singleton instance
_api_instance: Optional[DashboardAPIv2] = None


def initialize(db_path: str, config_dir: str) -> DashboardAPIv2:
    """Initialize the dashboard API."""
    global _api_instance
    if _api_instance is None:
        _api_instance = DashboardAPIv2(db_path, config_dir)
    return _api_instance


def get_api() -> DashboardAPIv2:
    """Get the dashboard API instance."""
    global _api_instance
    if _api_instance is None:
        raise RuntimeError("Dashboard API not initialized. Call initialize() first.")
    return _api_instance
