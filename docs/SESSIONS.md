# Session Definitions — QMMP Pipeline

## Purpose of This Document

This document defines all 12 trading sessions used in the QMMP pipeline, explains **why** each session exists, **how it behaves differently** from the others, and **how it is used** at each stage of the pipeline (discovery, Optuna, OOS backtest, live deployment).

Every developer working on `SessionRegistry`, `VbtDiscovery`, `OptunaSweep`, or the frontend **must read this document** before writing any session-related code.

---

## Why Sessions Matter

Markets behave fundamentally differently depending on which participants are active. A strategy that works well during the London session — where institutional FX desks dominate and spreads are tight — will produce completely different results during the Asian session, where liquidity is thinner and price moves are often range-bound. The weekly close period is driven by end-of-day position squaring, not directional flow.

**Running a single backtest across 24 hours of data and calling it a strategy is wrong.** Each session is a separate market regime. The pipeline treats them as separate experiments. A symbol like BTCUSD may have a profitable RSI mean-reversion strategy during the Asian session and a profitable momentum strategy during the London/NY overlap — these are different strategies, not one strategy.

The operator sees results per session and chooses which sessions to enable for live trading on a per-symbol basis. This is the core of the selection process.

---

## The 12 Sessions

### 1. `asian`

| Property | Value |
|---|---|
| UTC hours | 00:00 – 08:00 |
| Days | Monday – Friday |
| Broker server hours | Matches UTC for VT Markets |

**Character:** Lower liquidity. Tokyo, Hong Kong, and Singapore participants dominate. Price often consolidates within ranges established during the previous NY session close. Spreads are wider on FX pairs, tighter on crypto. Breakouts from Asian range become London session setups.

**Why test it separately:** Range-bound behaviour favours mean-reversion indicators (RSI, Bollinger Bands). Trend-following indicators underperform because sustained directional moves are rare. BTCUSD often has its largest retail-driven moves during this window.

**Symbols where this session is most relevant:** BTCUSD (crypto never sleeps), XAUUSD (gold has Asian demand), USDJPY, AUDUSD.

---

### 2. `london`

| Property | Value |
|---|---|
| UTC hours | 08:00 – 17:00 |
| Days | Monday – Friday |
| Broker server hours | Matches UTC for VT Markets |

**Character:** Highest FX liquidity of the day. European institutional participants open. Spreads tighten dramatically at 08:00. The Asian range often breaks in this session, providing strong directional moves. News events from European central banks (ECB, BoE) drive volatility at specific times.

**Why test it separately:** Trend-following strategies and breakout strategies perform best here. The session produces more consistent directional moves than Asian or off-hours. Momentum indicators (MACD, OsMA zero-cross) are most reliable in this session.

**Symbols where this session is most relevant:** EURUSD, GBPUSD, XAUUSD (gold reacts to USD strength against EUR), GER40.

---

### 3. `new_york`

| Property | Value |
|---|---|
| UTC hours | 13:00 – 21:00 |
| Days | Monday – Friday |
| Broker server hours | Matches UTC for VT Markets |

**Character:** US participants enter. Initially overlaps with London (13:00–17:00 is the highest volatility window of the entire trading day). After 17:00, London closes and volume drops. US equity market influences FX and gold significantly. NFP and FOMC announcements land in this session.

**Why test it separately:** The early NY period (13:00–17:00) is the overlap — highest volatility, tightest spreads, strongest moves. The late NY period (17:00–21:00) transitions toward quieter trading. Treating the entire 13:00–21:00 block as uniform misses this distinction — but the overlap is captured separately (see `london_ny_overlap` below).

**Symbols where this session is most relevant:** All USD pairs, XAUUSD, US indices (SPX, NAS).

---

### 4. `london_ny_overlap`

| Property | Value |
|---|---|
| UTC hours | 13:00 – 17:00 |
| Days | Monday – Friday |
| Broker server hours | Matches UTC for VT Markets |

**Character:** The highest volatility window in the entire trading week. Both London and New York are fully open. Institutional order flow from both sides of the Atlantic converges. Spreads are at their absolute tightest. Moves are fast and tend to follow through.

**Why test it separately:** This is a sub-window of both `london` and `new_york` but its character is distinctly different from either alone. Strategies that work in this specific window may not work outside it. Breakout and momentum strategies have the strongest edge here. The overlap also concentrates economic data releases (US data at 13:30 UTC).

**Note for implementation:** When filtering this session, bars must fall within `13:00 <= hour < 17:00` on Monday–Friday. A bar at 12:59 is `london` only. A bar at 17:01 is `new_york` only. The overlap is the intersection, not a union.

---

### 5–8. `weekly_close_mon`, `weekly_close_tue`, `weekly_close_wed`, `weekly_close_thu`

| Property | Value |
|---|---|
| UTC hours | 22:00 – 23:00 |
| Days | Monday / Tuesday / Wednesday / Thursday (one session per weekday) |
| Broker server hours | Matches UTC for VT Markets |

**Character:** End-of-day position squaring for each weekday. Liquidity drops sharply. Price often reverts toward the day's mean as traders close positions before the rollover. Spreads widen. The move is typically short, sharp, and mean-reverting.

**Why test them separately:** Each weekday's 22:00–23:00 close has a different character depending on what happened during that day's session. Monday close is influenced by weekly positioning. Thursday close precedes the critical Friday session. They are kept as four separate sessions (not combined as "weekday close") because:
- The strategy that works Monday close may not work Thursday close
- Thursday close directly precedes the highest-stakes Friday session
- Vectorbt will surface this if it exists — we let the data decide, not our assumption

**Why not Friday:** Friday's 22:00 onwards is the start of the BTC weekend session (see below). It is defined separately.

**Typical strategies that work here:** Short-duration mean-reversion, RSI extremes, Bollinger Band touch-and-reverse. Avoid trend-following — there is no sustained trend in a 1-hour window at low liquidity.

**Minimum trade requirement:** Due to the narrow 1-hour window, the minimum trade gate in `VbtDiscovery` should be relaxed to 10 trades (not 20) for these sessions.

---

### 9. `btcusd_weekend`

| Property | Value |
|---|---|
| UTC start | Friday 22:00 |
| UTC end | Sunday 21:00 |
| Days | Friday evening through Sunday |
| Applicable symbols | **BTCUSD only** (and other crypto if added) |

**Character:** Crypto markets never close. After regular equity and FX markets close on Friday at ~21:00 UTC, Bitcoin continues trading through the weekend driven entirely by retail participants, news events, and on-chain activity. There are no institutional FX desks, no hedging flows. Volume is typically lower than weekday sessions but spikes on news. Weekend moves can be violent in either direction.

**Why test it separately:** Weekend crypto behaviour is structurally different from weekday behaviour. The absence of institutional flow means:
- Price is more susceptible to social media-driven momentum
- Support and resistance levels from weekday trading may break without institutional defence
- Volatility patterns differ (can be very quiet then suddenly spike)
- Standard session-based indicators may give false signals

**Why only BTCUSD (and crypto):** XAUUSD and FX pairs do not trade on weekends through VT Markets. Applying this session filter to XAUUSD will return zero bars. `VbtDiscovery` must skip this session for non-crypto symbols with a clear log message, not fail silently.

**Implementation note:** This session spans across midnight (Fri 22:00 → Sun 21:00). The filter must handle:
- Friday: `weekday == 4` (ISO: Mon=0) AND `hour >= 22`
- Saturday: `weekday == 5` (all hours)
- Sunday: `weekday == 6` AND `hour < 21`

---

### 10–12. `market_open_15`, `market_open_30`, `market_open_60`

| Property | Value |
|---|---|
| Duration | First 15 / 30 / 60 minutes after session open |
| Days | Monday – Friday |
| Applicable to | Each major session open (Asian 00:00, London 08:00, NY 13:00) |

**Character:** The first few minutes after a session open are the most volatile and directionally biased window within that session. Order books reset. Overnight/overnight-held positions are closed. New institutional orders fire. Price discovery is most aggressive. This is also the window most prone to false breakouts and stop hunts.

**Why test them separately:** A strategy that trades the first 15 minutes after London open is a very different beast from a strategy that trades across the full London session. Many professional traders only trade specific opening windows. The 15/30/60-minute windows let the pipeline identify whether an opening effect exists for this symbol and whether it is exploitable.

**Three widths (15, 30, 60):** We test all three because the exploitable window varies by symbol. BTCUSD may have a 60-minute opening effect. XAUUSD may have only a 15-minute spike. Vectorbt will surface what the data supports.

**Implementation note — this is the most complex filter to implement correctly:**

These sessions are **not** defined by absolute UTC hours. They are defined as the first N minutes of bars after each session's open time, for each trading day. Implementation steps:

```python
# For each day in the data:
# 1. Find the first bar at or after the session open time (e.g. 08:00 for London)
# 2. Mark all bars within N minutes of that first bar as True
# 3. All other bars are False

# For "market_open_15" covering London open (08:00):
# Day 1: First bar at 08:00 → mark 08:00, 08:05, 08:10 as True (for M5 bars)
# Day 2: First bar at 08:00 → mark 08:00, 08:05, 08:10 as True
# etc.
```

The `filter_mask()` implementation for post-open sessions must:
1. Group bars by date
2. For each date, find the first bar in the relevant session window
3. Return True for bars within `[first_bar, first_bar + N_minutes)`
4. Return False for all other bars

Sessions to cover:
- `market_open_15/30/60` → covers all three major session opens (Asian 00:00, London 08:00, NY 13:00) combined into one mask. If the operator wants to test only the London open, they run discovery with just this session selected and filter their instrument accordingly.

---

## How Sessions Flow Through the Pipeline

### Stage 1 — Vectorbt Discovery

For each `(symbol, session, timeframe)` combination:
1. Load full OHLCV data via `DataManager.get_rates(symbol, timeframe, count=12000)`
2. Apply `SessionRegistry.filter_mask(ohlcv, session_key)` → boolean mask
3. Extract `session_ohlcv = ohlcv[mask]` — this is the data vectorbt sees
4. Build entry/exit signals from indicators computed on `session_ohlcv`
5. Run `vbt.Portfolio.from_signals(close=session_ohlcv["close"], ...)` — vectorbt only sees session bars
6. `pf.stats()` gives metrics for that session only

**The result is a shortlist of top 10 strategies per session**, not per symbol. A symbol has 12 sessions × N timeframes × up to 10 candidates each.

### Stage 2 — Optuna Sweep

For each discovery candidate `(symbol, session, strategy, timeframe)`:
- Optuna searches indicator parameter space using `vbt.Portfolio.from_signals()` on train folds of the **session-filtered data only**
- The objective function receives only bars belonging to that session

**This means:** Optuna is finding the best RSI window for BTCUSD during the Asian session specifically — not the best RSI window for BTCUSD overall. These are fundamentally different optimisation targets.

### Stage 3 — OOS Backtest

The held-out fold is the last chronological portion of the **session-filtered data**. The OOS backtest runs on session bars only, with the exact parameters Optuna found.

### Stage 4 — Deploy

The operator sees per-session results in the dashboard. For each session with `oos_passed` status, they can toggle it on or off for live trading.

When deployed:
- `session_preferences.json` stores which sessions are enabled per symbol
- `tuned_params.json` stores the best parameters per session (for the live bot)
- The generated EA has per-session logic — it only trades in enabled sessions, using the strategy parameters discovered for that session

The live scalp engine reads `session_of(hour)` to identify the current session on each tick and applies the session-specific parameters accordingly.

---

## Session Reference Card

Quick summary for the session selector UI — what to show as the description next to each checkbox:

| Session Key | Display Name | Description for UI |
|---|---|---|
| `asian` | Asian | Tokyo/HK/Singapore. 00:00–08:00 UTC. Range-bound, wider spreads. |
| `london` | London | LSE open. 08:00–17:00 UTC. Highest FX liquidity, directional moves. |
| `new_york` | New York | NYSE open. 13:00–21:00 UTC. US data events, strong momentum. |
| `london_ny_overlap` | London/NY Overlap | 13:00–17:00 UTC. Highest volatility window. Tightest spreads. |
| `weekly_close_mon` | Mon Weekly Close | Monday 22:00–23:00 UTC. Position squaring, mean-reversion. |
| `weekly_close_tue` | Tue Weekly Close | Tuesday 22:00–23:00 UTC. Position squaring, mean-reversion. |
| `weekly_close_wed` | Wed Weekly Close | Wednesday 22:00–23:00 UTC. Position squaring, mean-reversion. |
| `weekly_close_thu` | Thu Weekly Close | Thursday 22:00–23:00 UTC. Pre-Friday positioning, mean-reversion. |
| `market_open_15` | Post-Open 15 min | First 15 min after each session open. High volatility, direction bias. |
| `market_open_30` | Post-Open 30 min | First 30 min after each session open. Opening momentum window. |
| `market_open_60` | Post-Open 60 min | First 60 min after each session open. Extended opening effect. |
| `btcusd_weekend` | BTC Weekend | Fri 22:00–Sun 21:00 UTC. Crypto only. Retail-driven, no institutions. |

---

## Broker Context — VT Markets

All UTC hour references in this document assume the broker server time is UTC. VT Markets uses UTC+2 during winter (EET) and UTC+3 during summer (EEST) **server time**, but the OHLCV data stored in parquet files has timestamps converted to UTC by `DataManager`. Always work with UTC timestamps from the parquet/DataFrame — never with broker server time directly.

If you are loading raw tick data or using MT5's `copy_rates_from` directly, the timestamps will be in broker server time. `DataManager.get_rates()` converts these to UTC before returning. Use `DataManager` and you will always have UTC.

---

## Implementation Validation

The `tests/test_sessions.py` file must cover all of these:

```python
import pandas as pd
import numpy as np
from src.strategies.sessions import SessionRegistry

# Create 2 weeks of 15-minute UTC bars: Mon 2024-01-01 00:00 → Sun 2024-01-14 23:45
idx = pd.date_range("2024-01-01", "2024-01-14 23:45", freq="15min", tz="UTC")
ohlcv = pd.DataFrame({"open":1,"high":1,"low":1,"close":1,"volume":1}, index=idx)

# Each test: assert mask.sum() > 0 and all flagged bars are in correct window
def test_asian():
    mask = SessionRegistry.filter_mask(ohlcv, "asian")
    assert mask.any()
    flagged = ohlcv[mask]
    assert all(0 <= h < 8 for h in flagged.index.hour)
    assert all(d < 5 for d in flagged.index.weekday)   # Mon–Fri only

def test_btcusd_weekend():
    mask = SessionRegistry.filter_mask(ohlcv, "btcusd_weekend")
    assert mask.any()
    flagged = ohlcv[mask]
    for ts in flagged.index:
        wd, h = ts.weekday(), ts.hour
        assert (wd == 4 and h >= 22) or wd == 5 or (wd == 6 and h < 21), \
            f"Unexpected bar in btcusd_weekend: {ts}"

def test_weekly_close_mon():
    mask = SessionRegistry.filter_mask(ohlcv, "weekly_close_mon")
    assert mask.any()
    flagged = ohlcv[mask]
    assert all(ts.weekday() == 0 and 22 <= ts.hour < 23 for ts in flagged.index)

def test_no_overlap_between_weekly_close_days():
    masks = {
        day: SessionRegistry.filter_mask(ohlcv, f"weekly_close_{day}")
        for day in ["mon","tue","wed","thu"]
    }
    # No bar should appear in two different weekly close sessions
    for a, b in [("mon","tue"),("tue","wed"),("wed","thu")]:
        assert not (masks[a] & masks[b]).any()

def test_market_open_15_duration():
    mask = SessionRegistry.filter_mask(ohlcv, "market_open_15")
    assert mask.any()
    # For M15 bars, max 1 bar per session open per day (the 00:00, 08:00, or 13:00 bar)
    # For M5 bars, max 3 bars per session open per day
    # Assert no bars appear more than 15 minutes after any session open

def test_existing_session_of_still_works():
    from src.strategies.sessions import session_of
    assert session_of(0) == "Asian"
    assert session_of(8) == "London"
    assert session_of(12) == "NewYork"
    assert session_of(21) == "Off"
```
