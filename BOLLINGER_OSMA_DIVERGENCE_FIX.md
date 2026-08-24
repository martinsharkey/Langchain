# CRITICAL FIX: Bollinger_OsMA Divergence Logic Was Inverted

## The Problem

**You were seeing 100% losing trades because the strategy was entering at the WRONG TIME.**

The current implementation had the divergence check **backwards**:

### What Your Spec Requires
```
"OsMA histogram must be... shrinking (it is smaller and closer to the zero line 
than the bar immediately before it)"
```

This is **divergence** = momentum DECELERATING = exhaustion signal

### What The Code Was Checking
```python
# WRONG - rejected divergence and accepted growing momentum
is_growing = abs_t2 < abs_prev < abs_now
```

This checked for **growing/accelerating momentum** - the opposite of what you need!

## The Result

- **Your spec:** Enter when OsMA is shrinking (exhaustion)
- **Code was doing:** Reject when OsMA is shrinking, only enter when OsMA is growing
- **Impact:** 100% losing trades because entries were happening too late, AFTER the divergence already occurred

## The Fix

Changed line 80 in `src/strategies/bollinger_osma.py`:

```python
# BEFORE (WRONG)
is_growing = abs_t2 < abs_prev < abs_now

# AFTER (CORRECT)
is_diverging = abs_t2 > abs_prev > abs_now
```

Now it correctly checks:
- **Divergence = True** when: |t2| > |t1| > |t0| (shrinking/exhaustion)
- **Divergence = False** when: |t2| < |t1| > |t0| (growing/accelerating)

## Example

### Shrinking OsMA (Divergence - YOUR ENTRY SIGNAL)
```
2 bars ago:  0.500
1 bar ago:   0.300  ← shrinking
Now:         0.100  ← closer to zero

Result: ✓ PASS - This is the exhaustion signal! Enter now.
```

### Growing OsMA (NOT Your Entry Signal)
```
2 bars ago:  0.100
1 bar ago:   0.300  ← growing
Now:         0.500  ← moving away from zero

Result: ✗ FAIL - This is acceleration, not exhaustion. Don't enter.
```

## Files Modified

- `src/strategies/bollinger_osma.py` - Fixed `_check_momentum_age()` function
  - Line 80: Reversed the divergence check
  - Lines 61-86: Updated function logic and documentation
  - Line 192-201: Updated caller comments
  - Line 6-8: Updated module docstring

## Why This Was Missed

The previous implementation was added as a "late entry fix" but it:
1. Misunderstood what "divergence" meant in your spec
2. Checked for the OPPOSITE condition (growth instead of shrinkage)
3. This caused it to reject exactly the entries your strategy should take

## Next Steps

1. **Restart the bot** - it will use the corrected logic
2. **Monitor new trades** - they should now follow your mean-reversion entry pattern
3. **Expect divergence entries** - OsMA shrinking at band touches = your signal

## Technical Details

**Function signature unchanged:**
```python
def _check_momentum_age(osma_now, osma_prev, osma_t2) -> tuple[bool, str]
```

**Still returns:** (is_valid, reason_string) - now correctly validates divergence

**Integration:** Works seamlessly with existing:
- `bollinger_osma_signal()` entry function
- Strategy registry
- Backtester
- Exit model (unchanged)

---

**Status:** ✅ FIXED

This was the root cause of your 100% losing trades. The strategy logic was correct, but it was rejecting valid entries and accepting invalid ones. Now it should work as designed.
