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
from src.onboarding.sessions import filter_session
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

            ind = wrap(cand.indicator, cand.library)
            df = self._load_session_data(cand)
            if df is None or len(df) < 100:
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

            def objective(trial, _ind=ind, _df=df, _cand=cand, _param_names=param_names):
                params = _suggest_params(trial, _param_names)
                try:
                    run = run_indicator(
                        _ind, _df["close"], _df["high"], _df["low"],
                        _df["open"], _df["volume"], **params,
                    )
                    entries, exits = generate_signals(run, _ind.library, _ind.name)
                    if entries.sum() < 2:
                        return 0.0
                    res = run_backtest(
                        _df["close"], entries, exits,
                        init_cash=self.init_cash,
                        freq=f"{timeframe_minutes(_cand.timeframe)}min",
                    )
                    if res is None:
                        return 0.0
                    return composite_score(res)
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

    def _load_session_data(self, cand: ScoredResult) -> Optional[pd.DataFrame]:
        try:
            df = load_ohlcv(self.symbol, cand.timeframe, count=5000)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"load failed for {cand.timeframe}: {e}")
            return None
        return filter_session(df, cand.session)


__all__ = ["Optimizer"]
