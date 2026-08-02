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
   edge across market regimes.
2. The next real question (not another param sweep): **is there a detectable regime
   signal that separates the winning ~30% of months from the losing 70%?** If yes,
   gate entries on it. If no, the entry edge isn't there yet and needs rework.
3. Small-sample / recent-window results are not trustworthy for edge claims — this
   file is the reference.

## Data / storage note
The 5-year OHLCV lives in CryptoRTI S3 (`data/history_bars/coinbase/...`, ~195MB for
BTC 1m). We do NOT store it locally (storage constraint) — the harness STREAMS it in
one pass. Features/whale parquet only cover ~recent 28 days; long OHLCV is CSV back
to 2021-07-05.
