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

---

## 4. OWNER'S REAL EDGE — the momentum DYNAMICS (2026-08-12, verbatim intent)

The owner's proven MT5 EAs traded **dynamics (rate-of-change), not levels**. These
are the concepts that MUST become tunable and be honoured live:

### 4a. Timing mode — anticipation / "fizzle" vs confirmation
Enter relative to the OsMA zero-cross at one of three points, TUNABLE per symbol:
- **anticipation** — just BEFORE the cross (OsMA approaching zero + accelerating).
- **at cross** — the confirmed zero-cross.
- **after a full new candle** — most confirmed, but on **M1 the cycle is almost
  over by the close**, so spread+slippage eat the edge. This is WHY anticipation
  matters on fast timeframes — the confirmed close is too late.
Existing hooks: `allow_anticipated`, `osma_anticipate_atr`, `trigger_kind`.

### 4b. MACD / OsMA acceleration ("fizzle" detector)
Look at whether MACD/OsMA is **accelerating or decelerating** into the cross, not
just its sign/level. Accelerating momentum into the zero line = a real move;
decelerating = a fizzle to avoid. Existing hook: `accel_min` (|osma-osma_prev|/ATR)
— but this is a single-step magnitude, NOT a multi-bar acceleration/deceleration
trend. **Enhance to a trajectory.**

### 4c. Bulls/Bears POWER TUG-OF-WAR (the core, currently MISSING)
The decisive signal is the **trajectory of power across recent bars**, not its
level. For a LONG:
- Bears rising OUT of deeply negative toward zero (e.g. -2.1 -> -0.3), AND
- Bulls climbing hard, EVEN IF STILL NEGATIVE
  (e.g. -4.5 -> -2.3 -> 0.1 -> 1.8 -> 3.8).
A valid long can show bulls still negative but climbing steeply — the level gate
would WRONGLY reject it; the RATE-OF-CHANGE gate accepts it. This is exactly why
the fakeout study (static levels) failed to separate winners. **Requires capturing
`bulls_recent` / `bears_recent` series (not just last value) + slope gates.**

### 4d. OsMA candle threshold vs the M1 timing trap
A tunable OsMA magnitude before entry (e.g. >= 0.5 long / <= -0.5 short) — but on
M1 waiting for that closed value means the cycle is nearly done. So the threshold
must be balanced against anticipation/acceleration (4a/4b) rather than used alone.

### Build plan (tunable, default-off, optimiser-proven, per symbol)
1. Capture `bulls_recent` / `bears_recent` / `macd_recent` series in
   `compute_full_indicators` (like `osma_recent`).
2. Add tunable gates in `confluence_signal.py`:
   - `bulls_slope_min` / `bears_slope_min` — required rate-of-change of power over
     the last N bars (the tug-of-war), sign-aware, ATR-normalised.
   - `accel_bars` — multi-bar OsMA/MACD acceleration (extend `accel_min`).
   - power-trajectory works EVEN WHEN power level is still negative (climbing).
3. Exit: `osma_hook_exit` (OsMA[1] < OsMA[2] fading) + `power_flip_exit`
   (bulls<0 long / bears>0 short) as tunable hard exits.
4. Split `power_period` into `bulls_period` / `bears_period` (optional).
5. Add tests; prove each per symbol in walk-forward; enable only if it beats
   baseline out-of-sample.

## Strategy provenance (owner-confirmed 2026-08-12) � DO NOT CONFLATE

- **GoldShark** = OUR strategy. OsMA 7-indicator confluence. **XAUUSD, M1.**
  All GoldShark optimiser XMLs / telemetry / .set files belong to this edge.
- **Quantum Bitcoin (QB)** = a SEPARATE EA by a DIFFERENT developer.
  **BTCUSD, H1.** NOT GoldShark. Different parameter schema (Inp* names differ).
  Interesting as a BTCUSD reference ONLY � its parameters must NEVER be merged
  into GoldShark/BTCUSD confluence tuning or the adjustment_ledger as if they were
  the same strategy (would poison per-symbol learning). If ever ingested, tag it
  strategy="quantum_bitcoin" and keep it isolated from GoldShark rows.

Practical rule for the optimiser-XML ingester: map/keep only same-strategy,
same-symbol, same-timeframe data together. QB (BTCUSD/H1) is its own lane.
