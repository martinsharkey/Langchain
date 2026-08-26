# Developer Handoff — QMMP Pipeline

**Read this document before touching any code.**  
It tells you exactly what exists, what needs to be built, in what order, and how to do it correctly.

---

## Background

This project is a self-learning algorithmic trading bot (MetaTrader 5, VT Markets broker).  
The specific work described here is the **QMMP Pipeline** — a new symbol onboarding system that:

1. Tests a trading symbol (e.g. BTCUSD, XAUUSD) across 12 defined trading sessions and multiple timeframes
2. Uses **vectorbt** (`vbt.Portfolio.from_signals`) to discover which indicator combinations work best per session
3. Uses **Optuna** (TPE sampler + MedianPruner) to hyperparametrise the top 10 candidates per session
4. Runs a clean out-of-sample vectorbt backtest on the Optuna winners
5. Presents results in the dashboard so the operator can select which sessions to enable for live trading
6. Deploys selected strategies to the live bot and/or generates MQL5 Expert Advisors

The previous developer built a system that **claimed** to use vectorbt but actually used a manual Python for-loop instead. That is not acceptable. Every backtest in this pipeline **must** use `vbt.Portfolio.from_signals()`. See `scripts/qmmp/CODING_RULES.md` for the full rules.

---

## Step 1 — Environment Setup

### 1.1 Python version

The project requires Python 3.10+. The venv at `~/Langchain Bot/venv` uses Python 3.14.

### 1.2 Install the missing libraries

**vectorbt and optuna are listed in `requirements.txt` but are NOT installed.** Nothing in this pipeline will work until they are. Run this once:

```bash
cd "/Users/martinsharkey/Langchain Bot"
source venv/bin/activate

pip install "vectorbt>=0.27.0" "optuna>=4.0.0" "pandas-ta>=0.3.14"
```

### 1.3 Verify the installation

```bash
source venv/bin/activate

python - <<'EOF'
import vectorbt as vbt
import optuna
from vectorbt.generic.splitters import RollingSplitter, RangeSplitter
from vectorbt.indicators.factory import IndicatorFactory
from optuna.samplers import TPESampler
from optuna.pruners import MedianPruner
import pandas_ta

print(f"vectorbt:  {vbt.__version__}")
print(f"optuna:    {optuna.__version__}")
print(f"pandas_ta: {pandas_ta.version}")
print(f"RollingSplitter: OK")
print(f"IndicatorFactory: OK")
print(f"TPESampler: OK")
print(f"MedianPruner: OK")
EOF
```

Expected output — all lines print without error.

### 1.4 Rebuild the documentation RAG

The project has a local ChromaDB RAG containing vectorbt and Optuna documentation.  
It is stored at `data/chromadb_store/` (gitignored — runtime only).  
The source documents are at `docs/lib_docs/` (committed to git — always available).

After cloning or installing the libraries, rebuild the RAG once:

```bash
cd "/Users/martinsharkey/Langchain Bot"
source venv/bin/activate

python - <<'EOF'
from src.learning.docs_rag import DocsRAG
counts = DocsRAG.build_collections()
for name, count in counts.items():
    print(f"  {name}: {count} chunks")
EOF
```

Expected:
```
  vectorbt_docs: 299 chunks
  optuna_docs: 70 chunks
  ta_libs_docs: 148 chunks
```

---

## Step 2 — Read These Files Before Writing Any Code

| File | What it contains | Priority |
|---|---|---|
| `scripts/qmmp/CODING_RULES.md` | Mandatory rules — what you can and cannot do | **Read first** |
| `QMMP_PIPELINE_PLAN.md` | Full plan — 7 sub-tasks, confirmed API patterns, data flow | **Read second** |
| `docs/SESSIONS.md` | Why each session exists, how it behaves differently, exact UTC boundaries, broker context, implementation gotchas, full test cases | **Read before Sub-Task 1** |
| `docs/lib_docs/vectorbt/portfolio_base.md` | `vbt.Portfolio.from_signals()` full API | Reference |
| `docs/lib_docs/vectorbt/indicators_factory.md` | `vbt.IndicatorFactory` usage | Reference |
| `docs/lib_docs/vectorbt/splitters.md` | `RollingSplitter`, `RangeSplitter` for walk-forward | Reference |
| `docs/lib_docs/optuna/first_steps.md` | Optuna basics — study, trial, objective | Reference |
| `docs/lib_docs/optuna/samplers.md` | TPE, CMA-ES, pruners | Reference |
| `docs/lib_docs/optuna/trial.md` | `suggest_float`, `suggest_int`, `suggest_categorical` | Reference |
| `docs/lib_docs/ta_libs/ta.md` | ta library indicator catalogue | Reference |

### Using the RAG guard (required before writing code)

```bash
source venv/bin/activate

# Check the correct API for something before writing it:
python -m scripts.qmmp.rag_guard "Portfolio.from_signals sl_stop trailing stop"
python -m scripts.qmmp.rag_guard "suggest_float indicator period window" --collection optuna_docs
python -m scripts.qmmp.rag_guard "IndicatorFactory from_apply_func param sweep" --collection vectorbt_docs
python -m scripts.qmmp.rag_guard "RollingSplitter walk forward folds" --collection vectorbt_docs

# Search all collections at once:
python -m scripts.qmmp.rag_guard "Sharpe Ratio stats" --all
```

Paste the top result into your PR description as evidence you checked the real API.

---

## Step 3 — Understand What Already Exists

### What is real and correct

| File | What it does correctly |
|---|---|
| `scripts/qmmp/optuna_floor_optimizer.py` | Real `vbt.Portfolio.from_signals()` + real `optuna.create_study()`. This is the pattern to follow. |
| `scripts/qmmp/vbt_model.py` | Real `vbt.Portfolio.from_signals()` for BTCUSD H1. Another correct reference. |
| `src/strategies/indicators.py` | Real indicator functions (osma, bulls_power, bears_power, atr, ema). Use these as inputs to `IndicatorFactory`. |
| `src/learning/docs_rag.py` | ChromaDB RAG client. `DocsRAG.query()` and `DocsRAG.build_collections()`. |
| `src/data_acquisition/manager.py` | Data loader — reads parquet files, falls back to MT5. Always use `DataManager.get_rates()`. |
| `scripts/qmmp/ea_generator.py` | MQL5 EA generator — call this from the deploy step. |
| `src/learning/param_optimizer.py` | `ParameterOptimizer.apply_tuned()` — writes to `tuned_params.json` for the live bot. |
| `dashboard/api_symbols.py` | Flask routes for symbol management. Extend (do not replace) for the new pipeline stages. |

### What exists but is wrong (do not use as a pattern)

| File | Problem |
|---|---|
| `scripts/qmmp/vectorbt_onboard.py` | `import vectorbt as vbt` at the top but never calls it. Uses a manual for-loop backtest. Do not copy this pattern. |
| `src/learning/vectorbt_optimizer.py` | Same problem — imports vbt, never uses it. |
| `src/learning/vectorbt_expanded_optimizer.py` | Same problem. |
| `src/learning/vectorbt_session_filter_optimizer.py` | Same problem. |

### What needs to be built (the 7 sub-tasks)

| # | File to create | Depends on |
|---|---|---|
| 1 | `src/strategies/sessions.py` — SessionRegistry rewrite | Nothing |
| 2 | `scripts/qmmp/vbt_discovery.py` — Vectorbt Discovery Engine | Sub-task 1 |
| 3 | `scripts/qmmp/optuna_sweep.py` — Optuna Sweep | Sub-task 2 |
| 4 | `scripts/qmmp/vbt_oos_backtest.py` — OOS Backtest | Sub-task 3 |
| 5 | `dashboard/api_symbols.py` — new Flask routes for pipeline | Sub-tasks 2–4 |
| 6 | `dashboard-frontend/src/pages/SymbolOnboarding.tsx` — UI rewrite | Sub-task 5 |
| 7 | `scripts/qmmp/rag_guard.py` + `CODING_RULES.md` | ✅ Already done |

---

## Step 4 — The 12 Sessions

The pipeline tests each symbol across these 12 trading sessions. Each session produces its own vectorbt results.

| Session Key | Name | UTC Hours | Days |
|---|---|---|---|
| `asian` | Asian | 00:00–08:00 | Mon–Fri |
| `london` | London | 08:00–17:00 | Mon–Fri |
| `new_york` | New York | 13:00–21:00 | Mon–Fri |
| `london_ny_overlap` | London/NY Overlap | 13:00–17:00 | Mon–Fri |
| `weekly_close_mon` | Weekly Close Monday | 22:00–23:00 | Monday |
| `weekly_close_tue` | Weekly Close Tuesday | 22:00–23:00 | Tuesday |
| `weekly_close_wed` | Weekly Close Wednesday | 22:00–23:00 | Wednesday |
| `weekly_close_thu` | Weekly Close Thursday | 22:00–23:00 | Thursday |
| `market_open_15` | Post-Open 15 min | First 15 min after session open | Mon–Fri |
| `market_open_30` | Post-Open 30 min | First 30 min after session open | Mon–Fri |
| `market_open_60` | Post-Open 60 min | First 60 min after session open | Mon–Fri |
| `btcusd_weekend` | BTC Weekend | Fri 22:00 UTC – Sun 21:00 UTC | Fri–Sun |

The current `src/strategies/sessions.py` only has 3 sessions (Asian, London, NewYork). Sub-task 1 replaces it with a full `SessionRegistry` class that has all 12.

---

## Step 5 — Sub-Task Implementation Guide

Work through these in order. Do not start a sub-task until the previous one is complete and tested.

---

### Sub-Task 1 — Session Registry

**File:** `src/strategies/sessions.py`  
**What to build:** Replace the current file with a `SessionRegistry` class. Keep the existing `session_of(hour)` function working (the live trading engine uses it).

**The class must provide:**
```python
class SessionRegistry:
    @staticmethod
    def all_sessions() -> list[str]:
        """Returns list of all 12 session keys."""

    @staticmethod
    def session_info(session_key: str) -> dict:
        """Returns name, description, utc_start_hour, utc_end_hour, weekdays for a session key."""

    @staticmethod
    def filter_mask(ohlcv: pd.DataFrame, session_key: str) -> pd.Series:
        """Returns boolean pd.Series with True for rows belonging to this session.
        ohlcv must have a UTC-aware DatetimeIndex."""
```

**Gotchas:**
- `filter_mask()` must work on a UTC `DatetimeIndex`. Use `ohlcv.index.hour` and `ohlcv.index.weekday`.
- `btcusd_weekend` spans Fri 22:00 → Sun 21:00 — this wraps across midnight, needs careful boolean logic.
- `market_open_15/30/60` are relative to the session open, not absolute hours — you need to identify each day's first bar in the session window, then take only bars within N minutes of it.
- ISO weekday: Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6.

**Test it:**
```bash
python -m pytest tests/test_sessions.py -v
```

Write `tests/test_sessions.py` with a synthetic UTC DatetimeIndex covering Mon–Sun and assert each session mask returns the expected rows.

---

### Sub-Task 2 — Vectorbt Discovery Engine

**File:** `scripts/qmmp/vbt_discovery.py`  
**What to build:** `VbtDiscovery` class. No for-loop backtests. Everything through `vbt.Portfolio.from_signals()`.

**Confirmed correct pattern from `scripts/qmmp/optuna_floor_optimizer.py` lines 283–305:**
```python
pf = vbt.Portfolio.from_signals(
    close=close,
    entries=signals["entry_long"],
    exits=signals["exit_long"],
    short_entries=signals["entry_short"],
    short_exits=signals["short_exits"],
    sl_stop=tsl,
    sl_trail=True,
    fees=spread_frac,
    slippage=slip_frac,
    init_cash=5000,
    freq="1H",
)
stats = pf.stats()
# Keys: "Total Trades", "Win Rate [%]", "Profit Factor", "Sharpe Ratio",
#       "Expectancy", "Max Drawdown [%]", "Calmar Ratio", "Sortino Ratio"
```

**Confirmed correct IndicatorFactory pattern from `docs/lib_docs/vectorbt/indicators_factory.md`:**
```python
MyRSI = vbt.IndicatorFactory(
    input_names=["close"],
    param_names=["window"],
    output_names=["rsi"],
).from_apply_func(rsi_apply_func, window=14)

# Sweep multiple windows in ONE call — no loop:
rsi_result = MyRSI.run(close, window=[7, 14, 21, 28])
```

**The class must provide:**
```python
class VbtDiscovery:
    def run(
        self,
        symbol: str,
        timeframes: list[str],   # e.g. ["M1","M5","M15","M30","H1","H4","D1"]
        sessions: list[str],     # session keys from SessionRegistry
        min_trades: int = 20,
        progress_cb: callable = None,   # called with (pct: float, message: str)
    ) -> dict:
        """
        Returns:
        {
          "symbol": "BTCUSD",
          "sessions": {
            "asian": {
              "M15": {
                "shortlist": [   # top 10 by Sharpe, min_trades enforced
                  {
                    "rank": 1,
                    "indicator": "RSI",
                    "params": {"window": 14, "overbought": 70, "oversold": 30},
                    "sl_atr_mult": 1.5,
                    "tp_rr_ratio": 2.0,
                    "total_trades": 87,
                    "win_rate_pct": 58.6,
                    "profit_factor": 1.43,
                    "sharpe": 1.21,
                    "expectancy": 0.67,
                    "max_drawdown_pct": 12.3,
                  },
                  ...  # up to 10
                ]
              }
            }
          }
        }
        """
```

**Data flow:**
1. `DataManager.get_rates(symbol, timeframe, count=12000)` → OHLCV DataFrame
2. `SessionRegistry.filter_mask(ohlcv, session_key)` → boolean mask → `session_ohlcv = ohlcv[mask]`
3. For each indicator × param combination: build entry/exit boolean arrays
4. `vbt.Portfolio.from_signals(close=session_ohlcv["close"], entries=..., ...)` → `pf.stats()`
5. Shortlist top 10 by Sharpe where `stats["Total Trades"] >= min_trades`

**Save results:**
```
data/qmmp/{SYMBOL}/discovery/{session}_{timeframe}.json
```

**Progress callback:** Call `progress_cb(pct, message)` every ~5% so the API can report it.

---

### Sub-Task 3 — Optuna Sweep

**File:** `scripts/qmmp/optuna_sweep.py`  
**What to build:** `OptunaSweep` class. Takes the top-10 shortlist from Sub-task 2 and hyperparametrises each candidate.

**Confirmed Optuna pattern from `docs/lib_docs/optuna/first_steps.md` and `scripts/qmmp/optuna_floor_optimizer.py`:**
```python
import optuna
from optuna.samplers import TPESampler
from optuna.pruners import MedianPruner

def objective(trial):
    # Suggest param values — ranges derived from data distribution, not hardcoded
    rsi_window  = trial.suggest_int("rsi_window", lo, hi)
    bb_std      = trial.suggest_float("bb_std", 1.0, 3.0, step=0.25)
    sl_atr_mult = trial.suggest_float("sl_atr_mult", 0.5, 3.0, step=0.25)

    # Run vectorbt backtest on TRAIN folds only
    pf = vbt.Portfolio.from_signals(...)
    stats = pf.stats()

    n_trades = int(stats.get("Total Trades", 0))
    trial.report(n_trades, step=0)
    if trial.should_prune() or n_trades < 10:
        raise optuna.TrialPruned()

    return float(stats.get("Sharpe Ratio", -99.0))

# ALWAYS resumable
study = optuna.create_study(
    study_name=f"qmmp_{symbol}_{session}_{strategy}",
    storage=f"sqlite:///data/qmmp/{symbol}/optuna/study.db",
    sampler=TPESampler(seed=42),
    pruner=MedianPruner(n_warmup_steps=10),
    direction="maximize",
    load_if_exists=True,   # ← required
)
study.optimize(objective, n_trials=100, n_jobs=1)

best_params = study.best_params
all_trials  = study.trials_dataframe()   # export as CSV
```

**Walk-forward split:**
- Use `RollingSplitter` or `RangeSplitter` from `vectorbt.generic.splitters`
- Optuna objective evaluates on folds `0..N-2` only
- Fold `N-1` (last fold) is held out — Optuna **never** sees it
- Final `held_out_metrics` come from a separate `vbt.Portfolio.from_signals()` call on the last fold only

**Result status values:**
- `completed` — passed held-out evaluation (Sharpe > 0, trades >= 10, PF >= 1.0)
- `failed_validation` — held-out metrics did not pass (kept in dashboard with `failure_reason`)
- `pruned` — all trials were pruned (insufficient data for this session+timeframe)

**Save results:**
```
data/qmmp/{SYMBOL}/optuna/study.db                          # Optuna SQLite (resumable)
data/qmmp/{SYMBOL}/optuna/trials/{session}_{tf}_{strat}.json  # best trial
data/qmmp/{SYMBOL}/optuna/trials/{session}_{tf}_{strat}_all_trials.csv  # all trials
```

---

### Sub-Task 4 — Out-of-Sample Backtest

**File:** `scripts/qmmp/vbt_oos_backtest.py`  
**What to build:** `OOSBacktest` class. Takes Optuna best params and runs a clean final backtest on the held-out fold.

**The class must provide:**
```python
class OOSBacktest:
    def run(
        self,
        symbol: str,
        session: str,
        timeframe: str,
        strategy: str,
        best_params: dict,
    ) -> dict:
        """
        Returns:
        {
          "status": "oos_passed" | "oos_failed",
          "failure_reason": str | None,
          "metrics": {
            "total_trades": int,
            "win_rate_pct": float,
            "profit_factor": float,
            "sharpe": float,
            "expectancy": float,
            "max_drawdown_pct": float,
            "calmar_ratio": float,
            "sortino_ratio": float,
          },
          "equity_curve": [float, ...],   # pf.value().tolist() for charting
          "trades_parquet": str,           # path to saved trades parquet
          "summary_json": str,             # path to saved summary json
        }
        """
```

**Getting trades and equity curve:**
```python
pf = vbt.Portfolio.from_signals(...)
stats         = pf.stats()
trades_df     = pf.trades.records_readable   # individual trade records
equity_curve  = pf.value().tolist()           # equity curve for dashboard chart
```

**Save results:**
```
data/qmmp/{SYMBOL}/oos/{session}_{tf}_{strategy}.parquet
data/qmmp/{SYMBOL}/oos/{session}_{tf}_{strategy}_summary.json
```

**Pass/fail gate:**
- `oos_passed`: Sharpe > 0 AND total_trades >= 10 AND profit_factor >= 1.0
- `oos_failed`: anything else — set `failure_reason` to a human-readable string (e.g. "only 4 trades in held-out period")

---

### Sub-Task 5 — Backend API

**File:** `dashboard/api_symbols.py` (extend, do not replace)  
**What to add:** New Flask routes for the pipeline stages. The existing `/onboard`, `/refresh`, `/remove`, `/tasks` routes stay as-is.

**New routes to add:**

```python
# Stage 1 — trigger discovery
POST   /api/symbols/<sym>/discover
       Body: { "timeframes": ["M15","H1"], "sessions": ["asian","london"] }
       Returns: { "task_id": "...", "status": "queued" }

# Stage 1 — get discovery results
GET    /api/symbols/<sym>/discovery
       Returns: { shortlist per session per timeframe }

# Stage 2 — trigger Optuna sweep on selected candidates
POST   /api/symbols/<sym>/optimise
       Body: { "candidates": [{ "session": "asian", "timeframe": "M15", "rank": 1 }, ...] }
       Returns: { "task_id": "...", "status": "queued" }

# Stage 2 — get Optuna results
GET    /api/symbols/<sym>/optimise
       Returns: { per-candidate status, best_params, metrics }

# Stage 3 — trigger OOS backtest on Optuna-passed candidates
POST   /api/symbols/<sym>/backtest
       Body: { "candidates": [...] }
       Returns: { "task_id": "...", "status": "queued" }

# Stage 3 — get OOS results
GET    /api/symbols/<sym>/backtest
       Returns: { per-candidate OOS metrics, equity curve, status }

# Stage 4 — deploy selected sessions to live bot + EA
POST   /api/symbols/<sym>/deploy
       Body: { "enabled_sessions": ["asian", "london_ny_overlap"] }
       Returns: { "deployed": true, "ea_path": "...", "params_updated": true }
```

**Task progress schema** (extend existing `_tasks` dict):
```python
{
    "task_id": "uuid",
    "symbol": "BTCUSD",
    "stage": "discovery" | "optimise" | "backtest" | "deploy",
    "status": "queued" | "running" | "completed" | "failed",
    "progress": 0–100,
    "current_item": "asian M15 RSI(14)",   # what is being tested right now
    "items_total": 84,                      # total combinations
    "items_done": 37,
    "message": "Testing asian session, M15, RSI window=14",
    "started_at": "ISO timestamp",
    "completed_at": "ISO timestamp | null",
}
```

---

### Sub-Task 6 — Frontend

**File:** `dashboard-frontend/src/pages/SymbolOnboarding.tsx` (full rewrite)

**4-stage tabbed UI:**

```
[Discovery] → [Optuna] → [Backtest] → [Deploy]
```

Each stage tab is disabled until the previous stage has results. The current "Manage Symbols" and "Onboarding Tasks" tabs stay.

**Discovery tab:**
- Timeframe multi-select checkboxes: M1, M5, M15, M30, H1, H4, D1
- Session multi-select checkboxes: all 12 sessions (with descriptions)
- "Run Discovery" button → POST `/api/symbols/<sym>/discover`
- Progress bar (polling `/api/tasks/<id>` every 3s)
- Results table: one row per session×timeframe×strategy, sortable by Sharpe/PF/WR
- Each row has a checkbox to select for Optuna

**Optuna tab:**
- Shows the selected candidates from Discovery
- "Run Optuna" button → POST `/api/symbols/<sym>/optimise`
- Per-candidate status badge: `running` / `completed` / `failed_validation`
- Trial count + best Sharpe so far (polls every 5s while running)
- `failed_validation` candidates shown with reason — not hidden

**Backtest tab:**
- Shows Optuna-passed candidates
- "Run Backtest" button → POST `/api/symbols/<sym>/backtest`
- Per-candidate results: metrics table + mini equity curve (SVG line chart)
- Status badge: `oos_passed` / `oos_failed` + reason
- "Export" button → downloads JSON + CSV for all results

**Deploy tab:**
- Session grid: one row per OOS-passed session
- PF / Sharpe / WR shown per session
- Toggle checkbox: enable/disable this session for live trading
- "Deploy to Bot" button → POST `/api/symbols/<sym>/deploy`
- "Generate EA" checkbox option alongside deploy

**New TypeScript types needed in `types.ts`:**
```typescript
interface DiscoveryCandidate { session, timeframe, indicator, params, rank, total_trades, win_rate_pct, profit_factor, sharpe, expectancy, max_drawdown_pct }
interface OptunaResult { candidate: DiscoveryCandidate, status: 'running'|'completed'|'failed_validation', trial_count, best_sharpe, best_params, failure_reason? }
interface OOSResult { candidate: DiscoveryCandidate, optuna: OptunaResult, status: 'oos_passed'|'oos_failed', metrics: {...}, equity_curve: number[], failure_reason? }
interface PipelineTask extends OnboardingTask { stage: 'discovery'|'optimise'|'backtest'|'deploy', current_item: string, items_total: number, items_done: number }
```

---

## Step 6 — Testing Checklist

Before marking any sub-task complete, verify these:

### Sub-Task 1 (Sessions)
- [ ] `SessionRegistry.all_sessions()` returns exactly 12 keys
- [ ] `SessionRegistry.filter_mask(ohlcv, "asian")` returns True only for Mon–Fri 00:00–08:00 UTC
- [ ] `SessionRegistry.filter_mask(ohlcv, "btcusd_weekend")` returns True for Fri 22:00 → Sun 21:00 UTC
- [ ] `SessionRegistry.filter_mask(ohlcv, "weekly_close_mon")` returns True only for Mondays 22:00–23:00 UTC
- [ ] Existing `session_of(hour)` still works and returns "Asian"/"London"/"NewYork"/"Off"

### Sub-Task 2 (Discovery)
- [ ] `VbtDiscovery.run()` does not contain a single `for i in range(len(bars)):` trade loop
- [ ] Every backtest uses `vbt.Portfolio.from_signals()`
- [ ] `pf.stats()["Total Trades"]` is used for the min_trades gate (not a manual trade count)
- [ ] Results JSON is saved to `data/qmmp/{SYMBOL}/discovery/`
- [ ] Progress callback is called throughout (not just at start and end)

### Sub-Task 3 (Optuna)
- [ ] `study = optuna.create_study(..., load_if_exists=True)` — study is resumable
- [ ] Optuna objective calls `vbt.Portfolio.from_signals()` — not a loop
- [ ] Last fold is never passed to `study.optimize()`
- [ ] `failed_validation` results are saved to JSON with `failure_reason`
- [ ] `study.trials_dataframe()` exported as CSV

### Sub-Task 4 (OOS)
- [ ] `pf.trades.records_readable` saved as Parquet
- [ ] `pf.value().tolist()` included in summary JSON as `equity_curve`
- [ ] `oos_failed` results saved with `failure_reason` (not silently dropped)

### Sub-Task 5 (API)
- [ ] All 4 new POST routes exist and return task IDs
- [ ] All 4 new GET routes return results from the JSON files saved by the pipeline scripts
- [ ] Task dict includes `stage`, `current_item`, `items_total`, `items_done`
- [ ] Deploy route calls `param_optimizer.apply_tuned()` and `ea_generator.generate()`

### Sub-Task 6 (Frontend)
- [ ] Discovery tab: timeframe + session multi-select works
- [ ] Optuna tab: `failed_validation` candidates are visible with reason
- [ ] Backtest tab: equity curve is rendered
- [ ] Deploy tab: session toggles write to backend

---

## Step 7 — Data Directory Layout

After all sub-tasks are complete, `data/qmmp/{SYMBOL}/` will look like this:

```
data/qmmp/BTCUSD/
├── discovery/
│   ├── asian_M15.json
│   ├── asian_H1.json
│   ├── london_M15.json
│   └── ...  (one file per session × timeframe)
├── optuna/
│   ├── study.db                            (Optuna SQLite — all studies for this symbol)
│   └── trials/
│       ├── asian_M15_RSI.json              (best trial per candidate)
│       ├── asian_M15_RSI_all_trials.csv    (all Optuna trials)
│       └── ...
├── oos/
│   ├── asian_M15_RSI.parquet               (individual trade records)
│   ├── asian_M15_RSI_summary.json          (stats + equity curve)
│   └── ...
├── model.json                              (promoted floors — used by live bot)
├── session_preferences.json               (which sessions are enabled for trading)
└── GoldShark_BTCUSD_session.mq5           (generated EA)
```

---

## Step 8 — Files Not To Touch

These files are used by the live trading engine. Do not modify them as part of this work:

| File | Reason |
|---|---|
| `src/trading/scalp_engine.py` | Live trading loop |
| `src/mt5/broker_adapter.py` | MT5 order execution |
| `src/strategies/osma_confluence.py` | Live strategy |
| `dashboard/app.py` | Existing live dashboard routes |
| `src/learning/experience_db.py` | Trade outcome recording |
| `data/chromadb_store/xauusd_market_patterns` | Existing pattern RAG |

---

## Quick Reference — Key API Signatures

### `vbt.Portfolio.from_signals()` (the only way to run a backtest)
```python
pf = vbt.Portfolio.from_signals(
    close=close_series,          # pd.Series — price series
    entries=long_entries,        # boolean pd.Series — where to go long
    exits=long_exits,            # boolean pd.Series — where to exit long
    short_entries=short_entries, # boolean pd.Series — where to go short
    short_exits=short_exits,     # boolean pd.Series — where to exit short
    sl_stop=0.02,                # stop loss as fraction (0.02 = 2%)
    sl_trail=True,               # trailing stop
    tp_stop=0.04,                # take profit as fraction
    fees=spread_frac,            # spread as fraction of price
    slippage=slip_frac,          # slippage as fraction
    init_cash=5000,              # starting cash
    freq="1H",                   # required for duration metrics
)
stats = pf.stats()               # dict of all performance metrics
trades = pf.trades.records_readable  # DataFrame of individual trades
equity = pf.value()              # pd.Series equity curve
```

### `optuna.create_study()` (always resumable)
```python
study = optuna.create_study(
    study_name=f"qmmp_{symbol}_{session}_{strategy}",
    storage=f"sqlite:///data/qmmp/{symbol}/optuna/study.db",
    sampler=optuna.samplers.TPESampler(seed=42),
    pruner=optuna.pruners.MedianPruner(n_warmup_steps=10),
    direction="maximize",
    load_if_exists=True,
)
study.optimize(objective, n_trials=100, n_jobs=1)
best_params = study.best_params
all_trials  = study.trials_dataframe()
```

### `trial.suggest_*()` (inside objective function)
```python
def objective(trial):
    window    = trial.suggest_int("window", 5, 50)
    threshold = trial.suggest_float("threshold", 0.5, 3.0, step=0.25)
    method    = trial.suggest_categorical("method", ["rsi", "bb", "macd"])
    ...
    return sharpe_score  # float to maximise
```

### `DocsRAG.query()` (check the API before writing it)
```python
from src.learning.docs_rag import DocsRAG
rag = DocsRAG()
results = rag.query("Portfolio.from_signals fees slippage", collection="vectorbt_docs", n=3)
for r in results:
    print(r["text"][:400])
```
