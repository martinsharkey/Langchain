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
from src.utils.logger import get_logger

logger = get_logger("optuna_floor_optimizer")

D = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "qmmp")
FAST, SLOW, SIG = 12, 26, 9
SESSIONS = ("Asian", "London", "NewYork")


def _resolve_symbol(symbol):
    try:
        from scripts.qmmp.onboard_pipeline import _resolve_symbol as _rs
        return _rs(symbol)
    except Exception:
        return symbol


def pt_value(symbol):
    try:
        from scripts.qmmp.onboard_pipeline import pt_value as _pv
        return _pv(symbol)
    except Exception:
        return 0.01, 0.00007


def _adaptive_slip_pts(symbol):
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            info = mt5.symbol_info(symbol)
            if info:
                pt = getattr(info, "point", 0.01) or 0.01
                if pt <= 0.0001:
                    slip = 2.0
                elif pt <= 0.01:
                    slip = 20.0
                else:
                    slip = 100.0
            else:
                slip = 100.0
            mt5.shutdown()
            return slip
    except Exception:
        pass
    return 100.0


def _load_data(symbol: str, tf: str = "H1") -> pd.DataFrame:
    """Load parquet data for a symbol/timeframe."""
    resolved = _resolve_symbol(symbol)
    base = resolved.upper().split("-")[0].rstrip(".")
    d = os.path.join(D, base)
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

    # session labels (match live EA CurSession() exactly)
    from src.strategies.sessions import session_of

    sessions = pd.Series(df.index.hour).apply(session_of)
    sessions.index = df.index

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


def _backtest_floors(df: pd.DataFrame, ind: dict, floors: dict, pt: float = 0.01,
                     spread_pts: float = 200.0, slip_pts: float = 100.0) -> dict[str, float]:
    """Run vectorbt backtest with given floors and return key metrics."""
    signals = _apply_floors(df, ind, floors)
    close = ind["close"]

    med_price = float(close.median())
    sl_pts = floors.get("sl_pts", 628348)
    trail_pts = floors.get("trail_pts", 11057)
    tsl = max(0.002, (trail_pts * pt) / med_price)
    slf = max(0.01, (sl_pts * pt) / med_price)
    spread_frac = (spread_pts * pt) / med_price

    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=signals["entry_long"], exits=signals["exit_long"],
        short_entries=signals["entry_short"], short_exits=signals["short_exits"],
        sl_stop=tsl, sl_trail=True,
        fees=spread_frac,
        slippage=(slip_pts * pt) / med_price,
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


def objective(trial: optuna.Trial, df: pd.DataFrame, ind: dict, folds: int = 3,
              pt: float = 0.01, spread_pts: float = 200.0, slip_pts: float = 100.0) -> float:
    """Optuna objective: propose floor values, backtest, return walk-forward Sharpe.

    Uses only the first (folds-1) folds for optimization; the last fold is reserved
    as a genuine held-out set that Optuna never sees.
    """
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

    # Walk-forward evaluation on first (folds-1) folds only; last fold is held out
    n = len(df)
    fold_size = n // folds
    sharpes = []
    for i in range(folds - 1):
        te = df.iloc[(i + 1) * fold_size : (i + 2) * fold_size]
        if len(te) < 50:
            continue
        te_ind = {k: v.loc[te.index] for k, v in ind.items()}
        try:
            metrics = _backtest_floors(te, te_ind, floors, pt=pt, spread_pts=spread_pts, slip_pts=slip_pts)
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
        folds: Walk-forward folds (last fold is held out, never seen by Optuna).
        study_name: Optuna study name (default: `floors_<symbol>`).
        storage: Optuna storage URI (default: SQLite in symbol's optuna folder).

    Returns:
        Best trial params + metrics, including held-out evaluation.
    """
    resolved = _resolve_symbol(symbol)
    base = resolved.upper().split("-")[0].rstrip(".")
    df = _load_data(symbol, tf)
    ind = _compute_indicators(df)

    pt, gbp_pt = pt_value(symbol)
    spread_pts = 0.0
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            info = mt5.symbol_info(resolved)
            if info and info.spread > 0:
                spread_pts = float(info.spread)
            mt5.shutdown()
    except Exception:
        pass
    if spread_pts <= 0:
        spread_pts = 200.0

    slip_pts = _adaptive_slip_pts(resolved)

    if study_name is None:
        study_name = f"floors_{base}"
    if storage is None:
        optuna_dir = os.path.join(D, base, "optuna")
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
        return objective(trial, df, ind, folds, pt=pt, spread_pts=spread_pts, slip_pts=slip_pts)

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

    n_len = len(df)
    fold_size = n_len // folds
    # Optimization metrics = walk-forward on first (folds-1) folds
    opt_slice = df.iloc[: (folds - 1) * fold_size]
    opt_ind = {k: v.loc[opt_slice.index] for k, v in ind.items()}
    opt_metrics = _backtest_floors(opt_slice, opt_ind, floors, pt=pt, spread_pts=spread_pts, slip_pts=slip_pts)

    # Held-out metrics = last fold, genuinely unseen during optimization
    held_out_start = (folds - 1) * fold_size
    held_out = df.iloc[held_out_start:]
    held_out_ind = {k: v.loc[held_out.index] for k, v in ind.items()}
    held_out_metrics = _backtest_floors(held_out, held_out_ind, floors, pt=pt, spread_pts=spread_pts, slip_pts=slip_pts)

    result = {
        "symbol": base,
        "timeframe": tf,
        "study_name": study_name,
        "n_trials": len(study.trials),
        "best_value": best.value,
        "best_params": best_floors,
        "floors": floors,
        "optimization_metrics": opt_metrics,
        "held_out_metrics": held_out_metrics,
        "final_metrics": held_out_metrics,  # held-out is the true final metric
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Save trial result
    trials_dir = os.path.join(D, base, "optuna", "trials")
    os.makedirs(trials_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    trial_path = os.path.join(trials_dir, f"best_floors_{ts}.json")
    with open(trial_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    _try_promote(base, trial_path)

    return result


def _latest_trial_path(symbol: str) -> str | None:
    base = _resolve_symbol(symbol).upper().split("-")[0].rstrip(".")
    trials_dir = os.path.join(D, base, "optuna", "trials")
    if not os.path.isdir(trials_dir):
        return None
    candidates = sorted(
        [f for f in os.listdir(trials_dir) if f.startswith("best_floors_") and f.endswith(".json")],
        reverse=True,
    )
    if not candidates:
        return None
    return os.path.join(trials_dir, candidates[0])


def _try_promote(symbol: str, trial_path: str) -> dict:
    """Promote Optuna best_floors into model.json + tuned_params.json when held-out
    metrics beat the current baseline. Never overwrites a worse result."""
    try:
        with open(trial_path, encoding="utf-8") as f:
            result = json.load(f)
    except Exception:
        return {"promoted": False, "reason": "cannot_read_trial"}

    base = _resolve_symbol(symbol).upper().split("-")[0].rstrip(".")
    model_path = os.path.join(D, base, "model.json")
    current_model = {}
    if os.path.exists(model_path):
        try:
            with open(model_path, encoding="utf-8") as f:
                current_model = json.load(f)
        except Exception:
            current_model = {}

    held = result.get("held_out_metrics", {})
    cur_held = current_model.get("validation", {}).get("held_out_metrics", {})
    cur_wr = float(cur_held.get("win_rate", 0) or 0)
    cur_trades = int(cur_held.get("total_trades", 0) or 0)
    new_wr = float(held.get("win_rate", 0) or 0)
    new_trades = int(held.get("total_trades", 0) or 0)

    if new_trades < 10 or (cur_trades >= 10 and new_wr <= cur_wr):
        return {"promoted": False, "reason": f"held-out WR {new_wr:.1f}% (n={new_trades}) does not beat baseline {cur_wr:.1f}% (n={cur_trades})"}

    new_floors = result.get("floors", {})
    if not new_floors:
        return {"promoted": False, "reason": "no_floors_in_trial"}

    merged = dict(current_model)
    merged["floors"] = new_floors
    merged["floors_detail"] = {
        k: {"value": v, "helps": 1, "folds": 1, "summary": "promoted from Optuna"}
        for k, v in new_floors.items()
    }
    merged["build"] = int(merged.get("build", 0) or 0) + 1
    merged.setdefault("validation", {})
    merged["validation"]["held_out_metrics"] = held
    merged["validation"]["promoted_at"] = datetime.now(timezone.utc).isoformat()
    merged["validation"]["promoted_from"] = os.path.basename(trial_path)

    try:
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        tmp = model_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2)
        os.replace(tmp, model_path)
    except Exception as e:
        return {"promoted": False, "reason": f"model_write_failed: {e}"}

    _promote_to_tuned_params(base, new_floors)

    return {"promoted": True, "build": merged["build"], "win_rate": new_wr, "trades": new_trades}


def _promote_to_tuned_params(symbol: str, floors: dict) -> None:
    """Flatten per-session Optuna floors into the tuned_params.json schema
    (session_Asian / session_London / session_NewYork overrides)."""
    try:
        from src.learning.param_optimizer import ParameterOptimizer, TUNED_PATH
        opt = ParameterOptimizer(registry=None, backtest_fn=lambda *a, **k: None)
        key = opt._key(symbol)
        entry = opt.tuned.get(key, {})
        params = dict(entry.get("params", {}))
        for fk, fv in floors.items():
            if isinstance(fv, dict):
                for sess, val in fv.items():
                    sess_key = f"session_{sess}"
                    if sess_key not in params:
                        params[sess_key] = {}
                    params[sess_key][fk] = val
            elif isinstance(fv, (int, float)) and fv != 0:
                params[fk] = fv
        entry["params"] = params
        opt.tuned[key] = entry
        opt._persist()
    except Exception as e:
        logger.warning(f"Optuna promote to tuned_params failed: {e}")
