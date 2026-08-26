# Symbol Onboarding Pipeline — Brief

**Version**: 2.0
**Date**: August 26, 2026
**Status**: Active

---

## 1. Objective

Onboard any MetaTrader 5 (MT5) symbol — e.g. BTCUSD — by letting **VectorBT's
out-of-the-box functionality** enumerate and test **all** available indicators
(pandas_ta + ta-lib + VectorBT built-ins) across our own session model and the full
timeframe matrix, rank the best per session/timeframe by profit factor and drawdown,
tune the top-10 with Optuna, and validate with walk-forward out-of-sample testing to
reject overfit strategies.

The output is a per-symbol, per-session, per-timeframe set of validated strategies
ready for live MT5 deployment.

## 2. Background & Market Context

- **BTCUSD trades 24/7** — one of the only MT5 symbols to trade weekends. All other
  symbols (XAUUSD, GER40, AUDCAD, etc.) trade Sunday 22:00 GMT through Friday
  21:00–22:00 GMT.
- **Weekly close windows** occur Monday–Thursday around 22:00–23:00 GMT.
- **Three macro sessions** — Asian, London, New York — each with different liquidity,
  volume, and behaviour.
- **Overlaps** between sessions are highly volatile.
- **Post-market-open** (Mon–Thu) is a highly volatile 15–60 minute window.
- A symbol may perform best on any one of these micro/macro/overlap sessions using an
  entirely different set of indicators.

## 3. Approach

### 3.1 Session model (ours)

Each session is a distinct testable regime. Times are UTC; weekday is Mon=0..Sun=6.

| Key | Name | Days | Hours (UTC) | Kind |
|---|---|---|---|---|
| `asian` | Asian | Mon–Fri | 00:00–08:00 | macro |
| `london` | London | Mon–Fri | 08:00–17:00 | macro |
| `newyork` | New York | Mon–Fri | 13:00–22:00 | macro |
| `overlap_asia_london` | Asia–London overlap | Mon–Fri | 07:00–09:00 | overlap |
| `overlap_london_ny` | London–NY overlap | Mon–Fri | 13:00–17:00 | overlap |
| `post_market_open_15` | Post-market open (15m) | Mon–Thu | 22:00–22:15 | micro |
| `post_market_open_30` | Post-market open (30m) | Mon–Thu | 22:00–22:30 | micro |
| `post_market_open_60` | Post-market open (60m) | Mon–Thu | 22:00–23:00 | micro |
| `weekly_close` | Weekly close | Mon–Thu | 22:00–23:00 | micro |
| `sunday_open` | Sunday open | Sun | 22:00–24:00 | micro |
| `friday_close` | Friday close | Fri | 21:00–22:00 | micro |
| `weekend` | Weekend (24/7) | Sat–Sun | 00:00–24:00 | micro |

### 3.2 Timeframe matrix

M1 through M30 (all minute timeframes) plus H1, H4, D1. Some minute timeframes may
not be offered by the broker; the pipeline skips unavailable timeframes and logs them.

### 3.3 Indicator universe (VectorBT decides)

VectorBT's factory enumerates the full indicator universe — **no hardcoded list, no
pre-selection**:

- `IndicatorFactory.get_pandas_ta_indicators()` → ~145 pandas_ta indicators
- `IndicatorFactory.get_talib_indicators()` → ~157 ta-lib indicators
- `IndicatorFactory.get_ta_indicators()` → `ta` library indicators (if installed)
- VectorBT built-ins: ATR, BBANDS, MA, MACD, MSTD, OBV, RSI, STOCH

Each indicator is wrapped via `from_pandas_ta(name)` / `from_talib(name)` /
`from_ta(name)` and run with only the inputs it declares (`input_names`).

### 3.4 Combinations (VectorBT decides)

Test every single indicator first. Then combine the top singles' signals (AND/OR) up
to a configurable depth (default 10) and let the backtest results decide which
combination wins. We do not pre-limit the number of indicators in a combination.

### 3.5 Ranking

Composite score = weighted blend of:
- Profit Factor (0.35)
- Max Drawdown (0.30)
- Win Rate (0.15)
- Sharpe (0.10)
- Trade count (0.10)

Top-10 per session/timeframe feed Optuna.

### 3.6 Optuna tuning

For each top-10 candidate, Optuna tunes the indicator's own parameters (exposed via
VectorBT's `param_names`) plus entry/exit thresholds, maximizing the composite score.

### 3.7 Native reporting

The report renders VectorBT's native `pf.stats()` output (28 metrics: Total Return,
Max Drawdown, Win Rate, Profit Factor, Expectancy, Sharpe, Sortino, Calmar, Omega,
etc.) for every candidate — no hand-rolled metric table. The report is structured
per session, showing the best timeframe and its top-10 indicators.

### 3.8 Walk-forward validation (overfit guard)

Chronological walk-forward (5 folds): tune on earlier folds, test on later folds,
aggregate out-of-sample PF/drawdown. Reject if OOS PF < 1.0 or degradation > 30%.

### 3.9 Data source

MT5 (VTMarkets) only. Dukascopy removed. Fills use VectorBT's native
`vbt.Portfolio.from_signals` (bar-based) as the single source of truth.

## 4. Pipeline Stages

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

1. **Discovery** — all indicators × sessions × timeframes (+ combinations).
2. **Optimization** — Optuna per-indicator parameter tuning of the top-10.
3. **Validation** — walk-forward OOS; reject overfit candidates.
4. **Report** — per-symbol md/html/json with per-session breakdown.

## 5. Deliverables

1. Working pipeline in `src/onboarding/`.
2. Per-symbol onboarding report (`tests/onboarding/{symbol}/`).
3. This brief.

## 6. Out of Scope (v1)

- Live trade execution / deployment (Phase 4).
- Continuous tick recorder cache.
