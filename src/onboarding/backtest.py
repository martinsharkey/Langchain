"""VectorBT backtest wrapper.

Uses VectorBT's native ``vbt.Portfolio.from_signals`` exclusively. All metrics come
from VectorBT's own portfolio/trades accessors, and the native ``pf.stats()`` report
is captured verbatim for the onboarding report.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Metrics from a single backtest (all sourced from VectorBT)."""

    trades: int
    win_rate: float
    profit_factor: float
    total_return: float
    max_drawdown: float
    sharpe: float
    fill_mode: str  # "bar" (VectorBT native)
    # VectorBT's native pf.stats() report, as a dict of metric name -> value.
    stats: Dict = field(default_factory=dict)


def _stats_to_dict(stats: pd.Series) -> Dict:
    """Convert VectorBT's native pf.stats() Series to a JSON-safe dict."""
    out: Dict = {}
    for name, value in stats.items():
        if isinstance(value, (int, float, str, bool)) or value is None:
            out[str(name)] = value
        else:
            out[str(name)] = str(value)
    return out


def run_backtest(
    close: pd.Series,
    entries,
    exits,
    init_cash: float = 10_000.0,
    freq: Optional[str] = None,
    ticks: Optional[dict] = None,
    fill_mode: str = "bar",
) -> Optional[BacktestResult]:
    """Run a VectorBT portfolio backtest.

    Args:
        close: Close price series (datetime-indexed).
        entries: Boolean entry signal (Series or array).
        exits: Boolean exit signal (Series or array).
        init_cash: Initial capital.
        freq: Bar frequency string (e.g. "1min").
        ticks: Accepted for API compatibility; VectorBT's native bar-based
            ``from_signals`` is the single source of truth for fills.
        fill_mode: "bar" (VectorBT native).

    Returns None if no trades are produced.
    """
    import vectorbt as vbt

    entries = np.asarray(entries, dtype=bool)
    exits = np.asarray(exits, dtype=bool)

    if entries.sum() < 1:
        return None

    pf = vbt.Portfolio.from_signals(
        close,
        entries,
        exits,
        init_cash=init_cash,
        freq=freq,
    )

    n_trades = int(pf.trades.count() or 0)
    if n_trades < 1:
        return None

    # Capture VectorBT's native stats report.
    try:
        stats = _stats_to_dict(pf.stats())
    except Exception as e:  # noqa: BLE001
        logger.debug(f"pf.stats() failed: {e}")
        stats = {}

    return BacktestResult(
        trades=n_trades,
        win_rate=float(pf.trades.win_rate() or 0.0),
        profit_factor=float(pf.trades.profit_factor() or 0.0),
        total_return=float(pf.total_return() or 0.0),
        max_drawdown=float(pf.max_drawdown() or 0.0),
        sharpe=float(pf.sharpe_ratio() or 0.0),
        fill_mode="bar",
        stats=stats,
    )


__all__ = ["BacktestResult", "run_backtest"]
