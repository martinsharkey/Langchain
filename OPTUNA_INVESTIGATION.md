# How Optuna Works in Your Codebase - Actual Implementation

## CRITICAL FINDING: Optuna is NOT Used for Parameter Optimization Yet

After investigating the codebase, here's what I discovered:

### What EXISTS:
1. **param_optimizer.py** - Defines the parameter tuning structure
   - Defines `PARAM_SPACE` with 25+ tunable parameters (osma_fast, osma_slow, atr_period, sl_atr, tp_rr, etc.)
   - Defines `SYMBOL_BASELINES` with initial values (not hardcoded floors - those come from Vectorbt)
   - Has infrastructure for applying tuned params and session overrides
   - **BUT: No actual Optuna library usage - no trials, no studies, no optimization logic**

2. **param_optimizer.py applies_tuned()** - Persists tuned parameters to `data/tuned_params.json`
   - Structure: `tuned[symbol]["params"] = {...}`
   - Supports per-session overrides: `session_Asian`, `session_London`, etc.
   - BUT: No code that UPDATES these params based on live results

### What's MISSING:
- No Optuna library imports (`import optuna`)
- No trial creation/suggestion logic
- No walk-forward validation loop
- No feedback mechanism from closed trades to the tuning system
- No optimization algorithm (random search, Bayesian, etc.)

## Your Current Architecture

```
Vectorbt Baselines (EXIST ✅)
  ↓ stores in: {SYMBOL}_vectorbt_results.json
  
Tuned Params JSON (EXIST ✅)  
  ↓ stored at: data/tuned_params.json
  
Scalp Engine loads params (EXIST ✅)
  ↓ reads tuned params from JSON
  
Live Trading (EXIST ✅)
  ↓ closes trades
  
??? MISSING ??? - Feedback Loop
  ↓ NO CODE sends trade outcomes back to optimizer
  
Optuna Studies (DON'T EXIST ❌)
  ↓ NO CODE creates or manages Optuna studies
```

## What ACTUALLY Needs to Happen

For Optuna to work properly in your system:

### 1. Define What Optuna Changes
Optuna is a **hyperparameter optimization framework**. It needs to know:
- **PARAMETERS TO CHANGE:** Which ones? (osma_fast, sl_atr, tp_rr, etc.)
- **SEARCH SPACE:** What are min/max/step values for each? (already in PARAM_SPACE ✅)
- **OBJECTIVE FUNCTION:** What metric to maximize? (profit_factor? sharpe_ratio? win_rate?)
- **CONSTRAINTS:** What's acceptable? (min trades? max drawdown?)

### 2. Define the Optimization Loop
For EACH parameter suggestion from Optuna:
1. Take suggested values (e.g., osma_fast=18, sl_atr=1.2)
2. Run WALK-FORWARD BACKTEST on historical data filtered by session
3. Calculate objective (e.g., profit_factor)
4. Report result back to Optuna: `study.tell(trial, profit_factor)`
5. Optuna analyzes ALL past trials and suggests NEXT parameters
6. Repeat

### 3. Per-Session Requirement
For session-aware optimization:
- Create ONE study per session
- Each study only backtests data from that session
- Only trades in that session inform that study
- Can run studies in parallel (asian, london, newyork independently)

## Critical Questions YOU Must Answer

Before implementing Optuna, you need to decide:

### Q1: What Should Optuna CHANGE?
Options:
- **A) Indicator parameters only** (osma_fast, ema_period, rsi_period)
  - Pros: Conservative, less chaos
  - Cons: May not find best floors
- **B) Floors only** (osma_min_long, sl_atr, tp_rr)
  - Pros: Vectorbt already found indicators, just tune thresholds
  - Cons: Coupled with Vectorbt
- **C) Both indicators AND floors**
  - Pros: Full freedom
  - Cons: Huge search space, slow convergence
- **D) Session-specific overrides only** (tune session_{Asian,London} params)
  - Pros: Session-aware from start
  - Cons: Complex, many combinations

### Q2: What's the Objective Function?
Optuna maximizes ONE metric. What should it be?
- **profit_factor** (PF)? - Simple, proven, but can be gamed with few trades
- **sharpe_ratio**? - Risk-adjusted, good but requires sufficient trades
- **weighted score** (0.6*PF + 0.4*WinRate)? - Balanced
- **edge** (PF - 1.0) * TradeCount? - Accounts for sample size

### Q3: Where Do Validation Data Come From?
Options:
- **A) Historical backtest** (slower, offline)
- **B) Live trading** (slow, real risk)
- **C) Hybrid** (backtest initially, then live feedback)

### Q4: Optimization Frequency?
- **Daily?** (recalculate every 24h)
- **Weekly?** (slower but more stable)
- **Continuous** (every N closed trades)?
- **Manual only** (user triggers)?

### Q5: Session-Specific or Global?
Currently, you have 5 sessions (asian, london, newyork, overlap_london_ny, friday_evening).
Options:
- **Global optimization** - One study for all sessions
- **Per-session optimization** - Separate study per session
- **Hierarchical** - Global baseline + session-specific overrides

## How Optuna Typically Works (For Reference)

```python
import optuna

# 1. Define objective function
def objective(trial):
    # Suggest parameters
    osma_fast = trial.suggest_int("osma_fast", 5, 34)
    sl_atr = trial.suggest_float("sl_atr", 0.5, 3.0)
    
    # Backtest with these params
    pf = backtest_session(symbol, session, osma_fast=osma_fast, sl_atr=sl_atr)
    
    # Return objective to maximize
    return pf

# 2. Create study
study = optuna.create_study(
    direction="maximize",  # maximize profit_factor
    storage="sqlite:///study.db"
)

# 3. Optimize
study.optimize(objective, n_trials=100)

# 4. Get best params
best_params = study.best_params
best_value = study.best_value
```

## Recommendation: Before You Code Optuna

**YOU SHOULD DECIDE:**

1. Which parameters should Optuna tune? (Indicators? Floors? Both?)
2. What's the optimization objective? (PF? Sharpe? Custom formula?)
3. Per-session or global?
4. How often should it re-optimize?

**THEN:**

The Vectorbt → Optuna → Scalp Engine pipeline will be clear:
- Vectorbt discovers initial baseline
- Optuna refines it based on YOUR optimization criteria
- Scalp engine uses tuned params
- Closed trades feed back (if you choose live feedback)

Without answering these, implementing Optuna will be guessing at:
- What parameters matter
- How to measure "better"
- How to prioritize competing goals
