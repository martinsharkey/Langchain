"""Optuna-backed floor optimization for QMMP (HLD C, Option 1).

Replaces the fixed-heuristic `_validate_floor()` in `onboard_pipeline.py` with a
search over floor parameter space. Objective = walk-forward expectancy/Sharpe from
vectorbt backtest on historical data.

Folder layout (per symbol):
  data/qmmp/<SYMBOL>/optuna/
    study.db                    # Optuna SQLite storage (resumable, untracked)
    trials/
      best_floors_<YYYYMMDD_HHMM>.json   # winning trial, tracked
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

import numpy as np
import optuna
import pandas as pd
import vectorbt as vbt
from optuna.samplers import TPESampler

from src.strategies.indicators import osma as osma_fn, bulls_power as bp, bears_power as bpw, atr as atr_fn, ema as ema_fn

D = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "qmmp")
SPREAD_PTS = 1200.0; PT = 0.01
GBP_PER_PT_PER_LOT = 0.007
COMM_PER_LOT = 6.0
FAST, SLOW, SIG = 12, 26, 9
SESSIONS = ("Asian", "London", "NewYork")


def _load_data(symbol: str, tf: str = "H1") -> pd.DataFrame:
    """Load parquet data for a symbol/timeframe."""
    d = os.path.join(D, symbol.upper())
    path = os.path.join(d, f"{tf}.parquet")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No data file: {path}")
    import polars as pl
    df = pl.read_parquet(path).sort("time").to_pandas()
    df = df.set_index("time")
    return df


def _compute_indicators(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Compute all indicators needed for floor evaluation."""
    close = df["close"]
    osma = osma_fn(close, FAST, SLOW, SIG)
    bulls = bp(df, 13)
    bears = bpw(df, 13)
    atr = atr_fn(df, 14)
    ema = ema_fn(close, 13)
    return {"close": close, "osma": osma, "bulls": bulls, "bears": bears, "atr": atr, "ema": ema}


def _apply_floors(df: pd.DataFrame, ind: dict, floors: dict) -> pd.DataFrame:
    """Apply session-aware floors to produce entry signals.

    Returns DataFrame with 'entry_long', 'entry_short', 'exit_long', 'exit_short' columns.
    """
    close = ind["close"]; osma = ind["osma"]; bulls = ind["bulls"]; bears = ind["bears"]
    atr = ind["atr"]; ema = ind["ema"]

    # session labels (UTC hours)
    sessions = pd.Series(index=df.index, data="Off")
    for h, s in [(0, "Asian"), (7, "London"), (12, "NewYork")]:
        sessions[df.index.hour >= h] = s

    # OsMA zero-cross entries
    up = (osma.shift(1) <= 0) & (osma > 0)
    dn = (osma.shift(1) >= 0) & (osma < 0)

    # Floor gates
    osma_f = floors.get("osma_mag", {})
    ema_f = floors.get("ema_align", {})
    bulls_f = floors.get("bulls", {})
    bears_f = floors.get("bears", {})
    atr_f = floors.get("atr", {})

    entry_long = up.copy()
    entry_short = dn.copy()

    for sn in SESSIONS:
        mask = sessions == sn
        if not mask.any():
            continue

        # OsMA magnitude
        osma_thr = osma_f.get(sn, 0) if isinstance(osma_f, dict) else 0
        if osma_thr and osma_thr > 0:
            osma_mag = osma.abs()
            entry_long &= ~(mask & (osma_mag < osma_thr))
            entry_short &= ~(mask & (osma_mag < osma_thr))

        # EMA alignment
        ema_thr = ema_f.get(sn, 0) if isinstance(ema_f, dict) else 0
        if ema_thr and ema_thr > 0:
            ema_slope = ema - ema.shift(3)
            ema_align = ema_slope
            entry_long &= ~(mask & (ema_align < ema_thr))
            entry_short &= ~(mask & (ema_align > -ema_thr))

        # Bulls/Bears floors
        if isinstance(bulls_f, dict) and bulls_f:
            bulls_long_thr = bulls_f.get(f"{sn}_long", 0)
            bears_long_thr = bears_f.get(f"{sn}_long", 0) if isinstance(bears_f, dict) else 0
            if bulls_long_thr and bulls_long_thr > 0:
                entry_long &= ~(mask & (bulls < bulls_long_thr))
            if bears_long_thr and bears_long_thr < 0:
                entry_long &= ~(mask & (bears > bears_long_thr))

        if isinstance(bears_f, dict) and bears_f:
            bears_short_thr = bears_f.get(f"{sn}_short", 0)
            bulls_short_thr = bulls_f.get(f"{sn}_short", 0) if isinstance(bulls_f, dict) else 0
            if bears_short_thr and bears_short_thr < 0:
                entry_short &= ~(mask & (bears > bears_short_thr))
            if bulls_short_thr and bulls_short_thr > 0:
                entry_short &= ~(mask & (bulls < bulls_short_thr))

        # ATR floor
        atr_thr = atr_f.get(sn, 0) if isinstance(atr_f, dict) else 0
        if atr_thr and atr_thr > 0:
            entry_long &= ~(mask & (atr < atr_thr))
            entry_short &= ~(mask & (atr < atr_thr))

    # Exits: opposite cross
    exits = dn
    short_exits = up

    return pd.DataFrame({
        "entry_long": entry_long,
        "entry_short": entry_short,
        "exit_long": exits,
        "exit_short": short_exits,
    }, index=df.index)


def _backtest_floors(df: pd.DataFrame, ind: dict, floors: dict) -> dict[str, float]:
    """Run vectorbt backtest with given floors and return key metrics."""
    signals = _apply_floors(df, ind, floors)
    close = ind["close"]

    med_price = float(close.median())
    sl_pts = floors.get("sl_pts", 628348)
    trail_pts = floors.get("trail_pts", 11057)
    tsl = max(0.002, (trail_pts * PT) / med_price)
    slf = max(0.01, (sl_pts * PT) / med_price)
    spread_frac = (SPREAD_PTS * PT) / med_price

    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=signals["entry_long"], exits=signals["exit_long"],
        short_entries=signals["entry_short"], short_exits=signals["exit_short"],
        sl_stop=tsl, sl_trail=True,
        fees=spread_frac,
        slippage=(100.0 * PT) / med_price,
        init_cash=5000, freq="1H",
    )
    stats = pf.stats()
    trades = pf.trades.records_readable

    expectancy = float(stats.get("Win Rate [%]", 0)) / 100.0 * float(stats.get("Total Trades", 0))
    sharpe = float(stats.get("Sharpe Ratio", 0))
    max_dd = float(stats.get("Max Drawdown [%]", 100))

    return {
        "expectancy": expectancy,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "total_trades": int(stats.get("Total Trades", 0)),
        "win_rate": float(stats.get("Win Rate [%]", 0)),
    }


def objective(trial: optuna.Trial, df: pd.DataFrame, ind: dict, folds: int = 3) -> float:
    """Optuna objective: propose floor values, backtest, return walk-forward Sharpe."""
    floors = {}

    # OsMA magnitude floors (per session)
    osma_floors = {}
    for sn in SESSIONS:
        osma_floors[sn] = trial.suggest_float(f"osma_{sn}", 0.0, 100.0, step=1.0)
    floors["osma_mag"] = osma_floors

    # EMA alignment floors
    ema_floors = {}
    for sn in SESSIONS:
        ema_floors[sn] = trial.suggest_float(f"ema_{sn}", 0.0, 200.0, step=1.0)
    floors["ema_align"] = ema_floors

    # Bulls/Bears floors (per session, per side)
    bulls_floors = {}
    bears_floors = {}
    for sn in SESSIONS:
        bulls_floors[f"{sn}_long"] = trial.suggest_float(f"bulls_{sn}_long", 0.0, 1000.0, step=5.0)
        bulls_floors[f"{sn}_short"] = trial.suggest_float(f"bulls_{sn}_short", -500.0, 0.0, step=5.0)
        bears_floors[f"{sn}_long"] = trial.suggest_float(f"bears_{sn}_long", -500.0, 0.0, step=5.0)
        bears_floors[f"{sn}_short"] = trial.suggest_float(f"bears_{sn}_short", 0.0, 1000.0, step=5.0)
    floors["bulls"] = bulls_floors
    floors["bears"] = bears_floors

    # ATR floors
    atr_floors = {}
    for sn in SESSIONS:
        atr_floors[sn] = trial.suggest_float(f"atr_{sn}", 0.0, 5000.0, step=25.0)
    floors["atr"] = atr_floors

    # Walk-forward evaluation
    n = len(df)
    fold_size = n // folds
    sharpes = []
    for i in range(folds - 1):
        te = df.iloc[(i + 1) * fold_size : (i + 2) * fold_size]
        if len(te) < 50:
            continue
        te_ind = {k: v.loc[te.index] for k, v in ind.items()}
        try:
            metrics = _backtest_floors(te, te_ind, floors)
            if metrics["total_trades"] >= 10 and metrics["max_dd"] < 50:
                sharpes.append(metrics["sharpe"])
        except Exception:
            continue

    if not sharpes:
        return -10.0  # penalize unusable floor sets

    return float(np.mean(sharpes))


def run_study(
    symbol: str,
    tf: str = "H1",
    n_trials: int = 100,
    folds: int = 3,
    study_name: str | None = None,
    storage: str | None = None,
) -> dict:
    """Run Optuna study for floor optimization on a symbol.

    Args:
        symbol: Symbol to optimize (e.g. "XAUUSD", "BTCUSD").
        tf: Timeframe to use (default H1).
        n_trials: Number of Optuna trials to run.
        folds: Walk-forward folds.
        study_name: Optuna study name (default: `floors_<symbol>`).
        storage: Optuna storage URI (default: SQLite in symbol's optuna folder).

    Returns:
        Best trial params + metrics.
    """
    df = _load_data(symbol, tf)
    ind = _compute_indicators(df)

    if study_name is None:
        study_name = f"floors_{symbol.upper()}"
    if storage is None:
        optuna_dir = os.path.join(D, symbol.upper(), "optuna")
        os.makedirs(optuna_dir, exist_ok=True)
        storage = f"sqlite:///{os.path.join(optuna_dir, 'study.db')}"

    sampler = TPESampler(seed=42)
    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        sampler=sampler,
        direction="maximize",
        load_if_exists=True,
    )

    def _obj(trial):
        return objective(trial, df, ind, folds)

    study.optimize(_obj, n_trials=n_trials, n_jobs=1)

    best = study.best_trial
    best_floors = best.params

    # Convert flat params back to nested floor dict
    floors = {
        "osma_mag": {sn: best_floors.get(f"osma_{sn}", 0.0) for sn in SESSIONS},
        "ema_align": {sn: best_floors.get(f"ema_{sn}", 0.0) for sn in SESSIONS},
        "bulls": {f"{sn}_long": best_floors.get(f"bulls_{sn}_long", 0.0) for sn in SESSIONS} |
                 {f"{sn}_short": best_floors.get(f"bulls_{sn}_short", 0.0) for sn in SESSIONS},
        "bears": {f"{sn}_long": best_floors.get(f"bears_{sn}_long", 0.0) for sn in SESSIONS} |
                 {f"{sn}_short": best_floors.get(f"bears_{sn}_short", 0.0) for sn in SESSIONS},
        "atr": {sn: best_floors.get(f"atr_{sn}", 0.0) for sn in SESSIONS},
    }

    # Run final backtest on full dataset with best floors
    final_metrics = _backtest_floors(df, ind, floors)

    result = {
        "symbol": symbol,
        "timeframe": tf,
        "study_name": study_name,
        "n_trials": len(study.trials),
        "best_value": best.value,
        "best_params": best_floors,
        "floors": floors,
        "final_metrics": final_metrics,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Save trial result
    trials_dir = os.path.join(D, symbol.upper(), "optuna", "trials")
    os.makedirs(trials_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    trial_path = os.path.join(trials_dir, f"best_floors_{ts}.json")
    with open(trial_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return result
