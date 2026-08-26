"""
Phase 1: Strategy Discovery via Vectorbt Backtesting

Discovers best-performing strategies for each session using historical data.
Tests all registered strategies and ranks by Profit Factor.

Status: IMPLEMENTATION (Day 4)
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone
import logging

from src.phase_integration import (
    DiscoveredStrategy,
    Phase1Output,
    validate_phase1_to_phase2_flow
)
from src.strategy_interface import STRATEGY_REGISTRY, BaseStrategy, StrategySignal
from src.session_selection import get_sessions_for_weekday

logger = logging.getLogger(__name__)


class BacktestResult:
    """Single backtest result for a strategy on a session."""
    
    def __init__(
        self,
        strategy_name: str,
        strategy_type: str,
        session: str,
        timeframe: str,
        indicator_params: Dict,
        pf: float,
        wr: float,
        sharpe: float,
        trades: int,
        entry_prices: List[float],
        exit_prices: List[float],
        trade_results: List[float]
    ):
        self.strategy_name = strategy_name
        self.strategy_type = strategy_type
        self.session = session
        self.timeframe = timeframe
        self.indicator_params = indicator_params
        self.pf = pf
        self.wr = wr
        self.sharpe = sharpe
        self.trades = trades
        self.entry_prices = entry_prices
        self.exit_prices = exit_prices
        self.trade_results = trade_results
    
    def to_discovered_strategy(self) -> DiscoveredStrategy:
        """Convert to DiscoveredStrategy dataclass."""
        return DiscoveredStrategy(
            session=self.session,
            timeframe=self.timeframe,
            strategy_name=self.strategy_name,
            strategy_type=self.strategy_type,
            indicator_params=self.indicator_params,
            baseline_pf=self.pf,
            baseline_wr=self.wr,
            baseline_sharpe=self.sharpe,
            baseline_trades=self.trades
        )


class Phase1Discovery:
    """Phase 1: Strategy discovery via vectorbt-style backtesting."""
    
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        ohlcv_data: pd.DataFrame,
        entry_floors: Dict[str, float],
        min_trades: int = 10
    ):
        """
        Initialize Phase 1 discovery.
        
        Args:
            symbol: Trading symbol (e.g., "XAUUSD")
            timeframe: Timeframe (e.g., "M15", "H1")
            ohlcv_data: Historical OHLCV data with datetime index
            entry_floors: Per-session entry strength floors
            min_trades: Minimum trades required for valid backtest
        """
        self.symbol = symbol
        self.timeframe = timeframe
        self.ohlcv_data = ohlcv_data
        self.entry_floors = entry_floors
        self.min_trades = min_trades
        
        self._validate_inputs()
    
    def _validate_inputs(self):
        """Validate inputs."""
        if len(self.ohlcv_data) < 100:
            raise ValueError(f"Insufficient OHLCV data: {len(self.ohlcv_data)} < 100")
        
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing = [col for col in required_cols if col not in self.ohlcv_data.columns]
        if missing:
            raise ValueError(f"OHLCV missing columns: {missing}")
    
    def discover_for_session(
        self,
        session: str,
        max_strategies: Optional[int] = None
    ) -> List[DiscoveredStrategy]:
        """
        Discover strategies for a single session.
        
        Args:
            session: Session name (e.g., "asian", "london")
            max_strategies: Maximum strategies to test (None = all)
        
        Returns:
            List of DiscoveredStrategy ranked by PF (highest first)
        """
        logger.info(f"Phase 1: Discovering strategies for {self.symbol}/{session}/{self.timeframe}")
        
        # Get list of strategies to test
        strategy_names = STRATEGY_REGISTRY.list_strategies()
        if max_strategies:
            strategy_names = strategy_names[:max_strategies]
        
        results = []
        
        for strategy_name in strategy_names:
            try:
                strategy = STRATEGY_REGISTRY.get_strategy(strategy_name)
                
                # Run backtest
                backtest_result = self._backtest_strategy(
                    strategy,
                    session,
                    self.entry_floors.get(session, 0.0)
                )
                
                if backtest_result is None:
                    logger.warning(f"  {strategy_name}: backtest failed")
                    continue
                
                # Filter by minimum trades
                if backtest_result.trades < self.min_trades:
                    logger.warning(
                        f"  {strategy_name}: only {backtest_result.trades} trades < {self.min_trades}"
                    )
                    continue
                
                # Filter by profitability (PF >= 1.0)
                if backtest_result.pf < 1.0:
                    logger.warning(f"  {strategy_name}: PF {backtest_result.pf:.2f} < 1.0 (not profitable)")
                    continue
                
                discovered = backtest_result.to_discovered_strategy()
                results.append(discovered)
                
                logger.info(
                    f"  {strategy_name}: PF={backtest_result.pf:.2f}, "
                    f"WR={backtest_result.wr:.1%}, trades={backtest_result.trades}"
                )
            
            except Exception as e:
                logger.error(f"  {strategy_name}: {e}")
                continue
        
        # Sort by PF (highest first)
        results.sort(key=lambda x: x.baseline_pf, reverse=True)
        
        logger.info(f"Phase 1: Found {len(results)} profitable strategies for {session}")
        
        return results
    
    def discover_all_sessions(self) -> Dict[str, List[DiscoveredStrategy]]:
        """
        Discover strategies for all active sessions on a weekday.
        
        Returns:
            Dict mapping session name to list of discovered strategies
        """
        # Get sessions for this weekday (Monday-Friday)
        # Use weekday 0 (Monday) as default
        weekday = 0
        sessions = get_sessions_for_weekday(weekday)
        
        results = {}
        for session in sessions:
            discovered = self.discover_for_session(session)
            if discovered:
                results[session] = discovered
        
        return results
    
    def _backtest_strategy(
        self,
        strategy: BaseStrategy,
        session: str,
        entry_floor: float
    ) -> Optional[BacktestResult]:
        """
        Run backtest for a strategy on a session.
        
        Args:
            strategy: BaseStrategy instance
            session: Session name
            entry_floor: Entry strength floor (0.0-1.0)
        
        Returns:
            BacktestResult if successful, None if backtest failed
        """
        try:
            # Get default params for strategy
            default_params = self._get_default_params(strategy.strategy_name)
            
            # Calculate indicators
            indicators = strategy.calculate_indicators(self.ohlcv_data, default_params)
            
            # Generate signals and run backtest
            trades = []
            entry_prices = []
            exit_prices = []
            trade_results = []
            
            in_trade = False
            entry_price = 0
            entry_idx = 0
            
            for idx in range(len(self.ohlcv_data)):
                close_price = self.ohlcv_data['close'].iloc[idx]
                
                if not in_trade:
                    # Look for entry signal
                    try:
                        signal = strategy.generate_signal(
                            indicators,
                            {"min_strength": entry_floor},
                            idx
                        )
                    except Exception:
                        continue
                    
                    if signal.should_enter and signal.entry_type == "long":
                        in_trade = True
                        entry_price = close_price
                        entry_idx = idx
                        entry_prices.append(entry_price)
                
                else:
                    # In trade - look for exit (simple: next bar or loss)
                    # For discovery, use simple exit: 2% TP or 1% SL
                    exit_price = close_price
                    
                    tp_price = entry_price * 1.02
                    sl_price = entry_price * 0.99
                    
                    if exit_price >= tp_price or exit_price <= sl_price:
                        in_trade = False
                        exit_prices.append(exit_price)
                        
                        pnl = exit_price - entry_price
                        trade_results.append(pnl)
                        
                        trades.append({
                            'entry_idx': entry_idx,
                            'entry_price': entry_price,
                            'exit_idx': idx,
                            'exit_price': exit_price,
                            'pnl': pnl
                        })
            
            # Calculate metrics
            if len(trades) == 0:
                return None
            
            pnl_list = np.array([t['pnl'] for t in trades])
            
            # Profit Factor
            winning_trades = pnl_list[pnl_list > 0]
            losing_trades = pnl_list[pnl_list < 0]
            
            if len(losing_trades) == 0:
                pf = float('inf') if len(winning_trades) > 0 else 1.0
            else:
                pf = np.sum(winning_trades) / np.abs(np.sum(losing_trades))
            
            # Win Rate
            wins = len(winning_trades)
            total = len(trades)
            wr = wins / total if total > 0 else 0
            
            # Sharpe (annualized, simplified)
            returns = pnl_list / entry_prices[:len(pnl_list)]
            sharpe = np.mean(returns) / (np.std(returns) + 1e-10) * np.sqrt(252 * 24)  # intraday
            
            return BacktestResult(
                strategy_name=strategy.strategy_name,
                strategy_type=strategy.strategy_type,
                session=session,
                timeframe=self.timeframe,
                indicator_params=default_params,
                pf=float(pf),
                wr=float(wr),
                sharpe=float(sharpe),
                trades=len(trades),
                entry_prices=entry_prices,
                exit_prices=exit_prices,
                trade_results=list(pnl_list)
            )
        
        except Exception as e:
            logger.error(f"Backtest error for {strategy.strategy_name}: {e}")
            return None
    
    def _get_default_params(self, strategy_name: str) -> Dict:
        """
        Get default parameters for a strategy.
        
        Args:
            strategy_name: Name of strategy
        
        Returns:
            Dict of default parameters
        """
        # Strategy-specific defaults
        defaults = {
            'RSI14': {'period': 14},
            'RSI9': {'period': 9},
            'RSI21': {'period': 21},
            'OsMA_Confluence': {
                'osma_fast': 12,
                'osma_slow': 26,
                'osma_signal': 9,
                'ma_period': 20
            },
            'Stochastic14': {
                'k_period': 14,
                'd_period': 3,
                'smooth': 3
            },
            'MACD12': {
                'fast': 12,
                'slow': 26,
                'signal': 9
            },
            'Bollinger20': {
                'period': 20,
                'std_dev': 2.0
            },
            'ATR14': {'period': 14},
        }
        
        return defaults.get(strategy_name, {})


def run_phase1_discovery(
    symbol: str,
    timeframe: str,
    ohlcv_data: pd.DataFrame,
    entry_floors: Dict[str, float],
    sessions: Optional[List[str]] = None
) -> Dict[str, Phase1Output]:
    """
    Run Phase 1 discovery for multiple sessions.
    
    Args:
        symbol: Trading symbol
        timeframe: Timeframe
        ohlcv_data: Historical OHLCV data
        entry_floors: Per-session entry strength floors
        sessions: Specific sessions to test (None = all)
    
    Returns:
        Dict mapping session name to Phase1Output
    """
    logger.info(f"=== PHASE 1: DISCOVERY ===")
    logger.info(f"Symbol: {symbol}, Timeframe: {timeframe}")
    logger.info(f"OHLCV bars: {len(ohlcv_data)}")
    
    discoverer = Phase1Discovery(symbol, timeframe, ohlcv_data, entry_floors)
    
    # Discover for all sessions
    all_discovered = discoverer.discover_all_sessions()
    
    # Convert to Phase1Output
    date_range = {
        'start': ohlcv_data.index[0].strftime('%Y-%m-%d'),
        'end': ohlcv_data.index[-1].strftime('%Y-%m-%d')
    }
    
    timestamp = datetime.now(timezone.utc).isoformat()
    
    results = {}
    for session, strategies in all_discovered.items():
        if strategies:
            phase1_output = Phase1Output(
                symbol=symbol,
                timeframe=timeframe,
                session=session,
                discovered_strategies=strategies,
                date_range=date_range,
                timestamp=timestamp
            )
            results[session] = phase1_output
            
            logger.info(
                f"Phase 1 complete for {session}: "
                f"top strategy = {strategies[0].strategy_name} "
                f"(PF={strategies[0].baseline_pf:.2f})"
            )
    
    return results


__all__ = [
    'BacktestResult',
    'Phase1Discovery',
    'run_phase1_discovery',
]
