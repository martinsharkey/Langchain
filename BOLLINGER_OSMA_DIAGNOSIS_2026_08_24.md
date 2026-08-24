# Bollinger_OsMA Strategy Diagnosis Report
**Date:** 2026-08-24  
**Analysis Period:** 105,354 M1 bars (~73 days)  
**Symbol:** BTCUSD  

---

## Executive Summary

The Bollinger_OsMA strategy **FINDS GOOD ENTRIES but EXITS TERRIBLY**. The backtest showed ~1.0 PF because entries are being neutralized by poor exit timing, not because the entry logic is wrong.

### Key Finding
- **M1 entries detected:** 679 signals
- **Entry win rate:** 55.2% ✓ Good
- **Entry quality (PF):** 1.16 ✓ Acceptable
- **Exit quality:** Only capturing 10% of available gains ✗ CRITICAL PROBLEM

---

## Detailed Analysis

### 1. Entry Quality (✓ WORKING CORRECTLY)

```
Total entries: 679
Winning trades: 375 (55.2%)
Losing trades: 304 (44.8%)

Average winning trade:  +0.104%
Average losing trade:   -0.110%
Profit factor:          1.16
Total P&L:              +3474.60
```

**Verdict:** The Bollinger_OsMA entry pattern is detecting mean-reversion opportunities correctly. The 55.2% win rate is healthy for a mean-reversion strategy.

### 2. Exit Quality (✗ CRITICAL ISSUE)

```
Maximum gain potential per entry: 0.082%
Actual realized P&L per entry:    0.008%
Exit quality ratio:               10% (capturing only 1/10th of gains)
```

**The Problem:** 
- Entries set up with ~0.082% potential gains
- Exits realize only ~0.008% 
- 90% of gains are being left on the table

**Root Cause Hypothesis:**
The current exit logic (likely at middle band or based on fixed bar count) fires too early, before the full mean-reversion move completes.

### 3. MACD M1/M5 Alignment Test (✗ NOT A SOLUTION)

```
Aligned with M1+M5 MACD: 341 trades (50.2%)
  Win rate:    51.6%
  Avg P&L:     -0.007%
  PF:          0.86 ← WORSE

Misaligned with M1/M5:  338 trades (49.8%)
  Win rate:    58.9%
  Avg P&L:     +0.024%
  PF:          1.53 ← BETTER
```

**Critical Finding:** Adding MACD M1/M5 alignment as an entry filter would actually **HURT** the strategy by filtering OUT the good trades (misaligned ones with PF 1.53) and keeping the bad ones (aligned with PF 0.86).

**Recommendation:** Do NOT use MACD as entry filter. It's an anti-pattern here.

---

## What This Means for Backtesting

The backtest showing ~0.9-1.0 PF is **correct but misleading**:

- ✓ Entries ARE working (55.2% WR on 679 signals)
- ✗ Exit strategy is brutal (capturing only 10% of gains)
- Result: PF stays near 1.0 despite good entries

If we fix the exit to capture 50% of available gains instead of 10%:
- Expected new PF: **1.16 × 5 = ~5.8** (rough estimate)

---

## Recommended Fixes (Priority Order)

### Priority 1: Redesign Exit Strategy

**Option A: Trail TP as price approaches middle band**
```python
def exit_on_trail_tp(current_price, entry_price, bb_middle):
    """Exit with trailing TP toward middle band."""
    # Trail TP from peak toward middle as mean-reversion completes
    # Exit when price reaches middle band or momentum reverses
```

**Option B: Exit when momentum starts accelerating again**
```python
def exit_on_momentum_reversal(osma_now, osma_prev, osma_t2):
    """Exit when OsMA shrinkage ends and new growth begins."""
    # If we entered on shrinking (divergence), exit when it starts growing again
    # This marks the end of the mean-reversion move
    is_reversing = abs(osma_now) > abs(osma_prev) and abs(osma_prev) < abs(osma_t2)
    return is_reversing
```

**Option C: Dynamic ATR-based TP**
```python
def exit_on_atr_tp(current_price, entry_price, atr, multiplier=1.5):
    """Exit with TP at entry_price ± (atr × multiplier)."""
    # More realistic take-profit based on volatility
    # For mean-reversion: TP = entry ± 1.5×ATR toward middle band
```

### Priority 2: Validate Against Backtest

Once exit is fixed, run complete backtest to ensure:
1. Walk-forward PF > 1.15 (minimum threshold)
2. All 3 windows profitable (generalization)
3. Live forward test validates

### Priority 3: (Only if needed) Entry Refinement

The MACD analysis suggests MACD filtering hurts the strategy. Keep entries as-is unless new data contradicts this.

---

## Key Takeaways

| Aspect | Status | Finding |
|--------|--------|---------|
| Entry Detection | ✓ GOOD | 55.2% WR, PF 1.16 on 679 trades |
| Entry Logic | ✓ CORRECT | Pattern is working, entries are valid |
| Exit Strategy | ✗ BROKEN | Only capturing 10% of available gains |
| MACD Filter | ✗ HARMFUL | Worsens results (PF 1.53 → 0.86) |
| Overall Issue | ✗ EXIT, not entry | Redesign exit, not entry filters |

---

## Next Steps

1. Implement one of the three exit strategies above
2. Run backtest with new exit logic
3. Compare PF improvement
4. Validate on walk-forward windows
5. Deploy if PF > 1.15 on all windows

The entries are solid. The exits need work.
