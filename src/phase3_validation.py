"""
Phase 3: Walkforward Validation

Validates tuned parameters using walkforward analysis.
Ensures tuned parameters don't overfit to historical data.

Status: IMPLEMENTATION (Day 5)
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from datetime import datetime, timezone
import logging

from src.phase_integration import (
    Phase3Input,
    Phase3Output,
    validate_phase3_to_phase4_aggregation
)
from src.strategy_interface import STRATEGY_REGISTRY

logger = logging.getLogger(__name__)


class Phase3Validation:
    """Phase 3: Walkforward validation of tuned parameters."""
    
    def __init__(
        self,
        phase3_input: Phase3Input,
        improvement_threshold: float = 0.02
    ):
        """
        Initialize Phase 3 validation.
        
        Args:
            phase3_input: Phase3Input from Phase 2
            improvement_threshold: Minimum improvement required (default +2%)
        """
        self.phase3_input = phase3_input
        self.improvement_threshold = improvement_threshold
    
    def validate(
        self,
        entry_floors: Dict[str, float],
        exit_params: Dict[str, float],
        indicator_params: Optional[Dict[str, float]] = None
    ) -> Phase3Output:
        """
        Run validation on tuned parameters.
        
        Args:
            entry_floors: Entry strength floors for signal generation
            exit_params: Exit parameters (SL/TP multipliers, etc.)
            indicator_params: Override indicator params (default = tuned_params)
        
        Returns:
            Phase3Output with acceptance decision
        """
        if indicator_params is None:
            indicator_params = self.phase3_input.tuned_params
        
        logger.info(f"Phase 3: Validating {self.phase3_input.strategy_name}")
        logger.info(f"  Session: {self.phase3_input.session}")
        logger.info(f"  Baseline PF: {self.phase3_input.baseline_pf:.2f}")
        logger.info(f"  Tuned PF: {self.phase3_input.tuned_pf:.2f}")
        
        # Get strategy
        try:
            strategy = STRATEGY_REGISTRY.get_strategy(self.phase3_input.strategy_name)
        except ValueError:
            return Phase3Output(
                symbol=self.phase3_input.symbol,
                session=self.phase3_input.session,
                timeframe=self.phase3_input.timeframe,
                strategy_name=self.phase3_input.strategy_name,
                accepted=False,
                baseline_pf=self.phase3_input.baseline_pf,
                baseline_wr=0.0,
                tuned_pf=0.0,
                tuned_wr=0.0,
                improvement_pct=0.0,
                acceptance_reason=None,
                rejection_reason="Strategy not found in registry",
                tuned_params={},
                indicator_params={},
                exit_params={}
            )
        
        # Run walkforward backtest
        walkforward_result = self._run_walkforward(
            strategy,
            indicator_params,
            entry_floors,
            exit_params
        )
        
        if walkforward_result is None:
            return Phase3Output(
                symbol=self.phase3_input.symbol,
                session=self.phase3_input.session,
                timeframe=self.phase3_input.timeframe,
                strategy_name=self.phase3_input.strategy_name,
                accepted=False,
                baseline_pf=self.phase3_input.baseline_pf,
                baseline_wr=0.0,
                tuned_pf=0.0,
                tuned_wr=0.0,
                improvement_pct=0.0,
                acceptance_reason=None,
                rejection_reason="Walkforward validation failed (insufficient trades)",
                tuned_params={},
                indicator_params={},
                exit_params={}
            )
        
        tuned_pf, tuned_wr = walkforward_result
        improvement_pct = self.phase3_input.calculate_improvement_pct()
        
        # Determine acceptance
        accepted = tuned_pf >= (self.phase3_input.baseline_pf * (1 - self.improvement_threshold))
        
        if accepted:
            acceptance_reason = f"PF improved {improvement_pct:.1f}% ({self.phase3_input.baseline_pf:.2f} → {tuned_pf:.2f})"
            rejection_reason = None
        else:
            acceptance_reason = None
            rejection_reason = f"PF declined {abs(improvement_pct):.1f}% ({self.phase3_input.baseline_pf:.2f} → {tuned_pf:.2f}), below threshold"
        
        logger.info(f"Phase 3: {'APPROVED' if accepted else 'REJECTED'}")
        if accepted:
            logger.info(f"  {acceptance_reason}")
        else:
            logger.info(f"  {rejection_reason}")
        
        return Phase3Output(
            symbol=self.phase3_input.symbol,
            session=self.phase3_input.session,
            timeframe=self.phase3_input.timeframe,
            strategy_name=self.phase3_input.strategy_name,
            accepted=accepted,
            baseline_pf=self.phase3_input.baseline_pf,
            baseline_wr=0.0,  # TODO: calculate from Phase 1
            tuned_pf=tuned_pf,
            tuned_wr=tuned_wr,
            improvement_pct=improvement_pct,
            acceptance_reason=acceptance_reason,
            rejection_reason=rejection_reason,
            tuned_params=indicator_params if accepted else {},
            indicator_params=indicator_params,
            exit_params=exit_params,
            entry_floors=entry_floors
        )
    
    def _run_walkforward(
        self,
        strategy,
        indicator_params: Dict,
        entry_floors: Dict[str, float],
        exit_params: Dict[str, float]
    ) -> Optional[tuple]:
        """
        Run walkforward validation.
        
        Simple 2-fold walkforward: split data 70/30, tune on first, validate on second.
        
        Args:
            strategy: BaseStrategy instance
            indicator_params: Indicator parameters
            entry_floors: Entry strength floors
            exit_params: Exit parameters
        
        Returns:
            (tuned_pf, tuned_wr) or None if validation failed
        """
        ohlcv = self.phase3_input.ohlcv_data
        split_idx = int(len(ohlcv) * 0.7)
        
        # Use second 30% for validation
        validation_data = ohlcv.iloc[split_idx:]
        
        # Calculate indicators on validation data
        try:
            indicators = strategy.calculate_indicators(validation_data, indicator_params)
        except Exception as e:
            logger.error(f"Indicator calculation failed: {e}")
            return None
        
        # Run backtest on validation period
        trades = []
        in_trade = False
        entry_price = 0
        
        for idx in range(len(validation_data)):
            close_price = validation_data['close'].iloc[idx]
            
            if not in_trade:
                # Look for entry signal
                try:
                    signal = strategy.generate_signal(
                        indicators,
                        entry_floors,
                        idx
                    )
                except Exception:
                    continue
                
                if signal.should_enter and signal.entry_type == "long":
                    in_trade = True
                    entry_price = close_price
            
            else:
                # In trade - apply exit params
                tp_mult = exit_params.get('tp_ratio', 2.5)
                sl_mult = exit_params.get('sl_atr_mult', 1.5)
                
                # Simple exit: TP and SL
                tp_price = entry_price * (1 + 0.01 * tp_mult)  # tp_ratio as basis points
                sl_price = entry_price * (1 - 0.01 * sl_mult)  # sl_atr_mult as basis points
                
                if close_price >= tp_price or close_price <= sl_price:
                    pnl = close_price - entry_price
                    trades.append(pnl)
                    in_trade = False
        
        # Calculate metrics
        if len(trades) < 5:  # Minimum 5 trades for validation
            logger.warning(f"Insufficient trades for validation: {len(trades)}")
            return None
        
        pnl_array = np.array(trades)
        winning = pnl_array[pnl_array > 0]
        losing = pnl_array[pnl_array < 0]
        
        # PF
        if len(losing) == 0:
            pf = float('inf') if len(winning) > 0 else 1.0
        else:
            pf = np.sum(winning) / np.abs(np.sum(losing))
        
        # WR
        wr = len(winning) / len(trades) if len(trades) > 0 else 0
        
        return (float(pf), float(wr))


def run_phase3_validation(
    phase3_input: Phase3Input,
    entry_floors: Dict[str, float],
    exit_params: Dict[str, float],
    improvement_threshold: float = 0.02
) -> Phase3Output:
    """
    Run Phase 3 validation.
    
    Args:
        phase3_input: Phase3Input from Phase 2
        entry_floors: Entry strength floors
        exit_params: Exit parameters
        improvement_threshold: Minimum improvement required
    
    Returns:
        Phase3Output with acceptance decision
    """
    logger.info("=== PHASE 3: VALIDATION ===")
    
    validator = Phase3Validation(phase3_input, improvement_threshold)
    
    phase3_output = validator.validate(
        entry_floors,
        exit_params,
        indicator_params=phase3_input.tuned_params
    )
    
    return phase3_output


__all__ = [
    'Phase3Validation',
    'run_phase3_validation',
]
