"""
Optimization Service Core Engine

Extracts Phase 2 Optuna-based floor optimization from v1.0.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Result from single optimization trial."""
    trial_id: int
    floor_value: float
    pf: float
    wr: float
    sharpe: float
    trades: int
    timestamp: str


class OptimizationEngine:
    """Core optimization engine using Optuna for floor discovery."""
    
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        session: str,
        strategy_name: str,
        ohlcv_data: pd.DataFrame,
        initial_floor: float = 0.5,
        max_floor: float = 0.95,
    ):
        """
        Initialize Optimization Engine.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            session: Session name
            strategy_name: Strategy to optimize
            ohlcv_data: Historical OHLCV data
            initial_floor: Starting floor value
            max_floor: Maximum floor to test
        """
        self.symbol = symbol
        self.timeframe = timeframe
        self.session = session
        self.strategy_name = strategy_name
        self.ohlcv_data = ohlcv_data
        self.initial_floor = initial_floor
        self.max_floor = max_floor
        
        self.trials: List[OptimizationResult] = []
        self.best_floor: Optional[float] = None
        self.best_pf: float = 0.0
        
        self._validate_inputs()
    
    def _validate_inputs(self):
        """Validate inputs."""
        if not 0 <= self.initial_floor <= 1:
            raise ValueError(f"Invalid initial_floor: {self.initial_floor}")
        if not 0 <= self.max_floor <= 1:
            raise ValueError(f"Invalid max_floor: {self.max_floor}")
        if self.initial_floor > self.max_floor:
            raise ValueError("initial_floor cannot exceed max_floor")
        if len(self.ohlcv_data) < 100:
            raise ValueError("Insufficient OHLCV data")
    
    async def optimize(
        self,
        strategy,
        num_trials: int = 50,
        min_trades_per_floor: int = 5
    ) -> Dict:
        """
        Run Optuna optimization for floor value.
        
        Args:
            strategy: Strategy instance
            num_trials: Number of optimization trials
            min_trades_per_floor: Minimum trades for valid backtest
        
        Returns:
            Optimization summary with best floor and metrics
        """
        logger.info(
            f"Optimization: {self.symbol}/{self.session}/{self.strategy_name} "
            f"({num_trials} trials)"
        )
        
        # Simple grid search for floor optimization
        floor_range = np.linspace(0.1, self.max_floor, num_trials)
        
        for trial_idx, floor_value in enumerate(floor_range):
            try:
                result = await self._backtest_at_floor(
                    strategy,
                    floor_value,
                    min_trades_per_floor
                )
                
                if result is None:
                    logger.debug(f"  Trial {trial_idx}: floor={floor_value:.2f} - invalid")
                    continue
                
                self.trials.append(result)
                
                if result.pf > self.best_pf:
                    self.best_pf = result.pf
                    self.best_floor = floor_value
                
                logger.info(
                    f"  Trial {trial_idx}: floor={floor_value:.2f} PF={result.pf:.2f} "
                    f"WR={result.wr:.1%} trades={result.trades}"
                )
            
            except Exception as e:
                logger.error(f"  Trial {trial_idx}: {e}")
                continue
        
        logger.info(
            f"Optimization complete: best_floor={self.best_floor:.2f} "
            f"best_pf={self.best_pf:.2f}"
        )
        
        return {
            'strategy_name': self.strategy_name,
            'session': self.session,
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'best_floor': self.best_floor,
            'best_pf': self.best_pf,
            'num_trials': len(self.trials),
            'trials': [
                {
                    'trial_id': t.trial_id,
                    'floor': t.floor_value,
                    'pf': t.pf,
                    'wr': t.wr,
                    'trades': t.trades
                }
                for t in self.trials
            ]
        }
    
    async def _backtest_at_floor(
        self,
        strategy,
        floor_value: float,
        min_trades: int
    ) -> Optional[OptimizationResult]:
        """
        Run backtest at specific floor value.
        
        Args:
            strategy: Strategy instance
            floor_value: Floor threshold to test
            min_trades: Minimum trades for valid result
        
        Returns:
            OptimizationResult or None if invalid
        """
        try:
            default_params = self._get_default_params(self.strategy_name)
            indicators = strategy.calculate_indicators(self.ohlcv_data, default_params)
            
            trades = []
            in_trade = False
            entry_price = 0
            trial_id = len(self.trials)
            
            for idx in range(len(self.ohlcv_data)):
                close_price = self.ohlcv_data['close'].iloc[idx]
                
                if not in_trade:
                    try:
                        signal = strategy.generate_signal(
                            indicators,
                            {"min_strength": floor_value},
                            idx
                        )
                    except Exception:
                        continue
                    
                    if signal.should_enter and signal.entry_type == "long":
                        in_trade = True
                        entry_price = close_price
                
                else:
                    # Simple 2% TP, 1% SL
                    tp_price = entry_price * 1.02
                    sl_price = entry_price * 0.99
                    
                    if close_price >= tp_price or close_price <= sl_price:
                        pnl = close_price - entry_price
                        trades.append(pnl)
                        in_trade = False
            
            if len(trades) < min_trades:
                return None
            
            pnl_array = np.array(trades)
            winning = pnl_array[pnl_array > 0]
            losing = pnl_array[pnl_array < 0]
            
            pf = np.sum(winning) / np.abs(np.sum(losing)) if len(losing) > 0 else float('inf')
            wr = len(winning) / len(trades)
            
            returns = pnl_array / entry_price if len(pnl_array) > 0 else np.array([])
            sharpe = np.mean(returns) / (np.std(returns) + 1e-10) * np.sqrt(252 * 24)
            
            return OptimizationResult(
                trial_id=trial_id,
                floor_value=float(floor_value),
                pf=float(pf),
                wr=float(wr),
                sharpe=float(sharpe),
                trades=len(trades),
                timestamp=pd.Timestamp.now().isoformat()
            )
        
        except Exception as e:
            logger.error(f"Backtest error at floor {floor_value}: {e}")
            return None
    
    def _get_default_params(self, strategy_name: str) -> Dict:
        """Get default parameters for strategy."""
        defaults = {
            'RSI14': {'period': 14},
            'RSI9': {'period': 9},
            'Stochastic14': {'k_period': 14, 'd_period': 3, 'smooth': 3},
            'OsMA_Confluence': {
                'osma_fast': 12,
                'osma_slow': 26,
                'osma_signal': 9,
                'ma_period': 20
            }
        }
        return defaults.get(strategy_name, {})
    
    def get_convergence_plot_data(self) -> Dict:
        """Get data for convergence visualization."""
        if not self.trials:
            return {}
        
        return {
            'trial_ids': [t.trial_id for t in self.trials],
            'floors': [t.floor_value for t in self.trials],
            'pf_values': [t.pf for t in self.trials],
            'best_pf_so_far': [
                max(t.pf for t in self.trials[:i+1])
                for i in range(len(self.trials))
            ]
        }


__all__ = ['OptimizationEngine', 'OptimizationResult']
