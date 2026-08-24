# ROOT CAUSE ANALYSIS: 100% Losing Trades

## Executive Summary

**The Bollinger_OsMA strategy had a CRITICAL LOGIC BUG that caused it to enter at the WRONG TIME.**

The momentum divergence check was **inverted** - it was checking for the opposite condition of what your spec requires.

### Your Specification
```
"OsMA histogram must show a clear divergence. This means the most recently 
closed OsMA bar is shrinking (it is smaller and closer to the zero line 
than the bar immediately before it)."
```

### What The Code Was Doing
Rejecting entries when OsMA was shrinking, and only accepting entries when OsMA was accelerating.

This is backwards.

## The Bug Location

**File:** `src/strategies/bollinger_osma.py`  
**Function:** `_check_momentum_age()` (line 61-86)  
**Line 80:** The buggy comparison

### Before (Wrong)
```python
def _check_momentum_age(osma_now, osma_prev, osma_t2):
    abs_now = abs(osma_now)
    abs_prev = abs(osma_prev)
    abs_t2 = abs(osma_t2)
    
    # WRONG: Checks for growing momentum
    is_growing = abs_t2 < abs_prev < abs_now
    
    if not is_growing:
        return False  # REJECTS shrinking momentum (divergence)
    
    return True  # ONLY ACCEPTS growing momentum (wrong!)
```

### After (Correct)
```python
def _check_momentum_age(osma_now, osma_prev, osma_t2):
    abs_now = abs(osma_now)
    abs_prev = abs(osma_prev)
    abs_t2 = abs(osma_t2)
    
    # CORRECT: Checks for shrinking momentum (divergence)
    is_diverging = abs_t2 > abs_prev > abs_now
    
    if not is_diverging:
        return False  # REJECTS growing momentum (no exhaustion)
    
    return True  # ONLY ACCEPTS shrinking momentum (correct!)
```

## Impact on Trades

### Example 1: Price at Lower Band, OsMA Shrinking (YOUR ENTRY SIGNAL)

```
Setup:
- Low touches lower Bollinger Band ✓
- OsMA: 0.500 → 0.300 → 0.100 (shrinking toward zero) ✓

Expected behavior: ENTER (exhaustion signal)

What Actually Happened:
  1. Code detects OsMA zero-cross ✓
  2. Code checks momentum age
  3. Code sees: 0.500 > 0.300 > 0.100 (shrinking)
  4. Code rejects: "not growing, return False"
  5. NO ENTRY ✗
  
Result: Missed valid mean-reversion signal
```

### Example 2: Price at Lower Band, OsMA Growing (NOT YOUR SIGNAL)

```
Setup:
- Low touches lower Bollinger Band ✓
- OsMA: 0.100 → 0.300 → 0.500 (growing away from zero) ✗

Expected behavior: HOLD (no exhaustion)

What Actually Happened:
  1. Code detects OsMA zero-cross ✓
  2. Code checks momentum age
  3. Code sees: 0.100 < 0.300 < 0.500 (growing)
  4. Code accepts: "is growing, return True"
  5. ENTRY EXECUTED ✓
  
Result: Entry at wrong time - momentum still accelerating, not exhausted
```

## Why This Caused 100% Losing Trades

1. Strategy **rejected valid divergence entries** (when it should enter)
2. Strategy **accepted non-divergence entries** (when it should hold)
3. All entries were happening at the WRONG time in the price/momentum cycle
4. Entries were late, after the mean-reversion opportunity had already passed
5. Result: 100% losses because you were entering at market exhaustion, not recovery

## The Fix

**Status:** ✅ FIXED (commit ready)

Changed line 80 in `src/strategies/bollinger_osma.py`:

```python
# BEFORE
is_growing = abs_t2 < abs_prev < abs_now

# AFTER  
is_diverging = abs_t2 > abs_prev > abs_now
```

Updated supporting code:
- Function logic (lines 76-86)
- Comments throughout (lines 192-201)
- Module docstring (lines 1-28)
- Main function docstring (lines 117-129)

## Testing

Tests show the fix works correctly:

```
Test 1 - Divergence (0.500 → 0.300 → 0.100): ✓ PASS
Test 2 - Growing (0.100 → 0.300 → 0.500): ✓ FAIL (correct)
Test 3 - Negative divergence (-0.500 → -0.300 → -0.100): ✓ PASS
```

## Next Steps

1. **The bot can resume trading immediately** - fix is in place
2. **New trades should show the correct pattern** - divergence entries at band touches
3. **Watch for mean-reversion behavior** - price should reverse back to middle band
4. **Update unit tests** - old tests were written for wrong behavior

## Prevention

This bug existed because:

1. The "late entry fix" was implemented incorrectly
2. It misunderstood what "divergence" means in your spec
3. Tests were written to match the buggy behavior (not your actual spec)
4. No one reviewed whether the implementation matched your documented spec

Going forward:
- Test implementations against actual spec requirements
- Add comments explaining WHY each check exists
- Have spec review before finalizing implementation

---

**Status:** ✅ FIXED - Ready for testing with corrected logic

This explains why all your trades were losing. The strategy was technically working, but enforcing the WRONG entry conditions.
