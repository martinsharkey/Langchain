# PHASE INTEGRATION SPECIFICATION

**Document:** Phase 1 → Phase 2 → Phase 3 → Phase 4 Integration Contract
**Date:** 2026-08-25
**Status:** SPECIFICATION

---

## Phase 1 Output → Phase 2 Input

### Phase 1: Vectorbt Discovery Output Format

```python
@dataclass
class DiscoveredStrategy:
    session: str                    # e.g., "asian", "london", "newyork"
    timeframe: str                  # e.g., "M15", "H1"
    strategy_name: str              # e.g., "RSI14", "OsMA_Confluence", "Stochastic14"
    strategy_type: str              # e.g., "momentum", "confluence", "volatility"
    indicator_params: Dict[str, float]  # strategy-specific params
    baseline_pf: float              # Profit Factor from discovery
    baseline_wr: float              # Win Rate (0.0-1.0)
    baseline_sharpe: float          # Sharpe Ratio
    baseline_trades: int            # Number of trades in backtest
    
@dataclass
class Phase1Output:
    symbol: str
    timeframe: str
    session: str
    discovered_strategies: List[DiscoveredStrategy]  # ranked by PF
    date_range: Dict                # {"start": "2026-01-01", "end": "2026-08-25"}
    timestamp: str                  # ISO format
```

**Example JSON Output:**
```json
{
  "symbol": "XAUUSD",
  "timeframe": "M15",
  "session": "asian",
  "discovered_strategies": [
    {
      "session": "asian",
      "timeframe": "M15",
      "strategy_name": "RSI14",
      "strategy_type": "momentum",
      "indicator_params": {"period": 14},
      "baseline_pf": 1.52,
      "baseline_wr": 0.58,
      "baseline_sharpe": 1.25,
      "baseline_trades": 145
    },
    {
      "strategy_name": "OsMA_Confluence",
      "baseline_pf": 1.45,
      ...
    },
    {
      "strategy_name": "Stochastic14",
      "baseline_pf": 1.38,
      ...
    }
  ],
  "date_range": {"start": "2026-01-01", "end": "2026-08-25"},
  "timestamp": "2026-08-25T22:00:00Z"
}
```

### Phase 2 Input Requirements

Phase 2 (Optuna Tuning) receives the TOP strategy from Phase 1:

```python
@dataclass
class Phase2Input:
    symbol: str
    session: str
    timeframe: str
    strategy_name: str
    strategy_type: str
    indicator_params: Dict[str, float]          # FROM Phase 1
    baseline_pf: float                          # FROM Phase 1
    baseline_wr: float                          # FROM Phase 1
    baseline_sharpe: float                      # FROM Phase 1
    baseline_trades: int                        # FROM Phase 1
    ohlcv_data: pd.DataFrame                    # OHLCV bars
    optuna_trials: int = 500                    # Config
```

**Contract Verification:**
- ✅ Phase 1 output includes: strategy_name, indicator_params, baseline_pf
- ✅ Phase 2 input includes: all of the above
- ✅ No data transformation needed (direct pass-through)

---

## Phase 2 Output → Phase 3 Input

### Phase 2: Optuna Tuning Output

```python
@dataclass
class Phase2Output:
    symbol: str
    session: str
    timeframe: str
    strategy_name: str
    strategy_type: str
    baseline_pf: float
    baseline_wr: float
    baseline_sharpe: float
    tuned_params: Dict[str, float]              # optimized parameters
    best_trial_id: int
    best_trial_pf: float                        # PF with tuned params
    study_db_path: str                          # Optuna SQLite location
    timestamp: str
```

### Phase 3 Input Requirements

```python
@dataclass
class Phase3Input:
    symbol: str
    session: str
    timeframe: str
    strategy_name: str
    baseline_pf: float                          # FROM Phase 1
    baseline_wr: float
    baseline_sharpe: float
    tuned_params: Dict[str, float]              # FROM Phase 2
    tuned_pf: float                             # FROM Phase 2 trial
    ohlcv_data: pd.DataFrame                    # For validation backtest
    improvement_threshold: float = 0.02         # min +2% PF improvement
```

**Contract Verification:**
- ✅ Phase 2 output includes: strategy_name, tuned_params, best_trial_pf
- ✅ Phase 3 input includes: all of the above
- ✅ Direct pass-through, no transformation

---

## Phase 3 Output → Phase 4 Input

### Phase 3: Validation Output

```python
@dataclass
class Phase3Output:
    symbol: str
    session: str
    timeframe: str
    strategy_name: str
    accepted: bool                              # APPROVED or REJECTED
    baseline_pf: float
    baseline_wr: float
    tuned_pf: float
    tuned_wr: float
    improvement_pct: float                      # (tuned_pf - baseline_pf) / baseline_pf * 100
    acceptance_reason: str or None              # "PF improved 3.8%"
    rejection_reason: str or None               # "PF declined 1.2%"
    tuned_params: Dict[str, float]              # ONLY if accepted
    indicator_params: Dict[str, float]
    exit_params: Dict[str, float]
    entry_floors: Dict[str, float]
```

### Phase 4 Input Requirements

Phase 4 (Deployer) receives validation result per session:

```python
@dataclass
class Phase4Input:
    symbol: str
    validation_results: Dict[str, Phase3Output]  # per session
    # e.g., {
    #   "asian": Phase3Output(accepted=True, ...),
    #   "london": Phase3Output(accepted=False, ...),
    #   "newyork": Phase3Output(accepted=True, ...)
    # }
```

**Contract Verification:**
- ✅ Phase 3 output includes: strategy_name, accepted, tuned_params
- ✅ Phase 4 input includes: validation_results dict
- ✅ Phase 4 can determine: deploy or keep baseline per session

---

## Phase 4 Output → Live Trading Input

### Phase 4: Deployment Output (tuned_params.json)

```json
{
  "symbol": "XAUUSD",
  "generated_at": "2026-08-25T22:00:00Z",
  "version": 2,
  "session_strategies": {
    "asian": {
      "strategy_name": "RSI14",
      "strategy_type": "momentum",
      "indicator_params": {"period": 14},
      "entry_floors": {"min_strength": 0.3},
      "exit_params": {"sl_atr_mult": 1.5, "tp_ratio": 2.5},
      "baseline": {"pf": 1.52, "wr": 0.58},
      "tuned": {"pf": 1.58, "wr": 0.60},
      "improvement_pct": 3.8,
      "validation_status": "APPROVED"
    }
  }
}
```

### ScalpEngine (Live Trading) Input Requirements

```python
# ScalpEngine loads at entry time:
current_session = get_current_session()  # e.g., "asian"
strategy_config = tuned_params_json['session_strategies'][current_session]

strategy_name = strategy_config['strategy_name']      # e.g., "RSI14"
indicator_params = strategy_config['indicator_params'] # e.g., {"period": 14}
entry_floors = strategy_config['entry_floors']
exit_params = strategy_config['exit_params']

strategy = registry.get_strategy(strategy_name)
indicators = strategy.calculate_indicators(rates, indicator_params)
signal = strategy.generate_signal(indicators, entry_floors)
```

**Contract Verification:**
- ✅ Phase 4 output (JSON) includes: strategy_name, indicator_params, exit_params
- ✅ ScalpEngine can load and use all required fields
- ✅ Strategy registry can locate strategy by name

---

## INTEGRATION VALIDATION CHECKLIST

**Phase 1 → Phase 2:**
- [ ] Phase 1 returns `List[DiscoveredStrategy]`
- [ ] Phase 2 accepts top strategy from Phase 1
- [ ] strategy_name, indicator_params, baseline_pf flow through
- [ ] No data transformation needed

**Phase 2 → Phase 3:**
- [ ] Phase 2 returns `Phase2Output` with tuned_params, best_trial_pf
- [ ] Phase 3 accepts `Phase3Input` with same fields
- [ ] Validation logic: compare baseline_pf vs tuned_pf
- [ ] No data transformation needed

**Phase 3 → Phase 4:**
- [ ] Phase 3 returns acceptance/rejection per session
- [ ] Phase 4 receives `Dict[session, Phase3Output]`
- [ ] Phase 4 writes to tuned_params.json
- [ ] Only ACCEPTED strategies deployed

**Phase 4 → ScalpEngine:**
- [ ] tuned_params.json written correctly
- [ ] ScalpEngine can load strategy_name, indicator_params, exit_params
- [ ] Strategy registry can instantiate strategy by name
- [ ] Strategy can calculate_indicators() and generate_signal()

---

**Status:** SPECIFICATION COMPLETE - Ready for implementation
