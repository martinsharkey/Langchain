"""
Validation Service Core Engine

Validates discovered and optimized strategies before deployment.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result from strategy validation."""
    strategy_name: str
    symbol: str
    session: str
    timeframe: str
    is_valid: bool
    pf: float
    wr: float
    sharpe: float
    trades: int
    edge_percentage: float
    validation_rules_passed: List[str]
    validation_rules_failed: List[str]


class ValidationEngine:
    """Core validation engine for pre-deployment checks."""
    
    # Validation thresholds
    MIN_PROFIT_FACTOR = 1.3
    MIN_WIN_RATE = 0.45
    MIN_SHARPE = 1.0
    MIN_TRADES = 10
    MAX_CONSECUTIVE_LOSSES = 5
    MIN_EDGE_PERCENTAGE = 2.0
    
    def __init__(self, symbol: str, timeframe: str, session: str):
        """
        Initialize Validation Engine.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            session: Session name
        """
        self.symbol = symbol
        self.timeframe = timeframe
        self.session = session
    
    async def validate_strategy(
        self,
        strategy_name: str,
        backtest_result: Dict,
        trades_pnl: List[float]
    ) -> ValidationResult:
        """
        Validate strategy against pre-deployment rules.
        
        Args:
            strategy_name: Name of strategy
            backtest_result: Backtest metrics
            trades_pnl: List of trade P&L values
        
        Returns:
            ValidationResult with pass/fail status
        """
        logger.info(f"Validating: {self.symbol}/{self.session}/{strategy_name}")
        
        rules_passed = []
        rules_failed = []
        
        # Rule 1: Profit Factor
        pf = backtest_result.get('pf', 0.0)
        if pf >= self.MIN_PROFIT_FACTOR:
            rules_passed.append(f"PF {pf:.2f} >= {self.MIN_PROFIT_FACTOR}")
        else:
            rules_failed.append(f"PF {pf:.2f} < {self.MIN_PROFIT_FACTOR}")
        
        # Rule 2: Win Rate
        wr = backtest_result.get('wr', 0.0)
        if wr >= self.MIN_WIN_RATE:
            rules_passed.append(f"WR {wr:.1%} >= {self.MIN_WIN_RATE:.1%}")
        else:
            rules_failed.append(f"WR {wr:.1%} < {self.MIN_WIN_RATE:.1%}")
        
        # Rule 3: Sharpe Ratio
        sharpe = backtest_result.get('sharpe', 0.0)
        if sharpe >= self.MIN_SHARPE:
            rules_passed.append(f"Sharpe {sharpe:.2f} >= {self.MIN_SHARPE}")
        else:
            rules_failed.append(f"Sharpe {sharpe:.2f} < {self.MIN_SHARPE}")
        
        # Rule 4: Minimum Trades
        trades = backtest_result.get('trades', 0)
        if trades >= self.MIN_TRADES:
            rules_passed.append(f"Trades {trades} >= {self.MIN_TRADES}")
        else:
            rules_failed.append(f"Trades {trades} < {self.MIN_TRADES}")
        
        # Rule 5: Consecutive Losses
        if trades_pnl:
            max_consecutive_losses = self._calculate_max_consecutive_losses(trades_pnl)
            if max_consecutive_losses <= self.MAX_CONSECUTIVE_LOSSES:
                rules_passed.append(
                    f"Max consecutive losses {max_consecutive_losses} "
                    f"<= {self.MAX_CONSECUTIVE_LOSSES}"
                )
            else:
                rules_failed.append(
                    f"Max consecutive losses {max_consecutive_losses} "
                    f"> {self.MAX_CONSECUTIVE_LOSSES}"
                )
        
        # Rule 6: Edge Percentage
        edge_pct = self._calculate_edge_percentage(trades_pnl)
        if edge_pct >= self.MIN_EDGE_PERCENTAGE:
            rules_passed.append(f"Edge {edge_pct:.2f}% >= {self.MIN_EDGE_PERCENTAGE}%")
        else:
            rules_failed.append(f"Edge {edge_pct:.2f}% < {self.MIN_EDGE_PERCENTAGE}%")
        
        is_valid = len(rules_failed) == 0
        
        result = ValidationResult(
            strategy_name=strategy_name,
            symbol=self.symbol,
            session=self.session,
            timeframe=self.timeframe,
            is_valid=is_valid,
            pf=float(pf),
            wr=float(wr),
            sharpe=float(sharpe),
            trades=trades,
            edge_percentage=float(edge_pct),
            validation_rules_passed=rules_passed,
            validation_rules_failed=rules_failed
        )
        
        status = "✓ PASS" if is_valid else "✗ FAIL"
        logger.info(
            f"Validation {status}: {strategy_name} "
            f"(PF={pf:.2f}, WR={wr:.1%}, edge={edge_pct:.2f}%)"
        )
        
        return result
    
    def _calculate_max_consecutive_losses(self, trades_pnl: List[float]) -> int:
        """Calculate maximum consecutive losses."""
        if not trades_pnl:
            return 0
        
        max_consecutive = 0
        current_consecutive = 0
        
        for pnl in trades_pnl:
            if pnl < 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        return max_consecutive
    
    def _calculate_edge_percentage(self, trades_pnl: List[float]) -> float:
        """
        Calculate edge percentage (average win - average loss as % of average win).
        """
        if not trades_pnl:
            return 0.0
        
        trades_array = np.array(trades_pnl)
        winning_trades = trades_array[trades_array > 0]
        losing_trades = trades_array[trades_array < 0]
        
        if len(winning_trades) == 0 or len(losing_trades) == 0:
            return 0.0
        
        avg_win = np.mean(winning_trades)
        avg_loss = np.abs(np.mean(losing_trades))
        
        edge = ((avg_win + avg_loss) / avg_win) * 100 - 100
        return float(edge)


__all__ = ['ValidationEngine', 'ValidationResult']
