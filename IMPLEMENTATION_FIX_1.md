# PHASE 1, FIX #1: THREAD INDICATORS THROUGH PIPELINE
## Pass complete indicator data to ExperienceDB

**Status:** Ready to implement  
**Effort:** 2-4 hours  
**Priority:** CRITICAL (unblocks all learning)

---

## PROBLEM STATEMENT

Currently, when a trade is recorded in the learning system, the indicators passed to ExperienceDB are incomplete:

```python
# Current (BROKEN) - line 572-577 in meta_strategy_agent.py
indicators = {
    "trend": decision.get("market_regime", "unknown"),
    "rsi": None,
    "atr": None,
}
```

This means ExperienceDB can only analyze trends. It's missing:
- RSI (momentum indicator)
- ATR (volatility)
- MACD (trend strength)
- Bollinger Bands (volatility bands)
- Support/Resistance levels
- EMA (trend confirmation)
- Any other technical indicators

**Result:** Experience database is blind. Can't identify what conditions led to wins/losses.

---

## ROOT CAUSE ANALYSIS

The indicators ARE calculated in `run_research()` and `run_strategy_design()`, but they're not threaded through the execution pipeline.

**Current data flow:**
```
run_research()
  └─> calculates full indicators dict
  └─> returns to run_trading_cycle()

run_strategy_design(research)
  └─> receives research.get("indicators")
  └─> uses indicators to run strategies
  └─> BUT doesn't return them
  └─> returns only signal

run_trading_cycle()
  └─> receives strategy_result (no indicators)
  └─> passes to execute_trade()

execute_trade()
  └─> calls record_outcome()
  └─> BUT has no indicators!
  └─> creates empty indicators dict

meta_strategy.record_outcome()
  └─> receives empty indicators
  └─> records with {trend, rsi: None, atr: None}
```

**What we need:**
```
run_research()
  └─> returns {"indicators": full_dict, ...}

run_strategy_design()
  └─> returns {"indicators": full_dict, "signal": ..., ...}

execute_trade(strategy_result)
  └─> receives strategy_result["indicators"]
  └─> passes to record_outcome()

record_outcome()
  └─> receives full indicators
  └─> stores in experience DB
```

---

## IMPLEMENTATION STEPS

### Step 1: Add indicators parameter to record_outcome() method

**File:** `src/learning/meta_strategy_agent.py`  
**Current location:** Line ~520 (method definition)

**Change:**
```python
# BEFORE (line ~520)
def record_outcome(
    self,
    decision: dict,
    profit_loss: float,
    exit_price: Optional[float] = None,
    exit_reason: Optional[str] = None,
) -> None:

# AFTER
def record_outcome(
    self,
    decision: dict,
    profit_loss: float,
    exit_price: Optional[float] = None,
    exit_reason: Optional[str] = None,
    indicators: Optional[dict] = None,  # ← ADD THIS
) -> None:
```

### Step 2: Use passed-in indicators instead of creating empty dict

**File:** `src/learning/meta_strategy_agent.py`  
**Current location:** Line 572-577

**Change from:**
```python
# We need indicators for the experience DB - store what we have
indicators = {
    "trend": decision.get("market_regime", "unknown"),
    "rsi": None,
    "atr": None,
}
```

**Change to:**
```python
# Use passed-in indicators, fallback to minimal if not provided
if indicators is None:
    # Fallback: create minimal indicators from decision
    indicators = {
        "trend": decision.get("market_regime", "unknown"),
        "rsi": None,
        "atr": None,
    }
# Otherwise use the full indicators dict that was passed in
```

### Step 3: Update run_strategy_design() to return indicators

**File:** `src/main.py`  
**Current location:** Line ~389-477 (run_research method) or wherever run_strategy_design is defined

Need to find where run_strategy_design() returns its result. It should return the strategy signal AND the indicators used.

**Change the return statement to include indicators:**
```python
return {
    "signal": decision,
    "indicators": indicators,  # ← ADD THIS LINE
    "reasoning": reasoning,
    "rag_analysis": rag_analysis,
    "strategies_evaluated": strategies_evaluated,
}
```

### Step 4: Update run_trading_cycle() to capture indicators

**File:** `src/main.py`  
**Current location:** Line ~XXX (wherever run_trading_cycle calls run_strategy_design)

**Change:**
```python
# Before
strategy_result = self.run_strategy_design(research)

# After (no change needed - already captures full result)
strategy_result = self.run_strategy_design(research)
# strategy_result now has {"signal": ..., "indicators": ..., ...}
```

### Step 5: Update execute_trade() to pass indicators

**File:** `src/main.py`  
**Current location:** Line 791-795

**Change from:**
```python
if self.meta_strategy:
    self._print_step("Recording trade for learning...", "running")
    self.meta_strategy.record_outcome(
        decision=signal,
        profit_loss=0.0,  # Will be updated when trade closes
        exit_reason="pending",
    )
```

**Change to:**
```python
if self.meta_strategy:
    self._print_step("Recording trade for learning...", "running")
    self.meta_strategy.record_outcome(
        decision=signal,
        profit_loss=0.0,  # Will be updated when trade closes
        exit_reason="pending",
        indicators=strategy_result.get("indicators"),  # ← ADD THIS
    )
```

---

## VERIFICATION CHECKLIST

After implementing this fix, verify:

- [ ] Code compiles without errors
- [ ] Bot runs through one trading cycle
- [ ] ExperienceDB records show indicators field populated
- [ ] Check database: indicators should have RSI, ATR, MACD, etc. (not just trend)
- [ ] No exceptions raised when accessing strategy_result["indicators"]

**SQL Query to verify (SQLite):**
```sql
SELECT trade_id, indicators FROM trades 
WHERE trade_id > (SELECT MAX(trade_id) - 5 FROM trades);
```

Should show indicators JSON like:
```json
{
  "rsi": 45.2,
  "atr": 12.5,
  "macd": -0.15,
  "trend": "uptrend",
  "ema_9": 2050.4,
  "bb_upper": 2055.0,
  "bb_lower": 2045.0,
  ...
}
```

NOT like:
```json
{
  "trend": "uptrend",
  "rsi": null,
  "atr": null
}
```

---

## DEPENDENCIES

This fix has NO dependencies. It can be done independently.

**Blocks:** Fix #2 (pattern_id tracking), Fix #4 (using experience data)

---

## ESTIMATED TIME BREAKDOWN

- Finding run_strategy_design() definition: 10 min
- Adding indicators parameter: 5 min
- Threading through 3 methods: 30 min
- Testing + verification: 30 min
- Debugging issues: 30-60 min

**Total: 2-4 hours**

---

## NEXT STEP

Once this is complete:
1. Run bot for 2-3 trading cycles
2. Check SQLite database
3. Verify indicators are populated
4. Then move to Fix #2 (pattern_id tracking)

---

## RISK ASSESSMENT

**Low risk** - purely additive change
- No logic changes
- No algorithm changes
- Just threading data through
- If indicators param is None, fallback works

**Testing:** Run bot once, check database
