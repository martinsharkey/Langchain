# QMMP — Quant Matrix Mining Project (BTCUSD-first, symbol-general)

> Evidence-first pattern-mining engine. Ingests multi-timeframe bar + tick data,
> builds a multi-dimensional matrix of all 38 MT5 indicators against OsMA cycle
> states and trading sessions, brute-forces signal/threshold/cluster combinations,
> and simulates the multi-leg PYRAMID_TRAIL exit with **tick-accurate, wick-safe
> fills** — every candidate validated **out-of-sample** before it is trusted.

Owner spec: QMMP v1.0. This doc adapts it to this repo's reality and rules (R5/R10).

## 0. Non-negotiable guards (learned this session)
- **Wick-safe fills:** stops/BE/trail/pyramid fills are checked against **ticks**
  where tick data exists, else against **bar HIGH/LOW** (never just open/close).
  Bar-OHLC-only fills gave false results and hid real wick-outs.
- **Out-of-sample everything:** combinatorial search over thousands of combos will
  produce false positives by chance. Every surviving candidate MUST pass
  **walk-forward** (train fold k, validate fold k+1) before it is reported as an
  edge. In-sample-only results are labelled as such and never actioned. (R10)
- **No look-ahead:** HTF features are merged **as-of** (last CLOSED higher-TF bar at
  or before the M1 timestamp). Indicators use only past/closed bars.
- **Per-symbol magnitudes:** thresholds are derived per symbol; structure is shared,
  magnitudes are not (R5).

## 1. Data layer (`scripts/qmmp/ingest.py`)
- **Source priority:** Dukascopy deep M1 + ticks if reachable (verified: BTCUSD
  ticks reach >=6 months back), else MT5. MT5 M1 caps ~45 days; MT5 M15/H1/H4 reach
  400/900/1500 days.
- **Timeframes:** M1, M5, M15, M30, H1, H4 (the full M1->H4 range). M1 is the base;
  all HTFs are resampled/aligned onto the M1 index by causal as-of merge.
- **Storage:** Polars + compressed Parquet under `data/qmmp/<symbol>/<tf>.parquet`.
  Immutable; ingest is chunked to fit 12-month M1 (~350k bars) in memory.
- **Integrity guard:** strip phantom weekend bars and connection-gap fragments
  before computing indicators; flag gaps > 3 min.
- **Session flags (UTC, overlapping):** Asian 00:00-09:00, London 07:00-16:00,
  NewYork 12:00-21:00.

## 2. Feature matrix (`scripts/qmmp/features.py`)
- **All 38 MT5 indicators** (see `scripts/mt5_all_indicators.py`) computed per
  timeframe, aligned onto M1. Backtest-vs-live parity target: match MT5 to ~6dp
  (Wilder-smoothed ADX/ATR, SMMA Alligator, MT5 SAR).
- **OsMA 4-state classifier** (per TF): S1 Bull-Expanding, S2 Bull-Contracting,
  S3 Bear-Expanding, S4 Bear-Contracting, from OsMA sign and ΔOsMA.
- **Cycle internal index:** bar 0 = state transition, 1, 2, ... until next shift.
- **Cycle stats:** per cycle total point amplitude (high-low) and bar length.
- **Parameter sweeps:** MACD fast[6,12,18]/slow[18,26,34]/signal[6,9,12];
  RSI period[7,14,21] x threshold[20:5:80]; MA period[5:5:200]; oscillator
  overbought/oversold per session flag.

## 3. Combinatorial mining (`scripts/qmmp/mine.py`)
- Build conditional matrix masks combining Trend/Momentum/Volume clusters x session
  x OsMA state x cycle-index (e.g. Bull cluster AND oscillator-oversold AND London
  AND S1 AND cycle_index<=2).
- **Winner vs Fakeout labelling:** Winner = entry travels +X pts (target) without
  breaching the cycle structural swing low/high; Fakeout = immediate loss or
  flatline-reversal before target.
- **Attribution:** Random Forest / XGBoost feature-importance per session on
  winner-vs-fakeout — ranked, with permutation importance and PCA/UMAP cluster view.
- **Dimensional reduction** (PCA/UMAP) to find indicator clusters, not single cols.

## 4. Vectorised simulation (`scripts/qmmp/simulate.py`)
- **vectorbt** portfolio over the candidate entry matrix (parallel across combos).
- **Wick-safe multi-leg exit** (PYRAMID_TRAIL): broker SL (per-symbol, ATR- or
  cycle-swing-anchored), BE trigger, trailing (sized to measured pullback median),
  scale-in Leg N at +X pts with Leg N-1 SL trailed to Leg N entry (net risk capped),
  up to N legs. Fills resolved on ticks (else bar H/L). Costs modelled.
- Outputs: per-combo net points, win/fakeout rate, pyramiding rate, max adverse.

## 5. Validation + deliverables
- **Walk-forward folds** on every surviving combo; report train vs unseen-test.
- **Parity check:** Python indicators vs MT5 chart to ~6dp.
- **Attribution CSV:** every entry — session flag, OsMA amplitude/state/cycle-index,
  full indicator snapshot, winner/fakeout, realised excursion.
- **Memory:** vectorized only; 12-month M1 within standard profile.

## Run order
1. `python -m scripts.qmmp.ingest BTCUSD` (background; deep Dukascopy or MT5)
2. `python -m scripts.qmmp.features BTCUSD`
3. `python -m scripts.qmmp.mine BTCUSD` (attribution + candidates)
4. `python -m scripts.qmmp.vbt_ordermodel BTCUSD` (native vectorbt from_order_func = engine)

## THE VALIDATED PER-SYMBOL ASSESSMENT PROCESS (exact steps, apply to every symbol)

This is the repeatable playbook proven on BTCUSD. Run it per symbol; magnitudes are
symbol- AND timeframe-specific (R5) — never port thresholds across symbols/timeframes.

1. **Cost first, always.** Get the REAL ECN spread + commission (NOT the demo — demo has
   zero spread/slippage and produces false positives). BTCUSD: ~1200pt spread + $6/lot.
   Compute **move/cost ratio** = median OsMA-cycle peak / round-turn cost. If < ~10x the
   timeframe is unviable (M1 BTCUSD = 1.7x = dead). Raise timeframe until move/cost >> 10x
   (BTCUSD needed H1 = 36x).
2. **Entry = OsMA zero-cross** on the chosen timeframe (fresh cross confirmed on closed bar).
3. **Candle formation / strength** (tick-driven where the TF allows): does early-forming
   OsMA strength predict success? (M1: yes in isolation, but did NOT survive end-to-end.)
4. **Bulls/Bears power** per session (Asian/London/NY): winners vs losers, walk-forward.
   NOTE: polarity is timeframe-specific (M1 wants strong power; H1 wants NOT-extreme power).
5. **ATR + EMA**: ATR level (not direction) and EMA-stretch vs win — walk-forward.
6. **Filters end-to-end**: any candidate filter MUST be walk-forward validated ON THE
   ACTUAL MODEL P&L (not raw peak/trough) — filters that separate winners in-sample often
   just remove profitable trades (osma-strength filter did; power/ema filters must prove
   they raise net OOS, and on H1 BTCUSD the M1 filters did NOT transfer).
7. **Exit re-derived from the winners' movement**: measure peak/adverse/pullback of the
   filtered winners -> derive SL/BE/trail/add ranges -> walk-forward optimize (net + risk-
   adjusted, stable-on-both). Key lesson: trail must beat the SPREAD and match real pullback;
   mid-price sims overstate tight trails. H1 optimum: single basket trail ~15% of median
   peak + early-pyramid (add only in first 15% of cycle, new leg SL = prior entry, max 4).
8. **Money-management + compounding equity**: real sizing (GBP per 0.01), 1:500, 100-lot/
   account cap -> parallel accounts, slippage + spread, 70/30 backtest/forward. Report OOS
   fresh-account return (ignore in-sample compounded % — it's meaningless).
9. **Native vectorbt from_order_func** implements the exact model (basket trail + pyramid);
   cross-check vs the custom Numba sim (both must agree in sign/magnitude). Export vbt trade
   records for ONNX ML validation. Save `data/qmmp/<SYMBOL>/model.json`.

**BTCUSD RESULT (locked):** timeframe H1; OsMA-cross entry; basket-trail+early-pyramid exit
(SL 250k / BE 15850 / trail 15850 / add 15850 / early 15% / max 4 legs); £250/0.01
conservative sizing -> +34% OOS fresh-£5000, 1.3% DD (up to +299% at £50/0.01, 6.4% DD);
native vbt from_order_func: +2987%/56% win/Sharpe 6.6 at £250/0.01 over 2yr. Two engines
agree. See `data/qmmp/BTCUSD/model.json`.
