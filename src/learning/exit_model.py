"""
Shared exit model — arm/giveback peak-protection exit.

The single source of truth for how a trade exits. Both the live engine's
walk-forward validation and Optuna's floor search must compute exits through
this same logic, not two implementations that merely happen to agree.

Two callers are provided:
  - resolve_exit_tick:   tick-accurate, checks each bid/ask in sequence
  - resolve_exit_bar:    bar-level fast path, uses bar H/L only
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TradeState:
    dir: str
    entry: float
    sl: float
    tp: float
    risk: float
    rr: float
    peak: float = field(default=0.0)
    arm: float = 0.0


def resolve_exit_tick(ot: TradeState, ticks: list[tuple[float, float]]) -> Optional[float]:
    """Resolve an open trade against a sequence of (bid, ask) ticks.

    Returns realised R if the trade closes during these ticks, else None.
    Updates ot.peak in place as the favorable extreme advances.
    """
    d = ot.dir
    for bid, ask in ticks:
        px = bid if d == "buy" else ask
        if d == "buy":
            ot.peak = max(ot.peak, px)
            if px <= ot.sl:
                return -1.0
            if px >= ot.tp:
                return ot.rr
            fav = ot.peak - ot.entry
            if fav >= ot.arm and (ot.peak - px) >= 0.55 * fav:
                return (px - ot.entry) / ot.risk
        else:
            ot.peak = min(ot.peak, px)
            if px >= ot.sl:
                return -1.0
            if px <= ot.tp:
                return ot.rr
            fav = ot.entry - ot.peak
            if fav >= ot.arm and (px - ot.peak) >= 0.55 * fav:
                return (ot.entry - px) / ot.risk
    return None


def resolve_exit_bar(ot: TradeState, high: float, low: float, price: float) -> Optional[float]:
    """Resolve an open trade against a single bar's high/low.

    Returns realised R if the trade closes during this bar, else None.
    Updates ot.peak in place using the bar's extreme.
    """
    d = ot.dir
    if d == "buy":
        ot.peak = max(ot.peak, high)
        fav = ot.peak - ot.entry
        if low <= ot.sl:
            return -1.0
        if high >= ot.tp:
            return ot.rr
        if fav >= ot.arm and (ot.peak - price) >= 0.55 * fav:
            return (price - ot.entry) / ot.risk
    else:
        ot.peak = min(ot.peak, low)
        fav = ot.entry - ot.peak
        if high >= ot.sl:
            return -1.0
        if low <= ot.tp:
            return ot.rr
        if fav >= ot.arm and (price - ot.peak) >= 0.55 * fav:
            return (ot.entry - price) / ot.risk
    return None
