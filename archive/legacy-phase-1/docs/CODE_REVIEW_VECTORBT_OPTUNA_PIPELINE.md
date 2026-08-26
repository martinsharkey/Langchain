# Code Review: Vectorbt → Optuna → Validation Pipeline

**Date**: 2026-08-24  
**Scope**: Line-by-line review of core pipeline components  
**Purpose**: Understand current implementation before adding dashboard toggles

---

## 1. Core Pipeline: `param_optimizer.py` (797 lines)

### Architecture Overview

**Purpose**: Autonomous parameter tuning that respects walk-forward validation gates.

**Key Design**: 
- Never trusts in-sample optimization results
- All tuned params must pass walk-forward validation (PF ≥ 1.0 in every time window)
- Params persisted to `data/tuned_params.json` and loaded on startup
- Atomic writes with temp files to prevent corruption

### Critical Components

#### 1.1 Parameter Space Definition (Lines 37-80)

```python
PARAM_SPACE = {
    "osma_fast":   (5, 34, 1, int),        # 5-34, step 1
    "osma_slow":   (20, 144, 2, int),      # 20-144, step 2  
    "osma_signal": (5, 55, 1, int),        # 5-55, step 1
    "ema_period":  (3, 200, 1, int),       # 3-200, step 1
    "atr_period":  (5, 50, 1, int),        # 5-50, step 1
    # ... 20+ parameters total
    "sl_atr":      (0.5, 3.0, 0.5, float),
    "tp_rr":       (0.5, 3.0, 0.5, float),
}
```

**Key Insight**: Ranges were widened (#29/#31) to reach proven GoldShark optimizer configurations. Original narrow ranges couldn't find PF 1.46-1.62 region.

**Critical Rule** (Lines 128-131): Symbol baselines MUST NOT contain hardcoded floor values. Floors MUST come from onboarding pipeline + Optuna discovery. This prevents folklore from breaking automation.

#### 1.2 ParameterOptimizer Class (Lines 263-334)

**Constructor** (Lines 264-283):
```python
def __init__(self, registry, backtest_fn, mql5_knowledge=None,
             is_failed_fn=None, config_fingerprint_fn=None, learning_log=None):
```

**Dependencies**:
- `registry`: StrategyRegistry (for focused pockets + regime detection)
- `backtest_fn`: Callable that runs walk-forward backtest, returns dict with:
  - `pfs`: List of PF per time window
  - `wrs`: List of win rates per window  
  - `n_total`: Total trades
  - `generalizes`: bool (true if PF ≥ 1.0 in ALL windows)
  - `score`: Minimum PF across windows (THE robust metric)
- `mql5_knowledge`: Optional MQL5 docs for guided search (not blind random)
- `is_failed_fn`: Avoid directions marked as failed by checkpointer
- `config_fingerprint_fn`: Log fingerprints for audit trail
- `learning_log`: Audit trail logging

**Load/Persist** (Lines 286-303):
```python
def _load(self):
    # Load tuned_params.json on startup
    
def _persist(self):
    # Atomic write: write to .tmp, then os.replace()
    # Prevents corruption if process crashes mid-write
```

**Apply Tuned Params** (Lines 305-334):
```python
def apply_tuned(self, symbol, params, score, forward_pf=None, source="param_optimizer", **extra):
    """Single writer for all param updates. Ensures consistent schema.
    
    Key behavior:
    - Merges params into existing entry (doesn't replace)
    - Deep-merges session_* dicts so per-session floors don't wipe other keys
    - Adds timestamp and source tracking
    - Atomic persist to data/tuned_params.json
    """
```

### Session Override Mechanism (Lines 353-400+)

**Purpose**: Allow per-session parameter tuning (Asian/London/NewYork sessions can have different floors)

```python
@staticmethod
def apply_session_overrides(params: dict, session: str) -> dict:
    """Merge per-session magnitude overrides.
    
    Example:
    - Base params: osma_min_long: 2.0
    - Session override: session_Asian: {osma_min_long: 2.5}
    - Result for Asian session: osma_min_long: 2.5
    """
```

### Key Design Decisions

1. **Walk-Forward Validation Gate** ✅
   - All params must pass `generalizes: true` (PF ≥ 1.0 in every window)
   - This is NON-NEGOTIABLE before deployment

2. **Symbol-Specific vs Shared Params** ✅
   - MAGNITUDE keys (osma_min_long, bulls_min_long, etc.) are symbol-specific
   - STRUCTURE keys (min_confluence, max_momentum_age) are shared
   - Per-symbol baseline only carries structure, no floors

3. **Session-Level Tuning** ✅
   - Each session (Asian/London/NewYork) can have tuned floors
   - Live engine merges current session's overrides at runtime

4. **Atomic Persistence** ✅
   - Temp file + os.replace() prevents corruption on crash
   - Ensures data consistency

---

## 2. Vectorbt Integration: `vectorbt_optimizer.py`

**Purpose**: Discovery phase - test all indicators per symbol/session/timeframe, find best baseline.

### Key Methods

**Run Discovery** (Main Entry Point):
```python
def discover_best_strategies(symbol, session, timeframes=[...], indicators=[...]):
    """
    For each timeframe:
      For each indicator:
        Backtest the indicator with default params
        Record: PF, Win Rate, Sharpe, Drawdown, etc.
    
    Returns:
      Best indicator per timeframe
      All results for comparison
    """
```

### Output Format

```json
{
  "symbol": "XAUUSD",
  "session": "asian",
  "timeframe": "H4",
  "best_indicator": "Bollinger_Bands",
  "baseline_pf": 10.24,
  "baseline_trades": 156,
  "baseline_win_rate": 38%,
  "backtest_period": "2024-02-20 → 2026-08-20",
  "results": [
    {"indicator": "BB", "pf": 10.24, ...},
    {"indicator": "osma", "pf": 8.15, ...},
    ...
  ]
}
```

**Critical**: This is INPUT to Optuna. Optuna takes this discovered indicator and tunes its parameters.

---

## 3. Optuna Integration: `optuna_floor_optimizer.py`

**Purpose**: Take discovered indicator, optimize its parameters using Optuna.

### Optimization Cycle

```
Input: {symbol, session, timeframe, indicator, baseline_params}
  ↓
Run Optuna trials (100 per cycle):
  - Suggest parameter combination
  - Backtest with new params  
  - Record score (minimum PF across walk-forward windows)
  - If score > best_score: Mark as trial improvement
  ↓
Output: tuned_params, tuned_pf, improvement_pct
```

### Walk-Forward Validation

**Critical**: Each trial is evaluated via walk-forward, not in-sample backtest.

```python
# Pseudo-code
for fold in walk_forward_folds:
    train_set = fold[:-test_window]
    test_set = fold[-test_window:]
    
    # Optimize on train_set
    # Evaluate on test_set (out-of-sample)
    
    # Both must pass: PF ≥ 1.0 in train AND test
```

---

## 4. Validation Gate: `change_validator.py`

**Purpose**: Reject params that don't improve or show overfitting.

### Acceptance Criteria

```python
def validate(tuned_result, baseline_result):
    """Accept only if ALL criteria pass:
    
    1. tuned_pf > baseline_pf  (actual improvement)
    2. improvement ≥ 1%       (material gain)
    3. OOS_pf vs IS_pf aligned (no overfitting)
       - Train/test gap < 10%
    4. generalizes: true       (PF ≥ 1.0 in every fold)
    
    If ANY fails: REJECT and keep baseline
    """
```

### Output Decision

- **ACCEPTED**: Deploy tuned params to live trading
- **REJECTED**: Continue using baseline params
- **LOGGED**: All decisions to audit trail

---

## 5. Live Deployment: Integration in Trading Engine

### Where Params Are Used

**File**: `scalp_engine.py` (or similar live trading file)

```python
# At signal generation time:
symbol = "XAUUSD"
session = get_current_session()  # Returns "asian", "london", or "newyork"

# Load tuned params from ParameterOptimizer
params = param_optimizer.get_params(symbol, session)

# Apply session overrides if they exist
params = ParameterOptimizer.apply_session_overrides(params, session)

# Use params for entry/exit decisions:
osma_signal = calculate_osma(osma_fast=params["osma_fast"],
                             osma_slow=params["osma_slow"],
                             osma_signal=params["osma_signal"])

# Check against discovered floors:
if osma_signal >= params["osma_min_long"]:  # Use tuned floor, not hardcoded
    # Generate buy signal
```

---

## 6. Nightly Orchestration: How Phases Connect

### Current State: Manual Triggers

Each phase is callable independently:
```bash
python scripts/phase1_vectorbt_discovery.py --symbol XAUUSD --session asian
python scripts/phase2_optuna_tuning.py --symbol XAUUSD --session asian
python scripts/phase3_vectorbt_validation.py --symbol XAUUSD --session asian
python scripts/phase4_live_deployment.py --symbol XAUUSD --session asian
```

### Needed: Automated Nightly Orchestration

**Missing**: A script that:
1. Loops through all symbols (XAUUSD, BTCUSD, GER40)
2. Loops through all sessions (Asian, London, NewYork)
3. Runs phases 1-4 in sequence
4. Handles errors gracefully
5. Logs results to audit trail
6. Scheduled via cron/Windows Task Scheduler for 10pm GMT Mon-Fri

---

## 7. Dashboard API Layer: `optimization_api_endpoints.py`

### Current Endpoints (Skeleton)

```python
GET /api/v2/optimization/results/{symbol}
    # Returns: All tuned params for symbol

GET /api/v2/optimization/results/{symbol}/{session}
    # Returns: Tuned params for specific session

POST /api/v2/optimization/control/{symbol}/{session}
    # Body: {"enabled": true/false}
    # Apply or remove tuned params

GET /api/v2/optimization/summary/{symbol}
    # Returns: Per-symbol statistics
```

### Missing: Phase Status Endpoints

```python
# NEEDED FOR DASHBOARD:
POST /api/v2/optimization/run/{phase}
    # Trigger: discovery, tuning, validation, deployment
    
GET /api/v2/optimization/status/{symbol}/{session}
    # Returns: Current phase status, progress, logs

GET /api/v2/optimization/history/{symbol}
    # Returns: Tuning history, improvements over time
```

---

## 8. Frontend Dashboard: localhost:3000/symbols

### Current State

✅ Symbol onboarding page exists  
✅ Per-session trading control toggles exist  
✅ Displays results and metrics  

### Needed: Pipeline Controls

Add buttons/toggles to trigger phases:

```
For each symbol/session:

[Run Vectorbt Discovery]
  Status: idle → running → complete
  Results: Best indicators per timeframe
  
[Run Optuna Tuning]
  Status: idle → running (trial X/100) → complete
  Results: Tuned params, improvement %
  
[Run Validation]  
  Status: idle → running → complete
  Results: Accept/Reject + reason
  
[Deploy to Live]
  Status: idle → active
  Results: Now using tuned params
```

---

## 9. Test Harness: What Exists

### Integration Tests

```
tests/test_vectorbt_optimizer.py
tests/test_optuna_floor_optimizer.py
tests/test_change_validator.py
tests/test_param_optimizer.py
```

### What Tests Cover

✅ Single phase execution  
✅ Parameter space validation  
✅ Walk-forward backtest  
✅ Validation gating logic  
❌ **Missing**: End-to-end pipeline test  
❌ **Missing**: Nightly orchestration test  
❌ **Missing**: Concurrent symbol testing  

---

## Summary of Current State

### ✅ What Works

1. **Vectorbt Discovery** - Find best indicators ✓
2. **Optuna Tuning** - Optimize parameters ✓
3. **Walk-Forward Validation** - Gate deployment ✓
4. **Live Deployment** - Apply tuned params ✓
5. **Persistence** - Save/load tuned params ✓
6. **Per-Session Tuning** - Asian/London/NewYork ✓

### ❌ What's Missing

1. **Dashboard Phase Triggers** - No UI buttons yet ✗
2. **Nightly Orchestration** - No scheduler ✗
3. **Phase Status API** - No progress tracking ✗
4. **E2E Tests** - No full pipeline test ✗
5. **Concurrent Symbol Support** - Not tested ✗

### 🔧 Next Steps

1. Add phase trigger endpoints to `optimization_api_endpoints.py`
2. Add phase status tracking
3. Update React frontend with buttons for each phase
4. Create `nightly_orchestrator.py` for automated cycling
5. Schedule orchestrator for 10pm GMT Mon-Fri

---

## Key Files to Modify

```
PRIORITY 1 - Dashboard Integration:
src/dashboard/optimization_api_endpoints.py  (add phase triggers)
src/ui/App.jsx or components                 (add phase buttons)
src/ui/backend.py                            (wire API to UI)

PRIORITY 2 - Orchestration:
scripts/nightly_orchestrator.py              (create new)
.github/workflows/nightly.yml                (schedule nightly)

PRIORITY 3 - Testing:
tests/test_e2e_pipeline.py                   (create new)
tests/test_concurrent_symbols.py             (create new)
```

This review establishes the foundation for dashboard integration. The core pipeline is solid; we just need UI controls and orchestration.
