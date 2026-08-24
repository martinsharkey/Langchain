# Documentation Index: Vectorbt → Optuna → Validation Pipeline

**Last Updated**: 2026-08-24  
**Status**: Code review complete, test documentation complete, ready for dashboard integration

---

## Quick Navigation

### 📋 For Understanding the Pipeline
1. **START HERE**: `CODE_REVIEW_VECTORBT_OPTUNA_PIPELINE.md` (9 sections)
   - Architecture overview
   - Line-by-line component review
   - Design decisions explained
   - Gaps identified

2. **Detailed Tests**: `TEST_HARNESS_DOCUMENTATION.md` (8 sections)
   - Existing test coverage
   - Critical gaps
   - How to run tests
   - Test scenarios

3. **Session Status**: `SESSION_LOG_2026_08_24.md` (current session)
   - What was reviewed today
   - Key insights
   - Next steps

---

## What Each File Covers

### Core Pipeline Code

#### `src/learning/param_optimizer.py` (797 lines)
```
✅ Parameter space definition (24 tunable params)
✅ Walk-forward validation gating
✅ Per-session override mechanism  
✅ Atomic persistence

Key Rule: No hardcoded floors in SYMBOL_BASELINES
```

#### `src/learning/vectorbt_optimizer.py`
```
✅ Discovery phase (find best indicators)
✅ Multi-timeframe testing (M1-H4)
✅ Per-session stratification
✅ Baseline establishment
```

#### `src/learning/optuna_floor_optimizer.py`
```
✅ Optimization trials (100+ per cycle)
✅ Hill-climbing on parameters
✅ Walk-forward validation per trial
✅ Improvement tracking
```

#### `src/learning/change_validator.py`
```
✅ Acceptance/rejection gating
✅ Overfitting detection
✅ Generalization validation
✅ Audit trail logging
```

### Dashboard/API

#### `src/dashboard/optimization_api_endpoints.py`
```
✅ GET /results/{symbol}
✅ GET /results/{symbol}/{session}
✅ POST /control/{symbol}/{session}
✅ GET /summary/{symbol}
❌ Missing: Phase trigger endpoints
❌ Missing: Phase status endpoints
```

#### `src/ui/backend.py`
```
✅ Flask app running localhost:5000
✅ API routing
❌ Missing: Wire to localhost:3000/symbols
```

### Tests

#### `tests/test_change_validator.py` (9523 bytes)
```
✅ Accept valid improvements
✅ Detect overfitting
✅ Validate generalization
✅ Handle edge cases
```

#### `tests/test_directed_optimizer.py` (9005 bytes)
```
✅ Optuna convergence
✅ Parameter bounds checking
✅ Improvement threshold validation
```

#### `tests/test_edge_discovery.py` (4067 bytes)
```
✅ Indicator evaluation
✅ Per-session testing
✅ Multi-timeframe coverage
```

#### `tests/test_dashboard_api_v2.py` (7709 bytes)
✅ Endpoint testing

#### `tests/test_dashboard_integration.py` (6222 bytes)
✅ Data flow testing

---

## The Complete Pipeline Flow

```
┌──────────────────────────────────────────────────────────────┐
│ PHASE 1: VECTORBT DISCOVERY (5 seconds)                      │
├──────────────────────────────────────────────────────────────┤
│ Input:  Symbol (XAUUSD/BTCUSD/GER40)                        │
│         Session (Asian/London/NewYork)                      │
│         Timeframes (M1, M5, M15, M30, H1, H4)              │
│                                                              │
│ Process: For each timeframe:                                │
│   For each indicator (Bollinger, OSMA, RSI, etc.):         │
│     Backtest with DEFAULT params                           │
│     Record: PF, Win Rate, Sharpe, Drawdown               │
│                                                              │
│ Output: {                                                    │
│   "best_indicator": "Bollinger_Bands",                     │
│   "baseline_pf": 10.24,                                     │
│   "baseline_trades": 156                                   │
│ }                                                            │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ PHASE 2: OPTUNA TUNING (5 seconds, 100 trials)              │
├──────────────────────────────────────────────────────────────┤
│ Input:  Discovery output                                     │
│         Baseline params                                      │
│         Parameter space (PARAM_SPACE)                       │
│                                                              │
│ Process: Run 100 Optuna trials:                             │
│   - Suggest parameter combination                          │
│   - Backtest with new params (walk-forward)               │
│   - Record score (minimum PF across folds)                │
│   - If score > best: Update best                          │
│                                                              │
│ Output: {                                                    │
│   "tuned_params": {...},                                   │
│   "tuned_pf": 10.48,                                       │
│   "improvement_pct": 2.34                                  │
│ }                                                            │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ PHASE 3: VECTORBT VALIDATION (100 milliseconds)             │
├──────────────────────────────────────────────────────────────┤
│ CRITICAL SAFETY GATE: Walk-forward on OUT-OF-SAMPLE data   │
│                                                              │
│ Input:  Tuned params from Phase 2                          │
│         Baseline results from Phase 1                      │
│                                                              │
│ Process: Split data into train/test folds:                │
│   For each fold:                                           │
│     - Backtest tuned params on TEST (never seen before)   │
│     - Record: PF, Win Rate (out-of-sample only)          │
│                                                              │
│ Acceptance Criteria (ALL must pass):                       │
│   ✓ tuned_pf > baseline_pf                                │
│   ✓ improvement ≥ 1%                                      │
│   ✓ OOS_pf vs IS_pf gap < 10% (no overfitting)          │
│   ✓ PF ≥ 1.0 in EVERY fold (generalizes)                │
│                                                              │
│ Output: {                                                    │
│   "status": "ACCEPTED" | "REJECTED",                      │
│   "reason": "Validation passed" | "Overfitting detected" │
│ }                                                            │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ PHASE 4: LIVE DEPLOYMENT (immediate)                        │
├──────────────────────────────────────────────────────────────┤
│ IF ACCEPTED:                                                 │
│   - Save tuned params to data/tuned_params.json            │
│   - Load in live trading engine                           │
│   - Use for next signal generation                        │
│                                                              │
│ IF REJECTED:                                                 │
│   - Keep using baseline params                            │
│   - Log rejection reason to audit trail                   │
│                                                              │
│ Output: Tuned/baseline params live in trading             │
└──────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### 1. Walk-Forward Validation Gate ✅
**Why**: Prevents overfitting from breaking live trading
**How**: Test tuned params on out-of-sample data only
**Enforcement**: PF ≥ 1.0 in every fold required, OOS vs IS gap < 10%

### 2. Per-Session Tuning ✅
**Why**: Asian/London/NewYork have different characteristics
**How**: Discover and tune each session independently
**Implementation**: session_Asian, session_London, session_NewYork overrides in params

### 3. No Hardcoded Floors ✅
**Why**: Ensures automation doesn't rely on folklore
**How**: Hard assertion in code prevents SYMBOL_BASELINES from containing floor values
**Implementation**: `_assert_no_hardcoded_floors()` at module load

### 4. Atomic Persistence ✅
**Why**: Prevents data corruption on crash
**How**: Write to .tmp file, then os.replace() (atomic on filesystem)
**Implementation**: See `_persist()` method in param_optimizer.py

---

## What's Complete vs What's Missing

### ✅ Complete

| Component | Status | File |
|-----------|--------|------|
| Vectorbt discovery | ✅ Implemented | vectorbt_optimizer.py |
| Optuna tuning | ✅ Implemented | optuna_floor_optimizer.py |
| Walk-forward validation | ✅ Implemented | change_validator.py |
| Live deployment | ✅ Implemented | scalp_engine.py |
| Per-session tuning | ✅ Implemented | param_optimizer.py |
| Persistence | ✅ Implemented | tuned_params.json |
| Core API endpoints | ✅ Implemented | optimization_api_endpoints.py |
| Integration tests | ✅ Implemented | test_change_validator.py, etc. |

### ❌ Missing (For Dashboard Integration)

| Component | Needed | File |
|-----------|--------|------|
| Phase trigger endpoints | ❌ | optimization_api_endpoints.py |
| Phase status endpoints | ❌ | optimization_api_endpoints.py |
| Dashboard UI buttons | ❌ | localhost:3000/symbols |
| Nightly orchestrator | ❌ | scripts/nightly_orchestrator.py |
| E2E test | ❌ | tests/test_e2e_pipeline.py |
| Concurrent test | ❌ | tests/test_concurrent_symbols.py |

---

## Next Steps (In Order)

### IMMEDIATE (This Session)

1. **Add Phase Trigger Endpoints** to `optimization_api_endpoints.py`
   ```python
   POST /api/v2/optimization/run/{phase}  # Triggers discovery/tuning/validation/deploy
   GET /api/v2/optimization/status/{symbol}  # Returns current phase status
   ```

2. **Add Dashboard UI Buttons** to localhost:3000/symbols
   - [Run Vectorbt Discovery]
   - [Run Optuna Tuning]
   - [Run Validation]
   - [Deploy to Live]

3. **Wire Buttons to API** in React component

### SOON (Next Session)

4. Create `scripts/nightly_orchestrator.py` - Run full cycle 10pm GMT Mon-Fri
5. Create `tests/test_e2e_pipeline.py` - Full phase sequence test
6. Create `tests/test_nightly_orchestration.py` - Scheduler test
7. Schedule nightly job via cron/Windows Task Scheduler

---

## Reading Order for New Developers

**If you want to understand the system**:
1. Read: `CODE_REVIEW_VECTORBT_OPTUNA_PIPELINE.md` (sections 1-4)
2. Read: `TEST_HARNESS_DOCUMENTATION.md` (sections 1-3)
3. Code: `src/learning/param_optimizer.py` (lines 1-100, 260-334)
4. Code: `src/learning/change_validator.py` (validation logic)

**If you want to add dashboard toggles**:
1. Read: `CODE_REVIEW_VECTORBT_OPTUNA_PIPELINE.md` (sections 7-9)
2. Modify: `src/dashboard/optimization_api_endpoints.py`
3. Modify: `src/ui/App.jsx` or localhost:3000/symbols frontend
4. Test: `pytest tests/test_dashboard_api_v2.py -v`

**If you want to run nightly cycles**:
1. Read: `CODE_REVIEW_VECTORBT_OPTUNA_PIPELINE.md` (section 6)
2. Create: `scripts/nightly_orchestrator.py`
3. Create: `tests/test_nightly_orchestration.py`
4. Schedule: Cron job or Windows Task Scheduler

---

## Critical Files (Memorize These)

```
CODE LOGIC:
  src/learning/param_optimizer.py         # Main orchestrator
  src/learning/change_validator.py        # Safety gate
  src/learning/vectorbt_optimizer.py      # Discovery

DATA:
  data/tuned_params.json                  # Where params live

API:
  src/dashboard/optimization_api_endpoints.py  # Endpoints

TESTS:
  tests/test_change_validator.py          # Validation gate tests
  tests/test_directed_optimizer.py        # Optuna tests
  tests/test_dashboard_api_v2.py          # API tests
```

---

## Success Metrics

**Phase 1 (Discovery)**: Completed in < 5 seconds  
**Phase 2 (Tuning)**: Completed in < 5 seconds, improvement > 1%  
**Phase 3 (Validation)**: OOS gap < 10%, PF ≥ 1.0 all windows  
**Phase 4 (Deployment)**: Params live within 100ms  
**Nightly Cycle**: All symbols × sessions complete in < 2 min at 10pm GMT

---

**This index was created on 2026-08-24 after comprehensive code review and test documentation. Use it as your reference guide for understanding, modifying, and extending the pipeline.**
