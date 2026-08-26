"""Phase 3: walk-forward out-of-sample validation using VectorBT's native rolling splitter.

VectorBT provides native walk-forward splitting via ``price.vbt.rolling_split()``
(`generic/splitters.py:RollingSplitter`). This replaces manual fold slicing with
VectorBT's native in-sample/out-sample range generation, as demonstrated in the
``WalkForwardOptimization.ipynb`` example.

Native API:
    (in_price, in_indexes), (out_price, out_indexes) = price.vbt.rolling_split(
        n=30, window_len=365*2, set_lens=(180,), left_to_right=False
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.onboarding.backtest import run_backtest
from src.onboarding.data import load_ohlcv
from src.onboarding.indicators import run_indicator, wrap
from src.onboarding.sessions import load_session_ohlcv
from src.onboarding.signals import generate_signals
from src.onboarding.timeframes import timeframe_minutes

logger = logging.getLogger(__name__)

# Validation thresholds.
MIN_OOS_PF = 1.0
MAX_DEGRADATION_PCT = 30.0
N_FOLDS = 5


@dataclass
class ValidationResult:
    """Walk-forward validation outcome for a candidate."""

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
    """Walk-forward OOS validation using VectorBT's native ``rolling_split``."""

    def __init__(self, symbol: str, init_cash: float = 10_000.0, n_folds: int = N_FOLDS):
        self.symbol = symbol
        self.init_cash = init_cash
        self.n_folds = n_folds

    def validate(self, tuned: List[Dict]) -> List[ValidationResult]:
        results: List[ValidationResult] = []
        for cand in tuned:
            ohlcv = self._load_session_data(cand)
            if ohlcv is None or "close" not in ohlcv or ohlcv["close"].shape[1] == 0:
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

            result = self._walk_forward(cand, ohlcv)
            results.append(result)

        return results

    def _walk_forward(self, cand: Dict, ohlcv: Dict[str, pd.DataFrame]) -> ValidationResult:
        """Validate a single candidate using native ``rolling_split``.

        Uses VectorBT's ``price.vbt.rolling_split()`` to generate chronological
        in-sample/out-sample folds, replacing manual fold slicing.
        """
        freq = f"{timeframe_minutes(cand['timeframe'])}min"

        # Concatenate per-session occurrences into contiguous series for walk-forward.
        close = self._concat_session_columns(ohlcv["close"])
        if len(close) < self.n_folds * 50:
            return ValidationResult(
                indicator=cand["indicator"], library=cand["library"],
                session=cand["session"], timeframe=cand["timeframe"],
                passed=False, pf_in_sample=0.0, pf_oos=0.0,
                degradation_pct=0.0, trades_out_sample=0,
                reason="insufficient data for walk-forward",
            )
        high = self._concat_session_columns(ohlcv["high"])
        low = self._concat_session_columns(ohlcv["low"])
        open_ = self._concat_session_columns(ohlcv["open"])
        volume = self._concat_session_columns(ohlcv["volume"])

        price = close

        # Native VectorBT rolling walk-forward split.
        # window_len auto-derived from n_folds; set_lens reserves ~20% for testing.
        test_len = max(int(len(price) * 0.2), 20)
        try:
            (in_price, _), (out_price, _) = price.vbt.rolling_split(
                n=self.n_folds,
                set_lens=(test_len,),
                left_to_right=False,
            )
        except Exception as e:  # noqa: BLE001
            logger.debug(f"rolling_split failed for {cand['indicator']}: {e}")
            return ValidationResult(
                indicator=cand["indicator"], library=cand["library"],
                session=cand["session"], timeframe=cand["timeframe"],
                passed=False, pf_in_sample=0.0, pf_out_sample=0.0,
                degradation_pct=0.0, trades_out_sample=0,
                reason=f"rolling_split failed: {e}",
            )

        in_sample_pfs: List[float] = []
        out_sample_pfs: List[float] = []
        oos_trades = 0

        # in_price / out_price are DataFrames with one column per fold.
        for fold_idx in range(in_price.shape[1]):
            in_col = in_price.iloc[:, fold_idx].dropna()
            out_col = out_price.iloc[:, fold_idx].dropna()
            if len(in_col) < 50 or len(out_col) < 20:
                continue

            in_df = pd.DataFrame({
                "close": in_col,
                "high": high.loc[in_col.index],
                "low": low.loc[in_col.index],
                "open": open_.loc[in_col.index],
                "volume": volume.loc[in_col.index],
            })
            out_df = pd.DataFrame({
                "close": out_col,
                "high": high.loc[out_col.index],
                "low": low.loc[out_col.index],
                "open": open_.loc[out_col.index],
                "volume": volume.loc[out_col.index],
            })

            try:
                res = self._backtest_candidate(cand, in_df, freq)
                if res is not None:
                    in_sample_pfs.append(res.profit_factor)
            except Exception:  # noqa: BLE001
                continue

            try:
                res = self._backtest_candidate(cand, out_df, freq)
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

    @staticmethod
    def _concat_session_columns(df: pd.DataFrame) -> pd.Series:
        """Concatenate per-session occurrence columns into a contiguous series.

        Each column in the input represents one session occurrence (e.g. one day's
        London session). This concatenates them end-to-end (dropping NaN padding)
        to produce a contiguous price series suitable for walk-forward splitting.
        """
        parts = [df.iloc[:, i].dropna() for i in range(df.shape[1])]
        parts = [p for p in parts if len(p) > 0]
        if not parts:
            return pd.Series(dtype=float)
        return pd.concat(parts)

    def _backtest_candidate(self, cand: Dict, df: pd.DataFrame, freq: str):
        """Run a candidate (single or combo) on a data slice and return metrics."""
        params = cand.get("best_params", {}) or {}

        if cand["library"] == "combo":
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

    def _load_session_data(self, cand: Dict) -> Optional[Dict]:
        return load_session_ohlcv(self.symbol, cand["timeframe"], cand["session"], count=5000)


__all__ = ["Validator", "ValidationResult", "MIN_OOS_PF", "MAX_DEGRADATION_PCT", "N_FOLDS"]
