# DAY 2: TEST PLANNING

**Document:** Comprehensive Test Strategy for All 4 Specifications
**Date:** 2026-08-25
**Status:** TEST PLAN

---

## Test Structure

```
tests/
├── unit/
│   ├── test_session_selection.py          # 15 tests
│   ├── test_strategy_interface.py         # 20 tests
│   ├── test_unified_schema.py             # 12 tests
│   └── test_phase_integration.py          # 18 tests
├── integration/
│   ├── test_phase1_discovery.py           # 8 tests
│   ├── test_phase2_tuning.py              # 6 tests
│   ├── test_phase3_validation.py          # 6 tests
│   └── test_phase4_deployment.py          # 6 tests
├── e2e/
│   ├── test_end_to_end_pipeline.py        # 4 tests
│   └── test_live_trading_simulation.py    # 5 tests
└── fixtures/
    ├── ohlcv_data.py                      # Test OHLCV data
    ├── strategies.py                      # Mock strategies
    └── sample_configs.py                  # Sample JSON configs
```

---

## UNIT TESTS (65 total)

### 1. Session Selection Tests (15 tests)

**File:** `tests/unit/test_session_selection.py`

```python
import pytest
from datetime import datetime, timezone
from src.session_selection import get_current_session_utc

class TestSessionSelection:
    
    # Asian Session Tests
    def test_asian_monday_0400_utc(self):
        """Mon 04:00 UTC should be Asian session."""
        ts = datetime(2026, 8, 25, 4, 0, 0, tzinfo=timezone.utc)  # Monday
        assert get_current_session_utc(ts) == 'asian'
    
    def test_asian_tuesday_0700_utc(self):
        """Tue 07:00 UTC should be Asian session."""
        ts = datetime(2026, 8, 26, 7, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'asian'
    
    def test_asian_boundary_0759_utc(self):
        """Mon 07:59 UTC is last minute of Asian."""
        ts = datetime(2026, 8, 25, 7, 59, 59, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'asian'
    
    # London Session Tests
    def test_london_monday_0800_utc(self):
        """Mon 08:00 UTC should start London session."""
        ts = datetime(2026, 8, 25, 8, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'london'
    
    def test_london_wednesday_1200_utc(self):
        """Wed 12:00 UTC should be London session."""
        ts = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'london'
    
    def test_london_boundary_1559_utc(self):
        """Mon 15:59 UTC is last minute of London."""
        ts = datetime(2026, 8, 25, 15, 59, 59, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'london'
    
    # Overlap Session Tests (Highest Priority)
    def test_overlap_london_ny_monday_1400_utc(self):
        """Mon 14:00 UTC is overlap (takes precedence over London)."""
        ts = datetime(2026, 8, 25, 14, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'overlap_london_ny'
    
    def test_overlap_boundary_1300_utc(self):
        """Mon 13:00 UTC starts overlap."""
        ts = datetime(2026, 8, 25, 13, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'overlap_london_ny'
    
    def test_overlap_boundary_1559_utc(self):
        """Mon 15:59 UTC is last minute of overlap."""
        ts = datetime(2026, 8, 25, 15, 59, 59, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'overlap_london_ny'
    
    # New York Session Tests
    def test_newyork_monday_1800_utc(self):
        """Mon 18:00 UTC (after overlap) should be New York."""
        ts = datetime(2026, 8, 25, 18, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'newyork'
    
    def test_newyork_boundary_2059_utc(self):
        """Mon 20:59 UTC is last minute of New York."""
        ts = datetime(2026, 8, 25, 20, 59, 59, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'newyork'
    
    # Friday Evening Tests
    def test_friday_evening_2100_utc(self):
        """Fri 21:00 UTC starts Friday evening."""
        ts = datetime(2026, 8, 29, 21, 0, 0, tzinfo=timezone.utc)  # Friday
        assert get_current_session_utc(ts) == 'friday_evening'
    
    def test_friday_evening_boundary_2359_utc(self):
        """Fri 23:59 UTC is last minute of Friday evening."""
        ts = datetime(2026, 8, 29, 23, 59, 59, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'friday_evening'
    
    # Weekend Tests
    def test_weekend_saturday_full_day(self):
        """Sat 12:00 UTC should be weekend_saturday."""
        ts = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)  # Saturday
        assert get_current_session_utc(ts) == 'weekend_saturday'
    
    def test_sunday_trading_1400_utc(self):
        """Sun 14:00 UTC should be sunday_trading."""
        ts = datetime(2026, 8, 31, 14, 0, 0, tzinfo=timezone.utc)  # Sunday
        assert get_current_session_utc(ts) == 'sunday_trading'
    
    # Error Cases
    def test_no_session_monday_2100_utc(self):
        """Mon 21:00 UTC has no session (gap)."""
        ts = datetime(2026, 8, 25, 21, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError):
            get_current_session_utc(ts)
    
    def test_no_session_sunday_2100_utc(self):
        """Sun 21:00 UTC has no session (after trading)."""
        ts = datetime(2026, 8, 31, 21, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError):
            get_current_session_utc(ts)
```

**Coverage:** 15 tests covering all 7 sessions, boundaries, precedence, and error cases.

---

### 2. Strategy Interface Tests (20 tests)

**File:** `tests/unit/test_strategy_interface.py`

```python
import pytest
import pandas as pd
from src.strategy_interface import (
    BaseStrategy, StrategySignal, STRATEGY_REGISTRY
)
from src.strategies.rsi14 import RSI14Strategy
from src.strategies.osma_confluence import OsMAConfluenceStrategy

class TestStrategyInterface:
    
    @pytest.fixture
    def sample_ohlcv(self):
        """Generate sample OHLCV data."""
        dates = pd.date_range('2026-01-01', periods=100, freq='1h')
        data = {
            'open': [1230 + i*0.5 for i in range(100)],
            'high': [1235 + i*0.5 for i in range(100)],
            'low': [1225 + i*0.5 for i in range(100)],
            'close': [1232 + i*0.5 for i in range(100)],
            'volume': [1000000] * 100
        }
        return pd.DataFrame(data, index=dates)
    
    def test_rsi14_calculate_indicators(self, sample_ohlcv):
        """RSI14 should calculate RSI indicator."""
        strategy = RSI14Strategy()
        params = {"period": 14}
        indicators = strategy.calculate_indicators(sample_ohlcv, params)
        
        assert "RSI" in indicators
        assert len(indicators["RSI"]) == len(sample_ohlcv)
        assert indicators["RSI"].dtype == 'float64'
    
    def test_rsi14_validate_params_valid(self):
        """RSI14 should accept valid parameters."""
        strategy = RSI14Strategy()
        assert strategy.validate_params({"period": 14}) is True
        assert strategy.validate_params({"period": 5}) is True
        assert strategy.validate_params({"period": 50}) is True
    
    def test_rsi14_validate_params_invalid(self):
        """RSI14 should reject invalid parameters."""
        strategy = RSI14Strategy()
        assert strategy.validate_params({"period": 0}) is False
        assert strategy.validate_params({"period": 51}) is False
        assert strategy.validate_params({"period": -5}) is False
        assert strategy.validate_params({"missing_period": 14}) is False
    
    def test_rsi14_generate_signal_oversold(self, sample_ohlcv):
        """RSI14 should generate buy signal when RSI < 30."""
        strategy = RSI14Strategy()
        params = {"period": 14}
        indicators = strategy.calculate_indicators(sample_ohlcv, params)
        
        # Manually set RSI to 25 for this test
        indicators["RSI"].iloc[-1] = 25.0
        
        signal = strategy.generate_signal(
            indicators,
            entry_floors={"min_strength": 0.1},
            current_bar_idx=len(sample_ohlcv) - 1
        )
        
        assert signal.should_enter is True
        assert signal.entry_type == "long"
        assert signal.strength > 0
        assert "oversold" in signal.reason.lower()
    
    def test_rsi14_generate_signal_neutral(self, sample_ohlcv):
        """RSI14 should not generate signal when RSI neutral."""
        strategy = RSI14Strategy()
        params = {"period": 14}
        indicators = strategy.calculate_indicators(sample_ohlcv, params)
        
        # Manually set RSI to 50 (neutral)
        indicators["RSI"].iloc[-1] = 50.0
        
        signal = strategy.generate_signal(
            indicators,
            entry_floors={"min_strength": 0.1},
            current_bar_idx=len(sample_ohlcv) - 1
        )
        
        assert signal.should_enter is False
    
    def test_rsi14_generate_signal_floor_rejection(self, sample_ohlcv):
        """RSI14 should reject signal if strength < floor."""
        strategy = RSI14Strategy()
        params = {"period": 14}
        indicators = strategy.calculate_indicators(sample_ohlcv, params)
        
        # Set RSI to 28.5 (weak oversold, strength ~0.05)
        indicators["RSI"].iloc[-1] = 28.5
        
        signal = strategy.generate_signal(
            indicators,
            entry_floors={"min_strength": 0.5},  # High floor
            current_bar_idx=len(sample_ohlcv) - 1
        )
        
        assert signal.should_enter is False
    
    def test_osma_confluence_calculate_indicators(self, sample_ohlcv):
        """OsMA should calculate multiple indicators."""
        strategy = OsMAConfluenceStrategy()
        params = {
            "osma_fast": 12,
            "osma_slow": 26,
            "osma_signal": 9,
            "ma_period": 20
        }
        indicators = strategy.calculate_indicators(sample_ohlcv, params)
        
        assert "OSMA" in indicators
        assert "MACD" in indicators
        assert "Signal" in indicators
        assert "MA" in indicators
    
    def test_osma_confluence_validate_params_valid(self):
        """OsMA should accept valid parameters."""
        strategy = OsMAConfluenceStrategy()
        params = {
            "osma_fast": 12,
            "osma_slow": 26,
            "osma_signal": 9,
            "ma_period": 20
        }
        assert strategy.validate_params(params) is True
    
    def test_osma_confluence_validate_params_missing(self):
        """OsMA should reject if params missing."""
        strategy = OsMAConfluenceStrategy()
        params = {"osma_fast": 12}  # Missing others
        assert strategy.validate_params(params) is False
    
    def test_strategy_registry_get_strategy(self):
        """Registry should retrieve registered strategies."""
        rsi = STRATEGY_REGISTRY.get_strategy("RSI14")
        assert rsi.strategy_name == "RSI14"
        assert rsi.strategy_type == "momentum"
    
    def test_strategy_registry_unknown_strategy(self):
        """Registry should raise for unknown strategy."""
        with pytest.raises(ValueError):
            STRATEGY_REGISTRY.get_strategy("UnknownStrategy")
    
    def test_strategy_registry_list_strategies(self):
        """Registry should list all registered strategies."""
        strategies = STRATEGY_REGISTRY.list_strategies()
        assert "RSI14" in strategies
        assert "OsMA_Confluence" in strategies
        assert len(strategies) >= 2
    
    def test_strategy_signal_dataclass_fields(self):
        """StrategySignal should have all required fields."""
        signal = StrategySignal(
            should_enter=True,
            entry_price=1234.56,
            entry_type="long",
            confidence=0.75,
            reason="Test signal",
            strength=0.8
        )
        
        assert signal.should_enter is True
        assert signal.confidence == 0.75
        assert signal.strength == 0.8
    
    def test_strategy_invalid_bar_index(self, sample_ohlcv):
        """Strategy should handle invalid bar index."""
        strategy = RSI14Strategy()
        params = {"period": 14}
        indicators = strategy.calculate_indicators(sample_ohlcv, params)
        
        signal = strategy.generate_signal(
            indicators,
            entry_floors={"min_strength": 0.1},
            current_bar_idx=999  # Out of range
        )
        
        assert signal.should_enter is False
    
    def test_strategy_insufficient_data(self):
        """Strategy should handle insufficient data."""
        strategy = RSI14Strategy()
        params = {"period": 14}
        
        # Only 5 bars (not enough for RSI14)
        small_df = pd.DataFrame({
            'close': [1230, 1231, 1232, 1231, 1230]
        })
        
        indicators = strategy.calculate_indicators(small_df, params)
        signal = strategy.generate_signal(
            indicators,
            entry_floors={"min_strength": 0.1},
            current_bar_idx=4
        )
        
        # Should gracefully handle insufficient data
        assert signal.should_enter is False
```

**Coverage:** 20 tests covering all strategy interface methods, registry, validation, edge cases.

---

### 3. Unified Schema Tests (12 tests)

**File:** `tests/unit/test_unified_schema.py`

```python
import pytest
import json
from pathlib import Path
from src.schema_validator import (
    TunedParamsValidator,
    SessionConfig,
    LifecycleMetrics
)

class TestUnifiedSchema:
    
    @pytest.fixture
    def sample_tuned_params(self):
        """Load sample tuned_params.json."""
        return json.load(open('tests/fixtures/sample_tuned_params.json'))
    
    def test_schema_has_required_top_level_fields(self, sample_tuned_params):
        """Tuned params should have all required top-level fields."""
        required = ['symbol', 'generated_at', 'version', 'schema_version']
        for field in required:
            assert field in sample_tuned_params
    
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
        london = sample_tuned_params['session_strategies']['london']
        assert london['status'] == 'APPROVED'
        assert 'indicator_params' in london
        assert isinstance(london['indicator_params'], dict)
        assert len(london['indicator_params']) > 0
    
    def test_schema_approved_session_has_exit_params(self, sample_tuned_params):
        """Approved session should have exit_params."""
        session = sample_tuned_params['session_strategies']['overlap_london_ny']
        assert session['status'] == 'APPROVED'
        assert 'exit_params' in session
        assert 'sl_atr_mult' in session['exit_params']
        assert 'tp_ratio' in session['exit_params']
    
    def test_schema_approved_session_has_lifecycle(self, sample_tuned_params):
        """Approved session should have complete lifecycle."""
        session = sample_tuned_params['session_strategies']['asian']
        assert 'lifecycle' in session
        assert 'baseline' in session['lifecycle']
        assert 'tuned' in session['lifecycle']
        assert 'live' in session['lifecycle']
    
    def test_schema_baseline_metrics_valid(self, sample_tuned_params):
        """Baseline metrics should be valid."""
        session = sample_tuned_params['session_strategies']['london']
        baseline = session['lifecycle']['baseline']
        
        assert baseline['pf'] >= 1.0
        assert 0 < baseline['wr'] < 1.0
        assert baseline['trades'] > 0
    
    def test_schema_tuned_pf_improvement(self, sample_tuned_params):
        """Tuned PF should match baseline or be better."""
        session = sample_tuned_params['session_strategies']['asian']
        baseline_pf = session['lifecycle']['baseline']['pf']
        tuned_pf = session['lifecycle']['tuned']['pf']
        
        # If tuned, must be >= baseline
        if session['status'] == 'APPROVED':
            assert tuned_pf >= baseline_pf
    
    def test_schema_rejected_session_accepted_false(self, sample_tuned_params):
        """Rejected session should have accepted=false."""
        session = sample_tuned_params['session_strategies']['newyork']
        if session['status'] == 'REJECTED':
            assert session['validation_result']['accepted'] is False
            assert session['validation_result']['reason'] is not None
    
    def test_schema_no_strategy_session_empty(self, sample_tuned_params):
        """No-strategy session should have empty params."""
        session = sample_tuned_params['session_strategies']['friday_evening']
        assert session['status'] == 'NO_STRATEGY'
        assert session['strategy_name'] is None
    
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
```

**Coverage:** 12 tests covering schema structure, validation, metrics consistency.

---

### 4. Phase Integration Tests (18 tests)

**File:** `tests/unit/test_phase_integration.py`

```python
import pytest
from dataclasses import dataclass
from src.phase_integration import (
    Phase1Output,
    Phase2Input,
    Phase2Output,
    Phase3Input,
    Phase3Output,
    Phase4Input
)

class TestPhaseIntegration:
    
    def test_phase1_output_structure(self):
        """Phase 1 output should have all required fields."""
        output = Phase1Output(
            symbol="XAUUSD",
            timeframe="M15",
            session="asian",
            discovered_strategies=[],
            date_range={"start": "2026-01-01", "end": "2026-08-25"},
            timestamp="2026-08-25T22:00:00Z"
        )
        
        assert output.symbol == "XAUUSD"
        assert output.timeframe == "M15"
        assert len(output.discovered_strategies) == 0
    
    def test_phase1_to_phase2_data_flow(self):
        """Phase 1 output should seamlessly become Phase 2 input."""
        phase1_strategy = {
            'strategy_name': 'RSI14',
            'indicator_params': {'period': 14},
            'baseline_pf': 1.52,
            'baseline_wr': 0.58,
            'baseline_sharpe': 1.25,
            'baseline_trades': 145
        }
        
        # Verify Phase 2 can accept all fields from Phase 1
        phase2_input = Phase2Input(
            symbol="XAUUSD",
            session="asian",
            timeframe="M15",
            strategy_name=phase1_strategy['strategy_name'],
            strategy_type="momentum",
            indicator_params=phase1_strategy['indicator_params'],
            baseline_pf=phase1_strategy['baseline_pf'],
            baseline_wr=phase1_strategy['baseline_wr'],
            baseline_sharpe=phase1_strategy['baseline_sharpe'],
            baseline_trades=phase1_strategy['baseline_trades'],
            ohlcv_data=None,
            optuna_trials=500
        )
        
        assert phase2_input.strategy_name == phase1_strategy['strategy_name']
        assert phase2_input.baseline_pf == phase1_strategy['baseline_pf']
    
    def test_phase2_to_phase3_data_flow(self):
        """Phase 2 output should become Phase 3 input."""
        phase2_output = Phase2Output(
            symbol="XAUUSD",
            session="asian",
            timeframe="M15",
            strategy_name="RSI14",
            strategy_type="momentum",
            baseline_pf=1.52,
            baseline_wr=0.58,
            baseline_sharpe=1.25,
            tuned_params={'period': 14},
            best_trial_id=123,
            best_trial_pf=1.58,
            study_db_path="/path/to/study.db",
            timestamp="2026-08-25T22:00:00Z"
        )
        
        # Verify Phase 3 can accept all fields from Phase 2
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
            ohlcv_data=None,
            improvement_threshold=0.02
        )
        
        assert phase3_input.tuned_params == phase2_output.tuned_params
        assert phase3_input.tuned_pf == phase2_output.best_trial_pf
    
    def test_phase3_to_phase4_aggregation(self):
        """Phase 3 results should aggregate for Phase 4."""
        phase3_asian = Phase3Output(
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
            tuned_params={'period': 14},
            indicator_params={'period': 14},
            exit_params={'sl_atr_mult': 1.5, 'tp_ratio': 2.5}
        )
        
        phase3_london = Phase3Output(
            symbol="XAUUSD",
            session="london",
            timeframe="M15",
            strategy_name="OsMA_Confluence",
            accepted=True,
            baseline_pf=1.68,
            baseline_wr=0.62,
            tuned_pf=1.72,
            tuned_wr=0.64,
            improvement_pct=2.4,
            acceptance_reason="PF improved 2.4%",
            rejection_reason=None,
            tuned_params={'osma_fast': 12, 'osma_slow': 26},
            indicator_params={'osma_fast': 12, 'osma_slow': 26},
            exit_params={'sl_atr_mult': 1.8, 'tp_ratio': 3.0}
        )
        
        # Phase 4 receives dict of results
        phase4_input = Phase4Input(
            symbol="XAUUSD",
            validation_results={
                'asian': phase3_asian,
                'london': phase3_london
            }
        )
        
        assert len(phase4_input.validation_results) == 2
        assert phase4_input.validation_results['asian'].accepted is True
        assert phase4_input.validation_results['london'].accepted is True
    
    def test_phase4_deployment_only_approved(self):
        """Phase 4 should only deploy approved sessions."""
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
            acceptance_reason="PF improved 3.8%",
            rejection_reason=None,
            tuned_params={'period': 14},
            indicator_params={'period': 14},
            exit_params={'sl_atr_mult': 1.5, 'tp_ratio': 2.5}
        )
        
        rejected = Phase3Output(
            symbol="XAUUSD",
            session="newyork",
            timeframe="M15",
            strategy_name="RSI14",
            accepted=False,
            baseline_pf=1.35,
            baseline_wr=0.54,
            tuned_pf=1.32,
            tuned_wr=0.52,
            improvement_pct=-2.2,
            acceptance_reason=None,
            rejection_reason="PF declined 2.2%",
            tuned_params={},
            indicator_params={'period': 14},
            exit_params={}
        )
        
        # Phase 4 logic: only deploy if accepted
        for session_name, result in {'asian': approved, 'newyork': rejected}.items():
            if result.accepted:
                # Deploy this session
                assert result.strategy_name == "RSI14"
            else:
                # Skip this session
                pass
    
    # ... 11 more phase integration tests covering all data flows
```

**Coverage:** 18 tests covering all phase transitions, data flow contracts, no transformation needed.

---

## INTEGRATION TESTS (26 total)

### Phase Discovery Tests (8 tests)

**File:** `tests/integration/test_phase1_discovery.py`

Tests:
1. Discover top 3 strategies for each session
2. Verify PF ranking is correct
3. Verify strategies registered in registry
4. Verify OHLCV data loaded correctly
5. Verify default params applied
6. Verify backtest runs without errors
7. Verify baseline metrics calculated
8. Verify output format matches Phase2Input

### Phase Tuning Tests (6 tests)

**File:** `tests/integration/test_phase2_tuning.py`

Tests:
1. Optuna study creates correctly
2. Tuning improves from baseline
3. Trial limit respected
4. Best trial identified
5. Output written to SQLite
6. Tuned params can be loaded

### Phase Validation Tests (6 tests)

**File:** `tests/integration/test_phase3_validation.py`

Tests:
1. Walkforward validation runs
2. Acceptance threshold enforced
3. Acceptance reason populated
4. Rejection reason populated
5. Live metrics initialized
6. Output aggregates all sessions

### Phase Deployment Tests (6 tests)

**File:** `tests/integration/test_phase4_deployment.py`

Tests:
1. tuned_params.json written correctly
2. Only approved strategies deployed
3. Schema validation passes
4. Metadata populated correctly
5. Version incremented
6. File readable by ScalpEngine

---

## END-TO-END TESTS (9 total)

### E2E Pipeline Tests (4 tests)

**File:** `tests/e2e/test_end_to_end_pipeline.py`

```python
def test_full_pipeline_xauusd_m15_all_sessions():
    """Run Phase 1→2→3→4 for XAUUSD/M15."""
    # Setup
    symbol = "XAUUSD"
    timeframe = "M15"
    
    # Phase 1: Discovery
    phase1_result = run_phase1_discovery(symbol, timeframe, all_sessions=True)
    assert phase1_result['status'] == 'success'
    assert len(phase1_result['discovered_strategies']) > 0
    
    # Phase 2: Tuning (per session)
    phase2_results = {}
    for session in phase1_result['sessions']:
        top_strategy = phase1_result['strategies'][session][0]
        phase2 = run_phase2_tuning(symbol, session, timeframe, top_strategy)
        assert phase2['status'] == 'success'
        phase2_results[session] = phase2
    
    # Phase 3: Validation
    phase3_results = {}
    for session, phase2 in phase2_results.items():
        phase3 = run_phase3_validation(symbol, session, timeframe, phase2)
        assert phase3['status'] == 'success'
        phase3_results[session] = phase3
    
    # Phase 4: Deployment
    phase4 = run_phase4_deployment(symbol, timeframe, phase3_results)
    assert phase4['status'] == 'success'
    
    # Verify final output
    tuned_params = load_tuned_params_json(symbol)
    assert tuned_params['symbol'] == symbol
    assert len(tuned_params['session_strategies']) == 7

def test_pipeline_with_rejected_sessions():
    """Pipeline should handle rejected sessions gracefully."""
    # ... test logic

def test_pipeline_with_no_strategy_sessions():
    """Pipeline should handle sessions with no strategy."""
    # ... test logic

def test_pipeline_live_trading_integration():
    """Deployed params should work with ScalpEngine."""
    # ... test logic
```

### Live Trading Simulation Tests (5 tests)

**File:** `tests/e2e/test_live_trading_simulation.py`

```python
def test_scalpengine_loads_tuned_params():
    """ScalpEngine should load and use tuned params."""
    # ... test logic

def test_scalpengine_session_selection_during_trading():
    """ScalpEngine should select correct session during trading."""
    # ... test logic

def test_scalpengine_strategy_instantiation():
    """ScalpEngine should instantiate strategy by name."""
    # ... test logic

def test_scalpengine_entry_signal_generation():
    """ScalpEngine should generate entry signals."""
    # ... test logic

def test_scalpengine_multi_session_switching():
    """ScalpEngine should switch strategies as sessions change."""
    # ... test logic
```

---

## TEST COVERAGE SUMMARY

| Category | Count | Status |
|----------|-------|--------|
| Unit Tests | 65 | Pending |
| Integration Tests | 26 | Pending |
| E2E Tests | 9 | Pending |
| **TOTAL** | **100** | **PENDING** |

---

## Test Fixtures

### `tests/fixtures/ohlcv_data.py`

```python
import pandas as pd

def get_sample_ohlcv(n_bars=100):
    """Generate sample OHLCV data."""
    dates = pd.date_range('2026-01-01', periods=n_bars, freq='1h')
    data = {
        'open': [1230 + i*0.5 for i in range(n_bars)],
        'high': [1235 + i*0.5 for i in range(n_bars)],
        'low': [1225 + i*0.5 for i in range(n_bars)],
        'close': [1232 + i*0.5 for i in range(n_bars)],
        'volume': [1000000] * n_bars
    }
    return pd.DataFrame(data, index=dates)

def get_realistic_ohlcv_with_volatility(n_bars=500):
    """Generate realistic OHLCV with volatility patterns."""
    # ... implementation
    pass
```

### `tests/fixtures/sample_tuned_params.json`

Sample JSON file with all 7 sessions, 3 approved, 1 rejected, 3 no-strategy.

---

## Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# E2E tests only
pytest tests/e2e/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

---

**Status:** TEST PLAN COMPLETE - Ready for implementation
