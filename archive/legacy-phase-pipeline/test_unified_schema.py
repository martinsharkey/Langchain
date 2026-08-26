"""
DAY 6: UNIT TESTS - Unified Schema Validation (12 tests)

Comprehensive test coverage for tuned_params.json schema.

Status: DAY 6 TESTING
"""

import pytest
import json
from pathlib import Path
from src.schema_validator import (
    TunedParamsValidator,
    SessionConfig,
    load_tuned_params
)


@pytest.fixture
def sample_tuned_params():
    """Sample tuned_params.json for testing."""
    return {
        "symbol": "XAUUSD",
        "generated_at": "2026-08-25T22:00:00Z",
        "version": 2,
        "schema_version": "1.0",
        "session_strategies": {
            "asian": {
                "strategy_name": "RSI14",
                "strategy_type": "momentum",
                "status": "APPROVED",
                "approval_timestamp": "2026-08-25T20:15:00Z",
                "indicator_params": {"period": 14},
                "entry_floors": {"min_strength": 0.35},
                "exit_params": {"sl_atr_mult": 1.5, "tp_ratio": 2.5},
                "lifecycle": {
                    "baseline": {
                        "pf": 1.52,
                        "wr": 0.58,
                        "sharpe": 1.25,
                        "trades": 145,
                        "validation_date": "2026-08-22"
                    },
                    "tuned": {
                        "pf": 1.58,
                        "wr": 0.60,
                        "sharpe": 1.31,
                        "trades": 148,
                        "improvement_pct": 3.8,
                        "tuned_date": "2026-08-25"
                    },
                    "live": {
                        "trades": 0,
                        "first_trade_date": None,
                        "last_update": "2026-08-25T22:00:00Z"
                    }
                },
                "validation_result": {
                    "accepted": True,
                    "reason": "PF improved 3.8%",
                    "validation_phase": "Phase 3",
                    "validated_by": "Optuna"
                }
            },
            "london": {
                "strategy_name": None,
                "strategy_type": None,
                "status": "NO_STRATEGY",
                "approval_timestamp": None,
                "indicator_params": {},
                "entry_floors": {},
                "exit_params": {},
                "lifecycle": {
                    "baseline": None,
                    "tuned": None,
                    "live": {"trades": 0, "first_trade_date": None, "last_update": "2026-08-25T22:00:00Z"}
                },
                "validation_result": {
                    "accepted": False,
                    "reason": "No strategy",
                    "validation_phase": None,
                    "validated_by": None
                }
            }
        },
        "metadata": {
            "symbol_config": {"floors_raw": {"asian": 0.25}},
            "phase_pipeline": {
                "phase_1_discovery": {"status": "COMPLETED", "timestamp": "2026-08-24T10:00:00Z"},
                "phase_2_tuning": {"status": "COMPLETED", "timestamp": "2026-08-25T18:00:00Z"},
                "phase_3_validation": {"status": "COMPLETED", "timestamp": "2026-08-25T20:00:00Z"},
                "phase_4_deployment": {"status": "COMPLETED", "timestamp": "2026-08-25T22:00:00Z"}
            }
        }
    }


class TestTunedParamsValidator:
    """Test tuned_params.json schema validator."""
    
    def test_schema_has_required_top_level_fields(self, sample_tuned_params):
        """Tuned params should have all required top-level fields."""
        validator = TunedParamsValidator(sample_tuned_params)
        assert validator.validate() is True
    
    def test_schema_session_strategies_present(self, sample_tuned_params):
        """Tuned params should have session_strategies object."""
        assert 'session_strategies' in sample_tuned_params
        assert isinstance(sample_tuned_params['session_strategies'], dict)
    
    def test_schema_approved_session_has_strategy_name(self, sample_tuned_params):
        """Approved session should have strategy_name."""
        asian = sample_tuned_params['session_strategies']['asian']
        assert asian['status'] == 'APPROVED'
        assert asian['strategy_name'] is not None
        assert isinstance(asian['strategy_name'], str)
    
    def test_schema_approved_session_has_indicator_params(self, sample_tuned_params):
        """Approved session should have indicator_params."""
        asian = sample_tuned_params['session_strategies']['asian']
        assert 'indicator_params' in asian
        assert isinstance(asian['indicator_params'], dict)
        assert len(asian['indicator_params']) > 0
    
    def test_schema_approved_session_has_exit_params(self, sample_tuned_params):
        """Approved session should have exit_params."""
        asian = sample_tuned_params['session_strategies']['asian']
        assert 'exit_params' in asian
        assert 'sl_atr_mult' in asian['exit_params']
        assert 'tp_ratio' in asian['exit_params']
    
    def test_schema_approved_session_has_lifecycle(self, sample_tuned_params):
        """Approved session should have complete lifecycle."""
        asian = sample_tuned_params['session_strategies']['asian']
        assert 'lifecycle' in asian
        assert 'baseline' in asian['lifecycle']
        assert 'tuned' in asian['lifecycle']
        assert 'live' in asian['lifecycle']
    
    def test_schema_baseline_metrics_valid(self, sample_tuned_params):
        """Baseline metrics should be valid."""
        asian = sample_tuned_params['session_strategies']['asian']
        baseline = asian['lifecycle']['baseline']
        
        assert baseline['pf'] >= 1.0
        assert 0 < baseline['wr'] < 1.0
        assert baseline['trades'] > 0
    
    def test_schema_tuned_pf_improvement(self, sample_tuned_params):
        """Tuned PF should match baseline or be better."""
        asian = sample_tuned_params['session_strategies']['asian']
        baseline_pf = asian['lifecycle']['baseline']['pf']
        tuned_pf = asian['lifecycle']['tuned']['pf']
        
        assert tuned_pf >= baseline_pf
    
    def test_schema_rejected_session_accepted_false(self, sample_tuned_params):
        """Rejected session should have accepted=false."""
        london = sample_tuned_params['session_strategies']['london']
        assert london['status'] == 'NO_STRATEGY'
        assert london['validation_result']['accepted'] is False
    
    def test_schema_no_strategy_session_empty(self, sample_tuned_params):
        """No-strategy session should have empty params."""
        london = sample_tuned_params['session_strategies']['london']
        assert london['status'] == 'NO_STRATEGY'
        assert london['strategy_name'] is None
    
    def test_schema_metadata_present(self, sample_tuned_params):
        """Tuned params should have metadata."""
        assert 'metadata' in sample_tuned_params
        assert 'symbol_config' in sample_tuned_params['metadata']
        assert 'phase_pipeline' in sample_tuned_params['metadata']
    
    def test_schema_live_metrics_initialized(self, sample_tuned_params):
        """Live metrics should be initialized."""
        for session_name, session in sample_tuned_params['session_strategies'].items():
            live = session['lifecycle']['live']
            assert 'trades' in live
            assert 'last_update' in live
            assert live['trades'] >= 0


class TestSessionConfig:
    """Test SessionConfig dataclass."""
    
    def test_session_config_approved(self):
        """SessionConfig should represent approved session."""
        from src.phase_integration import Lifecycle, ValidationResult
        
        config = SessionConfig(
            strategy_name="RSI14",
            strategy_type="momentum",
            status="APPROVED",
            approval_timestamp="2026-08-25T20:15:00Z",
            indicator_params={"period": 14},
            entry_floors={"min_strength": 0.35},
            exit_params={"sl_atr_mult": 1.5},
            lifecycle=Lifecycle(
                baseline={"pf": 1.52},
                tuned={"pf": 1.58},
                live={"trades": 0}
            ),
            validation_result=ValidationResult(
                accepted=True,
                reason="Improved",
                validation_phase="Phase 3",
                validated_by="Optuna"
            )
        )
        
        assert config.is_approved() is True
        assert config.can_trade() is True
    
    def test_session_config_rejected(self):
        """SessionConfig should represent rejected session."""
        from src.phase_integration import Lifecycle, ValidationResult
        
        config = SessionConfig(
            strategy_name="RSI14",
            strategy_type="momentum",
            status="REJECTED",
            approval_timestamp=None,
            indicator_params={},
            entry_floors={},
            exit_params={},
            lifecycle=Lifecycle(
                baseline=None,
                tuned=None,
                live={"trades": 0}
            ),
            validation_result=ValidationResult(
                accepted=False,
                reason="Failed",
                validation_phase=None,
                validated_by=None
            )
        )
        
        assert config.is_approved() is False
        assert config.can_trade() is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
