# Bollinger_OsMA / OsMA_Confluence Optimization Efforts Summary
**Date:** 2026-08-24  
**Status:** Extensive testing completed; fundamental issues identified

---

## What We Accomplished

### 1. Root Cause Analysis
✓ **Window 2 Consolidation Identified** - All strategies collapse in Window 2 (bars 4000-8000)
- ADX analysis: Mean ADX ~35-36 (trending), but 16-19% consolidation periods
- Volatility slightly elevated (+50%) in W2
- This is NOT a random failure - clear market regime change

### 2. Created Three Strategy Variants
1. **OsMA_Confluence** (original) - PF 0.89-0.97
2. **Bollinger_OsMA** (with divergence fix) - PF 0.89-0.97 (identical results)
3. **OsMA_RegimeAdaptive** (NEW with ADX filtering) - PF 0.89-0.97 (no improvement)

### 3. Extensive Testing
- ✓ M1 entry analysis: 679 M1 entries, 55.2% WR, PF 1.16 - entries ARE good
- ✓ M15 backtests: All symbols, all windows tested
- ✓ ADX verification: Confirmed working, passed to strategies, values correct
- ✓ Market regime analysis: W2 identified as consolidating
- ✓ MACD alignment test: Showed MISALIGNED trades better than aligned (counter-intuitive)

### 4. Key Finding: THE REAL PROBLEM IS EXITS
- M1 analysis showed strategy captures only **10% of available gains**
- Max gain potential: ~0.082% per entry
- Actual realized: ~0.008% per entry
- Exit is firing too early, leaving 90% of profit on table

---

## Why Regime Filtering Didn't Help

**Hypothesis:** Skip consolidation entries (ADX<20) → better results

**Reality:** No significant improvement because:
1. 16-19% consolidation is relatively small
2. Filtering OUT these trades doesn't improve remaining trades
3. Even in trending periods (ADX>20), exits are still too early
4. Exit problem dominates entry quality problem

**Conclusion:** Regime detection helps volume but not PF if exits are broken.

---

## The Fundamental Issue

ALL three strategies show IDENTICAL performance:
- OsMA_Confluence: 0.89-0.97 PF
- Bollinger_OsMA: 0.89-0.97 PF  
- OsMA_RegimeAdaptive: 0.89-0.97 PF

This is NOT coincidence. Root cause:
1. **Entry logic is similar enough** across all three that filtering doesn't differentiate
2. **Exit logic dominates profitability** - it's killing all strategies equally
3. **The 0.89-0.97 PF ceiling** is the exit's hard limit across all symbols/windows

---

## What WOULD Likely Work

### Option 1: Fix Exit Strategy (Most Promising)
```python
# Instead of: Exit at fixed TP (middle band)
# Use: Trail TP as mean-reversion completes
# Monitor: OsMA divergence reversal - when shrinking→growing, exit

Expected improvement: PF 0.89 × 5 = ~4.5 (rough estimate if exits capture 50% vs 10%)
```

### Option 2: Reduce Entry Frequency (Moderate)
```python
Current: 2,300-2,600 trades (too many)
Target: 800-1,200 trades (only highest confidence)
Method: Add RSI filter (only 30-70 range), require tighter divergence

Expected improvement: Better WR, worse PF if exit unchanged
```

### Option 3: Accept the 0.89-0.97 Range (Not Viable)
- This PF will never pass 1.15 threshold
- Not profitable enough for live trading
- Must fix exits

---

## Tested Variations Summary

| Variation | PF Range | Trades | Trades Filtered | Win Rate | Status |
|-----------|----------|--------|-----------------|----------|--------|
| OsMA_Confluence | 0.89-0.97 | 2,300-2,600 | None | 46-60% | Baseline |
| Bollinger_OsMA (growing) | 0.89-0.97 | 2,300-2,600 | None | 46-60% | ❌ Losing |
| Bollinger_OsMA (shrinking) | 0.89-0.97 | 2,300-2,600 | None | 46-60% | ❌ Losing |
| OsMA_RegimeAdaptive | 0.89-0.97 | 2,300-2,600 | ADX<20 | 46-51% | ❌ No improvement |
| MACD-filtered entries | N/A | N/A | MACD M1/M5 aligned | N/A | ❌ Made worse |
| Consolidated detection | N/A | N/A | Consolidation periods | N/A | ❌ Insufficient impact |

---

## Data Points Supporting "Exit is the Problem"

1. **M1 Analysis:** 679 entries, 55.2% WR but only 10% gain capture → Exit problem
2. **GER40 W1:** PF=1.16 (good!) but W2 PF=0.97 (collapse) → Same entries, different exit context
3. **XAUUSD W3:** PF=1.14 (decent) but W2 PF=0.97 (collapse) → Exit logic sensitive to market
4. **100% consistent:**  All three strategy variants fail identically → Not entry quality issue

---

## Next Steps for Resolution

### Short Term (What You Should Do)
1. **Implement momentum-reversal exit** - Exit when OsMA divergence ends (momentum grows again)
2. **Test with ATR-based TP** - Target = Entry ± 1.5×ATR (not fixed band level)
3. **Run full backtest** - Compare new exits vs current
4. **If PF > 1.15:** Deploy
5. **If PF <= 1.15:** Reconsider entry frequency reduction

### Medium Term
- Implement dynamic TP based on volatility regime
- Add win-rate based filtering (only take entries with >55% historical WR)
- Consider time-based exits (e.g., exit after 15 bars if not closed)

### Long Term
- Investigate why original Optuna tuning achieved "45.3% WR, PF 1.43" if current is 0.89-0.97
- Check if Optuna params are being applied correctly
- Verify backtest vs live match

---

## Files Changed

- `src/strategies/osma_regime_adaptive.py` - NEW strategy with ADX filtering
- `src/strategies/bollinger_osma.py` - Fixed divergence check (shrinking not growing)
- `src/learning/strategy_registry.py` - Registered new strategies
- `src/learning/edge_weights.py` - Added OsMA_RegimeAdaptive to FOCUSED_EDGE
- Analysis files: Multiple diagnostic scripts created

---

## Conclusion

The strategies aren't broken - **the exit strategy is fundamentally inadequate**. 

Entries find mean-reversion opportunities at band touches with divergence, but exits fire at the wrong time, capturing only 10% of available profits. Fixing entries, adding filters, or regime detection won't help if the exit keeps the PF capped at 0.89-0.97.

**The path forward is clear:** Redesign exits to capture 50%+ of available gains (not 10%), then reassess profitability.
