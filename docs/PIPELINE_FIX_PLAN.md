# COMPREHENSIVE FIX PLAN: STRATEGY-AGNOSTIC 4-PHASE PIPELINE

**Document:** Master Fix Plan (CONSOLIDATED)
**Date:** 2026-08-25
**Version:** 2.0 (Strategy-Agnostic Architecture)
**Status:** READY FOR EXECUTION
**Timeline:** 7 days, 60 hours

---

## EXECUTIVE SUMMARY

**Your System Design:** All strategies (OsMA, RSI, Stochastic, MACD, etc.) compete equally. Phase 1 discovers the best-performing strategy per session. Phase 4 deploys the winner. ScalpEngine executes what the pipeline recommends.

**What's Broken:** OsMA is hardcoded in ScalpEngine, defeating the strategy-agnostic design.

**Fix:** Implement strategy registry and generic strategy selection. All strategies first-class citizens. No hardcoding.

**Timeline:** 7 days, single engineer, 60 hours total.

---

## CORE PRINCIPLE

**"The pipeline discovers what works best per session. ScalpEngine executes what the pipeline recommends. All strategies are equals. No hardcoding."**

---

## REVERSE-ENGINEERED REQUIREMENTS

### Functional Requirements (What It Must Do)

**FR-1: Strategy Discovery (Phase 1)**
- Test ALL 40+ MT5 indicators per session per timeframe
- Rank by Profit Factor (primary), Win Rate, Sharpe Ratio
- Return: winning strategy name + baseline performance
- No strategy preferences, all tested equally

**FR-2: Strategy Optimization (Phase 2)**
- Input: winning strategy from Phase 1
- Optimize: entry floors, SL/TP parameters via Optuna
- Walk-forward validation (prevent overfitting)
- Output: strategy name + tuned parameters

**FR-3: Strategy Validation (Phase 3)**
- Backtest strategy with tuned parameters
- Compare tuned PF vs baseline PF
- Accept only if improvement proven (e.g., +2%)
- Output: accept/reject decision with reason

**FR-4: Strategy Deployment (Phase 4)**
- Store per session: strategy name + tuned parameters
- If rejected: keep baseline
- Audit trail: what was deployed, when, by which phase
- Write to: tuned_params.json

**FR-5: Strategy Selection (Live Trading - ScalpEngine)**
- Determine current session (UTC hour + weekday)
- Load strategy for current session from tuned_params.json
- Execute that strategy's entry logic
- Fallback chain: session → asian (default) → OsMA_Confluence (emergency)

**FR-6: Strategy Interface**
- Every strategy implements: `calculate_indicators()` + `generate_signal()`
- Same interface for all strategies
- Returns: FocusedSignal(action, confidence, reason)

**FR-7: Parameter Management**
- tuned_params.json: session → strategy → parameters
- Schema supports any strategy type
- Versioning and audit trail

**FR-8: Error Handling**
- Missing strategy: fallback gracefully
- Corrupt JSON: fallback to baseline
- Signal function crash: fallback to safety signal
- Log all fallbacks

### Non-Functional Requirements (How It Must Behave)

**NFR-1: Extensibility**
- Add new strategy: register it + implement interface
- No code changes to phases 1-4 or ScalpEngine
- Remove strategy: just unregister

**NFR-2: Performance**
- Phase 1: < 60 min per symbol
- Phase 2: < 30 min per symbol
- Phase 3: < 10 min per symbol
- Phase 4: < 1 min per symbol
- ScalpEngine strategy selection: < 10ms

**NFR-3: Reliability**
- 99.9% uptime during trading hours
- No unplanned crashes or silent failures
- Graceful fallback for all error cases

**NFR-4: Observability**
- Log every strategy selection, why it was chosen
- Log every fallback and reason
- Metrics: strategy win rate, entry frequency per session

**NFR-5: Data Consistency**
- All phases read from same data source (DataManager only)
- No format mismatches between phases
- Audit trail: what was tuned = what was deployed = what was used

**NFR-6: Maintainability**
- Clear strategy interface and contract
- 95%+ test coverage for strategy selection
- Every phase has integration tests with adjacent phases

**NFR-7: Safety**
- Parameters validated before deployment
- PF improvements proven before acceptance
- Bad parameters can be reverted (audit trail enables rollback)
- Live trading never uses unvalidated parameters

---

## ARCHITECTURE

### Data Flow

```
DISCOVERY (Phase 1 - Vectorbt):
  Test Strategy: OsMA → PF 1.45
  Test Strategy: RSI14 → PF 1.52 ✓ WINNER for Asian session
  Test Strategy: Stochastic → PF 1.38
  Output: {"session": "asian", "winner_strategy": "RSI14", "baseline_pf": 1.52}

OPTIMIZATION (Phase 2 - Optuna):
  Input: RSI14 + baseline params
  Tuning: Period, oversold level, overbought level
  Output: {"strategy": "RSI14", "tuned_params": {...}, "tuned_pf": 1.58}

VALIDATION (Phase 3 - Vectorbt):
  Input: RSI14 tuned params (1.58 PF)
  Check: Does 1.58 > 1.52 (baseline)?
  Result: YES, improvement 3.8% → ACCEPT
  Output: {"status": "APPROVED", "improvement_pct": 3.8}

DEPLOYMENT (Phase 4):
  Input: APPROVED validation result
  Write to tuned_params.json:
    asian session → strategy: "RSI14", params: {...}
  Audit trail updated

LIVE TRADING (ScalpEngine):
  Current time: 04:00 UTC → Session = "asian"
  Load: tuned_params.json → asian → strategy = "RSI14"
  Get: strategy object from registry
  Call: rsi14_strategy.generate_signal(indicators, params)
  Result: FocusedSignal(action="BUY", confidence=0.82)
  Execute: Place order with tuned SL/TP
```

### Schema: tuned_params.json

```json
{
  "symbol": "XAUUSD",
  "generated_at": "2026-08-25T22:00:00Z",
  "version": 2,
  "session_strategies": {
    "asian": {
      "strategy_name": "RSI14",
      "strategy_type": "momentum",
      "indicator_params": {
        "period": 14,
        "oversold_level": 32,
        "overbought_level": 68
      },
      "entry_floors": {"min_strength": 0.3},
      "exit_params": {"sl_atr_mult": 1.5, "tp_ratio": 2.5},
      "baseline": {"pf": 1.52, "wr": 0.58, "sharpe": 1.25},
      "tuned": {"pf": 1.58, "wr": 0.60, "sharpe": 1.35},
      "improvement_pct": 3.8,
      "validation_status": "APPROVED",
      "nightly_run_id": "2026-08-25T22:00:00Z"
    },
    "london": {
      "strategy_name": "OsMA_Confluence",
      ...
    },
    "newyork": {
      "strategy_name": "Stochastic14",
      ...
    }
  },
  "fallback_strategy": "OsMA_Confluence",
  "audit_trail": [...]
}
```

### Strategy Interface (All Strategies Implement This)

```python
class Strategy:
    def __init__(self, name: str, strategy_type: str):
        self.name = name
        self.strategy_type = strategy_type
    
    def calculate_indicators(self, ohlcv: DataFrame, 
                            params: Dict) -> Dict[str, Series]:
        """Calculate indicators needed for this strategy."""
        raise NotImplementedError
    
    def generate_signal(self, indicators: Dict[str, Series],
                       entry_floors: Dict[str, float]) -> StrategySignal:
        """Generate entry signal (BUY/SELL/HOLD + confidence)."""
        raise NotImplementedError
    
    def validate_params(self, params: Dict) -> bool:
        """Validate that parameters are acceptable."""
        raise NotImplementedError
```

---

## CRITICAL ISSUES & FIXES

| # | Issue | Fix | Day |
|---|-------|-----|-----|
| 1 | Phase integration contracts undefined | Trace all phase boundaries, verify contracts | 3 |
| 2 | OsMA hardcoded (contradicts design) | Implement generic strategy registry + selection | 4 |
| 3 | Parameter schema doesn't support all strategies | Unified schema: strategy_name + params | 5 |
| 4 | Data path inconsistency (DataManager vs parquet) | All phases use DataManager only | 3 |
| 5 | No parameter validation | Add schema validation + logging | 5 |
| 6 | Parameters may not reach live trading | Update Phase 4 deployer to write correctly | 5 |
| 7 | Session precedence undefined | Define: overlap > london > newyork > asian | 2 |
| 8 | No canary deployment | Use atomic writes, rollback via audit trail | 5 |
| 9 | Missing wall-clock timing | Add timestamps to orchestrator logs | 1 |
| 10 | No E2E integration test | Write full pipeline E2E test | 6 |

---

## 7-DAY IMPLEMENTATION TIMELINE

### Days 1-2: Design & Planning

**Day 1 AM: Decisions & Architecture**
- [ ] Get sign-offs on strategy-agnostic approach
- [ ] Review strategy interface contract
- [ ] Define session precedence algorithm
- [ ] Review unified schema

**Day 1 PM: Documentation**
- [ ] Write Phase Integration Specification
- [ ] Write Session Selection Algorithm spec
- [ ] Write Strategy Interface spec
- [ ] Create architecture diagrams

**Day 2 AM: Test Planning**
- [ ] Unit test specifications
- [ ] Integration test specifications
- [ ] E2E test specification

**Day 2 PM: Preparatory Work**
- [ ] Locate all phase output/input code
- [ ] Map all 40+ strategies to interface
- [ ] Inventory existing signal functions

### Day 3: Phase Integration Tracing

**Morning: Phase 1-2 Integration**
- [ ] Verify Phase 1 output matches Phase 2 input
- [ ] Fix any mismatches
- [ ] Write integration validator

**Afternoon: Data Path Unification**
- [ ] Verify all phases use DataManager
- [ ] Remove fallback to data/qmmp/
- [ ] Add error if data missing

**Deliverable:** Phase 1-2 contracts verified ✓

### Day 4: Generic Strategy Selection

**Morning: Strategy Registry**
- [ ] Create strategy registry class
- [ ] Implement strategy interface
- [ ] Register all 40+ strategies (OsMA, RSI, Stochastic, etc.)
- [ ] Implement strategy lookup by name

**Afternoon: ScalpEngine Integration**
- [ ] Update entry logic to load strategy from pipeline
- [ ] Call strategy.generate_signal() instead of OsMA hardcoded logic
- [ ] Implement fallback chain
- [ ] Add comprehensive logging

**Deliverable:** Strategy-agnostic entry logic working ✓

### Day 5: Schema & Parameter Handling

**Morning: Parameter Schema & Validation**
- [ ] Create TunedParamsSchema class (supports any strategy)
- [ ] Implement validation (schema, PF improvement, etc.)
- [ ] Add JSON serialization/deserialization
- [ ] Unit tests for schema

**Afternoon: Phase 4 Deployer & ScalpEngine Loading**
- [ ] Update Phase 4 to write new schema
- [ ] Implement strategy loading in ScalpEngine
- [ ] Add parameter validation at startup
- [ ] Implement fallback chain for missing params
- [ ] Unit tests for loading and fallback

**Deliverable:** Parameter handling complete ✓

### Day 6: Integration & E2E Testing

**Morning: Integration Tests**
- [ ] Phase 1-2 integration test
- [ ] Phase 2-3 integration test
- [ ] Phase 3-4 integration test
- [ ] Phase 4-ScalpEngine integration test

**Afternoon: E2E Pipeline Test**
- [ ] Run full discovery → tuning → validation → deployment on test symbol
- [ ] Verify all data flows correctly
- [ ] Verify ScalpEngine loads and uses parameters
- [ ] Verify strategy-specific signals fire correctly

**Deliverable:** Full pipeline E2E test passing ✓

### Day 7: Regression & Live Validation

**Morning: Full Test Suite**
- [ ] Run all existing tests (no regressions)
- [ ] Code coverage 95%+ for pipeline code
- [ ] Fix any failures

**Afternoon: Live Validation**
- [ ] Monitor nightly run on live system
- [ ] Verify strategy loading
- [ ] Check parameter usage
- [ ] Validate no silent failures

**Deliverable:** All tests passing, live validation successful ✓

---

## SIGN-OFFS REQUIRED (TODAY)

- [ ] **Strategy-Agnostic Architecture** — All strategies are equals, not OsMA-hardcoded
- [ ] **Unified Parameter Schema** — Supports any strategy name + parameters
- [ ] **Session Precedence** — overlap > london > newyork > asian > default
- [ ] **Data Path Unification** — DataManager only, no parquet fallback
- [ ] **Strategy Interface** — All strategies implement same contract
- [ ] **7-Day Timeline** — Resources committed for full-time engineer

---

## SUCCESS CRITERIA

**End of Day 7:**
- ✅ All phases integrate properly
- ✅ Strategy-agnostic selection implemented
- ✅ Parameters load correctly for any strategy
- ✅ 95%+ test coverage
- ✅ All tests passing (no regressions)
- ✅ E2E pipeline verified on real symbol
- ✅ Live trading using recommended strategy confirmed

---

## KEY FILES (FINAL)

**Only Keep These:**
1. `PIPELINE_FIX_PLAN.md` ← YOU ARE HERE (This file)
2. `DECISIONS_SIGN_OFF.md` (updated with strategy-agnostic approach)
3. `IMPLEMENTATION_CHECKLIST.md` (updated with Day 4 revised to generic strategy)
4. `MASTER_PLAN_SUMMARY.md` (quick reference)

**Delete Everything Else.** No more supplementary documents.

---

**Next Step:** Get sign-offs on 6 decisions above, then start Day 1 tomorrow morning.
