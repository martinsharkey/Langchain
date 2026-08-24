# Vectorbt → Optuna Integration: Research & Design

## Executive Summary

Vectorbt and Optuna serve DIFFERENT purposes that are often confused:
- **Vectorbt**: Strategy discovery and backtesting (which indicators work)
- **Optuna**: Parameter optimization (tuning indicator settings for discovered strategies)

This document explores how to integrate them properly with a parameter library system, performance considerations, ML framework integration, and the viability of Rustuna.

---

## Part 1: Vectorbt vs Optuna - Understanding the Overlap

### Vectorbt (Current Pipeline)
**Purpose**: Strategy Discovery and Validation

```
Input: Raw OHLCV data + session filters
Process:
  1. Test many indicator combinations (osma, bb_20_2.0, rsi_21, etc.)
  2. For each: generate entry signals
  3. Backtest against historical data
  4. Calculate metrics (PF, WR, Sharpe)
  5. Walk-forward validate best strategies
Output: Ranked list of winning strategies per session
  - Example: "asian H4: bb_20_2.5 + stdev_20 filter, PF=10.24"
```

**Vectorbt Does**: 
- Tests WHICH indicators work
- Validates strategy logic
- Identifies promising entry signals
- Produces session-specific baselines

**Vectorbt Does NOT**:
- Fine-tune indicator parameters
- Optimize thresholds (floors)
- Vary SL/TP multipliers
- Adapt to market changes

### Optuna (Missing Pipeline)
**Purpose**: Parameter Tuning for Discovered Strategies

```
Input: Discovered strategy + indicator parameters to tune
Process:
  1. Receive indicator combo (bb_20_2.5)
  2. Define tunable parameters:
     - BB period: 15-30
     - BB std dev: 1.5-3.0
     - Entry threshold: 0.5-2.0
  3. Suggest parameter set (e.g., period=20, std=2.2, threshold=1.2)
  4. Backtest with those parameters
  5. Calculate objective (profit_factor)
  6. Learn from result, suggest next parameters
  7. Repeat until convergence
Output: Optimal parameters for each discovered strategy per session
  - Example: "asian H4, bb_20_2.5: period=22, std=2.1, threshold=1.3, PF=10.8"
```

**Optuna Does**:
- Fine-tunes discovered strategies
- Optimizes thresholds and multipliers
- Adapts to market microstructure
- Handles multi-objective optimization (PF vs Sharpe vs DD)

**Optuna Does NOT**:
- Discover new strategies
- Validate strategy logic
- Handle category selection (should we use BB or RSI?)

### The Pipeline Relationship

```
┌─────────────────────────────────────────────────────────────┐
│ VECTORBT: Strategy Discovery                               │
│ Input: All indicators, all combinations, session filter     │
│ Output: Top 5-10 winning strategies per session             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ FOR EACH DISCOVERED STRATEGY:                              │
│                                                              │
│ OPTUNA: Parameter Tuning                                    │
│ Input: Specific strategy (e.g., "bb_20_2.5")              │
│ Output: Tuned parameters (period, std, threshold, etc.)    │
└─────────────────────────────────────────────────────────────┘
```

**They Don't Overlap** - They Sequence:
1. Vectorbt says: "Use Bollinger Bands"
2. Optuna says: "Use period=22, std=2.1, threshold=1.3"

---

## Part 2: Parameter Library Architecture

### Current State
`param_optimizer.py` has one global `PARAM_SPACE` with 25+ parameters. This doesn't match Vectorbt's discovery - it's too broad.

### Proposed: Indicator-Specific Parameter Libraries

```python
INDICATOR_PARAM_SPACE = {
    "osma": {
        "fast": {"min": 5, "max": 34, "step": 1, "type": int, "default": 12},
        "slow": {"min": 20, "max": 144, "step": 2, "type": int, "default": 26},
        "signal": {"min": 5, "max": 55, "step": 1, "type": int, "default": 9},
    },
    "bb_20_2.0": {
        "period": {"min": 15, "max": 30, "step": 1, "type": int, "default": 20},
        "std_dev": {"min": 1.5, "max": 3.0, "step": 0.1, "type": float, "default": 2.0},
        "threshold": {"min": 0.5, "max": 2.0, "step": 0.1, "type": float, "default": 1.0},
    },
    "bb_20_2.5": {
        "period": {"min": 15, "max": 30, "step": 1, "type": int, "default": 20},
        "std_dev": {"min": 2.0, "max": 3.5, "step": 0.1, "type": float, "default": 2.5},
        "threshold": {"min": 0.5, "max": 2.0, "step": 0.1, "type": float, "default": 1.0},
    },
    "rsi_21": {
        "period": {"min": 14, "max": 30, "step": 1, "type": int, "default": 21},
        "overbought": {"min": 60, "max": 80, "step": 1, "type": int, "default": 70},
        "oversold": {"min": 20, "max": 40, "step": 1, "type": int, "default": 30},
    },
    "stdev_20": {
        "period": {"min": 15, "max": 30, "step": 1, "type": int, "default": 20},
        "multiplier": {"min": 1.0, "max": 3.0, "step": 0.1, "type": float, "default": 1.0},
    },
}

# Exit parameters (universal, not indicator-specific)
EXIT_PARAM_SPACE = {
    "sl_atr_mult": {"min": 0.5, "max": 3.0, "step": 0.1, "type": float, "default": 1.0},
    "tp_atr_mult": {"min": 1.5, "max": 6.0, "step": 0.5, "type": float, "default": 3.0},
}
```

### Integration with Vectorbt Output

When Vectorbt discovers: `{"indicator": "bb_20_2.5", "secondary": "stdev_20", ...}`:

```python
def get_optuna_search_space(vectorbt_result):
    """
    Extract the parameter search space for Optuna based on discovered indicators.
    """
    indicator = vectorbt_result["primary_ind"]
    
    # Get indicator-specific params
    params = INDICATOR_PARAM_SPACE.get(indicator, {}).copy()
    
    # Add exit params
    params.update(EXIT_PARAM_SPACE)
    
    return params
```

**Advantage**: 
- Optuna knows exactly which parameters to tune for each indicator
- Prevents tuning irrelevant parameters
- Faster convergence (smaller search space)
- Per-indicator parameter discovery

---

## Part 3: Performance Analysis & Framework Selection

### Optuna Performance Characteristics

**Single Trial Backtest Time** (on MT5 daily data, 2 years = ~500 bars):
- Simple strategy (2-3 indicators): 10-100ms
- Complex strategy (5+ indicators): 100-500ms

**Trials Needed for Convergence**:
- Simple parameter (1-2 values): 20-50 trials
- Medium (3-5 parameters): 50-100 trials
- Complex (6-10 parameters): 100-300 trials

**Total Time Estimate**:
```
Simple: 20 trials × 50ms = 1 second
Medium: 100 trials × 200ms = 20 seconds
Complex: 200 trials × 300ms = 60 seconds
```

### Framework Selection for Validation Backtest

**Option 1: Vectorbt (Current)**
- Pros: Already integrated, proven, handles indicators
- Cons: Pure Python, single-threaded, slower for many iterations
- Speed: ~50-200ms per backtest

**Option 2: PyTorch/TensorFlow**
- Not suitable: Overkill for backtest, designed for deep learning
- Would need custom backtest layer anyway

**Option 3: Scikit-learn with Numba**
- Pros: Fast with JIT compilation, vectorized operations
- Cons: Need to rewrite backtest logic
- Speed: ~5-20ms per backtest (10x faster)

**Option 4: Polars + Numba**
- Pros: Extremely fast, vectorized, low memory
- Cons: Requires rewrite, learning curve
- Speed: ~2-10ms per backtest (50x faster)

**Option 5: XGBoost/LightGBM**
- Not suitable: These are gradient boosting frameworks, not backtesting tools

**RECOMMENDATION: Hybrid Approach**
```
Primary: Vectorbt (for indicator calculation + signals)
Acceleration: Numba JIT for backtest loop (10-20x speedup)
Batching: Run multiple Optuna trials in parallel (8-16 cores)
```

### Rustuna Consideration

**Rustuna**: Rust implementation of Optuna algorithms

**Pros**:
- Likely 5-10x faster optimization algorithm
- Better for high-dimensional search spaces
- Lower memory footprint

**Cons**:
- May require new Python bindings
- Smaller ecosystem than Optuna
- Need to verify indicator+backtest compatibility

**When to Consider Rustuna**:
- If single trial optimization is already fast (<20ms)
- If you're doing 1000+ trials per symbol
- If running real-time tuning during live trading

**For Initial Implementation**: Stick with Optuna + Numba

---

## Part 4: Optuna Integration into Onboarding Workflow

### Current Onboarding Flow
```
User: "Onboard XAUUSD"
  ↓
1. Download OHLCV for all timeframes
2. Vectorbt tests all indicators × sessions × timeframes
3. Vectorbt outputs: {symbol}_vectorbt_results.json
4. Generate report
5. Done - user can trade
```

### Proposed: With Optuna Integration
```
User: "Onboard XAUUSD"
  ↓
1. Download OHLCV for all timeframes
2. Vectorbt tests all indicators × sessions × timeframes
3. Vectorbt outputs: {symbol}_vectorbt_results.json
  ↓
4. FOR EACH discovered strategy per session:
   ├─ Extract indicator + baseline params
   ├─ Get parameter search space from library
   ├─ Create Optuna study for this (session, indicator) combo
   ├─ Run N optimization trials (parallel across cores)
   ├─ Save tuned params: {SYMBOL}__{session}__{indicator}_tuned.json
   └─ Report improvement: baseline PF 10.24 → tuned PF 10.48
  ↓
5. Aggregate all tuned params into single file
6. Generate comparison report: vectorbt baseline vs Optuna tuned
7. Done - user can trade with tuned parameters
```

### Timing Analysis

**Vectorbt phase** (current): ~2-5 minutes
- 6 timeframes × 5 sessions = 30 timeframe-session combos
- ~5 seconds per combo

**NEW Optuna phase**: ???
- Depends on:
  - Number of discovered strategies (typically 5-10)
  - Number of parameters per strategy (typically 3-6)
  - Trials per optimization (target: 50-100)
  - Trial backtest time (target: <100ms with Numba)

**Estimation**:
```
Base case (5 strategies, 4 params, 50 trials):
  5 strategies × 50 trials × 100ms = 25 seconds

With 8-core parallelization:
  25 seconds / 8 = ~3 seconds

Best case with Numba (20ms per trial):
  5 strategies × 50 trials × 20ms / 8 cores = ~6 seconds

Worst case without optimization:
  5 strategies × 200 trials × 500ms = 500 seconds = ~8 minutes
```

**GOAL**: Total onboarding (Vectorbt + Optuna) < 5 minutes
- Achievable with: Numba + 8-core parallelization

---

## Part 5: Proposed Architecture

### Step 1: Build Indicator Parameter Library

**File**: `src/learning/indicator_param_library.py`

```python
class IndicatorParamLibrary:
    """
    Central registry of tunable parameters per indicator.
    Used by Optuna to know what can be optimized.
    """
    
    def __init__(self):
        self.indicators = INDICATOR_PARAM_SPACE  # From Part 2
    
    def get_search_space(self, indicator_name):
        """Return Optuna-compatible search space for this indicator."""
        if indicator_name not in self.indicators:
            raise ValueError(f"Unknown indicator: {indicator_name}")
        return self.indicators[indicator_name]
    
    def get_exit_space(self):
        """Return exit parameters (universal)."""
        return EXIT_PARAM_SPACE
```

### Step 2: Create Session-Aware Optuna Bridge

**File**: `src/learning/optuna_session_tuner.py`

```python
class OptunaSessionTuner:
    """
    Tunes parameters for a specific (symbol, session, indicator) combo.
    Called after Vectorbt discovers the indicator.
    """
    
    def __init__(self, symbol, session, indicator):
        self.symbol = symbol
        self.session = session
        self.indicator = indicator
        self.param_library = IndicatorParamLibrary()
        
    def objective(self, trial):
        """Optuna objective function: backtest and return profit_factor."""
        # Get tuned parameters from trial
        params = {}
        for param_name, param_spec in self.param_library.get_search_space(self.indicator).items():
            if param_spec["type"] == int:
                params[param_name] = trial.suggest_int(
                    param_name, 
                    param_spec["min"], 
                    param_spec["max"], 
                    step=param_spec.get("step", 1)
                )
            else:
                params[param_name] = trial.suggest_float(
                    param_name,
                    param_spec["min"],
                    param_spec["max"],
                    step=param_spec.get("step", None)
                )
        
        # Add exit parameters
        for param_name, param_spec in self.param_library.get_exit_space().items():
            if param_spec["type"] == int:
                params[param_name] = trial.suggest_int(...)
            else:
                params[param_name] = trial.suggest_float(...)
        
        # Backtest with these parameters (session-filtered)
        pf = self.backtest_with_numba(params)
        return pf
    
    def backtest_with_numba(self, params):
        """Fast backtest using Numba JIT."""
        # Load session-filtered OHLCV
        # Calculate indicators with params
        # Generate signals
        # Backtest
        # Return profit_factor
        pass
    
    def optimize(self, n_trials=100):
        """Run Optuna optimization for this indicator in this session."""
        study = optuna.create_study(
            study_name=f"{self.symbol}__{self.session}__{self.indicator}",
            direction="maximize"
        )
        study.optimize(self.objective, n_trials=n_trials)
        return study.best_params, study.best_value
```

### Step 3: Integrate into Onboarding Pipeline

**Modified**: `scripts/qmmp/vectorbt_onboard.py`

```python
def run_full_onboarding(self, min_pf: float = 1.2, sessions: list = None):
    # ... existing Vectorbt phase ...
    
    validated = self._validate_walk_forward()
    
    # NEW: Run Optuna tuning for each discovered strategy
    print("\n[Stage X] Optuna Parameter Tuning...")
    for session, strategy in validated.items():
        indicator = strategy["primary_ind"]
        print(f"  Tuning {session}/{indicator}...")
        
        tuner = OptunaSessionTuner(self.symbol, session, indicator)
        best_params, best_pf = tuner.optimize(n_trials=100)
        
        # Save tuned params
        self._save_tuned_params(session, indicator, best_params, best_pf)
    
    # Continue with EA generation, report, etc...
```

---

## Part 6: Performance Timeline

### Development Phases

**Phase 0: Research & Prototyping** (Current - Do This First)
- [ ] Profile Vectorbt backtest time per trial
- [ ] Implement Numba JIT version, measure speedup
- [ ] Test Optuna on single strategy (XAUUSD, H4, osma)
- [ ] Estimate realistic trial time
- [ ] Evaluate Rustuna viability

**Phase 1: Parameter Library** (1-2 days)
- [ ] Build IndicatorParamLibrary
- [ ] Map Vectorbt indicators to param spaces
- [ ] Create unit tests

**Phase 2: Optuna Bridge** (2-3 days)
- [ ] Build OptunaSessionTuner with Numba backtest
- [ ] Integrate into onboarding
- [ ] Test on one symbol (XAUUSD)
- [ ] Measure end-to-end time

**Phase 3: Parallelization** (1-2 days)
- [ ] Multi-core trial execution
- [ ] Session-parallel optimization
- [ ] Verify speedup

**Phase 4: Integration & Validation** (2-3 days)
- [ ] Full onboarding pipeline test
- [ ] Compare Vectorbt baseline vs Optuna tuned
- [ ] Scalp engine loads tuned params
- [ ] Live trading test

**Phase 5: Rustuna Evaluation** (Optional, 1 day)
- [ ] If Phase 4 shows Optuna is bottleneck
- [ ] Benchmark Rustuna
- [ ] Decide on permanent solution

---

## Part 7: Open Research Questions

Before implementation, you should research:

1. **Vectorbt Trial Speed**
   - How fast can Vectorbt backtest a single strategy?
   - With 6 indicators, how long does a backtest take?
   - Possible to parallelize?

2. **Numba Compatibility**
   - Can Vectorbt calculations be JIT-compiled?
   - What's the realistic speedup (10x? 50x? 100x)?

3. **Optuna Convergence**
   - How many trials needed for each indicator?
   - Does Optuna improve on Vectorbt baseline?
   - By how much? (1%? 5%? 10%?)

4. **Rustuna Viability**
   - Is there a Python binding?
   - Can it integrate with Vectorbt/backtest logic?
   - Is it actually faster for your use case?

5. **Onboarding Time Target**
   - What's acceptable? (2 min? 5 min? 10 min?)
   - Determines if you need Numba, Rustuna, or both

---

## Part 8: Recommendation

### DO THIS FIRST (Before Any Code)

1. **Profile Vectorbt**
   ```python
   # Time a single strategy backtest
   import time
   symbol = "XAUUSD"
   session = "asian"
   
   start = time.time()
   pf = backtest(symbol, session, indicators={...})
   elapsed = time.time() - start
   print(f"Single backtest: {elapsed*1000:.1f}ms")
   ```

2. **Test Optuna on One Strategy**
   ```python
   # Run 50 trials on one (symbol, session, indicator) combo
   # Measure total time
   # Record convergence (does PF improve?)
   ```

3. **Evaluate Speedup Opportunities**
   - Profile where time is spent
   - Numba candidates
   - Parallelization potential

4. **Research Rustuna**
   - Check Python bindings
   - Benchmark if available
   - Decide: stay with Optuna or switch

### THEN Design the Full Pipeline

Once you have real performance data, the architecture will be clear:
- How many trials can you afford?
- Can you parallelize?
- Do you need Numba/Rustuna?
- What's total onboarding time?

---

## Summary

**Vectorbt** and **Optuna** work together:
- Vectorbt: Which indicators? (Strategy discovery)
- Optuna: What settings? (Parameter tuning)

**Key Implementation Points**:
1. Build indicator-specific parameter library
2. Create OptunaSessionTuner for each discovered strategy
3. Integrate into onboarding after Vectorbt completes
4. Optimize for speed: Numba + parallelization

**Before coding**: Profile, test, research to answer open questions.
