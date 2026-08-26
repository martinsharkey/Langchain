# Test Harness Documentation: Vectorbt → Optuna Pipeline

**Date**: 2026-08-24  
**Purpose**: Comprehensive guide to existing tests + identify gaps

---

## Existing Tests for Pipeline Components

### 1. Change Validator Tests

**File**: `test_change_validator.py` (9523 bytes)

**Purpose**: Validate the acceptance/rejection gate for tuned parameters

**Test Coverage**:
```
✓ Accept valid improvements (tuned_pf > baseline_pf + 1%)
✓ Reject non-improvements
✓ Detect overfitting (OOS vs IS gap > 10%)
✓ Validate walk-forward generalization (PF ≥ 1.0 all windows)
✓ Handle edge cases (zero trades, negative PF, etc.)
```

**Example Test Structure**:
```python
def test_accept_valid_improvement():
    """Accept params that improve PF and generalize"""
    baseline = {"pf": 10.24, "wr": 38%, "trades": 156}
    tuned = {"pf": 10.48, "wr": 39%, "generalizes": True}
    
    result = validator.validate(tuned, baseline)
    assert result.status == "ACCEPTED"
    assert result.reason contains "improvement"
```

### 2. Directed Optimizer Tests

**File**: `test_directed_optimizer.py` (9005 bytes)

**Purpose**: Test Optuna floor optimization for specific symbols

**Test Coverage**:
```
✓ Hill-climbing on floor parameters
✓ Convergence to better solutions
✓ Rejection of non-improvements
✓ Per-symbol baseline initialization
✓ Trial counting and iteration limits
```

**Key Test**:
```python
def test_floor_optimization_finds_improvement():
    """Optuna discovers better floors than baseline"""
    optimizer = FloorOptimizer(symbol="XAUUSD", session="asian")
    
    baseline_pf = 10.24
    tuned = optimizer.optimize(n_trials=50)
    
    assert tuned.pf > baseline_pf * 1.01  # 1% improvement threshold
```

### 3. Edge Discovery Tests

**File**: `test_edge_discovery.py` (4067 bytes)

**Purpose**: Test baseline edge identification via vectorbt

**Test Coverage**:
```
✓ Indicator evaluation on historical data
✓ Per-session stratification (Asian/London/NewYork)
✓ Multiple timeframe testing (M1, M5, M15, H1, H4)
✓ Results ranking by performance
✓ Persistence of discovery results
```

**Example**:
```python
def test_discover_edges_per_timeframe():
    """Vectorbt finds best indicators per timeframe"""
    discoverer = EdgeDiscovery(symbol="XAUUSD")
    
    results = discoverer.discover_all_timeframes()
    
    assert "M1" in results
    assert "H4" in results
    assert results["H4"]["best_indicator"] is not None
```

### 4. Entry Strength Tests

**File**: `test_entry_strength.py` (12124 bytes)

**Purpose**: Test adaptive entry strength floor discovery

**Test Coverage**:
```
✓ Per-symbol strength floor learning
✓ Session-specific floor adaptation
✓ Convergence on stable values
✓ Rejection of weak entries
✓ Performance improvement tracking
```

### 5. Dashboard Integration Tests

**Files**: 
- `test_dashboard_api_v2.py` (7709 bytes)
- `test_dashboard_integration.py` (6222 bytes)

**Purpose**: Test dashboard API endpoints and data flows

**Test Coverage**:
```
✓ /api/v2/optimization/results endpoint
✓ /api/v2/optimization/control endpoint
✓ Data serialization/deserialization
✓ Error handling (missing symbol, invalid session, etc.)
✓ Real-time result retrieval
```

### 6. Closed-Loop Tests

**File**: `test_closed_loop.py` (8657 bytes)

**Purpose**: Test adaptive loop continuity

**Test Coverage**:
```
✓ Multiple optimization cycles in succession
✓ State persistence across restarts
✓ Learning progression over time
✓ Graceful handling of failed cycles
```

---

## Test Statistics

```
Total test files: 30+
Total tests: 200+
Core pipeline tests: 50+ (vectorbt, optuna, validation)
Dashboard tests: 10+
Integration tests: 15+

Passing rate: 95%+ (as of last CI run)
```

---

## Critical Tests for Pipeline Phases

### Phase 1: Vectorbt Discovery

**Tests Needed**:
```python
def test_discovery_all_indicators_m1_h4():
    """Discover best indicator across M1-H4 timeframes"""
    
def test_discovery_per_session_asian_london_newyork():
    """Each session gets its own best indicator baseline"""
    
def test_discovery_results_persisted():
    """Results saved to discoveryresults.json"""
```

**Status**: ⚠️ Partial coverage in `test_edge_discovery.py`

### Phase 2: Optuna Tuning

**Tests Needed**:
```python
def test_optuna_improves_baseline_by_min_1_percent():
    """Tuned PF > baseline PF × 1.01"""
    
def test_optuna_100_trials_converges():
    """After 100 trials, score improvement plateaus"""
    
def test_optuna_respects_parameter_bounds():
    """All tuned params within PARAM_SPACE ranges"""
```

**Status**: ⚠️ Partial coverage in `test_directed_optimizer.py`

### Phase 3: Vectorbt Validation

**Tests Needed**:
```python
def test_validation_catches_overfitting():
    """OOS PF vs IS PF gap > 10% → REJECT"""
    
def test_validation_requires_all_windows_pf_gte_1():
    """Any window with PF < 1.0 → REJECT"""
    
def test_validation_logs_decision_to_audit_trail():
    """Validation reason persisted for review"""
```

**Status**: ✅ Good coverage in `test_change_validator.py`

### Phase 4: Live Deployment

**Tests Needed**:
```python
def test_deployment_applies_session_overrides():
    """session_Asian overrides applied for Asian session"""
    
def test_deployment_gracefully_falls_back_to_baseline():
    """If tuned params missing, use baseline"""
    
def test_deployment_params_used_in_live_signals():
    """osma_min_long from tuned params, not hardcoded"""
```

**Status**: ⚠️ Minimal coverage - needs strengthening

---

## Missing Test Coverage

### Critical Gaps

1. **End-to-End Pipeline Test**
   - Run all 4 phases sequentially on one symbol/session
   - Verify output of each phase feeds into next
   - Track time: discovery (< 5s) → tuning (< 5s) → validation (< 100ms) → deployment
   - Expected in `test_e2e_pipeline.py` ❌

2. **Concurrent Symbol Testing**
   - Run discovery/tuning for XAUUSD, BTCUSD, GER40 simultaneously
   - Verify no state pollution between symbols
   - Check resource usage (CPU, memory)
   - Expected in `test_concurrent_symbols.py` ❌

3. **Nightly Orchestration Test**
   - Run full pipeline at "10pm GMT"
   - Verify all 3 symbols × 3 sessions = 9 runs complete
   - Log output captured and validated
   - Expected in `test_nightly_orchestration.py` ❌

4. **Error Recovery Tests**
   - Simulate backtest failure mid-trial
   - Verify optimizer recovers and continues
   - Check crash scenario: restart pipeline at same point
   - Expected in `test_error_recovery.py` ❌

5. **Performance Tests**
   - Discovery phase: < 5 seconds per symbol
   - Tuning phase (100 trials): < 5 seconds per symbol
   - Validation phase: < 100ms per symbol
   - Expected in `test_performance_pipeline.py` ❌

---

## How to Run Tests

### Run All Tests
```bash
pytest tests/ -v
```

### Run Pipeline Tests Only
```bash
pytest tests/test_change_validator.py \
        tests/test_directed_optimizer.py \
        tests/test_edge_discovery.py \
        -v
```

### Run With Coverage Report
```bash
pytest tests/ --cov=src/learning --cov=src/dashboard --cov-report=html
```

### Run Single Test
```bash
pytest tests/test_change_validator.py::test_accept_valid_improvement -v
```

---

## Test File Dependencies

```
conftest.py
├─ Fixtures for symbol data, session mocks, etc.
├─ Mock MT5 adapter
└─ Test database setup

test_edge_discovery.py
├─ Depends on: conftest, vectorbt_optimizer
├─ Tests: Discovery phase
└─ Output: best_indicators.json

test_directed_optimizer.py
├─ Depends on: conftest, param_optimizer
├─ Tests: Optuna tuning
└─ Output: tuned_params.json

test_change_validator.py
├─ Depends on: conftest, change_validator
├─ Tests: Validation gate
└─ Output: Acceptance/Rejection decision

test_closed_loop.py
├─ Depends on: all above
├─ Tests: Multi-cycle learning
└─ Output: Learning progression
```

---

## Key Test Utilities

### From conftest.py

```python
@pytest.fixture
def symbol_data():
    """Fixture: Historical OHLC data for XAUUSD"""
    
@pytest.fixture
def backtest_fn():
    """Fixture: Mock backtest function"""
    
@pytest.fixture
def param_optimizer():
    """Fixture: ParameterOptimizer instance"""
    
@pytest.fixture
def change_validator():
    """Fixture: ChangeValidator instance"""
```

### Test Helpers

```python
def create_mock_optimization_result(pf=10.24, generalizes=True):
    """Create mock result for testing"""
    
def create_mock_backtest_data(n_windows=5, pf_per_window=[...]):
    """Create mock walk-forward data"""
    
def assert_params_within_bounds(params):
    """Verify all params in PARAM_SPACE ranges"""
```

---

## Running Specific Pipeline Scenarios

### Scenario 1: Happy Path (Full Success)
```bash
pytest tests/test_directed_optimizer.py::test_optuna_improves_baseline_by_min_1_percent \
        tests/test_change_validator.py::test_accept_valid_improvement \
        -v
```

### Scenario 2: Overfitting Detection
```bash
pytest tests/test_change_validator.py::test_reject_overfit_params \
        tests/test_change_validator.py::test_reject_large_oos_gap \
        -v
```

### Scenario 3: Multi-Symbol Parallel
```bash
# Expected in future:
pytest tests/test_concurrent_symbols.py -v
```

---

## Documentation Quality

### ✅ Well-Documented Tests
- `test_change_validator.py` - Clear test names, good docstrings
- `test_directed_optimizer.py` - Good setup/teardown
- `test_dashboard_api_v2.py` - Good endpoint coverage

### ⚠️ Needs Documentation
- `test_edge_discovery.py` - Sparse docstrings
- `test_closed_loop.py` - Complex test logic, needs explanation

### ❌ Critical Gaps
- No `test_e2e_pipeline.py`
- No `test_nightly_orchestration.py`
- No `test_concurrent_symbols.py`
- No `test_error_recovery.py`

---

## Test Execution Summary

**Total Coverage**: ~60% of pipeline (missing E2E, nightly, concurrency, errors)

**Next Actions**:
1. Create `tests/test_e2e_pipeline.py` - Full phase sequence
2. Create `tests/test_nightly_orchestration.py` - Scheduler integration
3. Create `tests/test_concurrent_symbols.py` - Multi-symbol safety
4. Create `tests/test_error_recovery.py` - Failure scenarios
5. Increase coverage target to 85%+

**Blocker for Dashboard**: None - existing tests are sufficient. Dashboard UI can be added without breaking tests.

**Blocker for Nightly Scheduling**: Create orchestrator test + scheduler config.
