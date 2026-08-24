# Session-Aware Optimization Pipeline Design

## Executive Summary

The system currently has three disconnected layers:
1. **Vectorbt Onboarding** - Creates per-session baselines
2. **Optuna Optimization** - Tunes parameters (but currently ignores sessions)
3. **Scalp Engine** - Executes trades (uses static defaults, doesn't respect session toggles)

This design proposes connecting all three layers with **session-aware tuning and control**.

---

## Current Architecture Issues

### Issue 1: Vectorbt Baselines Not Feeding Into Optuna
- Vectorbt discovers best indicator/SL/TP per session (e.g., "asian H4 uses bb_20_2.5")
- These discoveries are stored but never used to initialize Optuna
- Optuna starts from scratch, ignoring proven baselines

### Issue 2: Optuna is Not Session-Aware
- Single global Optuna study per symbol
- Cannot tune different indicators for different sessions
- Doesn't understand that "asian" might prefer rsi_21 while "london" prefers bb_20_2.0"

### Issue 3: Scalp Engine Doesn't Use Session-Based Parameters
- Uses static indicator parameters from config
- Doesn't check if user has disabled sessions via UI
- Doesn't load tuned parameters per-session

### Issue 4: Session Preferences Stored But Unused
- UI toggles save enable/disable status per session
- Scalp engine ignores these preferences entirely

---

## Proposed Design: Session-Aware Optimization Pipeline

### Layer 1: Vectorbt Baseline Discovery (CURRENT ✅)
**Input:** Raw price data (all timeframes)  
**Output:** Per-session baseline strategies  
**File:** `data/qmmp/{SYMBOL}/{SYMBOL}_vectorbt_results.json`

```json
{
  "validated_strategies": {
    "asian": {
      "timeframe": "H4",
      "primary_ind": "bb_20_2.5",
      "secondary_ind": "stdev_20",
      "sl_mult": 0.5,
      "tp_ratio": 4.0,
      "pf": 10.24,
      "sharpe": 9.53
    },
    "london": {
      "timeframe": "H4",
      "primary_ind": "bb_20_2.0",
      "secondary_ind": "stdev_20",
      "sl_mult": 0.5,
      "tp_ratio": 4.0,
      "pf": 3.12,
      "sharpe": 4.53
    }
  }
}
```

**Next Step:** Initialize Optuna studies from these baselines

---

### Layer 2: Optuna Session-Aware Tuning (NEW 🚀)

#### 2.1 Create Per-Session Optuna Studies
**Trigger:** After Vectorbt onboarding completes

**For each session in validated_strategies:**
```python
study_name = f"{symbol}__{session}"
storage = f"sqlite:///data/qmmp/{symbol}/optuna/{session}_study.db"
study = optuna.create_study(
    study_name=study_name,
    storage=storage,
    direction="maximize"  # maximize profit_factor
)
```

#### 2.2 Seed Optuna with Vectorbt Baselines
**Input:** Vectorbt validated_strategies per session  
**Action:** Create initial trial from baseline

```python
# For asian session example:
baseline = validated_strategies["asian"]
trial = study.ask()
trial.suggest_categorical("indicator", [baseline["primary_ind"]])
trial.suggest_float("sl_mult", baseline["sl_mult"] * 0.8, baseline["sl_mult"] * 1.2)
trial.suggest_float("tp_ratio", baseline["tp_ratio"] * 0.9, baseline["tp_ratio"] * 1.1)
trial.suggest_categorical("secondary_filter", [baseline["secondary_ind"]])

# Evaluate against session-filtered backtest data
pf = backtest_session(symbol, session, trial_params)
study.tell(trial, pf)
```

#### 2.3 Continuous Per-Session Optimization
**During:** Live trading period

**Each session-specific Optuna study:**
- Receives live trade outcomes for that session only
- Tunes indicator/SL/TP specifically for that session
- Maintains separate hyperparameter history per session

**Storage:**
```
data/qmmp/{SYMBOL}/optuna/
├── {SESSION}_study.db          # Optuna study for this session
├── {SESSION}_tuned_params.json  # Current best params for this session
└── study_metadata.json          # Study status/progress
```

#### 2.4 Tuned Parameters Output
**File:** `data/qmmp/{SYMBOL}/optuna/{SESSION}_tuned_params.json`

```json
{
  "session": "asian",
  "indicator": "bb_20_2.5",
  "secondary_filter": "stdev_20",
  "sl_mult": 0.52,
  "tp_ratio": 4.1,
  "updated_at": "2026-08-24T17:00:00Z",
  "num_trials": 248,
  "best_pf": 10.48,
  "confidence": 0.87
}
```

---

### Layer 3: Scalp Engine Session-Aware Execution (MODIFIED ✅)

#### 3.1 Load Session Preferences
**At startup + every 30 seconds (polling):**

```python
def _load_session_preferences(symbol):
    prefs_file = f"data/qmmp/{symbol}/session_preferences.json"
    if os.path.exists(prefs_file):
        with open(prefs_file) as f:
            return json.load(f).get("enabled_sessions", [])
    return []  # If no prefs, all sessions enabled (default)
```

#### 3.2 Load Per-Session Tuned Parameters
**At startup + when file changes:**

```python
def _load_session_tuned_params(symbol, session):
    params_file = f"data/qmmp/{symbol}/optuna/{session}_tuned_params.json"
    if os.path.exists(params_file):
        with open(params_file) as f:
            return json.load(f)
    # Fallback to Vectorbt baseline
    return load_vectorbt_baseline(symbol, session)
```

#### 3.3 Check Session Before Trade
**In `_evaluate_and_trade()`:**

```python
def _evaluate_and_trade(self, base: str, adapter: BrokerAdapter):
    # ... existing checks ...
    
    # NEW: Get current session
    _session = self._get_current_session()
    
    # NEW: Check if user enabled this session
    enabled_sessions = self._load_session_preferences(base)
    if _session not in enabled_sessions:
        logger.info(f"{base}: {_session} disabled by user")
        return
    
    # NEW: Load session-specific tuned params
    tuned_params = self._load_session_tuned_params(base, _session)
    
    # Use session-tuned params for indicators
    indicators = compute_full_indicators(rates, tuned_params)
    
    # ... rest of trade logic with session-aware params ...
```

#### 3.4 Session-Specific SL/TP Application
**When placing trade:**

```python
# Get session-tuned stop-loss multiplier
sl_mult = tuned_params.get("sl_mult", 0.5)
tp_ratio = tuned_params.get("tp_ratio", 4.0)

result = adapter.place(
    action=signal.action,
    lot=_lot,
    sl=atr_value * sl_mult,  # Session-specific SL
    tp=atr_value * tp_ratio,   # Session-specific TP
    comment=f"{session}|{tuned_params['indicator']}"
)
```

---

## Data Flow: End-to-End

```
┌─────────────────────────────────────────────────────────────┐
│ 1. ONBOARDING (User clicks "Onboard Symbol")               │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. VECTORBT (test all timeframes x sessions x indicators)  │
│    Output: {SYMBOL}_vectorbt_results.json                   │
│    Per-session baseline: indicator, SL, TP, metrics        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. INIT OPTUNA (create per-session studies)                │
│    For each session:                                        │
│      - Create {SESSION}_study.db                           │
│      - Seed with vectorbt baseline trial                   │
│      - Set optimization bounds around baseline             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. LIVE TRADING (scalp_engine runs)                        │
│    Every tick:                                              │
│      - Determine current session (asian/london/etc)        │
│      - Check if user enabled this session                  │
│      - Load {SESSION}_tuned_params.json                    │
│      - Use session-specific indicators & SL/TP            │
│      - Place trade with session-aware parameters          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. OPTUNA CONTINUOUS TUNING                                │
│    For each closed trade:                                   │
│      - Extract session from trade metadata                 │
│      - Submit outcome to session-specific Optuna study     │
│      - Optuna evaluates trial, suggests next params        │
│      - Write updated {SESSION}_tuned_params.json          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. FEEDBACK LOOP                                           │
│    Dashboard shows:                                         │
│      - Per-session Optuna progress                         │
│      - Current best params per session                     │
│      - Session enable/disable toggles                      │
│      - Live P&L per session                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Foundation (Foundation for everything else)
- [ ] Create per-session Optuna studies after vectorbt onboarding
- [ ] Seed studies with vectorbt baselines
- [ ] Store tuned_params.json files per session
- [ ] Write unit tests for study initialization
- [ ] **Commit:** "feat: initialize per-session Optuna studies from vectorbt baselines"

### Phase 2: Scalp Engine Integration
- [ ] Add `_load_session_preferences()` to scalp_engine
- [ ] Add `_load_session_tuned_params()` to scalp_engine
- [ ] Modify `_evaluate_and_trade()` to check session enable/disable
- [ ] Modify trade placement to use session-tuned SL/TP
- [ ] Add session context to trade metadata/comments
- [ ] Write integration test: trade only enabled sessions
- [ ] **Commit:** "feat: scalp engine respects session preferences and uses tuned params"

### Phase 3: Optuna Integration Loop
- [ ] Connect closed trades to session-specific Optuna studies
- [ ] Extract session from trade history
- [ ] Submit P&L to appropriate session study
- [ ] Trigger new Optuna suggestions
- [ ] Write unit test: closed trade updates session study
- [ ] **Commit:** "feat: closed trades feed into session-specific Optuna optimization"

### Phase 4: Dashboard Updates
- [ ] Show per-session Optuna progress in UI
- [ ] Display current best params per session
- [ ] Show live P&L per session during trading
- [ ] Add test for dashboard endpoints
- [ ] **Commit:** "feat: dashboard displays per-session optimization progress"

### Phase 5: End-to-End Testing
- [ ] Simulate onboarding → optuna init → live trading → closed trades → retuning
- [ ] Verify session preferences control trading
- [ ] Verify tuned params improve over time
- [ ] Compare session-aware vs non-session-aware performance
- [ ] **Commit:** "test: end-to-end session-aware optimization pipeline"

---

## Testing Strategy

### Unit Tests
1. **Vectorbt → Optuna Init**
   - Input: vectorbt_results.json
   - Output: Per-session study.db files created
   - Verify: Study contains baseline trial

2. **Session Preferences Loading**
   - Create session_preferences.json
   - Verify: _load_session_preferences() returns correct list
   - Verify: Respects enable/disable state

3. **Tuned Params Loading**
   - Create {SESSION}_tuned_params.json
   - Verify: _load_session_tuned_params() returns correct params
   - Verify: Falls back to vectorbt baseline if file missing

4. **Trade Gate Check**
   - Simulate trade in disabled session
   - Verify: Trade is skipped
   - Verify: Trade proceeds if session enabled

### Integration Tests
1. **Onboarding → Optuna Chain**
   - Run vectorbt onboarding
   - Verify: Per-session studies created and seeded
   - Verify: tuned_params.json files exist per session

2. **Live Trading → Optuna Feedback**
   - Simulate 10 trades across 3 sessions
   - Verify: Each trade routed to correct session study
   - Verify: Optuna study reflects trade P&L
   - Verify: New params suggested

3. **Session Preference Control**
   - Enable only "london" and "newyork"
   - Simulate 100 ticks across all sessions
   - Verify: Only london/newyork trades executed
   - Verify: Asian/friday_evening trades skipped

### End-to-End Test
```python
def test_session_aware_pipeline_e2e():
    # 1. Onboard XAUUSD with vectorbt
    onboard_xauusd()
    
    # 2. Verify per-session Optuna studies created
    assert os.path.exists("data/qmmp/XAUUSD/optuna/asian_study.db")
    assert os.path.exists("data/qmmp/XAUUSD/optuna/london_study.db")
    
    # 3. Verify seeded with vectorbt baselines
    asian_study = optuna.load_study(storage=...)
    assert len(asian_study.trials) >= 1  # Baseline trial
    
    # 4. Disable friday_evening session
    set_session_preferences("XAUUSD", ["asian", "london", "newyork"])
    
    # 5. Start scalp engine, simulate 100 ticks
    engine = ScalpEngine()
    for tick in simulate_ticks(100):
        engine.on_tick(tick)
    
    # 6. Verify trades only in enabled sessions
    trades = get_executed_trades("XAUUSD")
    sessions_traded = {t.session for t in trades}
    assert sessions_traded <= {"asian", "london", "newyork"}
    assert "friday_evening" not in sessions_traded
    
    # 7. Verify session-tuned params were used
    for trade in trades:
        assert trade.comment  # Has session info
    
    # 8. Verify closed trades updated Optuna
    for session in ["asian", "london", "newyork"]:
        study = optuna.load_study(...)
        assert len(study.trials) > 1  # Baseline + new trials from trading
```

---

## Key Design Decisions

### Decision 1: Per-Session Optuna Studies vs Single Global Study
**Chosen:** Per-session studies
**Rationale:**
- Each session has different optimal indicators (asian prefers bb_20_2.5, london prefers bb_20_2.0)
- One global study can't represent this multi-session optimization space
- Per-session allows independent tuning, clearer optimization history
- Easier to pause/restart tuning for individual sessions

### Decision 2: Session Enable/Disable Control Location
**Chosen:** Scalp engine checks before every trade
**Rationale:**
- Real-time control (immediate effect)
- No need to restart bot after UI toggle
- Polling-based (checks file every 30s) for resilience
- Respects user intent even if checkbox changes

### Decision 3: Tuned Params Format (File vs Database)
**Chosen:** JSON files per session
**Rationale:**
- Simple, human-readable, debuggable
- Easy to inspect current state
- Easy to manually override if needed
- Optuna study.db keeps full history, JSON keeps current best

### Decision 4: Backward Compatibility
**Rationale:**
- If no session preferences file exists → all sessions enabled (safe default)
- If no tuned_params.json exists → fall back to vectorbt baseline (not silent fail)
- If no Optuna study exists → still works with vectorbt baseline

---

## Success Criteria

- ✅ Vectorbt baselines automatically seed Optuna studies
- ✅ Per-session Optuna studies created and updated independently
- ✅ Scalp engine respects session preferences (toggles prevent trades)
- ✅ Scalp engine uses session-tuned params for indicators/SL/TP
- ✅ Closed trades feed back into session-specific Optuna studies
- ✅ UI reflects session-aware optimization progress
- ✅ End-to-end test passes: onboard → optuna → trade → tune loop
- ✅ Session enable/disable works in real-time without restart

---

## Open Questions

1. **Timeframe Locking:** Should each session stick to the vectorbt-selected timeframe (e.g., asian always uses H4), or can Optuna switch timeframes?
   - Proposed: Lock to vectorbt-selected timeframe per session (less chaos)

2. **Session Overlap:** Current sessions don't cleanly separate. Should overlaps (e.g., 13:00 = london AND newyork) trade both or pick one?
   - Proposed: Check enabled sessions, if both enabled, use highest priority session's params

3. **Optuna Study Lifecycle:** When should per-session Optuna studies be created/reset?
   - Proposed: Create after vectorbt onboarding, keep across bot restarts, reset only on manual symbol re-onboarding

4. **Tuning Frequency:** How often should Optuna suggest new params? Every trade? Every 10 trades? Daily?
   - Proposed: Every completed trade (feedback loop as tight as possible)
