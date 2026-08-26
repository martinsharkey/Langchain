# LOW LEVEL DESIGN - src/onboarding Module

**Module**: Symbol Onboarding Pipeline
**Version**: 2.0
**Last Updated**: August 26, 2026
**Status**: Active

---

## Overview

The single authoritative pipeline for onboarding an MT5 symbol. It uses
**VectorBT's out-of-the-box factory** to enumerate and test **all** available
indicators (pandas_ta + ta-lib + built-ins) across our own session model and the
full timeframe matrix, ranks the best per session/timeframe by composite score,
tunes the top-10 with Optuna, and validates with chronological walk-forward
out-of-sample testing to reject overfit strategies.

This module supersedes the retired `src/phase*` pipeline and the stub `services/*`
engines.

## Structure

```
src/onboarding/
├── __init__.py
├── __lld__.md
├── brief.md           # the clear written brief (deliverable)
├── sessions.py        # full session taxonomy (macro/overlap/micro)
├── timeframes.py      # M1..M30 + H1/H4/D1
├── data.py            # MT5 OHLCV + tick loader
├── indicators.py      # VectorBT-native enumeration + wrapping (NO custom compute)
├── signals.py         # native signal methods + AND/OR combination
├── backtest.py        # vbt.Portfolio.from_signals (bar + tick fills)
├── metrics.py         # composite score + viability
├── discovery.py       # Phase 1: all indicators x sessions x timeframes (+ combos)
├── optimize.py        # Phase 2: Optuna per-indicator tuning
├── validate.py        # Phase 3: walk-forward OOS
├── pipeline.py        # orchestrator
└── report.py          # md/html/json reports
```

## Data Flow

```
MT5 (VTMarkets) ──get_rates()──▶ OHLCV per timeframe
        └──get_ticks()──▶ ticks (M1/M5, shallow)

OHLCV ──session filter──▶ session slice
        ──enumerate_indicators()──▶ wrap(from_pandas_ta/talib/ta)──▶ .run()
        ──native signal methods + AND/OR──▶ entries/exits
        ──vbt.Portfolio.from_signals──▶ metrics ──composite score──▶ top-10
top-10 ──Optuna──▶ tuned params
tuned  ──walk-forward OOS──▶ PASS/FAIL ──▶ validated strategies ──▶ report
```

## Key Decisions

- **Indicator universe = VectorBT decides.** `get_pandas_ta_indicators()` /
  `get_talib_indicators()` / `get_ta_indicators()` + built-ins. No hardcoded list.
- **Combinations = VectorBT decides.** Singles first, then AND/OR combinations of the
  top singles up to a configurable depth (default 10).
- **Native reporting.** The report renders VectorBT's native `pf.stats()` output
  (28 metrics) for every candidate — no hand-rolled metric table.
- **Session model.** Full 12-session taxonomy with minute-level precision
  (macro/overlap/micro, including 15/30/60-min post-market-open windows).
- **Timeframes.** M1-M30 + H1/H4/D1; report shows the best timeframe per session.
- **Ranking**: composite score = PF (0.35), max drawdown (0.30), win rate (0.15),
  Sharpe (0.10), trades (0.10).
- **Overfit guard**: chronological walk-forward (5 folds), reject if OOS PF < 1.0 or
  degradation > 30%.
- **Data source**: MT5 (VTMarkets) only. Dukascopy removed.
- **Fills**: VectorBT native `vbt.Portfolio.from_signals` (bar-based) is the single
  source of truth.

## Failure Modes

- Indicator wrap/run failure: logged and skipped (never silently swallowed).
- Unavailable timeframe: logged and skipped.
- No viable indicators: reported honestly as 0.
- Tick window too shallow for M1: fall back to bar-based fills, record fill mode.

---

**Status**: Active
**Maintainer**: @team-dev
