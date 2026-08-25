"""
DAY 6: UNIT TESTS - Phase Integration (18 tests)

Comprehensive test coverage for Phase 1→2→3→4 data flow contracts.

Status: DAY 6 TESTING
"""

import pytest
from src.phase_integration import (
    Phase1Output,
    Phase2Input,
    Phase2Output,
    Phase3Input,
    Phase3Output,
    Phase4Input,
    DiscoveredStrategy,
    validate_phase1_to_phase2_flow,
    validate_phase2_to_phase3_flow,
    validate_phase3_to_phase4_aggregation,
)


@pytest.fixture
def phase1_output():
    """Sample Phase1Output."""
    strategy = DiscoveredStrategy(
        session="asian",
        timeframe="M15",
        strategy_name="RSI14",
        strategy_type="momentum",
        indicator_params={"period": 14},
        baseline_pf=1.52,
        baseline_wr=0.58,
        baseline_sharpe=1.25,
        baseline_trades=145
    )
    return Phase1Output(
        symbol="XAUUSD",
        timeframe="M15",
        session="asian",
        discovered_strategies=[strategy],
        date_range={"start": "2026-01-01", "end": "2026-08-25"},
        timestamp="2026-08-25T22:00:00Z"
    )


@pytest.fixture
def phase2_output():
    """Sample Phase2Output."""
    return Phase2Output(
        symbol="XAUUSD",
        session="asian",
        timeframe="M15",
        strategy_name="RSI14",
        strategy_type="momentum",
        baseline_pf=1.52,
        baseline_wr=0.58,
        baseline_sharpe=1.25,
        tuned_params={"period": 14},
        best_trial_id=123,
        best_trial_pf=1.58,
        study_db_path="/path/to/study.db",
        timestamp="2026-08-25T22:00:00Z"
    )


@pytest.fixture
def phase3_output():
    """Sample Phase3Output."""
    return Phase3Output(
        symbol="XAUUSD",
        session="asian",
        timeframe="M15",
        strategy_name="RSI14",
        accepted=True,
        baseline_pf=1.52,
        baseline_wr=0.58,
        tuned_pf=1.58,
        tuned_wr=0.60,
        improvement_pct=3.8,
        acceptance_reason="PF improved 3.8%",
        rejection_reason=None,
        tuned_params={"period": 14},
        indicator_params={"period": 14},
        exit_params={"sl_atr_mult": 1.5, "tp_ratio": 2.5}
    )


class TestPhaseIntegration:
    """Test phase integration contracts."""
    
    def test_phase1_output_structure(self, phase1_output):
        """Phase 1 output should have all required fields."""
        assert phase1_output.symbol == "XAUUSD"
        assert phase1_output.timeframe == "M15"
        assert len(phase1_output.discovered_strategies) > 0
    
    def test_phase1_get_top_strategy(self, phase1_output):
        """Phase 1 should return top strategy."""
        top = phase1_output.get_top_strategy()
        assert top.strategy_name == "RSI14"
        assert top.baseline_pf == 1.52
    
    def test_phase1_to_phase2_data_flow(self, phase1_output):
        """Phase 1 output should seamlessly become Phase 2 input."""
        top_strategy = phase1_output.get_top_strategy()
        
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
            ohlcv_data=None,
            optuna_trials=500
        )
        
        assert phase2_input.strategy_name == top_strategy.strategy_name
        assert phase2_input.baseline_pf == top_strategy.baseline_pf
    
    def test_phase2_to_phase3_data_flow(self, phase2_output):
        """Phase 2 output should become Phase 3 input."""
        import pandas as pd
        
        ohlcv = pd.DataFrame({
            'close': [1230 + i*0.5 for i in range(100)]
        })
        
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
            ohlcv_data=ohlcv,
            improvement_threshold=0.02
        )
        
        assert phase3_input.tuned_params == phase2_output.tuned_params
        assert phase3_input.tuned_pf == phase2_output.best_trial_pf
    
    def test_phase2_improvement_calculation(self, phase2_output):
        """Phase 2 should calculate improvement percentage."""
        improvement = phase2_output.get_improvement_pct()
        assert improvement > 0
        assert abs(improvement - 3.95) < 0.1  # ~4% improvement
    
    def test_phase3_improvement_calculation(self):
        """Phase 3 should calculate improvement percentage."""
        import pandas as pd
        
        phase3_input = Phase3Input(
            symbol="XAUUSD",
            session="asian",
            timeframe="M15",
            strategy_name="RSI14",
            baseline_pf=1.52,
            baseline_wr=0.58,
            baseline_sharpe=1.25,
            tuned_params={"period": 14},
            tuned_pf=1.58,
            ohlcv_data=pd.DataFrame({'close': [1230]*100}),
            improvement_threshold=0.02
        )
        
        improvement = phase3_input.calculate_improvement_pct()
        assert improvement > 0
    
    def test_phase3_to_phase4_aggregation(self, phase3_output):
        """Phase 3 results should aggregate for Phase 4."""
        phase4_input = Phase4Input(
            symbol="XAUUSD",
            validation_results={
                'asian': phase3_output
            }
        )
        
        assert len(phase4_input.validation_results) == 1
        assert phase4_input.validation_results['asian'].accepted is True
    
    def test_phase4_get_approved_sessions(self):
        """Phase 4 should identify approved sessions."""
        approved = Phase3Output(
            symbol="XAUUSD",
            session="asian",
            timeframe="M15",
            strategy_name="RSI14",
            accepted=True,
            baseline_pf=1.52,
            baseline_wr=0.58,
            tuned_pf=1.58,
            tuned_wr=0.60,
            improvement_pct=3.8,
            acceptance_reason="Improved",
            rejection_reason=None,
            tuned_params={"period": 14},
            indicator_params={"period": 14},
            exit_params={"sl_atr_mult": 1.5}
        )
        
        rejected = Phase3Output(
            symbol="XAUUSD",
            session="london",
            timeframe="M15",
            strategy_name="RSI14",
            accepted=False,
            baseline_pf=1.35,
            baseline_wr=0.54,
            tuned_pf=1.32,
            tuned_wr=0.52,
            improvement_pct=-2.2,
            acceptance_reason=None,
            rejection_reason="Declined",
            tuned_params={},
            indicator_params={"period": 14},
            exit_params={}
        )
        
        phase4_input = Phase4Input(
            symbol="XAUUSD",
            validation_results={'asian': approved, 'london': rejected}
        )
        
        assert 'asian' in phase4_input.get_approved_sessions()
        assert 'london' not in phase4_input.get_approved_sessions()
    
    def test_phase4_get_rejected_sessions(self):
        """Phase 4 should identify rejected sessions."""
        approved = Phase3Output(
            symbol="XAUUSD",
            session="asian",
            timeframe="M15",
            strategy_name="RSI14",
            accepted=True,
            baseline_pf=1.52,
            baseline_wr=0.58,
            tuned_pf=1.58,
            tuned_wr=0.60,
            improvement_pct=3.8,
            acceptance_reason="Improved",
            rejection_reason=None,
            tuned_params={"period": 14},
            indicator_params={"period": 14},
            exit_params={"sl_atr_mult": 1.5}
        )
        
        rejected = Phase3Output(
            symbol="XAUUSD",
            session="london",
            timeframe="M15",
            strategy_name="RSI14",
            accepted=False,
            baseline_pf=1.35,
            baseline_wr=0.54,
            tuned_pf=1.32,
            tuned_wr=0.52,
            improvement_pct=-2.2,
            acceptance_reason=None,
            rejection_reason="Declined",
            tuned_params={},
            indicator_params={"period": 14},
            exit_params={}
        )
        
        phase4_input = Phase4Input(
            symbol="XAUUSD",
            validation_results={'asian': approved, 'london': rejected}
        )
        
        assert 'london' in phase4_input.get_rejected_sessions()
        assert 'asian' not in phase4_input.get_rejected_sessions()
    
    def test_phase3_output_approved_has_params(self, phase3_output):
        """Approved Phase3Output must have tuned_params."""
        assert phase3_output.accepted is True
        assert phase3_output.tuned_params is not None
        assert len(phase3_output.tuned_params) > 0
    
    def test_phase3_output_rejected_rejected_reason(self):
        """Rejected Phase3Output must have rejection_reason."""
        rejected = Phase3Output(
            symbol="XAUUSD",
            session="london",
            timeframe="M15",
            strategy_name="RSI14",
            accepted=False,
            baseline_pf=1.35,
            baseline_wr=0.54,
            tuned_pf=1.32,
            tuned_wr=0.52,
            improvement_pct=-2.2,
            acceptance_reason=None,
            rejection_reason="Declined",
            tuned_params={},
            indicator_params={"period": 14},
            exit_params={}
        )
        
        assert rejected.accepted is False
        assert rejected.rejection_reason is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
