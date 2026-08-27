"""Signal generation using VectorBT's native signal methods.

VectorBT's generated indicator classes expose comparison and combination
methods out of the box (``.above()``, ``.below()``, ``.crossed_above()``,
``.crossed_below()``, ``&``, ``|``). This module uses those native methods
with DATA-DRIVEN thresholds (median, rolling mean) — not hardcoded values.

The key principle: let the data determine the signal, not human-assigned
thresholds. For any indicator output, we use its median as the neutral level
and generate signals when the value crosses above/below that level.
"""

from __future__ import annotations

import logging
from typing import Tuple

import pandas as pd

logger = logging.getLogger(__name__)


def _first_output(ind) -> pd.Series:
    """Return the first output of a run indicator as a pandas Series."""
    for name in ind.output_names:
        try:
            return getattr(ind, name)
        except Exception:
            continue
    raise ValueError("indicator has no outputs")


def generate_signals(ind, library: str, name: str) -> Tuple[pd.Series, pd.Series]:
    """Generate (entries, exits) for a run indicator using VectorBT-native methods.

    Uses data-driven thresholds:
    - For any indicator output, compute its median (neutral level).
    - Entry: value crosses above its median (bullish momentum).
    - Exit: value crosses below its median (bearish momentum).

    This is fully VectorBT-native: uses .crossed_above() / .crossed_below()
    on the indicator's own output, with a threshold derived from the data.
    """
    v = _first_output(ind)

    # Data-driven neutral level: the median of the series.
    # This adapts to each indicator's natural range.
    neutral = v.median()

    # Native VectorBT signal generation: cross above/below neutral.
    entries = v.vbt.crossed_above(neutral)
    exits = v.vbt.crossed_below(neutral)

    return entries, exits


def combine_signals(
    entries_list: List[pd.Series],
    exits_list: List[pd.Series],
    mode: str = "and",
) -> Tuple[pd.Series, pd.Series]:
    """Combine multiple entry/exit signal Series with AND or OR logic.

    Uses VectorBT-native ``&`` / ``|`` operators.
    """
    if not entries_list:
        return pd.Series(dtype=bool), pd.Series(dtype=bool)

    entries = entries_list[0]
    exits = exits_list[0]
    for e, x in zip(entries_list[1:], exits_list[1:]):
        if mode == "and":
            entries = entries & e
            exits = exits & x
        else:
            entries = entries | e
            exits = exits | x
    return entries, exits


__all__ = ["generate_signals", "combine_signals"]
