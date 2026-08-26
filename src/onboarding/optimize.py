"""Phase 2: Optuna per-indicator parameter tuning of the top-N candidates.

Uses VectorBT's native indicator classes: each wrapped indicator exposes
``param_names``, so Optuna suggests values for the indicator's own parameters
and we re-run it with those values, then backtest and score.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.onboarding.backtest import run_backtest
from src.onboarding.data import load_ohlcv
from src.onboarding.indicators import run_indicator, wrap
from src.onboarding.metrics import ScoredResult, composite_score
from src.onboarding.sessions import load_session_ohlcv
from src.onboarding.signals import generate_signals
from src.onboarding.timeframes import timeframe_minutes

logger = logging.getLogger(__name__)


def _suggest_params(trial, param_names) -> Dict:
    """Suggest values for an indicator's parameters based on their names.

    VectorBT exposes ``param_names`` on each wrapped indicator class. We map
    common parameter names to sensible integer/float ranges; unknown parameters
    default to an integer in [5, 40].
    """
    params: Dict = {}
    for p in param_names:
        pl = p.lower()
        if pl in ("length", "window", "timeperiod", "period", "n", "lookback"):
            params[p] = trial.suggest_int(p, 5, 60)
        elif pl in ("fast", "fastperiod", "fast_length"):
            params[p] = trial.suggest_int(p, 5, 20)
        elif pl in ("slow", "slowperiod", "slow_length"):
            params[p] = trial.suggest_int(p, 20, 40)
        elif pl in ("signal", "signalperiod"):
            params[p] = trial.suggest_int(p, 5, 15)
        elif pl in ("multiplier", "mult", "scalar", "alpha", "af", "af0"):
            params[p] = trial.suggest_float(p, 0.01, 5.0)
        elif pl in ("k", "d", "smooth"):
            params[p] = trial.suggest_int(p, 2, 20)
        elif pl in ("lower", "low"):
            params[p] = trial.suggest_float(p, 0.0, 50.0)
        elif pl in ("upper", "high"):
            params[p] = trial.suggest_float(p, 50.0, 100.0)
        else:
            params[p] = trial.suggest_int(p, 5, 40)
    return params


class Optimizer:
    """Optuna-based per-indicator parameter tuning."""

    def __init__(self, symbol: str, init_cash: float = 10_000.0, n_trials: int = 50):
        self.symbol = symbol
        self.init_cash = init_cash
        self.n_trials = n_trials

    def optimize(
        self,
        candidates: List[ScoredResult],
        studies_dir: Path,
    ) -> List[Dict]:
        """Tune each candidate's parameters, returning tuned results."""
        import optuna

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        tuned: List[Dict] = []
        for cand in candidates:
            # Skip combination candidates (no single indicator to tune).
            if cand.library == "combo":
                tuned.append(self._combo_entry(cand))
                continue

            # Skip combination candidates (cannot be tuned as single indicators).
            if cand.library == "combo":
                tuned.append(self._baseline_entry(cand))
                continue

            ind = wrap(cand.indicator, cand.library)
            ohlcv = self._load_session_data(cand)
            if ohlcv is None or "close" not in ohlcv or ohlcv["close"].shape[1] == 0:
                continue

            param_names = list(getattr(ind.cls, "param_names", ()) or ())
            if not param_names:
                # No tunable parameters; keep baseline.
                tuned.append(self._baseline_entry(cand))
                continue

            study_name = f"{cand.library}_{cand.indicator}_{cand.timeframe}_{cand.session}"
            db_path = studies_dir / f"{study_name}.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            storage = optuna.storages.RDBStorage(f"sqlite:///{db_path}")

            study = optuna.create_study(
                study_name=study_name,
                storage=storage,
                direction="maximize",
                load_if_exists=True,
            )

            def objective(trial, _ind=ind, _ohlcv=ohlcv, _cand=cand, _param_names=param_names):
                params = _suggest_params(trial, _param_names)
                try:
                    # Native VectorBT run per session occurrence.
                    close_cols = _ohlcv["close"]
                    n_cols = close_cols.shape[1]
                    all_trades: List[int] = []
                    all_win_rates: List[float] = []
                    all_pf: List[float] = []
                    all_returns: List[float] = []

                    for col_idx in range(n_cols):
                        col_data = {k: v.iloc[:, col_idx].dropna() for k, v in _ohlcv.items()}
                        if len(col_data.get("close", [])) < 50:
                            continue
                        inputs = {k: col_data[k] for k in _ind.cls.input_names if k in col_data}
                        run = _ind.cls.run(**inputs, **params)
                        entries, exits = generate_signals(run, _ind.library, _ind.name)
                        if entries.sum() < 2:
                            continue
                        import vectorbt as vbt
                        pf = vbt.Portfolio.from_signals(
                            col_data["close"], entries, exits,
                            init_cash=self.init_cash,
                            freq=f"{timeframe_minutes(_cand.timeframe)}min",
                        )
                        if pf.trades.count() < 1:
                            continue
                        all_trades.append(int(pf.trades.count()))
                        all_win_rates.append(float(pf.trades.win_rate() or 0.0))
                        pf_val = pf.trades.profit_factor()
                        all_pf.append(float(pf_val) if np.isfinite(pf_val) else 0.0)
                        all_returns.append(float(pf.total_return() or 0.0))

                    if not all_trades:
                        return 0.0
                    # Score using aggregated native stats.
                    import numpy as np
                    result_trades = int(np.sum(all_trades))
                    result_win_rate = float(np.mean(all_win_rates))
                    result_pf = float(np.mean(all_pf))
                    result_return = float(np.mean(all_returns))
                    # Composite score components.
                    score = result_pf * 0.35 + (1 + min(0, result_return)) * 0.30 + result_win_rate * 0.15
                    return max(0.0, score)
                except Exception:  # noqa: BLE001
                    return 0.0

            study.optimize(objective, n_trials=self.n_trials, show_progress_bar=False)

            best = study.best_trial
            tuned.append(
                {
                    "indicator": cand.indicator,
                    "library": cand.library,
                    "category": cand.category,
                    "session": cand.session,
                    "timeframe": cand.timeframe,
                    "combination": cand.combination,
                    "baseline_score": cand.score,
                    "best_score": float(best.value),
                    "best_params": dict(best.params),
                    "study_db": str(db_path),
                }
            )

        return tuned

    def _baseline_entry(self, cand: ScoredResult) -> Dict:
        return {
            "indicator": cand.indicator,
            "library": cand.library,
            "category": cand.category,
            "session": cand.session,
            "timeframe": cand.timeframe,
            "combination": cand.combination,
            "baseline_score": cand.score,
            "best_score": cand.score,
            "best_params": {},
            "study_db": None,
        }

    def _combo_entry(self, cand: ScoredResult) -> Dict:
        return {
            "indicator": cand.indicator,
            "library": cand.library,
            "category": cand.category,
            "session": cand.session,
            "timeframe": cand.timeframe,
            "combination": cand.combination,
            "baseline_score": cand.score,
            "best_score": cand.score,
            "best_params": {},
            "study_db": None,
        }

    def _load_session_data(self, cand: ScoredResult) -> Optional[dict]:
        return load_session_ohlcv(self.symbol, cand.timeframe, cand.session, count=5000)


__all__ = ["Optimizer"]
