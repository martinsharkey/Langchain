"""
Phase 2: Optuna-based Parameter Tuning

Optimizes strategy parameters using Optuna's Bayesian optimization.
Takes Phase 1 top strategy and tunes parameters for improvement.

Status: IMPLEMENTATION (Day 5)
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Callable
from datetime import datetime, timezone
import logging

try:
    import optuna
    from optuna.samplers import TPESampler
except ImportError:
    optuna = None
    TPESampler = None

from src.phase_integration import (
    Phase2Input,
    Phase2Output,
    validate_phase2_to_phase3_flow
)
from src.strategy_interface import STRATEGY_REGISTRY

logger = logging.getLogger(__name__)


class Phase2Tuning:
    """Phase 2: Optuna-based parameter optimization."""
    
    def __init__(
        self,
        phase2_input: Phase2Input,
        study_name: Optional[str] = None,
        storage_path: Optional[str] = None
    ):
        """
        Initialize Phase 2 tuning.
        
        Args:
            phase2_input: Phase2Input from Phase 1
            study_name: Optuna study name (auto-generated if None)
            storage_path: Path to Optuna SQLite DB (temp if None)
        """
        if optuna is None:
            raise ImportError("optuna not installed: pip install optuna")
        
        self.phase2_input = phase2_input
        self.study_name = study_name or f"study_{phase2_input.symbol}_{phase2_input.session}"
        self.storage_path = storage_path
        
        self.study = None
        self.best_trial = None
    
    def optimize(
        self,
        n_trials: Optional[int] = None,
        timeout: Optional[int] = None
    ) -> Phase2Output:
        """
        Run Optuna optimization.
        
        Args:
            n_trials: Number of trials (default from phase2_input)
            timeout: Timeout in seconds (None = no timeout)
        
        Returns:
            Phase2Output with tuned parameters
        """
        if n_trials is None:
            n_trials = self.phase2_input.optuna_trials
        
        logger.info(f"Phase 2: Starting Optuna tuning for {self.phase2_input.strategy_name}")
        logger.info(f"  Sessions: {self.phase2_input.session}")
        logger.info(f"  Trials: {n_trials}")
        logger.info(f"  Baseline PF: {self.phase2_input.baseline_pf:.2f}")
        
        # Create study
        sampler = TPESampler(seed=42)
        study_storage = f"sqlite:///{self.storage_path}" if self.storage_path else None
        
        self.study = optuna.create_study(
            study_name=self.study_name,
            storage=study_storage,
            sampler=sampler,
            direction='maximize',
            load_if_exists=True
        )
        
        # Define objective function
        objective = self._create_objective()
        
        # Optimize
        self.study.optimize(objective, n_trials=n_trials, timeout=timeout, show_progress_bar=True)
        
        # Get best trial
        self.best_trial = self.study.best_trial
        
        logger.info(f"Phase 2: Optimization complete")
        logger.info(f"  Best trial ID: {self.best_trial.number}")
        logger.info(f"  Best PF: {self.best_trial.value:.2f}")
        logger.info(f"  Best params: {self.best_trial.params}")
        
        # Create Phase2Output
        phase2_output = Phase2Output(
            symbol=self.phase2_input.symbol,
            session=self.phase2_input.session,
            timeframe=self.phase2_input.timeframe,
            strategy_name=self.phase2_input.strategy_name,
            strategy_type=self.phase2_input.strategy_type,
            baseline_pf=self.phase2_input.baseline_pf,
            baseline_wr=self.phase2_input.baseline_wr,
            baseline_sharpe=self.phase2_input.baseline_sharpe,
            tuned_params=self.best_trial.params,
            best_trial_id=self.best_trial.number,
            best_trial_pf=self.best_trial.value,
            study_db_path=self.storage_path or "",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        return phase2_output
    
    def _create_objective(self) -> Callable:
        """
        Create objective function for Optuna.
        
        Returns:
            Callable that takes trial and returns PF score
        """
        strategy = STRATEGY_REGISTRY.get_strategy(self.phase2_input.strategy_name)
        ohlcv = self.phase2_input.ohlcv_data
        baseline_pf = self.phase2_input.baseline_pf
        
        def objective(trial: optuna.Trial) -> float:
            """Objective: maximize Profit Factor."""
            try:
                # Suggest parameters based on strategy
                params = self._suggest_parameters(trial, self.phase2_input.strategy_name)
                
                # Validate params
                if not strategy.validate_params(params):
                    return 0.0  # Invalid params get zero score
                
                # Calculate indicators
                indicators = strategy.calculate_indicators(ohlcv, params)
                
                # Backtest with simple entry/exit
                pf = self._backtest_pf(
                    strategy,
                    indicators,
                    ohlcv,
                    params
                )
                
                return pf
            
            except Exception as e:
                logger.error(f"Trial error: {e}")
                return 0.0
        
        return objective
    
    def _suggest_parameters(self, trial: optuna.Trial, strategy_name: str) -> Dict:
        """
        Suggest parameters for Optuna trial.
        
        Strategy-specific parameter ranges.
        """
        params = {}
        
        if strategy_name == "RSI14":
            params['period'] = trial.suggest_int('period', 5, 30)
        
        elif strategy_name == "Stochastic14":
            params['k_period'] = trial.suggest_int('k_period', 8, 20)
            params['d_period'] = trial.suggest_int('d_period', 2, 5)
            params['smooth'] = trial.suggest_int('smooth', 2, 5)
        
        elif strategy_name == "OsMA_Confluence":
            params['osma_fast'] = trial.suggest_int('osma_fast', 6, 15)
            params['osma_slow'] = trial.suggest_int('osma_slow', 20, 30)
            params['osma_signal'] = trial.suggest_int('osma_signal', 5, 12)
            params['ma_period'] = trial.suggest_int('ma_period', 15, 30)
        
        # TODO: Add parameter ranges for other strategies
        
        return params
    
    def _backtest_pf(
        self,
        strategy,
        indicators: Dict,
        ohlcv: pd.DataFrame,
        params: Dict
    ) -> float:
        """
        Run simplified backtest and return Profit Factor.
        
        Args:
            strategy: BaseStrategy instance
            indicators: Calculated indicators
            ohlcv: OHLCV data
            params: Strategy parameters
        
        Returns:
            Profit Factor (0.0 if no trades)
        """
        trades = []
        in_trade = False
        entry_price = 0
        
        for idx in range(len(ohlcv)):
            close_price = ohlcv['close'].iloc[idx]
            
            if not in_trade:
                # Look for entry
                try:
                    signal = strategy.generate_signal(
                        indicators,
                        {"min_strength": 0.0},  # No floor for tuning
                        idx
                    )
                except Exception:
                    continue
                
                if signal.should_enter and signal.entry_type == "long":
                    in_trade = True
                    entry_price = close_price
            
            else:
                # In trade - simple TP/SL exit
                tp_price = entry_price * 1.02  # 2% TP
                sl_price = entry_price * 0.99  # 1% SL
                
                if close_price >= tp_price or close_price <= sl_price:
                    pnl = close_price - entry_price
                    trades.append(pnl)
                    in_trade = False
        
        # Calculate PF
        if len(trades) == 0:
            return 0.0
        
        pnl_array = np.array(trades)
        winning = pnl_array[pnl_array > 0]
        losing = pnl_array[pnl_array < 0]
        
        if len(losing) == 0:
            pf = float('inf') if len(winning) > 0 else 1.0
        else:
            pf = np.sum(winning) / np.abs(np.sum(losing))
        
        return float(pf)


def run_phase2_tuning(
    phase2_input: Phase2Input,
    n_trials: int = 500,
    storage_path: Optional[str] = None
) -> Phase2Output:
    """
    Run Phase 2 tuning.
    
    Args:
        phase2_input: Phase2Input from Phase 1
        n_trials: Number of Optuna trials
        storage_path: Path to Optuna SQLite DB
    
    Returns:
        Phase2Output with tuned parameters
    """
    logger.info("=== PHASE 2: TUNING ===")
    
    tuner = Phase2Tuning(
        phase2_input,
        storage_path=storage_path
    )
    
    phase2_output = tuner.optimize(n_trials=n_trials)
    
    logger.info(
        f"Phase 2 complete: {phase2_output.strategy_name} "
        f"improved from {phase2_output.baseline_pf:.2f} "
        f"to {phase2_output.best_trial_pf:.2f} "
        f"({phase2_output.get_improvement_pct():.1f}%)"
    )
    
    return phase2_output


__all__ = [
    'Phase2Tuning',
    'run_phase2_tuning',
]
