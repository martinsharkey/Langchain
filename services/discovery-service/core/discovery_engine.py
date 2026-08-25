"""
Discovery Service Core Engine

Extracts Phase 1 discovery logic from v1.0 and adapts for service architecture.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class DiscoveryEngine:
    """Core discovery engine for finding optimal strategies."""
    
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        ohlcv_data: pd.DataFrame,
        entry_floors: Dict[str, float],
        min_trades: int = 10
    ):
        """
        Initialize Discovery Engine.
        
        Args:
            symbol: Trading symbol (e.g., "XAUUSD")
            timeframe: Timeframe (e.g., "M15")
            ohlcv_data: Historical OHLCV data
            entry_floors: Entry strength floors per session
            min_trades: Minimum trades for valid backtest
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
    
    async def discover_for_session(
        self,
        session: str,
        strategy_registry,
        max_strategies: Optional[int] = None
    ) -> List[Dict]:
        """
        Discover best strategies for a session.
        
        Args:
            session: Session name
            strategy_registry: Strategy registry instance
            max_strategies: Max strategies to test (None = all)
        
        Returns:
            List of discovered strategies ranked by PF (highest first)
        """
        logger.info(f"Discovery: Finding strategies for {self.symbol}/{session}/{self.timeframe}")
        
        strategy_names = strategy_registry.list_strategies()
        if max_strategies:
            strategy_names = strategy_names[:max_strategies]
        
        results = []
        
        for strategy_name in strategy_names:
            try:
                strategy = strategy_registry.get_strategy(strategy_name)
                
                # Run backtest
                backtest_result = await self._backtest_strategy(
                    strategy,
                    session,
                    self.entry_floors.get(session, 0.0)
                )
                
                if backtest_result is None:
                    logger.warning(f"  {strategy_name}: backtest failed")
                    continue
                
                # Filter by minimum trades
                if backtest_result['trades'] < self.min_trades:
                    logger.warning(f"  {strategy_name}: only {backtest_result['trades']} trades")
                    continue
                
                # Filter by profitability
                if backtest_result['pf'] < 1.0:
                    logger.warning(f"  {strategy_name}: PF {backtest_result['pf']:.2f} < 1.0")
                    continue
                
                results.append(backtest_result)
                logger.info(f"  {strategy_name}: PF={backtest_result['pf']:.2f}, WR={backtest_result['wr']:.1%}")
            
            except Exception as e:
                logger.error(f"  {strategy_name}: {e}")
                continue
        
        # Sort by PF (highest first)
        results.sort(key=lambda x: x['pf'], reverse=True)
        
        logger.info(f"Discovery: Found {len(results)} profitable strategies")
        return results
    
    async def _backtest_strategy(
        self,
        strategy,
        session: str,
        entry_floor: float
    ) -> Optional[Dict]:
        """
        Run backtest for a strategy.
        
        Args:
            strategy: Strategy instance
            session: Session name
            entry_floor: Entry strength floor
        
        Returns:
            Backtest result or None if failed
        """
        try:
            # Get default params
            default_params = self._get_default_params(strategy.strategy_name)
            
            # Calculate indicators
            indicators = strategy.calculate_indicators(self.ohlcv_data, default_params)
            
            # Run backtest
            trades = []
            in_trade = False
            entry_price = 0
            
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
                
                else:
                    # In trade - simple exit (2% TP, 1% SL)
                    tp_price = entry_price * 1.02
                    sl_price = entry_price * 0.99
                    
                    if close_price >= tp_price or close_price <= sl_price:
                        pnl = close_price - entry_price
                        trades.append(pnl)
                        in_trade = False
            
            # Calculate metrics
            if len(trades) == 0:
                return None
            
            pnl_array = np.array(trades)
            winning = pnl_array[pnl_array > 0]
            losing = pnl_array[pnl_array < 0]
            
            # Profit Factor
            if len(losing) == 0:
                pf = float('inf') if len(winning) > 0 else 1.0
            else:
                pf = np.sum(winning) / np.abs(np.sum(losing))
            
            # Win Rate
            wr = len(winning) / len(trades) if len(trades) > 0 else 0
            
            # Sharpe
            returns = pnl_array / entry_price if len(pnl_array) > 0 else np.array([])
            sharpe = np.mean(returns) / (np.std(returns) + 1e-10) * np.sqrt(252 * 24)
            
            return {
                'strategy_name': strategy.strategy_name,
                'strategy_type': strategy.strategy_type,
                'session': session,
                'timeframe': self.timeframe,
                'indicator_params': default_params,
                'pf': float(pf),
                'wr': float(wr),
                'sharpe': float(sharpe),
                'trades': len(trades),
            }
        
        except Exception as e:
            logger.error(f"Backtest error for {strategy.strategy_name}: {e}")
            return None
    
    def _get_default_params(self, strategy_name: str) -> Dict:
        """Get default parameters for a strategy."""
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
        }
        return defaults.get(strategy_name, {})


__all__ = ['DiscoveryEngine']
