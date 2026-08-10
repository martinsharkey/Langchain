# BASELINE — Where We Actually Stand

> The durable, honest record of the strategy's measured performance, so we never
> lose track again. Regenerate: `python -m scripts.baseline_history BTC-USD 1m 3`
> (streams 5yr history from S3, no local storage). Raw: `data/history_baseline.json`.

## Current baseline (2026-08-02) — UNIFIED confluence, 5-year BTC-USD 1m

**Config:** sl_atr 3.0, tp_rr 0.7, min_confluence 4, require_m5, EMA 50, mql5 ranges.

**Across 21 sampled months (2021-07 → 2026-07), streamed from S3:**
- **pass_rate 0.30** (profitable in ~30% of months)
- **median PF 0.90** (losing/break-even overall)

**Verdict: NOT a proven edge across regimes.** The strategy is profitable only in
select windows and loses in ~70% of months over 5 years.

### Profitable months (the ~30%)
2022-01 (PF 1.52), 2022-04 (1.27), 2023-04 (1.23), 2024-04 (1.25), 2026-01 (1.33),
2026-04 (1.48).

### Critical correction to earlier claims
The earlier **"positive OOS PF 1.29"** re-baseline (recent ~40-day broker window)
was a **favourable-period artifact** — that window landed on 2026-01/04, which are
among the best months in 5 years. It was NOT representative. **Any edge claim must
be judged against this full-history baseline, not a recent window.**

## What this means (honest)
1. The 7-indicator confluence, as configured, does **not** have a durable standalone
   edge across market regimes **on OHLCV alone**.
2. **BUT — important reframe (BTCUSD is special):** BTCUSD is the only symbol with
   **Level-2 orderbook data**, and its *intended* edge is technical confluence **+
   L2/orderbook/VPIN/whale confirmation**. The 5-year OHLCV baseline structurally
   **cannot** measure that — it only tested the technical half. So the 0.30 pass-rate
   condemns the *OHLCV-only technical config*, not BTC's real (L2-enhanced) thesis.
3. **Data reality that limits testing the real BTC edge:** L2 orderbook + v5 features
   (vpin/ob_/flow_) on S3 only cover ~**30 days** (2026-07-03 → present) — the RT
   collectors are new. OHLCV goes back 5 years but has no L2. So the L2-enhanced BTC
   edge can currently only be tested on ~30 days (still small-sample).
4. **XAUUSD / GER40** have NO L2 — they must stand on the technical confluence alone,
   which the 5yr baseline says is not (yet) a durable edge → they need the regime
   analysis (#50) or rework.
5. The next real question splits by symbol:
   - **BTC:** does L2/VPIN/whale confirmation turn the technical confluence positive
     on the ~30-day L2 window? (test #43/#50) — and gather more L2 days over time.
   - **XAU/GER:** is there a detectable regime gate (#50), or does the entry need rework?


## Data / storage note
The 5-year OHLCV lives in CryptoRTI S3 (`data/history_bars/coinbase/...`, ~195MB for
BTC 1m). We do NOT store it locally (storage constraint) — the harness STREAMS it in
one pass. Features/whale parquet only cover ~recent 28 days; long OHLCV is CSV back
to 2021-07-05.
