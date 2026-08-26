"""Performance metrics and the composite ranking score."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from src.onboarding.backtest import BacktestResult

# Composite score weights (sum to 1.0). PF and drawdown weighted highest.
WEIGHTS = {
    "profit_factor": 0.35,
    "max_drawdown": 0.30,
    "win_rate": 0.15,
    "sharpe": 0.10,
    "trades": 0.10,
}

# Viability thresholds.
MIN_TRADES = 10
MIN_PROFIT_FACTOR = 1.0


@dataclass
class ScoredResult:
    """A backtest result with a composite score."""

    indicator: str
    library: str
    category: str
    session: str
    timeframe: str
    result: BacktestResult
    score: float
    combination: tuple = ()  # tuple of (library, name) for multi-indicator combos


def _normalise_drawdown(dd: float) -> float:
    """Map max drawdown (negative, e.g. -0.15) to a [0,1] score (higher=better)."""
    # dd is negative; clamp to [-1, 0]. Score = 1 + dd (so -0.15 -> 0.85).
    dd = min(0.0, float(dd))
    return max(0.0, 1.0 + dd)


def _normalise_profit_factor(pf: float) -> float:
    """Map profit factor to [0,1] (higher=better)."""
    if not np.isfinite(pf):
        return 1.0
    # PF 1.0 -> 0.5, PF 2.0 -> ~0.88, PF 3.0 -> ~0.95 (saturating).
    return 1.0 - 1.0 / (1.0 + max(0.0, pf - 1.0))


def _normalise_win_rate(wr: float) -> float:
    return float(np.clip(wr, 0.0, 1.0))


def _normalise_sharpe(sharpe: float) -> float:
    if not np.isfinite(sharpe):
        return 0.0
    # Sharpe 0 -> 0.5, 2 -> ~0.88, 4 -> ~0.95.
    return 1.0 - 1.0 / (1.0 + max(0.0, sharpe))


def _normalise_trades(trades: int) -> float:
    # More trades (up to ~50) is better for statistical confidence.
    return float(np.clip(trades / 50.0, 0.0, 1.0))


def composite_score(result: BacktestResult) -> float:
    """Compute the weighted composite score for a backtest result."""
    components = {
        "profit_factor": _normalise_profit_factor(result.profit_factor),
        "max_drawdown": _normalise_drawdown(result.max_drawdown),
        "win_rate": _normalise_win_rate(result.win_rate),
        "sharpe": _normalise_sharpe(result.sharpe),
        "trades": _normalise_trades(result.trades),
    }
    score = sum(WEIGHTS[k] * components[k] for k in WEIGHTS)
    return float(score)


def is_viable(result: BacktestResult) -> bool:
    """A result is viable if it meets minimum trade and PF thresholds."""
    return result.trades >= MIN_TRADES and result.profit_factor >= MIN_PROFIT_FACTOR


__all__ = [
    "WEIGHTS",
    "MIN_TRADES",
    "MIN_PROFIT_FACTOR",
    "ScoredResult",
    "composite_score",
    "is_viable",
]
