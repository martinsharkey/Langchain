"""Trading session taxonomy for symbol onboarding.

Defines the full set of testable sessions (macro, overlap, and micro) in UTC.
Each session is a distinct market regime with its own liquidity, volume, and
behaviour, so a symbol may perform best on any one of them with a different
indicator set.

Times are UTC. Weekday is Python ``datetime.weekday()`` (Mon=0 .. Sun=6).
Sessions carry minute-level precision so micro-sessions (e.g. the 15/30/60-minute
post-market-open windows) can be expressed exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import pandas as pd


@dataclass(frozen=True)
class Session:
    """A single testable trading session."""

    key: str
    name: str
    days: List[int]          # weekday indices (Mon=0 .. Sun=6)
    start_hour: int          # inclusive, UTC
    start_minute: int        # inclusive, UTC
    end_hour: int            # exclusive, UTC (24 = midnight wrap)
    end_minute: int          # exclusive, UTC
    kind: str                # "macro" | "overlap" | "micro"
    description: str = ""


# Full session taxonomy. Hours are UTC.
#   Macro:    asian, london, newyork
#   Overlap:  overlap_asia_london, overlap_london_ny
#   Micro:    post_market_open (15/30/60-min variants), weekly_close,
#             sunday_open, friday_close, weekend
SESSION_DEFINITIONS: Dict[str, Session] = {
    "asian": Session(
        key="asian", name="Asian Session", days=[0, 1, 2, 3, 4],
        start_hour=0, start_minute=0, end_hour=8, end_minute=0, kind="macro",
        description="Tokyo/Sydney/Hong Kong/Singapore (00:00-08:00 UTC)",
    ),
    "london": Session(
        key="london", name="London Session", days=[0, 1, 2, 3, 4],
        start_hour=8, start_minute=0, end_hour=17, end_minute=0, kind="macro",
        description="European morning/afternoon (08:00-17:00 UTC)",
    ),
    "newyork": Session(
        key="newyork", name="New York Session", days=[0, 1, 2, 3, 4],
        start_hour=13, start_minute=0, end_hour=22, end_minute=0, kind="macro",
        description="North American session (13:00-22:00 UTC)",
    ),
    "overlap_asia_london": Session(
        key="overlap_asia_london", name="Asia-London Overlap", days=[0, 1, 2, 3, 4],
        start_hour=7, start_minute=0, end_hour=9, end_minute=0, kind="overlap",
        description="Tokyo close meets London open (07:00-09:00 UTC)",
    ),
    "overlap_london_ny": Session(
        key="overlap_london_ny", name="London-New York Overlap", days=[0, 1, 2, 3, 4],
        start_hour=13, start_minute=0, end_hour=17, end_minute=0, kind="overlap",
        description="London afternoon meets NY open (13:00-17:00 UTC)",
    ),
    # Post-market-open micro-sessions: highly volatile 15/30/60-minute windows
    # after the weekday open (Mon-Thu).
    "post_market_open_15": Session(
        key="post_market_open_15", name="Post-Market Open (15m)", days=[0, 1, 2, 3],
        start_hour=22, start_minute=0, end_hour=22, end_minute=15, kind="micro",
        description="Mon-Thu first 15 min after open (22:00-22:15 UTC)",
    ),
    "post_market_open_30": Session(
        key="post_market_open_30", name="Post-Market Open (30m)", days=[0, 1, 2, 3],
        start_hour=22, start_minute=0, end_hour=22, end_minute=30, kind="micro",
        description="Mon-Thu first 30 min after open (22:00-22:30 UTC)",
    ),
    "post_market_open_60": Session(
        key="post_market_open_60", name="Post-Market Open (60m)", days=[0, 1, 2, 3],
        start_hour=22, start_minute=0, end_hour=23, end_minute=0, kind="micro",
        description="Mon-Thu first 60 min after open (22:00-23:00 UTC)",
    ),
    "weekly_close": Session(
        key="weekly_close", name="Weekly Close", days=[0, 1, 2, 3],
        start_hour=22, start_minute=0, end_hour=23, end_minute=0, kind="micro",
        description="Mon-Thu weekly close window (22:00-23:00 UTC)",
    ),
    "sunday_open": Session(
        key="sunday_open", name="Sunday Open", days=[6],
        start_hour=22, start_minute=0, end_hour=24, end_minute=0, kind="micro",
        description="Sunday market open (22:00-24:00 UTC)",
    ),
    "friday_close": Session(
        key="friday_close", name="Friday Close", days=[4],
        start_hour=21, start_minute=0, end_hour=22, end_minute=0, kind="micro",
        description="Friday market close (21:00-22:00 UTC)",
    ),
    "weekend": Session(
        key="weekend", name="Weekend (24/7)", days=[5, 6],
        start_hour=0, start_minute=0, end_hour=24, end_minute=0, kind="micro",
        description="Saturday-Sunday (BTCUSD trades 24/7)",
    ),
}

# Order in which sessions are evaluated (for reporting / precedence).
SESSION_ORDER: List[str] = [
    "asian",
    "london",
    "newyork",
    "overlap_asia_london",
    "overlap_london_ny",
    "post_market_open_15",
    "post_market_open_30",
    "post_market_open_60",
    "weekly_close",
    "sunday_open",
    "friday_close",
    "weekend",
]


def get_session(key: str) -> Session:
    """Return a session definition by key."""
    if key not in SESSION_DEFINITIONS:
        raise ValueError(f"Unknown session: {key}")
    return SESSION_DEFINITIONS[key]


def all_session_keys() -> List[str]:
    """Return all session keys in canonical order."""
    return list(SESSION_ORDER)


def _minutes_of_day(hour: int, minute: int) -> int:
    return hour * 60 + minute


def filter_session(df: pd.DataFrame, session_key: str) -> pd.DataFrame:
    """Filter a datetime-indexed DataFrame to a single session's bars.

    Args:
        df: DataFrame with a tz-aware (or naive-UTC) DatetimeIndex.
        session_key: Session key from SESSION_DEFINITIONS.

    Returns:
        A copy of ``df`` containing only bars within the session window.
    """
    session = get_session(session_key)
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        raise TypeError("filter_session requires a DatetimeIndex")

    # Normalise to UTC-naive for hour/minute/weekday comparison.
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)

    weekday = idx.weekday
    minutes = idx.hour * 60 + idx.minute

    day_mask = weekday.isin(session.days)

    start = _minutes_of_day(session.start_hour, session.start_minute)
    end = _minutes_of_day(session.end_hour, session.end_minute)

    if end == 24 * 60:
        # Full-day session (e.g. weekend).
        time_mask = minutes >= start
    elif start < end:
        time_mask = (minutes >= start) & (minutes < end)
    else:
        # Overnight wrap (e.g. 22:00 -> 02:00).
        time_mask = (minutes >= start) | (minutes < end)

    return df[day_mask & time_mask].copy()


__all__ = [
    "Session",
    "SESSION_DEFINITIONS",
    "SESSION_ORDER",
    "get_session",
    "all_session_keys",
    "filter_session",
]
