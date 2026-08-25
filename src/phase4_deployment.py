"""
Phase 4: Deployment - Generate tuned_params.json

Aggregates Phase 3 validation results and generates the final deployment file.
This file is consumed by ScalpEngine for live trading.

Status: IMPLEMENTATION (Day 5)
"""

import json
from typing import Dict, Optional
from datetime import datetime, timezone
from pathlib import Path
import logging

from src.phase_integration import (
    Phase4Input,
    Phase3Output,
)
from src.schema_validator import (
    TunedParamsValidator,
    save_tuned_params
)

logger = logging.getLogger(__name__)


class Phase4Deployer:
    """Phase 4: Generate deployment configuration."""
    
    def __init__(
        self,
        phase4_input: Phase4Input,
        symbol_config: Optional[Dict] = None,
        version: int = 2
    ):
        """
        Initialize Phase 4 deployer.
        
        Args:
            phase4_input: Phase4Input from Phase 3
            symbol_config: Symbol configuration (floors, timeframe, etc.)
            version: Schema version number
        """
        self.phase4_input = phase4_input
        self.symbol_config = symbol_config or {}
        self.version = version
    
    def deploy(self, output_path: str) -> Dict:
        """
        Generate and save tuned_params.json.
        
        Args:
            output_path: Path to write tuned_params.json
        
        Returns:
            Generated tuned_params dict
        """
        logger.info("=== PHASE 4: DEPLOYMENT ===")
        logger.info(f"Generating tuned_params.json for {self.phase4_input.symbol}")
        
        # Build tuned_params structure
        tuned_params = {
            "symbol": self.phase4_input.symbol,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": self.version,
            "schema_version": "1.0",
            "comment": "Tuned parameters for all sessions. Updated via Phase 4 deployer.",
            
            "session_strategies": {},
            "metadata": {
                "symbol_config": self.symbol_config,
                "phase_pipeline": self._build_phase_pipeline(),
                "data_sources": {}
            }
        }
        
        # Add session strategies
        for session_name, phase3_output in self.phase4_input.validation_results.items():
            session_config = self._build_session_config(session_name, phase3_output)
            tuned_params["session_strategies"][session_name] = session_config
        
        # Validate schema
        validator = TunedParamsValidator(tuned_params)
        if not validator.validate():
            raise ValueError(f"Schema validation failed: {validator.errors}")
        
        # Save to file
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        save_tuned_params(tuned_params, str(output_path))
        
        logger.info(f"Phase 4 complete: tuned_params.json saved to {output_path}")
        
        # Log summary
        approved = self.phase4_input.get_approved_sessions()
        rejected = self.phase4_input.get_rejected_sessions()
        
        logger.info(f"  Approved sessions: {len(approved)} - {', '.join(approved)}")
        logger.info(f"  Rejected sessions: {len(rejected)} - {', '.join(rejected)}")
        
        return tuned_params
    
    def _build_session_config(
        self,
        session_name: str,
        phase3_output: Phase3Output
    ) -> Dict:
        """Build configuration for a single session."""
        
        if phase3_output.accepted:
            status = "APPROVED"
        else:
            status = "REJECTED"
        
        config = {
            "strategy_name": phase3_output.strategy_name if phase3_output.accepted else None,
            "strategy_type": phase3_output.strategy_name.split('_')[0].lower() if phase3_output.accepted else None,
            "status": status,
            "approval_timestamp": datetime.now(timezone.utc).isoformat() if phase3_output.accepted else None,
            
            "indicator_params": phase3_output.indicator_params or {},
            "entry_floors": phase3_output.entry_floors or {},
            "exit_params": phase3_output.exit_params or {},
            
            "lifecycle": {
                "baseline": {
                    "pf": phase3_output.baseline_pf,
                    "wr": phase3_output.baseline_wr,
                    "sharpe": 0.0,  # TODO: get from Phase 1
                    "trades": 0,  # TODO: get from Phase 1
                    "validation_date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
                },
                "tuned": {
                    "pf": phase3_output.tuned_pf,
                    "wr": phase3_output.tuned_wr,
                    "sharpe": 0.0,  # TODO: calculate
                    "trades": 0,  # TODO: count from backtest
                    "improvement_pct": phase3_output.improvement_pct,
                    "tuned_date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
                } if phase3_output.accepted else None,
                "live": {
                    "trades": 0,
                    "first_trade_date": None,
                    "last_update": datetime.now(timezone.utc).isoformat()
                }
            },
            
            "validation_result": {
                "accepted": phase3_output.accepted,
                "reason": phase3_output.acceptance_reason or phase3_output.rejection_reason,
                "validation_phase": "Phase 3 Walkforward",
                "validated_by": "Optuna"
            }
        }
        
        return config
    
    def _build_phase_pipeline(self) -> Dict:
        """Build phase pipeline metadata."""
        return {
            "phase_1_discovery": {
                "status": "COMPLETED",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            "phase_2_tuning": {
                "status": "COMPLETED",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            "phase_3_validation": {
                "status": "COMPLETED",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            "phase_4_deployment": {
                "status": "COMPLETED",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }


def run_phase4_deployment(
    phase4_input: Phase4Input,
    output_path: str,
    symbol_config: Optional[Dict] = None
) -> Dict:
    """
    Run Phase 4 deployment.
    
    Args:
        phase4_input: Phase4Input from Phase 3
        output_path: Path to write tuned_params.json
        symbol_config: Symbol configuration
    
    Returns:
        Generated tuned_params dict
    """
    logger.info("=== PHASE 4: DEPLOYMENT ===")
    
    deployer = Phase4Deployer(phase4_input, symbol_config)
    
    tuned_params = deployer.deploy(output_path)
    
    logger.info(
        f"Phase 4 complete: tuned_params.json ready for ScalpEngine"
    )
    
    return tuned_params


__all__ = [
    'Phase4Deployer',
    'run_phase4_deployment',
]
