"""Phase 3: walk-forward out-of-sample validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.onboarding.backtest import run_backtest
from src.onboarding.data import load_ohlcv
from src.onboarding.indicators import run_indicator, wrap
from src.onboarding.sessions import filter_session
from src.onboarding.signals import generate_signals
from src.onboarding.timeframes import timeframe_minutes

logger = logging.getLogger(__name__)

# Validation thresholds.
MIN_OOS_PF = 1.0
MAX_DEGRADATION_PCT = 30.0
N_FOLDS = 5


@dataclass
class ValidationResult:
    """Walk-forward validation outcome for a tuned candidate."""

    indicator: str
    library: str
    session: str
    timeframe: str
    passed: bool
    pf_in_sample: float
    pf_out_sample: float
    degradation_pct: float
    trades_out_sample: int
    reason: str


class Validator:
    """Chronological walk-forward OOS validation."""

    def __init__(self, symbol: str, init_cash: float = 10_000.0, n_folds: int = N_FOLDS):
        self.symbol = symbol
        self.init_cash = init_cash
        self.n_folds = n_folds

    def validate(self, tuned: List[Dict]) -> List[ValidationResult]:
        results: List[ValidationResult] = []
        for cand in tuned:
            df = self._load_session_data(cand)
            if df is None or len(df) < self.n_folds * 50:
                results.append(
                    ValidationResult(
                        indicator=cand["indicator"], library=cand["library"],
                        session=cand["session"], timeframe=cand["timeframe"],
                        passed=False, pf_in_sample=0.0, pf_out_sample=0.0,
                        degradation_pct=0.0, trades_out_sample=0,
                        reason="insufficient data for walk-forward",
                    )
                )
                continue

            result = self._walk_forward(cand, df)
            results.append(result)

        return results

    def _walk_forward(self, cand: Dict, df: pd.DataFrame) -> ValidationResult:
        freq = f"{timeframe_minutes(cand['timeframe'])}min"
        n = len(df)
        fold_size = n // self.n_folds

        in_sample_pfs: List[float] = []
        out_sample_pfs: List[float] = []
        oos_trades = 0

        for i in range(self.n_folds - 1):
            train = df.iloc[: (i + 1) * fold_size]
            test = df.iloc[(i + 1) * fold_size: (i + 2) * fold_size]
            if len(train) < 50 or len(test) < 20:
                continue

            try:
                res = self._backtest_candidate(cand, train, freq)
                if res is not None:
                    in_sample_pfs.append(res.profit_factor)
            except Exception:  # noqa: BLE001
                continue

            try:
                res = self._backtest_candidate(cand, test, freq)
                if res is not None:
                    out_sample_pfs.append(res.profit_factor)
                    oos_trades += res.trades
            except Exception:  # noqa: BLE001
                continue

        if not out_sample_pfs:
            return ValidationResult(
                indicator=cand["indicator"], library=cand["library"],
                session=cand["session"], timeframe=cand["timeframe"],
                passed=False, pf_in_sample=0.0, pf_out_sample=0.0,
                degradation_pct=0.0, trades_out_sample=0,
                reason="no out-of-sample trades",
            )

        pf_is = float(np.mean(in_sample_pfs)) if in_sample_pfs else 0.0
        pf_oos = float(np.mean(out_sample_pfs))
        degradation = ((pf_is - pf_oos) / pf_is * 100.0) if pf_is > 0 else 0.0

        passed = pf_oos >= MIN_OOS_PF and degradation <= MAX_DEGRADATION_PCT
        reason = (
            "PASS"
            if passed
            else f"OOS PF {pf_oos:.2f} < {MIN_OOS_PF} or degradation {degradation:.1f}% > {MAX_DEGRADATION_PCT}%"
        )

        return ValidationResult(
            indicator=cand["indicator"], library=cand["library"],
            session=cand["session"], timeframe=cand["timeframe"],
            passed=passed, pf_in_sample=pf_is, pf_out_sample=pf_oos,
            degradation_pct=degradation, trades_out_sample=oos_trades,
            reason=reason,
        )

    def _backtest_candidate(self, cand: Dict, df: pd.DataFrame, freq: str):
        """Run a candidate (single or combo) on a data slice and return metrics."""
        params = cand.get("best_params", {}) or {}

        if cand["library"] == "combo":
            # Combination candidate: re-derive signals from its members.
            entries_list = []
            exits_list = []
            for lib, name in cand.get("combination", ()):
                ind = wrap(name, lib)
                run = run_indicator(
                    ind, df["close"], df["high"], df["low"], df["open"], df["volume"],
                    **params,
                )
                e, x = generate_signals(run, lib, name)
                entries_list.append(e)
                exits_list.append(x)
            from src.onboarding.signals import combine_signals
            entries, exits = combine_signals(entries_list, exits_list, cand["category"])
        else:
            ind = wrap(cand["indicator"], cand["library"])
            run = run_indicator(
                ind, df["close"], df["high"], df["low"], df["open"], df["volume"],
                **params,
            )
            entries, exits = generate_signals(run, cand["library"], cand["indicator"])

        if entries.sum() < 2:
            return None
        return run_backtest(df["close"], entries, exits, init_cash=self.init_cash, freq=freq)

    def _load_session_data(self, cand: Dict) -> Optional[pd.DataFrame]:
        try:
            df = load_ohlcv(self.symbol, cand["timeframe"], count=5000)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"load failed for {cand['timeframe']}: {e}")
            return None
        return filter_session(df, cand["session"])


__all__ = ["Validator", "ValidationResult", "MIN_OOS_PF", "MAX_DEGRADATION_PCT", "N_FOLDS"]
