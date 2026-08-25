"""
Complete Pipeline Orchestrator - Phase 1→2→3→4

Coordinates all four phases into a single executable pipeline.

Status: IMPLEMENTATION (Day 5)
"""

import pandas as pd
from typing import Dict, Optional, List
from datetime import datetime, timezone
import logging

from src.phase1_discovery import run_phase1_discovery
from src.phase2_tuning import run_phase2_tuning
from src.phase3_validation import run_phase3_validation
from src.phase4_deployment import run_phase4_deployment

from src.phase_integration import (
    Phase1Output,
    Phase2Input,
    Phase2Output,
    Phase3Input,
    Phase3Output,
    Phase4Input,
    PipelineMetadata,
    validate_phase1_to_phase2_flow,
    validate_phase2_to_phase3_flow,
    validate_phase3_to_phase4_aggregation,
)

logger = logging.getLogger(__name__)


class CompletePipeline:
    """Orchestrate all 4 phases into single pipeline execution."""
    
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        ohlcv_data: pd.DataFrame,
        entry_floors: Dict[str, float],
        exit_params: Dict[str, float],
        symbol_config: Optional[Dict] = None
    ):
        """
        Initialize complete pipeline.
        
        Args:
            symbol: Trading symbol (e.g., "XAUUSD")
            timeframe: Timeframe (e.g., "M15")
            ohlcv_data: Historical OHLCV data
            entry_floors: Per-session entry strength floors
            exit_params: Exit parameters (SL/TP multipliers)
            symbol_config: Symbol configuration (optional)
        """
        self.symbol = symbol
        self.timeframe = timeframe
        self.ohlcv_data = ohlcv_data
        self.entry_floors = entry_floors
        self.exit_params = exit_params
        self.symbol_config = symbol_config or {}
        
        self.phase1_results = {}
        self.phase2_results = {}
        self.phase3_results = {}
        self.phase4_result = None
        
        self.metadata = PipelineMetadata(
            symbol=symbol,
            timeframe=timeframe,
            sessions=[]
        )
    
    def run(
        self,
        output_path: str,
        n_trials: int = 500,
        max_strategies_per_session: Optional[int] = None
    ) -> Dict:
        """
        Run complete Phase 1→2→3→4 pipeline.
        
        Args:
            output_path: Path to write tuned_params.json
            n_trials: Number of Optuna trials per strategy
            max_strategies_per_session: Limit strategies tested (None = all)
        
        Returns:
            Final Phase4 tuned_params dict
        """
        logger.info("=" * 60)
        logger.info("COMPLETE PIPELINE: Phase 1→2→3→4")
        logger.info("=" * 60)
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Timeframe: {self.timeframe}")
        logger.info(f"OHLCV bars: {len(self.ohlcv_data)}")
        logger.info("=" * 60)
        
        try:
            # PHASE 1: Discovery
            logger.info("\n>>> PHASE 1: DISCOVERY")
            self._run_phase1(max_strategies_per_session)
            self.metadata.mark_phase_1_complete()
            
            # PHASE 2: Tuning
            logger.info("\n>>> PHASE 2: TUNING")
            self._run_phase2(n_trials)
            self.metadata.mark_phase_2_complete()
            
            # PHASE 3: Validation
            logger.info("\n>>> PHASE 3: VALIDATION")
            self._run_phase3()
            
            # Count approved/rejected
            approved_count = sum(1 for r in self.phase3_results.values() if r.accepted)
            rejected_count = sum(1 for r in self.phase3_results.values() if not r.accepted)
            self.metadata.mark_phase_3_complete(approved_count, rejected_count)
            
            # PHASE 4: Deployment
            logger.info("\n>>> PHASE 4: DEPLOYMENT")
            self._run_phase4(output_path)
            self.metadata.mark_phase_4_complete()
            
            logger.info("\n" + "=" * 60)
            logger.info("PIPELINE COMPLETE ✅")
            logger.info("=" * 60)
            logger.info(f"Output: {output_path}")
            logger.info(f"Approved sessions: {approved_count}")
            logger.info(f"Rejected sessions: {rejected_count}")
            logger.info("=" * 60)
            
            return self.phase4_result
        
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            raise
    
    def _run_phase1(self, max_strategies: Optional[int] = None):
        """Run Phase 1 discovery."""
        self.phase1_results = run_phase1_discovery(
            self.symbol,
            self.timeframe,
            self.ohlcv_data,
            self.entry_floors,
            sessions=None
        )
        
        self.metadata.sessions = list(self.phase1_results.keys())
        
        logger.info(f"Phase 1: Discovered strategies for {len(self.phase1_results)} sessions")
        for session, phase1_output in self.phase1_results.items():
            top_strategy = phase1_output.get_top_strategy()
            logger.info(
                f"  {session}: {top_strategy.strategy_name} "
                f"(PF={top_strategy.baseline_pf:.2f})"
            )
    
    def _run_phase2(self, n_trials: int = 500):
        """Run Phase 2 tuning for each session's top strategy."""
        for session, phase1_output in self.phase1_results.items():
            top_strategy = phase1_output.get_top_strategy()
            
            logger.info(f"\nPhase 2: Tuning {session}/{top_strategy.strategy_name}")
            
            # Convert Phase 1 → Phase 2
            phase2_input = Phase2Input(
                symbol=phase1_output.symbol,
                session=phase1_output.session,
                timeframe=phase1_output.timeframe,
                strategy_name=top_strategy.strategy_name,
                strategy_type=top_strategy.strategy_type,
                indicator_params=top_strategy.indicator_params,
                baseline_pf=top_strategy.baseline_pf,
                baseline_wr=top_strategy.baseline_wr,
                baseline_sharpe=top_strategy.baseline_sharpe,
                baseline_trades=top_strategy.baseline_trades,
                ohlcv_data=self.ohlcv_data,
                optuna_trials=n_trials
            )
            
            # Run Phase 2
            try:
                phase2_output = run_phase2_tuning(phase2_input, n_trials=n_trials)
                self.phase2_results[session] = phase2_output
                
                logger.info(
                    f"  Phase 2 complete: PF improved from {phase2_output.baseline_pf:.2f} "
                    f"to {phase2_output.best_trial_pf:.2f}"
                )
            except Exception as e:
                logger.error(f"  Phase 2 failed: {e}")
                # Continue with next session
                continue
    
    def _run_phase3(self):
        """Run Phase 3 validation for each session's tuned strategy."""
        for session, phase2_output in self.phase2_results.items():
            logger.info(f"\nPhase 3: Validating {session}/{phase2_output.strategy_name}")
            
            # Convert Phase 2 → Phase 3
            phase3_input = Phase3Input(
                symbol=phase2_output.symbol,
                session=phase2_output.session,
                timeframe=phase2_output.timeframe,
                strategy_name=phase2_output.strategy_name,
                baseline_pf=phase2_output.baseline_pf,
                baseline_wr=phase2_output.baseline_wr,
                baseline_sharpe=phase2_output.baseline_sharpe,
                tuned_params=phase2_output.tuned_params,
                tuned_pf=phase2_output.best_trial_pf,
                ohlcv_data=self.ohlcv_data,
                improvement_threshold=0.02
            )
            
            # Run Phase 3
            try:
                phase3_output = run_phase3_validation(
                    phase3_input,
                    self.entry_floors,
                    self.exit_params
                )
                self.phase3_results[session] = phase3_output
                
                status = "✅ APPROVED" if phase3_output.accepted else "❌ REJECTED"
                logger.info(f"  Phase 3 result: {status}")
            except Exception as e:
                logger.error(f"  Phase 3 failed: {e}")
                continue
    
    def _run_phase4(self, output_path: str):
        """Run Phase 4 deployment."""
        # Convert Phase 3 → Phase 4
        phase4_input = Phase4Input(
            symbol=self.symbol,
            validation_results=self.phase3_results
        )
        
        # Run Phase 4
        self.phase4_result = run_phase4_deployment(
            phase4_input,
            output_path,
            symbol_config=self.symbol_config
        )


def run_complete_pipeline(
    symbol: str,
    timeframe: str,
    ohlcv_data: pd.DataFrame,
    entry_floors: Dict[str, float],
    exit_params: Dict[str, float],
    output_path: str,
    symbol_config: Optional[Dict] = None,
    n_trials: int = 500
) -> Dict:
    """
    Run complete Phase 1→2→3→4 pipeline.
    
    Args:
        symbol: Trading symbol
        timeframe: Timeframe
        ohlcv_data: Historical OHLCV data
        entry_floors: Per-session entry strength floors
        exit_params: Exit parameters
        output_path: Path to write tuned_params.json
        symbol_config: Symbol configuration (optional)
        n_trials: Number of Optuna trials
    
    Returns:
        Final tuned_params dict
    """
    pipeline = CompletePipeline(
        symbol,
        timeframe,
        ohlcv_data,
        entry_floors,
        exit_params,
        symbol_config
    )
    
    return pipeline.run(output_path, n_trials=n_trials)


__all__ = [
    'CompletePipeline',
    'run_complete_pipeline',
]
