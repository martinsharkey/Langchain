# TESTING & CALIBRATION — Complete Reference

> How this bot is tested, backtested, calibrated, and continually self-adjusted.
> Covers the unit-test suite, the offline backtest/optimisation harnesses, the
> live self-learning loops, and how they connect. Last updated 2026-08-02.

---

## 1. Unit test suite (`tests/`, pytest)

Run: `python -m pytest tests -q` (79 passing as of 2026-08-02).

| Test file | Covers |
|---|---|
| `test_confluence_*` / `test_osma_confluence.py` | 7-indicator confluence entry logic (OsMA cross + MACD-lead + hard gates + soft confirmations) |
| `test_pattern_optimizer.py` | MACD-leads-OsMA trigger discovery + exit-config sweep |
| `test_excursion_analyzer.py` | Per-symbol OsMA-cycle excursion (peak/trough/wick) + exit recommendation |
| `test_config_checkpointer.py` | Revert-to-best-config + learn-from-failure |
| `test_learning_killswitch.py` | Adaptation freeze (uniform variant weights when frozen) |
| `test_graduation.py` | Per-symbol edge → size-up gate; force-probation only lowers |
| `test_dynamic_fixer.py` | Losing-symbol ReAct fix escalation (exit-fix → retune → strategy → research) |
| `test_onnx_predictor.py` | Per-symbol chronological train/export/predict + thin-holdout rejection |
| `test_edge_discovery.py` | Strategy×regime sweep → overlay; no-edge → empty focused entry |
| `test_continual_researcher.py` | Review + mql5 hypothesis + daily idempotency |
| `test_wave_predictor.py` | Whale confidence model (confirmed→high, thin→discounted) |
| `test_account_scoping.py` | Per-account journal scoping + backfill |
| `test_trade_manager_giveback.py` | Giveback/exit (winners run, arm threshold, TP-awareness) |
| `test_control_channel.py` | Dashboard control.json → engine apply |
| `test_react_alt_tuning.py` | Optimizer mql5-guided candidate + skip failed directions |
| `test_training_sizing_safety.py` | TRAINING-mode symbols never size up |
| `test_closed_loop.py` | Reflection → optimize → validate end-to-end |

**Note:** a few tests need the local MiniLM model (first run downloads it) and MT5
package; on a machine without MT5 those skip/fail (tracked, issue #39).

---

## 2. Offline backtest / calibration harnesses (`scripts/`)

All use REAL MT5 history via `copy_rates_range` (M1 ~40 days, M5/M15 up to 6 months).
**Run with the live bot stopped** (single MT5 connection). All are read-only analysis.

### 2a. `backtest_macd_osma.py` — single-pass confluence backtest
`python -m scripts.backtest_macd_osma BTCUSD 5000`
Finds full 7-indicator confluence triggers (via `confluence_signal`), sweeps
sl_atr × tp_rr × MTF-alignment, prints WR/PF/expectancy per cell.

### 2b. `iterative_walkforward.py` — chronological in-sample → out-of-sample (the "10-round tuning")
`python -m scripts.iterative_walkforward BTCUSD 10 50000`
Splits history 60% in-sample / 40% out-of-sample. Each round makes ONE incremental
adjustment (sl_atr/tp_rr/lead/MTF) that best improves OOS PF while staying IS-profitable.
Logs each round to `data/walkforward_results.json`.
**Purpose:** does a change GENERALISE (not overfit one window)?

### 2c. `robust_tester.py` — random-window robustness (regime-agnostic) + full-confluence calibration
`python -m scripts.robust_tester BTCUSD 40 10 10`  (symbol, days, N-random-windows, iters)
Tunes the FULL confluence + all indicator strengths (osma/ema/atr/power/rsi periods,
min_confluence, atr range, price-stretch, sl/tp) over the mql5-doc ranges; validates
each candidate across N RANDOM date sub-windows; keeps a config only if it passes a
MAJORITY of windows. Writes `data/robust_config.json`. **This is the primary tuner.**
**Purpose:** find a config that trades well at ANY random date, not one fitted window.

### 2d. `validate_whale_backtest.py` — CryptoRTI whale hybrid validation (#43)
`python -m scripts.validate_whale_backtest 30`
Attaches S3 whale/VPIN features onto BTC M1 bars CAUSALLY (`feature_align`), then
compares confluence-trigger outcomes whale_active vs NOT — so the live whale boost is
validated on history. **Verdict rule:** if whale_active PF/WR ≤ NOT, keep the live
boost conservative/observe-only.

### 2e. `backtest_peak_capture.py` — exit-capture study (caveated)
Replays per-trade telemetry under peak-capture trailing rules. NOTE: the GoldShark
`BTCUSD_UnifiedLog.csv` is a SIMULATED (non-closing) run — not valid for exit backtesting;
use only clean closed-trade telemetry.

### Known data limits (honest)
- MT5 serves ~40 days of BTC **M1** (57k bars → ~80–95 confluence triggers). Not enough
  for statistically bulletproof conclusions; PF wanders (1.3–1.9) with window sampling.
- M5/M15 reach ~6 months (longer-history testing is a future harness).
- Deeper past-date validation needs older history (broker limit) — open item.

---

## 3. The CONTINUAL (live) self-learning loop

Runs inside the live engine (`scalp_engine.py`). Two cadences, both non-fatal:
- **Fast (~every 40 cycles, `EXIT_CALIBRATION_CYCLES`)**: excursion measurement +
  pattern lock → apply exit config live; ConfigCheckpointer revert/learn.
- **Slow (~hourly, `ADAPTIVE_EVERY_CYCLES=240`, background thread)**: researcher
  daily-cycle (review → mql5 query → hypothesis → robust optimise → edge-discovery
  sweep → auto-file GitHub issues), param optimizer, ONNX retrain, DynamicFixer.

### Component → connection map (all verified wired, 2026-08-02 audit)
```
mql5 knowledge RAG (#22) ─┐
experience DB (per-account) ─┼─> ContinualResearcher.daily_cycle (#32)
                             │      ├─ lock_in_pattern (#40) ─┐
                             │      ├─ measure_excursion (#41) ┼─> apply_exit_config -> _exit_override (LIVE)
                             │      ├─ robust_optimise (#44) ──┘         │
                             │      ├─ edge_discovery.sweep_all (#31) -> data/edge_weights.json -> focused_rules (LIVE)
                             │      └─ profile_indicator_scale + auto-file issues
param_optimizer (#25/#44, mql5 ranges) -> tuned_params.json -> compute_full_indicators -> LIVE entry
ConfigCheckpointer (#27) -> revert bad configs + record failed dirs -> KnowledgeStore
DynamicFixer (#37) -> per losing symbol: exit-fix->retune->strategy->research (LIVE)
ONNX per-symbol (#42) -> P(win) nudge on entry confidence (LIVE, conservative)
Graduation (#24) -> gates position sizing (TRAINING = micro lot)
KnowledgeStore (#13) <- startup recall + reflection write-back + all findings
CryptoRTI whale: live boost (wave_predictor) + backtest validation (feature_align) [#43]
```

### Safety gates (verify/revert everywhere)
- Every self-tuned change is verified on realised expectancy by the **ConfigCheckpointer**
  and REVERTED if it degrades; the failed direction is recorded so it isn't retried.
- `LEARNING_ADAPTATION_ENABLED` (kill-switch) freezes mutation; `LEARNING_AUTO_REVERT_ENABLED`
  keeps the safety revert running regardless.
- Sizing only increases when a symbol is GRADUATED and OperatingMode==LIVE.
- Whale boost authority capped (`WHALE_BOOST_MAX`/`WHALE_SCALE_MAX`) until validated.

---

## 4. How we continually test + adjust (the process)

1. **Offline:** run `robust_tester` (random-window) + `iterative_walkforward` (OOS) on a
   symbol to find/confirm a generalising confluence config → written to `data/robust_config.json`.
2. **Live:** the researcher re-runs robust optimise + excursion calibration on cadence,
   applies the winning exit config live; the checkpointer verifies on realised expectancy
   and reverts if worse.
3. **Validate new features** (e.g. whale) on the backtest path before trusting them live
   (`validate_whale_backtest`); keep authority conservative until validated.
4. **Inspect** via the dashboard (`/api/status`, `learning_health`, `exit_calibration`,
   `config_checkpoints`, `graduation`, `onnx_model`) and `data/*.json` artifacts.
5. **Reproduce** any live decision offline with the harnesses above (same confluence module).

### Artifacts written by the running bot (all under `data/`, gitignored)
`tuned_params.json`, `robust_config.json`, `edge_weights.json`, `config_checkpoints.json`,
`graduation.json`, `walkforward_results.json`, `models/outcome_*.onnx`,
`trading_experience.db`, `chromadb_store/` (knowledge + whale + mql5 RAGs).
