# QMMP Inventory — complete accounting (GitHub #57)

> Lossless record of every script, tool, database, and artifact in the QMMP symbol
> onboarding + validation work. GitHub is the single source of truth (AGENTS.md).
> Each entry notes what it is, where it lives, and whether it is committed to git or is a
> machine-local (gitignored) regenerable artifact.

## 1. Pipeline & tooling scripts (committed)

| Script | Purpose |
| --- | --- |
| `scripts/qmmp/onboard_pipeline.py` | **Master symbol-agnostic onboarding pipeline** (#57): cost model -> timeframe selection by move/cost -> OsMA cycles -> session split -> per-session winner/loser floors -> walk-forward floor validation -> exit derivation -> equity -> model.json + report. |
| `scripts/qmmp/ingest.py` | Multi-timeframe (M1-H4) ingest, MT5 + optional Dukascopy deep ticks -> Parquet; integrity guard; session flags. |
| `scripts/qmmp/features.py` | 38 MT5 indicators per TF + OsMA 4-state + cycle index, HTF as-of aligned onto M1 -> features_m1.parquet. |
| `scripts/qmmp/mine.py` | Winner/fakeout labelling + RandomForest/XGBoost feature-importance per session + walk-forward AUC. |
| `scripts/qmmp/exit_sim.py` | Tick-accurate per-leg PYRAMID_TRAIL Numba simulator + walk-forward exit grid (net + risk-adjusted). |
| `scripts/qmmp/vbt_ordermodel.py` | **Native vectorbt** `from_order_func` implementing the exact basket-trail + early-pyramid model (engine of record); exports trade records for ONNX. |
| `scripts/qmmp/vbt_model.py` | vectorbt `from_signals` single-position variant + ONNX feature export (reference). |
| `scripts/qmmp/forming_candle.py` | Tick-driven forming-candle OsMA-strength analysis (25/50/75% formation). |
| `scripts/qmmp/fetch_ticks_30d.py` | Dukascopy 30d tick fetch -> ticks_30d.parquet (background job). |
| `scripts/mt5_all_indicators.py` | All 38 native MT5 indicators computed from OHLCV (Python). |
| `scripts/onboard_symbol.py` | Earlier per-symbol onboarding analyzer (SL/BE/trail/add + session ranking, significance-gated). |
| `scripts/onboard_analyze.py` | Earlier OsMA-cycle onboarding analysis (excursion + entry profile). |

## 2. Specs & docs (committed)

| Doc | Purpose |
| --- | --- |
| `QMMP_SPEC.md` | Architecture + the exact 9-step repeatable per-symbol assessment process. |
| `QMMP_INVENTORY.md` | This file. |
| `data/qmmp/<SYMBOL>/model.json` | Per-symbol locked/validated config (force-added past data/ gitignore). |

## 3. Live-engine changes (committed, in src/)

| File | Change |
| --- | --- |
| `src/config.py` | `SYMBOL_ENTRY_TIMEFRAME` + `entry_timeframe_for()` (BTCUSD->H1); PYRAMID_* validated H1 exit params + `PYRAMID_EARLY_FRAC`. |
| `src/trading/scalp_engine.py` | Per-symbol entry timeframe; early-only pyramiding (`_pyramid_within_early_window`); H1/PYRAMID symbols null out M1-scale strength floors in `_tuned_params`. |
| `src/trading/trade_manager.py` | `PYRAMID_TRAIL` variant + basket trail + SL-aware catastrophe failsafe. |
| `src/learning/param_optimizer.py` | BTCUSD baseline = validated H1 config (floors zeroed, H1 exit magnitudes). |
| `src/core_rules.py` | R2 allows PYRAMID_TRAIL for configured symbols. |

## 4. Machine-local artifacts (data/, gitignored — REGENERABLE, listed for completeness)

Regenerate with the pipeline; NOT in git (per AGENTS.md `data/` is machine-local).

| Artifact | Size | Regenerate with |
| --- | --- | --- |
| `data/qmmp/BTCUSD/{M1,M5,M15,M30,H1,H4}.parquet` | ~4MB | `python -m scripts.qmmp.ingest BTCUSD` |
| `data/qmmp/BTCUSD/ticks_30d.parquet` | 11MB | `python -m scripts.qmmp.fetch_ticks_30d` |
| `data/qmmp/BTCUSD/features_m1.parquet` | 25MB | `python -m scripts.qmmp.features BTCUSD` |
| `data/qmmp/BTCUSD/attribution.csv` | 0.8MB | `python -m scripts.qmmp.mine BTCUSD` |
| `data/qmmp/BTCUSD/vbt_ordermodel_trades.parquet` + stats | 0.1MB | `python -m scripts.qmmp.vbt_ordermodel BTCUSD` |
| `data/qmmp/BTCUSD/onboarding_report.md` | small | `python -m scripts.qmmp.onboard_pipeline BTCUSD` |
| Analysis outputs `data/btc_*.md` (cycle paths, indicator tables, osma sweep, forming candle) | ~2.5MB | temp analysis scripts (this session) |

## 5. Databases (data/, gitignored — machine-local live state)

| DB | Purpose |
| --- | --- |
| `data/trading_experience.db` | Trade journal / learning source (incl. MT5_BACKFILL rows). |
| `data/trading_knowledge.db` | Semantic knowledge store (findings/corrections/decisions). |
| `data/whale_outcomes.db` | CryptoRTI whale-signal outcomes. |
| `data/hypotheses.db`, `handoff_protocol.db`, `version_management.db` | Research/handoff/version state. |

## 6. Dependencies added this session
- `vectorbt==1.1.0`, `polars` (venv). `numba`, `xgboost`, `pyarrow`, `sklearn` already present.
- NOTE: vectorbt pulled numba 0.67/numpy 2.5 (conflicts pandas-ta pin, but pandas-ta is unused at runtime; live bot verified unaffected).
