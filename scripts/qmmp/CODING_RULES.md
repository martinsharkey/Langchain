# QMMP Pipeline — Coding Rules

These rules apply to **all** code in `scripts/qmmp/` and any file that imports `vectorbt` or `optuna`.

---

## Rule 1 — Read the docs before writing code

Before writing any vectorbt or optuna code, query the local RAG to confirm the correct API.

```bash
# From the project root, with the venv active:
python -m scripts.qmmp.rag_guard "Portfolio.from_signals stop loss trailing"
python -m scripts.qmmp.rag_guard "Optuna TPE sampler suggest_float" --collection optuna_docs
python -m scripts.qmmp.rag_guard "IndicatorFactory from_apply_func param sweep" --collection vectorbt_docs
```

Paste the top result into your PR description as evidence you checked the real API.

---

## Rule 2 — No custom backtest loops

**Never** write a manual `for i in range(len(bars)):` trade loop.

Use `vbt.Portfolio.from_signals()` instead. It is vectorised, handles SL/TP/trail natively,
returns a `stats()` dict with all the metrics you need, and runs 100–1000× faster.

✅ Correct:
```python
pf = vbt.Portfolio.from_signals(
    close=close,
    entries=long_entries,
    exits=long_exits,
    short_entries=short_entries,
    short_exits=short_exits,
    sl_stop=0.02,          # 2% stop loss
    sl_trail=True,         # trailing stop
    tp_stop=0.04,          # 4% take profit
    fees=spread_frac,      # spread as fraction of price
    slippage=slip_frac,
    init_cash=5000,
    freq="1H",
)
stats = pf.stats()
# stats["Total Trades"], stats["Win Rate [%]"], stats["Profit Factor"],
# stats["Sharpe Ratio"], stats["Expectancy"], stats["Max Drawdown [%]"]
```

❌ Wrong:
```python
for i in range(1, len(close)):   # DO NOT DO THIS
    if entries[i]:
        ...
```

---

## Rule 3 — No custom indicator loops

**Never** reimplement RSI, Bollinger Bands, MACD, ATR, etc. from scratch.

Use `vbt.IndicatorFactory` to wrap an existing function from `ta`, `pandas_ta`, or
the project's own `src/strategies/indicators.py`.

✅ Correct:
```python
import vectorbt as vbt

MyRSI = vbt.IndicatorFactory(
    input_names=["close"],
    param_names=["window"],
    output_names=["rsi"],
).from_apply_func(rsi_numba_func, window=14)

# Sweep multiple values in one call — no loop:
rsi = MyRSI.run(close, window=[7, 14, 21, 28])
```

---

## Rule 4 — No hardcoded parameter ranges

Search bounds for Optuna must come from `_data_bounds()` (see `optuna_floor_optimizer.py`)
which derives ranges from the actual indicator distribution of the data being tested.
This prevents optimising a BTCUSD range on XAUUSD by accident.

---

## Rule 5 — Optuna studies must be resumable

Always pass `load_if_exists=True` and a `storage=` SQLite path to `create_study()`.
Never run a study that cannot be resumed after a crash.

✅ Correct:
```python
study = optuna.create_study(
    study_name=f"qmmp_{symbol}_{session}_{strategy}",
    storage=f"sqlite:///data/qmmp/{symbol}/optuna/study.db",
    sampler=TPESampler(seed=42),
    pruner=MedianPruner(n_warmup_steps=10),
    direction="maximize",
    load_if_exists=True,        # ← required
)
```

---

## Rule 6 — Keep failed candidates in the dashboard

A strategy that fails Optuna validation or OOS backtest must **not** be silently discarded.
Set its status to `failed_validation` or `oos_failed` with a `failure_reason` string.
This gives the operator visibility into what was tried and why it was rejected.

---

## Rule 7 — Walk-forward: Optuna never sees the held-out fold

When running walk-forward validation:
- Split data into N folds using `RollingSplitter` or `RangeSplitter`
- Optuna objective evaluates on folds `0..N-2` only
- Fold `N-1` (the last fold) is the held-out set — never passed to `study.optimize()`
- Final metrics reported to the dashboard come from the held-out fold only

---

## Source documentation

All library docs are in `docs/lib_docs/` (tracked in git):
- `docs/lib_docs/vectorbt/` — Portfolio, IndicatorFactory, splitters, records
- `docs/lib_docs/optuna/`   — create_study, Trial API, samplers, pruners, RDB storage
- `docs/lib_docs/ta_libs/`  — ta, pandas-ta, ta-lib indicator references

To rebuild the ChromaDB RAG from these docs (run once after cloning):
```bash
python -c "from src.learning.docs_rag import DocsRAG; counts = DocsRAG.build_collections(); print(counts)"
```
