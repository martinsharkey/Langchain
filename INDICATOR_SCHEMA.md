# Indicator Stack — Canonical Schema & "Adjusted vs Not" Audit

> Source of knowledge (owner-authored table, reviewed + enhanced 2026-08-12).
> This is the AUTHORITATIVE map of every indicator input, its intended trade
> logic, and — critically — **whether the bot's optimiser actually tunes it and
> whether the confluence engine actually implements the rule.** Keep this in sync
> with `src/learning/param_optimizer.py::PARAM_SPACE` and
> `src/strategies/confluence_signal.py`. The researcher should read this before
> proposing changes.

---

## 1. Optimisation Schema (Inputs) — owner table vs what the bot TUNES

Legend: ✅ tuned by optimiser · ⚠️ used but FIXED (not searched) · ❌ not present.

| Indicator | Owner param | Default | Owner range | Bot param | Bot search range | Status |
|---|---|---|---|---|---|---|
| MACD/OsMA | fast_ema_period | 12 | 5–50 | `osma_fast` | 5–34 step 1 | ✅ |
| MACD/OsMA | slow_ema_period | 26 | 10–100 | `osma_slow` | 20–144 step 2 | ✅ |
| MACD/OsMA | signal_period | 9 | 3–30 | `osma_signal` | 5–55 step 1 | ✅ |
| MACD/OsMA | applied_price | CLOSE | 0–6 | — | — | ❌ **not tunable (always CLOSE)** |
| ATR | ma_period | 14 | 5–30 | `atr_period` | 5–50 step 1 | ✅ |
| EMA | ma_period | 14 | 10–200 | `ema_period` | 3–200 step 1 | ✅ |
| EMA | applied_price | CLOSE | 0–6 | — | — | ❌ not tunable |
| Bulls Power | ma_period | 13 | 5–50 | `power_period` | 5–26 step 1 | ✅ (shared bulls+bears) |
| Bears Power | ma_period | 13 | 5–50 | `power_period` | 5–26 step 1 | ⚠️ **shares one period with Bulls** |
| RSI | ma_period | 14 | 5–30 | `rsi_period` | 2–30 step 1 | ✅ |
| RSI | applied_price | CLOSE | 0–6 | — | — | ❌ not tunable |
| Custom | atr_threshold | 0.0010 | varies | `atr_min` / `atr_min_rel` | 0–4 / 0–1.5 | ✅ (ATR-normalised) |

### Extra levers the BOT tunes that are NOT in the owner table
(these are enhancements already in `PARAM_SPACE` — worth knowing they exist)
`osma_min_long/max_short`, `macd_min_long/max_short`, `bulls_min_long`,
`bears_min_long/max_short`, `bulls_max_short`, `min_ema_slope`,
`price_stretch_mult`, `min_confluence`, `rsi_long_max`, `rsi_short_min`,
`macd_lead_bars`, `max_momentum_age`, `accel_min`, `sl_atr`, `tp_rr`,
`rsi_buy_below`, `rsi_sell_above`, `require_htf_align`, `trail_min_atr`.

**Audit conclusion (inputs):** the bot tunes MORE than the table for *thresholds*,
but is MISSING three table items: (a) **applied_price** is never tuned (all
indicators use CLOSE); (b) **Bulls and Bears share a single `power_period`** —
they cannot be optimised independently as the table intends; (c) `atr_threshold`
is expressed ATR-normalised, not as a raw price value.

---

## 2. Trade Logic Schema — owner rules vs what the ENGINE implements

Legend: ✅ implemented · ⚠️ partial/different · ❌ missing.

### ENTRY
| Owner rule (index [1]=last closed, [2]=prev) | In `confluence_signal.py`? |
|---|---|
| Long: `osma[1] > 0 AND osma[2] < 0` (zero-cross up) | ✅ `cu = osma_prev<=0<osma_now` |
| Long confirm: `bulls_power[1] > 0` | ✅ soft-check bulls>0 |
| **Long confirm: `bears[1] < 0 AND bears[1] > bears[2]` (bears WEAKENING toward zero)** | ❌ **MISSING — engine checks bears level, NOT the rate-of-change toward zero** |
| Long filter: `ema[1] > ema[2]` (slope up) | ✅ `min_ema_slope` |
| Vol filter: `atr[1] > threshold` | ✅ `atr_min` |
| Short: `osma[1] < 0 AND osma[2] > 0` | ✅ `cd` |
| Short confirm: `bears_power[1] < 0` | ✅ |
| **Short confirm: `bulls[1] > 0 AND bulls[1] < bulls[2]` (bulls WEAKENING)** | ❌ **MISSING (rate-of-change not checked)** |
| Short filter: `ema[1] < ema[2]` | ✅ |

### EXIT
| Owner rule | In engine? |
|---|---|
| **Suggested exit (long): `osma[1] < osma[2]` (histogram hooks down — momentum fading BEFORE zero-cross)** | ⚠️ **PARTIAL — momentum-exhaustion/reversal exits exist in `trade_manager`, but there is no simple explicit "OsMA hooks down" exit** |
| **Hard exit (long): `bulls_power[1] < 0` (bulls lost dominance)** | ❌ **MISSING as an explicit hard exit** |
| Suggested exit (short): `osma[1] > osma[2]` | ⚠️ partial |
| Hard exit (short): `bears_power[1] > 0` | ❌ missing |

**Audit conclusion (logic):** the ENTRY zero-cross + EMA + ATR gates match. The
KEY GAPS vs the owner's intended strategy are the **rate-of-change / momentum
nuances**:
1. **Power weakening on entry** ("bears pulling toward zero" for a long) — the bot
   only checks the *level* of power, never whether it is *turning*. This is the
   exact nuance the owner emphasised and the fakeout study could not test.
2. **OsMA-hook + power-flip HARD EXIT** — a simple, decisive exit the owner wants;
   the engine has complex reversal logic but not this clean rule.

---

## 3. What this means for the ML / self-learning direction

The bot today tunes *thresholds* (levels) heavily but does not model the
*dynamics* the owner trades on (power turning, OsMA hooking). Two paths:
- **Cheap, deterministic:** add the missing rate-of-change entry confirmations and
  the OsMA-hook/power-flip hard exit as TUNABLE gates (default-off), then let the
  optimiser prove them per symbol. Low risk, no ML needed.
- **ML (per-symbol pattern):** for each trade, pull M1/M5/M15 around entry and
  learn which multi-timeframe dynamic patterns precede winners vs fakeouts — a
  per-symbol classifier feeding a confidence, retrained from the experience DB.
  Higher effort; justified only once the deterministic dynamics above are in and
  we still see unexplained variance.

**Next action:** implement the 4 missing dynamics as tunable gates, add tests,
prove per-symbol in the walk-forward, and only then decide if ML adds anything.
