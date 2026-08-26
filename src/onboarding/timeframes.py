"""Timeframe definitions for symbol onboarding.

Includes the full minute matrix M1..M30 plus H1, H4, D1. Some minute
timeframes may not be offered by the broker; the discovery phase skips any
unavailable timeframe and logs it.
"""

from __future__ import annotations

from typing import Dict, List

# Full minute matrix M1..M30 plus the higher timeframes.
TIMEFRAMES: List[str] = (
    [f"M{i}" for i in range(1, 31)] + ["H1", "H4", "D1"]
)

# Approximate bar frequency in minutes, used to infer vectorbt `freq`.
TIMEFRAME_MINUTES: Dict[str, int] = {f"M{i}": i for i in range(1, 31)}
TIMEFRAME_MINUTES.update({"H1": 60, "H4": 240, "D1": 1440})

# Timeframes that should use tick-accurate fills when tick data is available.
TICK_ACCURATE_TIMEFRAMES = {"M1", "M5"}


def timeframe_minutes(timeframe: str) -> int:
    """Return the number of minutes per bar for a timeframe."""
    if timeframe not in TIMEFRAME_MINUTES:
        raise ValueError(f"Unknown timeframe: {timeframe}")
    return TIMEFRAME_MINUTES[timeframe]


__all__ = [
    "TIMEFRAMES",
    "TIMEFRAME_MINUTES",
    "TICK_ACCURATE_TIMEFRAMES",
    "timeframe_minutes",
]
