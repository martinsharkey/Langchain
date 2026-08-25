"""
Unified Schema Validator - tuned_params.json Validation

Validates and loads the unified parameter schema for live trading.

Status: IMPLEMENTATION (Day 3)
"""

import json
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Any
from pathlib import Path


@dataclass
class BaselineMetrics:
    """Baseline strategy metrics from discovery."""
    pf: float
    wr: float
    sharpe: float
    trades: int
    validation_date: str


@dataclass
class TunedMetrics:
    """Tuned strategy metrics from Optuna."""
    pf: float
    wr: float
    sharpe: float
    trades: int
    improvement_pct: float
    tuned_date: str


@dataclass
class LiveMetrics:
    """Live trading metrics."""
    trades: int
    first_trade_date: Optional[str]
    last_update: str


@dataclass
class Lifecycle:
    """Complete lifecycle: baseline → tuned → live."""
    baseline: Optional[Dict[str, Any]]
    tuned: Optional[Dict[str, Any]]
    live: Dict[str, Any]


@dataclass
class ValidationResult:
    """Result of Phase 3 validation."""
    accepted: bool
    reason: str
    validation_phase: Optional[str]
    validated_by: Optional[str]


@dataclass
class SessionConfig:
    """Configuration for a single session."""
    
    strategy_name: Optional[str]
    strategy_type: Optional[str]
    status: str  # "APPROVED", "REJECTED", "NO_STRATEGY"
    approval_timestamp: Optional[str]
    
    indicator_params: Dict[str, float]
    entry_floors: Dict[str, float]
    exit_params: Dict[str, float]
    
    lifecycle: Lifecycle
    validation_result: ValidationResult
    
    def is_approved(self) -> bool:
        """Check if session is approved."""
        return self.status == "APPROVED"
    
    def can_trade(self) -> bool:
        """Check if session is ready for live trading."""
        return (
            self.is_approved() and
            self.strategy_name is not None and
            self.indicator_params and
            self.exit_params
        )


class TunedParamsValidator:
    """Validator for tuned_params.json schema."""
    
    # Schema version this validator supports
    SUPPORTED_SCHEMA_VERSIONS = ["1.0"]
    
    def __init__(self, data: Dict[str, Any]):
        """Initialize validator with parsed JSON data."""
        self.data = data
        self.errors = []
    
    def validate(self) -> bool:
        """
        Validate entire tuned_params.json.
        
        Returns:
            True if valid, False otherwise
        
        Side Effects:
            Populates self.errors with validation messages
        """
        self.errors = []
        
        # Check top-level fields
        self._validate_top_level()
        
        # Check session_strategies
        self._validate_session_strategies()
        
        # Check metadata
        self._validate_metadata()
        
        return len(self.errors) == 0
    
    def _validate_top_level(self):
        """Validate top-level fields."""
        required = ['symbol', 'generated_at', 'version', 'session_strategies', 'metadata']
        for field in required:
            if field not in self.data:
                self.errors.append(f"Missing top-level field: {field}")
        
        if 'schema_version' in self.data:
            if self.data['schema_version'] not in self.SUPPORTED_SCHEMA_VERSIONS:
                self.errors.append(
                    f"Unsupported schema_version: {self.data['schema_version']}"
                )
    
    def _validate_session_strategies(self):
        """Validate session_strategies dict."""
        if 'session_strategies' not in self.data:
            self.errors.append("Missing session_strategies")
            return
        
        strategies = self.data['session_strategies']
        if not isinstance(strategies, dict):
            self.errors.append("session_strategies must be dict")
            return
        
        # Expected sessions
        expected_sessions = [
            'asian', 'london', 'newyork', 'overlap_london_ny',
            'friday_evening', 'weekend_saturday', 'sunday_trading'
        ]
        
        for session in expected_sessions:
            if session not in strategies:
                self.errors.append(f"Missing session: {session}")
        
        # Validate each session
        for session_name, session_config in strategies.items():
            self._validate_session_config(session_name, session_config)
    
    def _validate_session_config(self, session_name: str, config: dict):
        """Validate single session configuration."""
        # Required fields for all sessions
        required = ['status', 'indicator_params', 'entry_floors', 'exit_params', 'lifecycle', 'validation_result']
        for field in required:
            if field not in config:
                self.errors.append(f"{session_name}: missing field {field}")
        
        # Check status
        status = config.get('status')
        if status not in ['APPROVED', 'REJECTED', 'NO_STRATEGY']:
            self.errors.append(f"{session_name}: invalid status {status}")
        
        # If APPROVED, must have strategy_name and params
        if status == 'APPROVED':
            if not config.get('strategy_name'):
                self.errors.append(f"{session_name}: APPROVED but no strategy_name")
            if not config.get('indicator_params'):
                self.errors.append(f"{session_name}: APPROVED but empty indicator_params")
            if not config.get('exit_params'):
                self.errors.append(f"{session_name}: APPROVED but empty exit_params")
            
            # Must have baseline and tuned metrics
            lifecycle = config.get('lifecycle', {})
            if not lifecycle.get('baseline'):
                self.errors.append(f"{session_name}: APPROVED but no baseline metrics")
            if not lifecycle.get('tuned'):
                self.errors.append(f"{session_name}: APPROVED but no tuned metrics")
            
            # Validate metrics
            baseline = lifecycle.get('baseline', {})
            if baseline.get('pf', 0) < 1.0:
                self.errors.append(f"{session_name}: baseline PF {baseline.get('pf')} < 1.0")
            
            tuned = lifecycle.get('tuned', {})
            if tuned.get('pf', 0) < baseline.get('pf', 0):
                self.errors.append(f"{session_name}: tuned PF worse than baseline")
        
        # If REJECTED, must have rejection reason
        if status == 'REJECTED':
            validation_result = config.get('validation_result', {})
            if not validation_result.get('reason'):
                self.errors.append(f"{session_name}: REJECTED but no reason")
        
        # Validate lifecycle.live
        lifecycle = config.get('lifecycle', {})
        live = lifecycle.get('live', {})
        if not isinstance(live.get('trades'), int) or live.get('trades') < 0:
            self.errors.append(f"{session_name}: invalid live.trades")
    
    def _validate_metadata(self):
        """Validate metadata section."""
        if 'metadata' not in self.data:
            self.errors.append("Missing metadata")
            return
        
        metadata = self.data['metadata']
        
        # Check phase_pipeline if present
        if 'phase_pipeline' in metadata:
            pipeline = metadata['phase_pipeline']
            for phase in ['phase_1_discovery', 'phase_2_tuning', 'phase_3_validation', 'phase_4_deployment']:
                if phase in pipeline:
                    phase_info = pipeline[phase]
                    if 'status' in phase_info:
                        if phase_info['status'] not in ['COMPLETED', 'FAILED', 'PENDING']:
                            self.errors.append(f"Invalid phase status: {phase_info['status']}")
    
    def get_approved_sessions(self) -> list:
        """Return list of approved sessions."""
        approved = []
        strategies = self.data.get('session_strategies', {})
        for session_name, config in strategies.items():
            if config.get('status') == 'APPROVED':
                approved.append(session_name)
        return approved
    
    def get_session_config(self, session_name: str) -> Optional[SessionConfig]:
        """Get parsed SessionConfig for a session."""
        strategies = self.data.get('session_strategies', {})
        if session_name not in strategies:
            return None
        
        config = strategies[session_name]
        
        return SessionConfig(
            strategy_name=config.get('strategy_name'),
            strategy_type=config.get('strategy_type'),
            status=config.get('status'),
            approval_timestamp=config.get('approval_timestamp'),
            indicator_params=config.get('indicator_params', {}),
            entry_floors=config.get('entry_floors', {}),
            exit_params=config.get('exit_params', {}),
            lifecycle=Lifecycle(
                baseline=config.get('lifecycle', {}).get('baseline'),
                tuned=config.get('lifecycle', {}).get('tuned'),
                live=config.get('lifecycle', {}).get('live', {})
            ),
            validation_result=ValidationResult(
                accepted=config.get('validation_result', {}).get('accepted', False),
                reason=config.get('validation_result', {}).get('reason', ''),
                validation_phase=config.get('validation_result', {}).get('validation_phase'),
                validated_by=config.get('validation_result', {}).get('validated_by')
            )
        )


def load_tuned_params(filepath: str) -> Dict[str, Any]:
    """
    Load tuned_params.json and validate schema.
    
    Args:
        filepath: path to tuned_params.json
    
    Returns:
        Parsed JSON data
    
    Raises:
        FileNotFoundError: if file not found
        json.JSONDecodeError: if JSON invalid
        ValueError: if schema invalid
    """
    filepath = Path(filepath)
    
    if not filepath.exists():
        raise FileNotFoundError(f"tuned_params.json not found: {filepath}")
    
    with open(filepath) as f:
        data = json.load(f)
    
    # Validate schema
    validator = TunedParamsValidator(data)
    if not validator.validate():
        raise ValueError(f"Schema validation failed: {validator.errors}")
    
    return data


def get_strategy_for_session(filepath: str, session_name: str) -> Optional[Dict[str, Any]]:
    """
    Load strategy config for a specific session.
    
    Args:
        filepath: path to tuned_params.json
        session_name: session name (e.g., "asian", "london")
    
    Returns:
        Strategy config dict if approved, None otherwise
    
    Raises:
        FileNotFoundError: if file not found
        ValueError: if session not found
    """
    data = load_tuned_params(filepath)
    
    strategies = data.get('session_strategies', {})
    if session_name not in strategies:
        raise ValueError(f"Session not found: {session_name}")
    
    config = strategies[session_name]
    
    if config.get('status') != 'APPROVED':
        return None
    
    return {
        'strategy_name': config.get('strategy_name'),
        'strategy_type': config.get('strategy_type'),
        'indicator_params': config.get('indicator_params'),
        'entry_floors': config.get('entry_floors'),
        'exit_params': config.get('exit_params'),
        'baseline_pf': config.get('lifecycle', {}).get('baseline', {}).get('pf'),
        'tuned_pf': config.get('lifecycle', {}).get('tuned', {}).get('pf'),
    }


def save_tuned_params(data: Dict[str, Any], filepath: str) -> None:
    """
    Save and validate tuned_params.json.
    
    Args:
        data: parsed tuned params dict
        filepath: path to write to
    
    Raises:
        ValueError: if schema invalid
    """
    # Validate before saving
    validator = TunedParamsValidator(data)
    if not validator.validate():
        raise ValueError(f"Schema validation failed: {validator.errors}")
    
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)


__all__ = [
    'TunedParamsValidator',
    'SessionConfig',
    'BaselineMetrics',
    'TunedMetrics',
    'LiveMetrics',
    'Lifecycle',
    'ValidationResult',
    'load_tuned_params',
    'get_strategy_for_session',
    'save_tuned_params',
]
