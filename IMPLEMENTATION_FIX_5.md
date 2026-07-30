# PHASE 2, FIX #5: APPLY RAG ADJUSTMENT EARLY IN DECISION
## Make confidence penalties influence actual trading decisions

**Status:** Ready to implement  
**Effort:** 1-2 hours  
**Priority:** HIGH (closes knowledge gap in risk assessment)  
**Dependencies:** Fix #3 (real outcomes) recommended

---

## PROBLEM STATEMENT

RAG analysis calculates a confidence penalty but it's applied too late to matter:

**Current flow (BROKEN):**
```
1. Strategies run → base confidence = 0.65
2. Ensemble calculated
3. RAG analysis done → penalty = -15%
4. LLM evaluates signals → confidence adjusted to 0.55
5. Decision synthesized
6. Risk manager checks → uses ORIGINAL 0.65!
7. Trade executed
```

**Result:** RAG penalty shown in console but has 0% impact on actual trading

**Why this matters:**
- Historical analysis suggests caution (pattern not winning recently)
- But risk manager doesn't hear the warning
- Bot trades with confidence it shouldn't have

---

## ROOT CAUSE

The confidence adjustment is calculated but never passed to the risk manager.

```python
# In main.py, around line 520-541
# RAG analysis calculates adjustment
rag_analysis = {
    "confidence_adjustment": -0.15,
    "reasoning": "Recent similar patterns had 40% win rate",
}

# But risk_check() receives original signal, not adjusted signal
risk_result = self.run_risk_check(signal)  # ← Gets original confidence

# Decision uses adjusted confidence
# But what matters for trading is risk_result approval, which didn't see adjustment
```

---

## IMPLEMENTATION STEPS

### Step 1: Modify signal dict to include RAG adjustment

**File:** `src/learning/meta_strategy_agent.py`  
**Location:** In `decide()` method, after RAG analysis

**Add this:**
```python
def decide(self, indicators, market_data, min_confidence=0.5):
    # ... existing code ...
    
    # Run RAG analysis
    rag_analysis = self.matcher.analyze_current_market(indicators)
    
    # ← ADD THIS SECTION:
    # Calculate confidence adjustment from RAG
    rag_adjustment = rag_analysis.get("confidence_adjustment", 0.0)
    rag_reasoning = rag_analysis.get("reasoning", "No historical data available")
    
    # Return both the adjustment and reasoning
    return {
        "rag_adjustment": rag_adjustment,
        "rag_reasoning": rag_reasoning,
        # ... existing return values ...
    }
```

### Step 2: Pass RAG adjustment to risk check

**File:** `src/main.py`  
**Location:** In `run_trading_cycle()`, where risk check is called

**Change from:**
```python
def run_trading_cycle(self):
    # ... existing code ...
    
    risk_result = self.run_risk_check(signal, strategy_result)
```

**Change to:**
```python
def run_trading_cycle(self):
    # ... existing code ...
    
    # Get RAG adjustment from strategy result
    rag_adjustment = strategy_result.get("rag_adjustment", 0.0)
    
    # Pass adjusted confidence to risk check
    signal_with_adjustment = signal.copy()
    original_confidence = signal.get("confidence", 0.5)
    adjusted_confidence = max(0.0, min(1.0, original_confidence + rag_adjustment))
    signal_with_adjustment["confidence"] = adjusted_confidence
    signal_with_adjustment["rag_adjustment"] = rag_adjustment
    
    risk_result = self.run_risk_check(signal_with_adjustment, strategy_result)
```

### Step 3: Risk check uses adjusted confidence

**File:** `src/agents/risk_agent.py`  
**Location:** In `run_risk_check()` method

**Change from:**
```python
def run_risk_check(self, signal):
    confidence = signal.get("confidence", 0.5)
    
    if confidence < 0.5:
        return {"approved": False, "reason": "Low confidence"}
```

**Change to:**
```python
def run_risk_check(self, signal):
    confidence = signal.get("confidence", 0.5)
    rag_adjustment = signal.get("rag_adjustment", 0.0)
    
    # Log the adjustment for transparency
    if rag_adjustment != 0.0:
        adjustment_text = f"{rag_adjustment*100:+.1f}%" 
        print(f"  [dim]RAG confidence adjustment: {adjustment_text}[/dim]")
    
    if confidence < 0.5:
        return {
            "approved": False,
            "reason": f"Low confidence ({confidence:.2f})",
            "rag_adjustment_applied": rag_adjustment,
        }
```

### Step 4: Display RAG influence in console

**File:** `src/main.py`  
**Location:** In `run_trading_cycle()`, after risk check

**Add this:**
```python
# After risk_result = self.run_risk_check(...)

# Show RAG impact
rag_adjustment = strategy_result.get("rag_adjustment", 0.0)
if rag_adjustment != 0.0:
    console.print(f"\n  [bold cyan]RAG Historical Analysis:[/bold cyan]")
    console.print(f"    Confidence adjustment: {rag_adjustment*100:+.1f}%")
    console.print(f"    Reasoning: {strategy_result.get('rag_reasoning', 'N/A')}")
    
    if risk_result.get("approved"):
        console.print(f"    [green]✓ Risk approved despite adjustment[/green]")
    else:
        console.print(f"    [yellow]⚠ Risk rejected (adjustment contributed)[/yellow]")
```

---

## VERIFICATION CHECKLIST

After implementing this fix, verify:

- [ ] RAG adjustment captured in decide()
- [ ] Adjustment passed through to risk_check()
- [ ] Risk manager applies adjusted confidence
- [ ] Console shows RAG adjustment clearly
- [ ] Code compiles without errors

**Test scenario:**
1. Run bot
2. Force RAG analysis to return -15% adjustment
3. Verify signal confidence reduced
4. Verify risk manager sees reduced confidence
5. Check console output shows adjustment

**Expected console output:**
```
Phase 5: Risk Assessment
  RAG Historical Analysis:
    Confidence adjustment: -15.0%
    Reasoning: Similar patterns had 40% win rate (below threshold)
    ⚠ Risk rejected (adjustment contributed)
```

---

## BEFORE & AFTER

**BEFORE (Broken):**
```
Bot calculates: "Similar patterns had 40% win rate, reduce confidence 15%"
Console shows: "Confidence adjustment: -15%"
Risk manager checks: Original confidence (no adjustment)
Result: Risk manager approves trade bot should have rejected
```

**AFTER (Fixed):**
```
Bot calculates: "Similar patterns had 40% win rate, reduce confidence 15%"
Console shows: "Confidence adjustment: -15%"
Risk manager checks: Adjusted confidence (reduced by 15%)
Result: Risk manager properly rejects/approves based on historical data
```

---

## DEPENDENCIES

**Depends on:** Fix #3 (real outcomes) - Need ground truth for RAG confidence

**Enables:** Fix #6 (knowledge extraction), Fix #7 (weight persistence)

---

## ESTIMATED TIME BREAKDOWN

- Modifying decide() return: 10 min
- Passing adjustment through: 15 min
- Updating risk_check(): 15 min
- Console display: 10 min
- Testing + debugging: 20 min

**Total: 1-2 hours**

---

## RISK ASSESSMENT

**Low risk:**
- No logic changes to core algorithms
- Just threading existing data
- Falls back gracefully if adjustment is 0
- Improves signal quality without breaking anything

---

## IMPACT

**After this fix:**
- RAG analysis actually influences trades
- Risk manager makes better decisions
- Historical patterns matter
- Bot becomes more cautious when appropriate

**Metric to track:**
- % of trades rejected due to RAG adjustment
- Average confidence of accepted vs rejected trades
- Correlation between RAG adjustment and trade outcomes

---

## NEXT STEP

After Fix #5, move to Fix #6 (knowledge rule extraction)
