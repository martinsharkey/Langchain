# QMMP Pipeline Plan — Symbol Onboarding, Vectorbt Discovery, Optuna Hyperparametrisation, Backtest & EA/Bot Deployment

**Status:** Planning  
**Author:** Bob (grounded in fetched vectorbt + optuna documentation)  
**RAG Collections built:** `vectorbt_docs` (299 chunks), `optuna_docs` (70 chunks), `ta_libs_docs` (148 chunks)  
**Constraint:** All backtesting and optimisation code MUST use `vbt.Portfolio.from_signals()`, `vbt.IndicatorFactory`, and `optuna.create_study()` — no custom bar-loop reimplementations.

---

## Overview

Replace the existing shallow `VectorbtOnboarder` (which used a manual Python for-loop and never called `vbt.Portfolio`) with a complete, library-native pipeline:

```
Symbol + Sessions + Timeframes
        ↓
[STAGE 1] Vectorbt Discovery
  - Filter OHLCV by session (boolean mask on DatetimeIndex hour + weekday)
  - Run IndicatorFactory param sweeps (RSI, BB, MACD, OsMA, ATR, ADX, etc.) via vbt.run()
  - Each combination → vbt.Portfolio.from_signals() with fees + slippage
  - stats() gives: Total Trades, Win Rate [%], Profit Factor, Sharpe Ratio, Expectancy, Max Drawdown [%]
  - Top 10 candidates per session shortlisted by Sharpe + min trade threshold
        ↓
[STAGE 2] Optuna Hyperparametrisation
  - For each of the top 10 candidates: define an Optuna study per (symbol, session, strategy)
  - objective(trial): trial.suggest_int / suggest_float / suggest_categorical for each indicator param
  - objective calls vbt.Portfolio.from_signals() on train folds (RollingSplitter)
  - TPE sampler (default) with MedianPruner for early trial stopping
  - Persisted to SQLite (resumable, load_if_exists=True)
  - Status: running / completed / failed_validation tracked per candidate
        ↓
[STAGE 3] Vectorbt Out-of-Sample Backtest
  - Take best Optuna trial params per candidate
  - Run vbt.Portfolio.from_signals() on held-out fold (RangeSplitter last fold)
  - Produce full stats() + trades.records_readable DataFrame
  - Results saved as JSON + Parquet for export
  - Status: passed / failed (failed kept in dashboard with reason)
        ↓
[STAGE 4] Report, Selection & Deployment
  - Dashboard shows all candidates: status, metrics, session, timeframe
  - User selects which sessions to enable per symbol
  - Selected strategies → tuned_params.json (live bot) or MQL5 EA generation
```

---

## Session Definitions

Confirmed sessions for the new pipeline (12 total, covering your requirements):

| Key | Name | UTC Hours | Days | Notes |
|-----|------|-----------|------|-------|
| `asian` | Asian | 00:00–08:00 | Mon–Fri | Tokyo/HK/Singapore open |
| `london` | London | 08:00–17:00 | Mon–Fri | LSE open |
| `new_york` | New York | 13:00–21:00 | Mon–Fri | NYSE open |
| `london_ny_overlap` | London/NY Overlap | 13:00–17:00 | Mon–Fri | Highest FX volatility |
| `weekly_close_mon` | Weekly Close Mon | 22:00–23:00 | Mon | Low liquidity close |
| `weekly_close_tue` | Weekly Close Tue | 22:00–23:00 | Tue | Low liquidity close |
| `weekly_close_wed` | Weekly Close Wed | 22:00–23:00 | Wed | Low liquidity close |
| `weekly_close_thu` | Weekly Close Thu | 22:00–23:00 | Thu | Low liquidity close |
| `market_open_15` | Post-Open 15m | Open+0–15m | Mon–Fri | First 15 min after session open |
| `market_open_30` | Post-Open 30m | Open+0–30m | Mon–Fri | First 30 min after session open |
| `market_open_60` | Post-Open 60m | Open+0–60m | Mon–Fri | First 60 min after session open |
| `btcusd_weekend` | BTC Weekend | Fri 22:00–Sun 21:00 | Fri–Sun | Crypto-only; starts after GMT 22:00 Fri |

Implemented in `src/strategies/sessions.py` as a new `SessionRegistry` with `filter_mask(ohlcv, session_key)` returning a boolean `pd.Series` suitable for masking a DatetimeIndex.

---

## Library-Native Patterns (from fetched docs)

### vectorbt — confirmed from source

```python
# 1. IndicatorFactory for parameter sweeps
MyRSI = vbt.IndicatorFactory(
    input_names=['close'],
    param_names=['window'],
    output_names=['rsi'],
).from_apply_func(rsi_nb, window=14)

# Run across multiple param values in one call:
rsi = MyRSI.run(close, window=vbt.Default([7, 14, 21, 28]))

# 2. Portfolio.from_signals with real costs
pf = vbt.Portfolio.from_signals(
    close=close,
    entries=entries,        # boolean array
    exits=exits,
    short_entries=short_entries,
    short_exits=short_exits,
    sl_stop=sl_stop,        # fraction e.g. 0.02 = 2%
    sl_trail=True,          # trailing SL
    tp_stop=tp_stop,
    fees=spread_frac,       # spread as fraction of price
    slippage=slip_frac,
    init_cash=5000,
    freq="1H",              # required for duration metrics
)

# 3. stats() — confirmed metrics:
#   Total Trades, Win Rate [%], Profit Factor, Expectancy,
#   Sharpe Ratio, Calmar Ratio, Sortino Ratio, Omega Ratio,
#   Max Drawdown [%], Max Drawdown Duration
stats = pf.stats()

# 4. Individual trades
trades_df = pf.trades.records_readable

# 5. RollingSplitter for walk-forward (train/test splits)
from vectorbt.generic.splitters import RollingSplitter
splitter = RollingSplitter(n=5)   # 5-fold rolling window
# Returns split indices usable to slice the data
```

### optuna — confirmed from docs

```python
import optuna
from optuna.samplers import TPESampler
from optuna.pruners import MedianPruner

def objective(trial):
    # Suggest indicator parameters
    rsi_window  = trial.suggest_int("rsi_window", 5, 30)
    bb_window   = trial.suggest_int("bb_window", 10, 40)
    bb_std      = trial.suggest_float("bb_std", 1.0, 3.0, step=0.25)
    sl_atr_mult = trial.suggest_float("sl_atr_mult", 0.5, 3.0, step=0.25)
    tp_rr_ratio = trial.suggest_float("tp_rr_ratio", 1.0, 4.0, step=0.25)

    # Run vectorbt backtest
    pf = vbt.Portfolio.from_signals(...)
    stats = pf.stats()
    
    # Prune if not enough trades
    n_trades = int(stats.get("Total Trades", 0))
    trial.report(n_trades, step=0)
    if trial.should_prune() or n_trades < 10:
        raise optuna.TrialPruned()
    
    return float(stats.get("Sharpe Ratio", -99))

# Resumable study persisted to SQLite
study = optuna.create_study(
    study_name=f"floors_{symbol}_{session}_{strategy}",
    storage=f"sqlite:///data/qmmp/{symbol}/optuna/study.db",
    sampler=TPESampler(seed=42),
    pruner=MedianPruner(n_warmup_steps=10),
    direction="maximize",
    load_if_exists=True,
)
study.optimize(objective, n_trials=100, n_jobs=1)

# Get results
best_params = study.best_params
all_trials_df = study.trials_dataframe()
```

---

## Sub-Tasks

### Sub-Task 1 — Session Registry Rewrite
**Status:** `[ ] pending`

**Intent:** Replace the current 3-session `session_of(hour)` function in `src/strategies/sessions.py` with a full 12-session `SessionRegistry` that can filter an OHLCV DataFrame by session, supporting all your identified sessions including weekend BTC, weekly close windows, and post-open windows.

**Expected Outcomes:**
- `SessionRegistry.all_sessions()` returns list of 12 session keys
- `SessionRegistry.filter_mask(ohlcv: pd.DataFrame, session_key: str) -> pd.Series[bool]` returns correct boolean mask for any session
- Post-open sessions (15/30/60 min) work relative to each session's open time
- Backward-compatible: `session_of(hour)` still works for live engine
- Unit tests cover each session mask on known data

**Todo List:**
1. Rewrite `src/strategies/sessions.py` — add `SESSION_DEFINITIONS` dict (12 sessions), `SessionRegistry` class, `filter_mask()`, `session_hours()`, `is_weekend_session()` helpers
2. Preserve `session_of(hour)` as a backward-compatible alias
3. Write `tests/test_sessions.py` with parametrised tests for each session using synthetic UTC DatetimeIndex

**Relevant Context:**
- `langchain/src/strategies/sessions.py` — current file (41 lines), simple `session_of()` only
- `langchain/src/learning/vectorbt_session_filter_optimizer.py` — has the old 8-session SESSIONS dict, superseded by this task
- Sessions used by: `optuna_floor_optimizer.py`, `osma_confluence.py`, `scalp_engine.py`

---

### Sub-Task 2 — Vectorbt Discovery Engine
**Status:** `[ ] pending`

**Intent:** Build a new `scripts/qmmp/vbt_discovery.py` that is the **sole** entry point for Stage 1. It uses `vbt.IndicatorFactory` to sweep indicator parameters, `vbt.Portfolio.from_signals()` for all backtests, and `SessionRegistry.filter_mask()` to slice each session. No manual for-loops. No custom backtest logic. Returns a structured shortlist of top-10 candidates per session.

**Expected Outcomes:**
- `VbtDiscovery.run(symbol, timeframes, sessions, min_trades=20)` produces a shortlist JSON
- Each candidate has: `session`, `timeframe`, `indicator`, `params`, `pf`, `wr`, `sharpe`, `expectancy`, `max_dd`, `total_trades`
- Progress is streamed via a callback so the API can report `X/Y combos tested (Z%)`
- Results saved to `data/qmmp/{SYMBOL}/discovery/{session}_{timeframe}.json`
- Reads data from `DataManager` (parquet first, MT5 fallback)
- Uses `vbt.Portfolio.from_signals()` with real fees (spread from MT5 symbol info) and slippage

**Todo List:**
1. Create `scripts/qmmp/vbt_discovery.py` — `VbtDiscovery` class
2. Implement `_build_indicator_grid()` — uses `vbt.IndicatorFactory` to build RSI, BB, MACD/OsMA, ATR, ADX, CCI, Stochastic, Williams%R, EMA cross indicators with param ranges sourced from `DocsRAG` query on `ta_libs_docs`
3. Implement `_run_session_timeframe(session_key, tf, ohlcv)` — applies `SessionRegistry.filter_mask()`, runs all indicator×param combinations via `vbt.Portfolio.from_signals()`, collects `stats()`
4. Implement `_shortlist(results, n=10)` — rank by Sharpe, min 20 trades, return top-10 per session
5. Implement `run()` — orchestrates all sessions × timeframes, writes JSON, calls progress callback
6. Add `DocsRAG` query guard at top of file: any developer adding new indicator code must query `vectorbt_docs` + `ta_libs_docs` first
7. Write `tests/test_vbt_discovery.py` with mocked data confirming output schema

**Relevant Context:**
- `langchain/scripts/qmmp/vbt_model.py` — existing real `vbt.Portfolio.from_signals()` usage pattern to follow
- `langchain/scripts/qmmp/optuna_floor_optimizer.py` lines 283–305 — the only other real vbt.Portfolio call, confirmed working
- `langchain/src/learning/docs_rag.py` — RAG query client
- `langchain/src/data_acquisition/manager.py` — data loading
- `langchain/src/strategies/indicators.py` — existing indicator functions (osma, bulls_power, bears_power, atr, ema) reusable as `from_apply_func` inputs

---

### Sub-Task 3 — Optuna Hyperparametrisation Service
**Status:** `[ ] pending`

**Intent:** Build `scripts/qmmp/optuna_sweep.py` — takes the top-10 shortlist from Stage 1 and runs an Optuna study per candidate. The objective function uses `vbt.Portfolio.from_signals()` on rolling train folds. Results are persisted to SQLite (resumable). Candidates that fail (< 10 trades, negative Sharpe on held-out) get status `failed_validation` with reason — they are kept, not discarded.

**Expected Outcomes:**
- `OptunaSweep.run(symbol, session, shortlist_path, n_trials=100)` produces a results JSON per candidate
- Each candidate result has: `status` (completed/failed_validation), `best_params`, `optimization_metrics` (train folds), `held_out_metrics` (final fold), `failure_reason` if failed
- Studies are resumable: re-running adds trials to existing study
- `study.trials_dataframe()` exported as CSV alongside JSON for data analysis
- `DocsRAG` guard in place — no suggest_* calls added without querying `optuna_docs`

**Todo List:**
1. Create `scripts/qmmp/optuna_sweep.py` — `OptunaSweep` class
2. Implement `_build_search_space(strategy_name, indicator_params)` — maps each indicator's tunable params to `trial.suggest_*` calls; param ranges derived from `_data_bounds()` pattern from existing `optuna_floor_optimizer.py`
3. Implement `_objective(trial, ohlcv_train, indicator, session_key)` — calls `vbt.Portfolio.from_signals()` on train fold, returns Sharpe; prunes with `MedianPruner` if insufficient trades
4. Implement `_held_out_eval(best_params, ohlcv_held_out)` — final evaluation on never-seen fold
5. Implement `run()` — iterates shortlist, creates/resumes study per candidate, exports results JSON + CSV
6. Wire `_try_promote()` pattern from `optuna_floor_optimizer.py` — only promote to `model.json` if held-out metrics beat existing baseline

**Relevant Context:**
- `langchain/scripts/qmmp/optuna_floor_optimizer.py` — existing Optuna + vbt integration (lines 308–377 objective function, lines 380–498 run_study); extend rather than duplicate
- `langchain/src/learning/docs_rag.py` — query `optuna_docs` before coding suggest_* calls
- Walk-forward: use `vectorbt.generic.splitters.RollingSplitter` (confirmed in docs) — first N-1 folds for Optuna, last fold held out

---

### Sub-Task 4 — Out-of-Sample Backtest & Results Export
**Status:** `[ ] pending`

**Intent:** Build `scripts/qmmp/vbt_oos_backtest.py` — takes Optuna best params and runs a clean out-of-sample `vbt.Portfolio.from_signals()` on the held-out fold. Produces full stats, individual trade records, and exports to JSON + Parquet. This is the evidence layer — what gets shown in the dashboard and exported.

**Expected Outcomes:**
- Full `pf.stats()` dict persisted per candidate
- `pf.trades.records_readable` saved as Parquet at `data/qmmp/{SYMBOL}/oos/{session}_{timeframe}_{strategy}.parquet`
- Summary JSON at `data/qmmp/{SYMBOL}/oos/{session}_{timeframe}_{strategy}_summary.json`
- CSV export at same path for external tools
- Equity curve data (for dashboard chart) included in summary JSON

**Todo List:**
1. Create `scripts/qmmp/vbt_oos_backtest.py` — `OOSBacktest` class
2. Implement `run(symbol, session, timeframe, strategy, best_params)` — loads held-out data slice, runs `vbt.Portfolio.from_signals()` with exact params from Optuna, calls `pf.stats()` and `pf.trades.records_readable`
3. Implement `export(results, output_dir)` — writes JSON summary, Parquet trades, CSV trades
4. Include equity curve: `pf.value()` series serialised as list for dashboard charting
5. Mark result status as `oos_passed` (Sharpe > 0, trades >= 10, PF >= 1.0) or `oos_failed` with reason

**Relevant Context:**
- `pf.stats()` confirmed keys from docs: `Total Trades`, `Win Rate [%]`, `Profit Factor`, `Expectancy`, `Sharpe Ratio`, `Max Drawdown [%]`
- `pf.trades.records_readable` — individual trade DataFrame from `vectorbt.records.base`
- `pf.value()` — equity curve series

---

### Sub-Task 5 — Backend API (Flask routes)
**Status:** `[ ] pending`

**Intent:** Wire all four pipeline stages into the Flask backend with endpoints the frontend can call. Each stage is a background task. Progress is streamed via polling. Results flow through a unified status model.

**Expected Outcomes:**
- `POST /api/symbols/<sym>/discover` — triggers Stage 1 (VbtDiscovery) as background task
- `GET /api/symbols/<sym>/discovery` — returns discovery results (shortlist per session)
- `POST /api/symbols/<sym>/optimise` — triggers Stage 2 (OptunaSweep) for selected candidates
- `GET /api/symbols/<sym>/optimise` — returns Optuna results per candidate (status + metrics)
- `POST /api/symbols/<sym>/backtest` — triggers Stage 3 (OOSBacktest) for Optuna-passed candidates
- `GET /api/symbols/<sym>/backtest` — returns OOS results + equity curve data
- `POST /api/symbols/<sym>/deploy` — user selects sessions → writes tuned_params.json + triggers EA gen
- `GET /api/tasks/<task_id>` — task progress polling (existing, extend for new stages)
- All stages emit granular progress updates (stage name, % complete, current item)

**Todo List:**
1. Extend `dashboard/api_symbols.py` with new route handlers for `/discover`, `/optimise`, `/backtest`, `/deploy`
2. Extend `_tasks` dict schema to include `stage` (discovery/optimise/backtest/deploy), `current_item`, `items_total`
3. Background thread for discovery: call `VbtDiscovery.run()` with `progress_cb` updating `_tasks`
4. Background thread for optimise: call `OptunaSweep.run()` per candidate, update task per trial milestone
5. Background thread for backtest: call `OOSBacktest.run()` for each passed candidate
6. Deploy endpoint: write session enables to `session_preferences.json`, call `param_optimizer.apply_tuned()`, call `ea_generator.generate()`
7. Result endpoints: read JSON files from `data/qmmp/{SYMBOL}/` and return structured responses

**Relevant Context:**
- `langchain/dashboard/api_symbols.py` — existing routes to extend (not replace)
- `langchain/src/learning/param_optimizer.py` — `apply_tuned()`, `current_params()` for deploy step
- `langchain/scripts/qmmp/ea_generator.py` — existing EA generator to call from deploy

---

### Sub-Task 6 — Frontend: Symbol Onboarding & Pipeline UI
**Status:** `[ ] pending`

**Intent:** Rewrite `SymbolOnboarding.tsx` to expose the full 4-stage pipeline. The user can see discovery progress, inspect the shortlist, select candidates for Optuna, watch Optuna trial progress, review OOS results, then select which sessions to deploy for each symbol.

**Expected Outcomes:**
- Stage tabs: Discovery → Optuna → Backtest → Deploy (linear flow, each stage unlocks when previous completes)
- Discovery tab: timeframe selector (M1–D1 multi-select), session selector (12 sessions multi-select), progress bar per session×timeframe sweep, shortlist table (top 10 per session, sortable by Sharpe/PF/WR)
- Optuna tab: candidate grid (from shortlist), "Run Optuna" button per candidate or "Run All", per-candidate status badge (running/completed/failed_validation), trial count, best Sharpe so far
- Backtest tab: OOS results per candidate — stats table, equity curve mini-chart, trades count, status (oos_passed / oos_failed + reason)
- Deploy tab: session toggle grid (enable/disable per session for this symbol), deploy button → writes to bot + generates EA
- Export button on Backtest tab: downloads JSON+CSV for all results

**Todo List:**
1. Replace `dashboard-frontend/src/pages/SymbolOnboarding.tsx` entirely
2. Add TypeScript interfaces: `DiscoveryCandidate`, `OptunaResult`, `OOSResult`, `PipelineStage`
3. Build `DiscoveryPanel` component: timeframe + session multi-select, progress tracking, shortlist table
4. Build `OptunaPanel` component: candidate card grid, per-card status + trial metrics, Run/Cancel buttons
5. Build `BacktestPanel` component: results table, equity curve chart (using existing `create_chart` pattern or lightweight SVG), export button
6. Build `DeployPanel` component: session toggle grid with PF/Sharpe annotations, deploy button
7. Extend `dashboard-frontend/src/api.ts` with new endpoint calls
8. Extend `dashboard-frontend/src/types.ts` with new interfaces

**Relevant Context:**
- `langchain/dashboard-frontend/src/pages/SymbolOnboarding.tsx` — current file (527 lines) to replace
- `langchain/dashboard-frontend/src/types.ts` — type definitions to extend
- `langchain/dashboard-frontend/src/api.ts` — API client to extend

---

### Sub-Task 7 — RAG Agent Guard Utility
**Status:** `[ ] pending`

**Intent:** Add a lightweight developer-facing utility that any agent or developer must call before writing vectorbt/optuna code. This enforces the discipline you've insisted on: all code must be grounded in what the library actually provides, not assumed.

**Expected Outcomes:**
- `src/learning/docs_rag.py` (already built) is the query interface
- A `scripts/qmmp/rag_guard.py` script that any developer can run: `python -m scripts.qmmp.rag_guard "Portfolio.from_signals stop loss"` and gets back the relevant doc chunks
- A `CODING_RULES.md` in `scripts/qmmp/` stating: "Before adding any vectorbt or optuna code, run `rag_guard.py` with your question and paste the result into your PR description"
- RAG used inside `vbt_discovery.py` and `optuna_sweep.py` to fetch the correct API for each indicator before building its factory — enforced via assertions

**Todo List:**
1. Write `scripts/qmmp/rag_guard.py` — CLI tool wrapping `DocsRAG.query_all()`
2. Write `scripts/qmmp/CODING_RULES.md`
3. Add `_rag_assert_api(query, collection)` helper in `vbt_discovery.py` and `optuna_sweep.py` — logs RAG result to learning log at startup as evidence the correct API was checked

**Relevant Context:**
- `langchain/src/learning/docs_rag.py` — already built and tested (517 chunks)
- `langchain/data/docs_rag/` — raw docs (vectorbt, optuna, ta_libs)

---

## Data Flow

```
data/broker_data/vt_markets/{SYMBOL}/{TF}.parquet
         ↓  DataManager.get_rates()
         ↓  SessionRegistry.filter_mask()
data/qmmp/{SYMBOL}/discovery/{session}_{tf}.json   ← Stage 1 output
         ↓  shortlist top-10 per session
data/qmmp/{SYMBOL}/optuna/study.db                 ← Stage 2 Optuna SQLite (resumable)
data/qmmp/{SYMBOL}/optuna/trials/best_*.json       ← Stage 2 best trial per candidate
         ↓  passed candidates only
data/qmmp/{SYMBOL}/oos/{session}_{tf}_{strat}.parquet  ← Stage 3 trade records
data/qmmp/{SYMBOL}/oos/{session}_{tf}_{strat}_summary.json
         ↓  user selection in Deploy tab
data/tuned_params.json                             ← live bot params
data/qmmp/{SYMBOL}/GoldShark_{SYMBOL}_session.mq5 ← EA output
```

---

## What is NOT Changing

- `src/trading/scalp_engine.py` — live trading loop untouched
- `src/mt5/broker_adapter.py` — execution layer untouched
- `src/strategies/osma_confluence.py` — live strategy untouched
- `dashboard/app.py` — existing live dashboard routes untouched
- `src/learning/experience_db.py` — trade outcome recording untouched
- `data/chromadb_store/xauusd_market_patterns` — existing RAG collection untouched

---

## Implementation Order

Sub-Tasks must be done in this order (each depends on the previous):

1. **Sub-Task 1** — Session Registry (foundation for all stages)
2. **Sub-Task 2** — Vectorbt Discovery Engine (uses sessions)
3. **Sub-Task 3** — Optuna Sweep (uses discovery shortlist)
4. **Sub-Task 4** — OOS Backtest (uses Optuna results)
5. **Sub-Task 5** — Backend API (wires all four engines)
6. **Sub-Task 6** — Frontend (calls the new API)
7. **Sub-Task 7** — RAG Guard (can be done any time, ideally before Sub-Task 2)
