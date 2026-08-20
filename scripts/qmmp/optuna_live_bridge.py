"""Optuna → Live Tuning Bridge (HLD #76 follow-up).

Reads the latest completed Optuna study for a symbol, translates the best trial's
QMMP floor names into the live tuned_params schema, validates through the same
`ChangeValidator` gate the live optimizer uses, and on pass writes directly to
`ParameterOptimizer.tuned[symbol]` so the change takes effect immediately.

Aggregate-fallback caveat
-------------------------
`ChangeValidator.validate()` scores via `walkforward_focused()`, which currently
returns a single aggregate score across all sessions. Optuna's floors are genuinely
per-session. Feeding a per-session floor through an aggregate scorer is the same
validity issue that disabled the optimizer's own per-session search (`sess_budget = 0`
in `param_optimizer.py`). This bridge does NOT solve that — it shares the same
prerequisite (#76). As an interim, the mapper collapses per-session floors down to
a base scalar (first non-zero session) plus `session_*` overrides; the validator
scores the base scalar path, so the session overrides are carried along but their
per-session impact is diluted in the aggregate score. This is a deliberate, visible
trade-off documented here, not a silent approximation.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import optuna
from optuna.samplers import TPESampler

from src import config
from src.learning.learning_log import LearningLog
from src.learning.param_optimizer import ParameterOptimizer, qmmp_floors_to_live_params
from src.utils.logger import get_logger

logger = get_logger("optuna_live_bridge")

SESSIONS = ("Asian", "London", "NewYork")
D = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "qmmp")
MAX_STUDY_AGE_DAYS = 7


def _resolve_symbol(symbol: str) -> str:
    """Resolve symbol to broker format WITHOUT touching MT5.

    The live bot already has an active MT5 terminal session. Calling
    mt5.initialize()/shutdown() from a daily-cycle background task can
    disrupt live data feeds. This resolver uses a static approximation
    (same logic as the study runner's allow_mt5=False path).
    """
    return symbol.upper().split("-")[0].rstrip(".")


def _load_best_trial_from_study(symbol: str) -> Optional[dict]:
    """Load the best trial params from the Optuna study DB for `symbol`.

    Returns the flat best params dict (e.g. ``{"osma_Asian": 2.0, ...}``) or None
    if the study has no completed trials.
    """
    base = _resolve_symbol(symbol).upper().split("-")[0].rstrip(".")
    optuna_dir = os.path.join(D, base, "optuna")
    study_name = f"floors_{base}"
    storage = f"sqlite:///{os.path.join(optuna_dir, 'study.db')}"

    if not os.path.exists(os.path.join(optuna_dir, "study.db")):
        logger.debug(f"No Optuna study DB for {symbol} at {optuna_dir}")
        return None

    try:
        study = optuna.create_study(
            study_name=study_name,
            storage=storage,
            sampler=TPESampler(seed=42),
            direction="maximize",
            load_if_exists=True,
        )
        if study.best_trial is None or study.best_trial.value is None:
            logger.debug(f"Optuna study for {symbol} has no completed trials")
            return None
        completed_at = getattr(study.best_trial, "datetime_complete", None)
        if completed_at is not None:
            age_days = (datetime.now(timezone.utc) - completed_at.replace(tzinfo=timezone.utc)).total_seconds() / 86400.0
            if age_days > MAX_STUDY_AGE_DAYS:
                logger.debug(f"Optuna study for {symbol} is stale ({age_days:.1f} days > {MAX_STUDY_AGE_DAYS})")
                return None
        return dict(study.best_trial.params)
    except Exception as e:
        logger.warning(f"Failed to load Optuna study for {symbol}: {e}")
        return None


def _flat_params_to_floors(flat_params: dict) -> dict:
    """Convert Optuna's flat best params back to the nested QMMP floor dict shape.

    Optuna stores keys like ``osma_Asian``, ``bulls_London_long``, etc. This
    reconstructs the nested ``floors`` dict that ``qmmp_floors_to_live_params``
    expects.
    """
    floors = {}
    for key, val in flat_params.items():
        if val == 0.0 or val == 0:
            continue
        if key.startswith("osma_"):
            sess = key[len("osma_"):]
            floors.setdefault("osma_mag", {})[sess] = float(val)
        elif key.startswith("ema_"):
            sess = key[len("ema_"):]
            floors.setdefault("ema_align", {})[sess] = float(val)
        elif key.startswith("bulls_"):
            rest = key[len("bulls_"):]
            sess, side = rest.split("_", 1)
            floors.setdefault("bulls", {})[f"{sess}_{side}"] = float(val)
        elif key.startswith("bears_"):
            rest = key[len("bears_"):]
            sess, side = rest.split("_", 1)
            floors.setdefault("bears", {})[f"{sess}_{side}"] = float(val)
        elif key.startswith("atr_"):
            sess = key[len("atr_"):]
            floors.setdefault("atr", {})[sess] = float(val)
    return floors


def propose_live_params(symbol: str) -> Optional[dict]:
    """Read the best Optuna trial for `symbol` and return live-schema params.

    Returns ``None`` if no study, no completed trials, or the mapper produces
    no non-zero floors.
    """
    flat = _load_best_trial_from_study(symbol)
    if flat is None:
        return None
    floors = _flat_params_to_floors(flat)
    if not floors:
        logger.debug(f"Optuna study for {symbol} has no non-zero floors")
        return None
    return qmmp_floors_to_live_params(floors)


class OptunaLiveBridge:
    """Bridge Optuna validated output into the live tuning loop.

    Usage (from ``scalp_engine`` or standalone)::

        bridge = OptunaLiveBridge(
            param_optimizer=self.param_optimizer,
            change_validator=self.change_validator,
            learning_log=self.learning_log,
        )
        result = bridge.propose_and_apply(symbol)
    """

    def __init__(
        self,
        param_optimizer: Optional[ParameterOptimizer] = None,
        change_validator: Optional[Any] = None,
        learning_log: Optional[LearningLog] = None,
        backtest_fn: Optional[Callable] = None,
    ):
        self.param_optimizer = param_optimizer
        self.change_validator = change_validator
        self.learning_log = learning_log
        self.backtest_fn = backtest_fn

    def propose_and_apply(self, symbol: str, min_trades: int = 40) -> dict:
        """Propose Optuna's best floors for `symbol` and apply if validated.

        Returns a summary dict with ``proposed``, ``floors``, ``validation``,
        ``applied``, and ``reason``.
        """
        proposed = propose_live_params(symbol)
        summary = {
            "symbol": symbol,
            "proposed": proposed is not None,
            "floors": proposed,
            "validation": None,
            "applied": False,
            "reason": "",
        }

        if proposed is None:
            summary["reason"] = "no completed Optuna study or no non-zero floors"
            logger.debug(f"[OPTUNA] {symbol}: {summary['reason']}")
            return summary

        if self.change_validator is None:
            summary["reason"] = "no ChangeValidator configured"
            logger.warning(f"[OPTUNA] {symbol}: {summary['reason']}")
            return summary

        validation = self.change_validator.validate(
            symbol, proposed, source="optuna", min_trades=min_trades
        )
        summary["validation"] = validation

        if not validation.get("passed"):
            summary["reason"] = f"validation failed: {validation.get('reason')}"
            logger.warning(f"[OPTUNA] {symbol}: {summary['reason']}")
            session_scores = validation.get("session_scores") or {}
            if session_scores:
                session_parts = []
                for sess, d in session_scores.items():
                    if d.get("trades", 0) > 0:
                        session_parts.append(f"{sess}:PF={d.get('pf', 0):.2f} WR={d.get('wr', 0):.1f}% n={d.get('trades', 0)}")
                if session_parts:
                    logger.warning(f"[OPTUNA] {symbol}: per-session breakdown — {'; '.join(session_parts)}")
            if self.learning_log is not None:
                try:
                    metric = (f"score={validation.get('score')} fwdPF={validation.get('forward_pf')} "
                              f"n={validation.get('n_total')}")
                    if session_scores:
                        metric += " | " + "; ".join(
                            f"{s}={d.get('pf', 0):.2f}" for s, d in session_scores.items() if d.get("trades", 0) > 0
                        )
                    self.learning_log.record(
                        kind="OPTUNA",
                        symbol=symbol,
                        what="proposed params rejected by best-ever gate",
                        why=validation.get("reason", ""),
                        metric=metric,
                    )
                except Exception:
                    pass
            return summary

        # Apply: write to param_optimizer.tuned and persist, exactly as optimize() does.
        if self.param_optimizer is None:
            summary["reason"] = "validation passed but no ParameterOptimizer to apply"
            logger.warning(f"[OPTUNA] {symbol}: {summary['reason']}")
            return summary

        try:
            key = self.param_optimizer._key(symbol)
            existing = self.param_optimizer.tuned.get(key)
            incoming_score = validation.get("score", 0) or 0
            if existing is not None and isinstance(existing, dict):
                existing_score = existing.get("score")
                if isinstance(existing_score, (int, float)) and incoming_score < existing_score:
                    summary["reason"] = (f"skipped: incoming score {incoming_score:.3f} "
                                         f"< existing tuned score {existing_score:.3f}")
                    logger.warning(f"[OPTUNA] {symbol}: {summary['reason']}")
                    if self.learning_log is not None:
                        try:
                            self.learning_log.record(
                                kind="OPTUNA",
                                symbol=symbol,
                                what="skipped applying Optuna floors to preserve higher-scoring tuned params",
                                why=summary["reason"],
                                metric=f"incoming={incoming_score:.3f} existing={existing_score:.3f}",
                            )
                        except Exception:
                            pass
                    return summary
            self.param_optimizer.tuned[key] = {
                "params": proposed,
                "score": validation.get("score"),
                "forward_pf": validation.get("forward_pf"),
                "source": "optuna",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.param_optimizer._persist()
            summary["applied"] = True
            summary["reason"] = "applied"
            logger.info(f"[OPTUNA] {symbol}: APPLIED score={validation.get('score')} "
                        f"fwdPF={validation.get('forward_pf')}")
            if self.learning_log is not None:
                try:
                    self.learning_log.record(
                        kind="OPTUNA",
                        symbol=symbol,
                        what="applied Optuna best floors to live tuned_params",
                        why="beat best-ever gate",
                        metric=f"score={validation.get('score')} fwdPF={validation.get('forward_pf')}",
                    )
                except Exception:
                    pass
        except Exception as e:
            summary["reason"] = f"apply failed: {e}"
            logger.warning(f"[OPTUNA] {symbol}: {summary['reason']}")
        return summary
