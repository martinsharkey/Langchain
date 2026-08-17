# BTCUSD Session — Authoritative Methodology Record (2026-08-16/17)

Reconstructed IN FULL from every analysis script + output file on disk (the chat transcript
had 511,805 chars truncated from its middle; the artifacts are the complete, untruncated
record). This is the lossless account of the day's work.

## Global constants (every script)
OsMA/MACD 12/26/9 · EMA 13 · ATR 14 · Bulls/Bears power 13 · point 0.01 ·
USD/pt/lot 0.0073723478 · GBP/pt/0.01 = 0.00007 (equity_sim) / 0.0001 (model.json — DISCREPANCY) ·
spread 1200pt ($12 real ECN, demo showed ~1700) · commission $6/lot round-turn · slippage 100pt/fill ·
round-turn cost/leg 0.01 lot = £0.18 · sizing £50 per 0.01 (=£5000→1.0 lot; alt £100/£250) · 100-lot/account cap.
Session windows: EARLY M1 scripts Asian 0-8/London 8-13/NY 13-21; LATER tick/HTF/spec Asian 0-9/London 7-16/NY 12-21 (precedence NY>London>Asian).

## Entry rule
OsMA zero-cross; the M1 mining used "fresh MACD-M1 zero-cross then first directionally-aligned OsMA cycle".
Cycle = OsMA sign-run (min 2 bars); cycle end = sign flip (cap f+240 tick / f+300 HTF). win = fav>adv (peak beats trough).

## Stages (ordered)
1. Excursion mapping (btc_cycle_points/full, macd_aligned_cycles) — per-cycle fav/adv + indicators.
2. Correlation (corr_analysis) — Pearson/Spearman indicator→fav. n=23 long/30 short.
3. Session power (session_edge, session_threshold_sweep, power_pattern, power_wf) — learned per-session floors:
   LONG bulls≥ Asian 29.5/London 28.6/NY 38.1 ; SHORT bears≤ Asian -33.9/London -26.4/NY -40.4.
4. Forming-candle 25/50/75% tick (forming_candle, wf_forming): LONG early-strong 55% vs late 47% (base 53%);
   SHORT 59% vs 52% (base 58%). osma→fav ~±0.30, osma→win ~0. Early-strong = osma@25% ≥50% of final.
5. OsMA strength sweep (osma_strength_sweep): raising floor MONOTONICALLY LOWERS win (long 54→41%, short 57→47%) -> REJECTED.
6. 37/46-indicator XGBoost + walk-forward entry (full37_edge, xgb_edge, xgb_entry_90d, wf_entry):
   AUC NOT stable across folds -> no entry-filter edge transfers OOS.
7. Exit/pyramid (candle_exit, xgb_exit_walkforward, pyramid_sim/optimize, derive_exit_range, reopt_exit,
   sl_proximity, sl_headtohead, atr_ema_fail, ema_atr_wf, pullback_analysis, trail_spread_sweep):
   M1 validated exit SL6000/BE400/trail200/add2500/BE-lock200. Tight trail wins because entry is negative-expectancy;
   mid-price sims overstate tight trails -> spread-aware bid/ask fills required. Real median pullback measured.
8. Timeframe move/cost (htf_cost): M1 1.9x(dead)/M5 6.8x/M15 17.4x/M30 27.1x/H1 41x/H4 83.7x.
9. H1 full revalidation (h1_full, h1_diag, h1_session_analysis, h1_floor_wf, h1_basket_pyramid,
   h1_early_pyramid, h1_tighttrail_wf, leg_count_wf):
   Per-session H1 (validated exit): Asian 88%/+£1.66, London 88%/+£1.25, NY 81%/+£0.88.
   Power polarity FLIPS on H1 (M1 wants strong power; H1 wants NOT-extreme). Entry filters DON'T transfer M1->H1.
   Winners have ~2x osma magnitude + aligned ema-slope (H1 scale). Tight trail ~15% median peak stable OOS. Max 4 legs.
   H1 exit: SL250000/BE15850/trail15850/add15850/early0.15/max4.
10. Compounding equity (equity_sim): OOS fresh £5000 -> £50/0.01 +299%/6.4%DD, £100 +102%/3.3%, £250 +34%/1.3%; 80% win.
    In-sample +28,999% DISCARDED (meaningless exponential compounding).
11. Native vectorbt (vbt_ordermodel from_order_func = engine): 2yr +2987%, 56.48% win, PF 2.745, Sharpe 6.63, DD 7.49%,
    1257 trades @ £250/0.01. Agrees in sign/magnitude with custom Numba sim. from_signals FAILED (-72%, wrong exit).

## KEY LESSONS
- Demo hides spread -> always model real ECN cost FIRST.
- M1 spread-negative (1.9x); H1 viable (41x). Move must dwarf cost.
- Tight trail wins on negative-expectancy entry; trail must beat spread + match real pullback.
- Entry filters/floors are TIMEFRAME-SPECIFIC; don't transfer M1->H1; durable edge is EXIT/pyramiding.
- Tick data essential on low TF, less on high TF -> make it a DATA-measured decision (#62), not a hardcoded list.
- Per-session Asian best on H1.
- Timeframe by DATA (walk-forward net), not a move/cost multiplier.
- In-sample compounded returns meaningless; only OOS fresh-account counts.

## CRITICAL DISCREPANCY TO RECONCILE
- model.json (auto-pipeline, today) = **M30** (SL431226/BE7324) chosen by a >=25x multiplier gate.
- QMMP_SPEC + live config (config.entry_timeframe_for) + saved memory = **H1** (SL250000/BE15850), the human-validated pick.
- The M30 pick is the exact "multiplier not data" bug; the pipeline must select timeframe by walk-forward net, which gave H1.
Other discrepancies: GBP/pt 0.00007 vs 0.0001; session windows differ M1-era vs later; "37" label vs 46 actual indicators.

## GitHub issues: #57 master, #58 H1 floors, #59 numba/numpy dep, #60 reproduce BTCUSD, #61 EA fleet, #62 tick-aware data-driven.
