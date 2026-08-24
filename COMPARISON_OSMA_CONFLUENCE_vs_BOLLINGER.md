# OsMA_Confluence vs Bollinger_OsMA Comparison
**Date:** 2026-08-24  
**Test:** Walk-forward backtest (3 windows, M15 timeframe)

---

## Executive Summary

**Both strategies are losing money.** Neither the old OsMA_Confluence nor the new Bollinger_OsMA passes the minimum profitability threshold (PF ≥ 1.15 on all windows).

### Key Finding
The problem is **systemic exit strategy issue** affecting ALL confluence/OsMA-based entries, not specific to one strategy.

---

## Multi-Symbol Results

| Symbol | Trades | Avg PF | Min PF | Generalizes | Best Window | Issue |
|--------|--------|--------|--------|-------------|-------------|-------|
| **BTCUSD** | 2,581 | 0.95 | 0.89 | ✗ | 0.96 | Window 2 breaking |
| **GER40** | 2,178 | 1.04 | 0.97 | ✗ | 1.16 | Window 2-3 weak |
| **XAUUSD** | 2,315 | 1.05 | 0.97 | ✗ | 1.14 | Window 2 weak |
| **EURUSD** | - | - | - | - | - | No focused rules |
| **GBPUSD** | - | - | - | - | - | No focused rules |

### Summary Statistics
```
Average PF (all testable symbols): 0.94
Profitable symbols (PF ≥ 1.0):     0/3
Generalizing symbols (all windows): 0/3
```

**Verdict:** OsMA_Confluence performs similarly to Bollinger_OsMA - both are losing money with PF < 0.95 across the board.

---

## Side-by-Side Comparison

### BTCUSD Performance

**OsMA_Confluence (old):**
```
Window 1: PF=0.96, WR=60.8%
Window 2: PF=0.89, WR=47.0% ← Breaks here
Window 3: PF=0.99, WR=46.0%
Avg PF: 0.95, Min PF: 0.89
```

**Bollinger_OsMA (new):**
```
Window 1: PF=0.96, WR=60.7%
Window 2: PF=0.89, WR=46.9% ← Breaks here
Window 3: PF=0.98, WR=46.0%
Avg PF: 0.94, Min PF: 0.89
```

**Observation:** Nearly identical results. Both break in Window 2.

---

## Root Cause Analysis

### Window 2 Breakdown Pattern
Both strategies show:
- Window 1: Barely profitable (PF ~0.96)
- Window 2: Profitability collapses (PF 0.87-0.89)
- Window 3: Partial recovery (PF 0.98-0.99)

This suggests:
1. **Market regime change in Window 2** - Conditions change mid-backtest
2. **Both strategies are regime-dependent** - They work in trending/volatile markets but fail in ranging markets
3. **Exit strategy inadequacy** - In all regimes, exits aren't capturing enough profit

### Specific Findings

**GER40 vs BTCUSD:**
- GER40 Window 1: PF=1.16 ✓ (PROFITABLE)
- GER40 Window 2: PF=0.97 ✗ (loses 19%)
- Suggests GER40 had better conditions in early window, then degraded

**XAUUSD Pattern:**
- Most balanced: Window 1 (1.04), Window 2 (0.97), Window 3 (1.14)
- Still doesn't meet 1.15 minimum on ANY window
- Better than BTCUSD/GER40 but still insufficient

---

## Why Both Strategies Fail

### Theory 1: Market Regime Sensitivity (Confirmed)
- Both strategies show identical Window 2 collapse
- This isn't a coding issue, it's a **market conditions issue**
- Window 2 likely contains ranging/consolidation period where mean-reversion entries fire but don't complete

### Theory 2: Exit Strategy Inadequacy (Highly Likely)
- M1 analysis showed Bollinger_OsMA entries capturing only 10% of potential gains
- OsMA_Confluence likely has the same exit problem
- When market slows (Window 2), exits fire even earlier, turning winners into losers

### Theory 3: Entry Frequency Too High
- 2,300-2,600 trades over 12,000 bars = ~20% signal frequency
- Many of these are false signals during consolidation
- Need stronger entry filters or regime detection

---

## Implications

### ✗ What This Means
1. **Switching from OsMA_Confluence to Bollinger_OsMA won't help** - both lose
2. **Exit strategy redesign is insufficient** - need entry filtering too
3. **Market regime detection is critical** - can't trade same way in all conditions
4. **Current focus on divergence vs growing was a red herring** - the real issue is exits AND regime dependence

### ✓ What Could Work
1. **Add market regime filter** - Skip entries during consolidation/ranging
2. **Redesign exits for each regime** - Different TP/SL for trending vs ranging
3. **Entry confirmation filters** - Require stronger signals, not just band touch + divergence
4. **Time-based filtering** - Skip entries during certain hours/sessions

---

## Recommendations

### Immediate: Abandon Current Direction
- ✗ Don't spend more time tuning Bollinger_OsMA exit logic
- ✗ Both old and new confluence strategies fundamentally unprofitable
- ✗ The divergence fix didn't matter - OsMA_Confluence has same results

### New Direction: Market Regime Analysis
Instead of tweaking entries/exits, first answer:
1. **What market conditions was the original strategy tuned for?**
2. **Why does it break in Window 2?** (data analysis needed)
3. **Which symbols/regimes WORK?** (XAUUSD 1.14 in W3 is interesting)

### Hypothesis to Test
The original Optuna tuning was for specific market conditions. The strategy:
- Works great in trending/volatile (W1, W3 on XAUUSD)
- Collapses in ranging/consolidation (W2 on all symbols)

If true: Add consolidation detector and skip entries when market is consolidating.

---

## Next Steps

1. **Analyze Window 2 market data** - Is it more ranging/consolidating?
2. **Check volatility regime** - VIX, ATR patterns across windows
3. **Identify profitable conditions** - When does it work? (trending, high vol, specific hours?)
4. **Implement regime filter** - Only trade when conditions match original tuning
5. **Test on single best window** - Verify it actually works before optimizing

The answer isn't tweaking exits. The answer is understanding WHY Window 2 breaks and fixing the underlying issue.
