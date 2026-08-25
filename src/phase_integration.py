"""
Phase Integration Layer - Data Flow Contracts

Defines dataclasses for Phase 1→2→3→4 integration.
Ensures seamless data transformation across all phases.

Status: IMPLEMENTATION (Day 3)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd


# ============================================================================
# PHASE 1: DISCOVERY OUTPUT
# ============================================================================

@dataclass
class DiscoveredStrategy:
    """Single strategy discovered by Phase 1 vectorbt backtest."""
    
    session: str                          # e.g., "asian", "london", "newyork"
    timeframe: str                        # e.g., "M15", "H1"
    strategy_name: str                    # e.g., "RSI14", "OsMA_Confluence"
    strategy_type: str                    # e.g., "momentum", "confluence", "volatility"
    indicator_params: Dict[str, float]    # Strategy-specific params (e.g., {"period": 14})
    
    baseline_pf: float                    # Profit Factor from vectorbt backtest
    baseline_wr: float                    # Win Rate (0.0-1.0)
    baseline_sharpe: float                # Sharpe Ratio
    baseline_trades: int                  # Number of trades in backtest
    
    def __post_init__(self):
        """Validate discovered strategy."""
        if self.baseline_pf < 1.0:
            raise ValueError(f"{self.strategy_name}: baseline PF {self.baseline_pf} < 1.0 (not profitable)")
        if not (0 < self.baseline_wr < 1.0):
            raise ValueError(f"{self.strategy_name}: baseline WR {self.baseline_wr} not in (0, 1)")
        if self.baseline_trades < 10:
            raise ValueError(f"{self.strategy_name}: only {self.baseline_trades} trades (need >= 10)")


@dataclass
class Phase1Output:
    """Phase 1 discovery output - top strategies per session."""
    
    symbol: str                                    # e.g., "XAUUSD"
    timeframe: str                                 # e.g., "M15"
    session: str                                   # Single session being tested
    discovered_strategies: List[DiscoveredStrategy]  # Ranked by PF (highest first)
    date_range: Dict[str, str]                     # {"start": "2026-01-01", "end": "2026-08-25"}
    timestamp: str                                 # ISO format: "2026-08-25T22:00:00Z"
    
    def __post_init__(self):
        """Validate phase 1 output."""
        if not self.discovered_strategies:
            raise ValueError(f"Phase 1 found no strategies for {self.symbol}/{self.session}/{self.timeframe}")
        
        # Verify strategies are ranked by PF
        pf_values = [s.baseline_pf for s in self.discovered_strategies]
        if pf_values != sorted(pf_values, reverse=True):
            raise ValueError("Discovered strategies not ranked by PF (highest first)")
    
    def get_top_strategy(self) -> DiscoveredStrategy:
        """Return the best-performing discovered strategy."""
        return self.discovered_strategies[0]


# ============================================================================
# PHASE 2: TUNING INPUT & OUTPUT
# ============================================================================

@dataclass
class Phase2Input:
    """Phase 2 tuning input - receives Phase 1 top strategy."""
    
    symbol: str
    session: str
    timeframe: str
    strategy_name: str                   # FROM Phase 1
    strategy_type: str                   # FROM Phase 1
    indicator_params: Dict[str, float]   # FROM Phase 1 (starting params)
    
    baseline_pf: float                   # FROM Phase 1 (baseline to beat)
    baseline_wr: float                   # FROM Phase 1
    baseline_sharpe: float               # FROM Phase 1
    baseline_trades: int                 # FROM Phase 1
    
    ohlcv_data: pd.DataFrame             # Historical OHLCV for tuning
    optuna_trials: int = 500             # Config: number of trials
    
    def __post_init__(self):
        """Validate Phase 2 input."""
        if self.ohlcv_data is None or len(self.ohlcv_data) == 0:
            raise ValueError(f"Phase 2 input: no OHLCV data")
        if len(self.ohlcv_data) < 100:
            raise ValueError(f"Phase 2 input: only {len(self.ohlcv_data)} bars (need >= 100)")
        if not all(col in self.ohlcv_data.columns for col in ['open', 'high', 'low', 'close', 'volume']):
            raise ValueError("Phase 2 input: OHLCV missing required columns")
    
    def get_phase1_baseline(self) -> Dict:
        """Return Phase 1 baseline metrics."""
        return {
            'pf': self.baseline_pf,
            'wr': self.baseline_wr,
            'sharpe': self.baseline_sharpe,
            'trades': self.baseline_trades
        }


@dataclass
class Phase2Output:
    """Phase 2 tuning output - optimized parameters from Optuna."""
    
    symbol: str
    session: str
    timeframe: str
    strategy_name: str
    strategy_type: str
    
    baseline_pf: float                   # FROM Phase 1 (for comparison)
    baseline_wr: float                   # FROM Phase 1
    baseline_sharpe: float               # FROM Phase 1
    
    tuned_params: Dict[str, float]       # Optimized parameters from Optuna
    best_trial_id: int                   # Which trial was best
    best_trial_pf: float                 # PF achieved with tuned params
    
    study_db_path: str                   # Path to Optuna SQLite DB
    timestamp: str                       # ISO format
    
    def __post_init__(self):
        """Validate Phase 2 output."""
        if not self.tuned_params:
            raise ValueError(f"Phase 2 output: no tuned_params")
        if self.best_trial_pf < 1.0:
            raise ValueError(f"Phase 2 output: best_trial_pf {self.best_trial_pf} < 1.0 (not profitable)")
    
    def get_improvement_pct(self) -> float:
        """Calculate % improvement from baseline to tuned."""
        if self.baseline_pf == 0:
            return 0.0
        return ((self.best_trial_pf - self.baseline_pf) / self.baseline_pf) * 100


# ============================================================================
# PHASE 3: VALIDATION INPUT & OUTPUT
# ============================================================================

@dataclass
class Phase3Input:
    """Phase 3 validation input - receives Phase 2 tuned params."""
    
    symbol: str
    session: str
    timeframe: str
    strategy_name: str
    
    baseline_pf: float                   # FROM Phase 1
    baseline_wr: float                   # FROM Phase 1
    baseline_sharpe: float               # FROM Phase 1
    
    tuned_params: Dict[str, float]       # FROM Phase 2 (tuned by Optuna)
    tuned_pf: float                      # FROM Phase 2 (best_trial_pf)
    
    ohlcv_data: pd.DataFrame             # For walkforward validation
    improvement_threshold: float = 0.02  # Minimum +2% improvement required
    
    def __post_init__(self):
        """Validate Phase 3 input."""
        if self.ohlcv_data is None or len(self.ohlcv_data) < 50:
            raise ValueError(f"Phase 3: insufficient OHLCV for validation")
        if not self.tuned_params:
            raise ValueError(f"Phase 3: no tuned_params from Phase 2")
    
    def calculate_improvement_pct(self) -> float:
        """Calculate % improvement for comparison."""
        if self.baseline_pf == 0:
            return 0.0
        return ((self.tuned_pf - self.baseline_pf) / self.baseline_pf) * 100


@dataclass
class Phase3Output:
    """Phase 3 validation output - accept or reject tuned strategy."""
    
    symbol: str
    session: str
    timeframe: str
    strategy_name: str
    
    accepted: bool                       # APPROVED or REJECTED
    
    baseline_pf: float
    baseline_wr: float
    
    tuned_pf: float
    tuned_wr: float
    
    improvement_pct: float               # (tuned_pf - baseline_pf) / baseline_pf * 100
    
    acceptance_reason: Optional[str]     # e.g., "PF improved 3.8%"
    rejection_reason: Optional[str]      # e.g., "PF declined 1.2%"
    
    tuned_params: Dict[str, float]       # ONLY populated if accepted
    indicator_params: Dict[str, float]   # Full indicator config
    exit_params: Dict[str, float]        # Exit config
    entry_floors: Optional[Dict] = None  # Entry strength floors
    
    def __post_init__(self):
        """Validate Phase 3 output."""
        if self.accepted:
            if not self.tuned_params:
                raise ValueError(f"Phase 3 output: accepted but no tuned_params")
            if not self.acceptance_reason:
                raise ValueError(f"Phase 3 output: accepted but no acceptance_reason")
        else:
            if not self.rejection_reason:
                raise ValueError(f"Phase 3 output: rejected but no rejection_reason")
    
    def is_approved(self) -> bool:
        """Check if this result is approved for deployment."""
        return self.accepted


# ============================================================================
# PHASE 4: DEPLOYMENT INPUT
# ============================================================================

@dataclass
class Phase4Input:
    """Phase 4 deployment input - receives ALL Phase 3 validation results."""
    
    symbol: str
    validation_results: Dict[str, Phase3Output]  # Per-session results
    # Example:
    # {
    #   "asian": Phase3Output(..., accepted=True),
    #   "london": Phase3Output(..., accepted=True),
    #   "newyork": Phase3Output(..., accepted=False),
    #   ...
    # }
    
    def __post_init__(self):
        """Validate Phase 4 input."""
        if not self.validation_results:
            raise ValueError("Phase 4 input: no validation results")
    
    def get_approved_sessions(self) -> List[str]:
        """Return list of approved sessions."""
        return [
            session for session, result in self.validation_results.items()
            if result.is_approved()
        ]
    
    def get_rejected_sessions(self) -> List[str]:
        """Return list of rejected sessions."""
        return [
            session for session, result in self.validation_results.items()
            if not result.is_approved()
        ]


# ============================================================================
# LIVE TRADING: SCALPENGINE INPUT
# ============================================================================

@dataclass
class StrategyConfig:
    """Configuration for a strategy in live trading."""
    
    strategy_name: str                   # e.g., "RSI14"
    strategy_type: str                   # e.g., "momentum"
    indicator_params: Dict[str, float]   # FROM tuned_params.json
    entry_floors: Dict[str, float]       # Entry strength floors
    exit_params: Dict[str, float]        # Exit configuration
    
    baseline_pf: float                   # Reference baseline
    tuned_pf: float                      # Tuned performance


# ============================================================================
# INTEGRATION VALIDATION
# ============================================================================

def validate_phase1_to_phase2_flow(phase1: Phase1Output) -> Phase2Input:
    """
    Convert Phase 1 output to Phase 2 input.
    Validates all required fields are present.
    """
    top_strategy = phase1.get_top_strategy()
    
    phase2_input = Phase2Input(
        symbol=phase1.symbol,
        session=phase1.session,
        timeframe=phase1.timeframe,
        strategy_name=top_strategy.strategy_name,
        strategy_type=top_strategy.strategy_type,
        indicator_params=top_strategy.indicator_params,
        baseline_pf=top_strategy.baseline_pf,
        baseline_wr=top_strategy.baseline_wr,
        baseline_sharpe=top_strategy.baseline_sharpe,
        baseline_trades=top_strategy.baseline_trades,
        ohlcv_data=None,  # Will be populated by Phase 2 loader
        optuna_trials=500
    )
    
    return phase2_input


def validate_phase2_to_phase3_flow(phase2: Phase2Output, ohlcv_data: pd.DataFrame) -> Phase3Input:
    """
    Convert Phase 2 output to Phase 3 input.
    Validates all required fields are present.
    """
    phase3_input = Phase3Input(
        symbol=phase2.symbol,
        session=phase2.session,
        timeframe=phase2.timeframe,
        strategy_name=phase2.strategy_name,
        baseline_pf=phase2.baseline_pf,
        baseline_wr=phase2.baseline_wr,
        baseline_sharpe=phase2.baseline_sharpe,
        tuned_params=phase2.tuned_params,
        tuned_pf=phase2.best_trial_pf,
        ohlcv_data=ohlcv_data,
        improvement_threshold=0.02
    )
    
    return phase3_input


def validate_phase3_to_phase4_aggregation(
    results_per_session: Dict[str, Phase3Output]
) -> Phase4Input:
    """
    Aggregate Phase 3 results (per session) into Phase 4 input.
    """
    # All results should have the same symbol
    symbols = set(r.symbol for r in results_per_session.values())
    if len(symbols) > 1:
        raise ValueError(f"Phase 3→4: Multiple symbols in results: {symbols}")
    
    symbol = symbols.pop()
    
    phase4_input = Phase4Input(
        symbol=symbol,
        validation_results=results_per_session
    )
    
    return phase4_input


# ============================================================================
# METADATA
# ============================================================================

@dataclass
class PipelineMetadata:
    """Metadata for the entire pipeline run."""
    
    symbol: str
    timeframe: str
    sessions: List[str]                  # Sessions being tested
    
    phase_1_completed_at: Optional[datetime] = None
    phase_2_completed_at: Optional[datetime] = None
    phase_3_completed_at: Optional[datetime] = None
    phase_4_completed_at: Optional[datetime] = None
    
    approved_strategies: int = 0
    rejected_strategies: int = 0
    
    def mark_phase_1_complete(self):
        """Mark Phase 1 as complete."""
        self.phase_1_completed_at = datetime.now()
    
    def mark_phase_2_complete(self):
        """Mark Phase 2 as complete."""
        self.phase_2_completed_at = datetime.now()
    
    def mark_phase_3_complete(self, approved: int, rejected: int):
        """Mark Phase 3 as complete with approval counts."""
        self.phase_3_completed_at = datetime.now()
        self.approved_strategies = approved
        self.rejected_strategies = rejected
    
    def mark_phase_4_complete(self):
        """Mark Phase 4 as complete."""
        self.phase_4_completed_at = datetime.now()


__all__ = [
    'DiscoveredStrategy',
    'Phase1Output',
    'Phase2Input',
    'Phase2Output',
    'Phase3Input',
    'Phase3Output',
    'Phase4Input',
    'StrategyConfig',
    'PipelineMetadata',
    'validate_phase1_to_phase2_flow',
    'validate_phase2_to_phase3_flow',
    'validate_phase3_to_phase4_aggregation',
]
