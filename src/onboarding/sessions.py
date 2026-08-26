"""Trading session taxonomy for symbol onboarding.

Defines the full set of testable sessions (macro, overlap, and micro) in UTC.
Uses VectorBT's native ``range_split`` (`generic/splitters.py:RangeSplitter`) to
split price data into per-session ranges, replacing hand-rolled pandas filtering.

Native API (from ``TradingSessions.ipynb`` example):
    session_price = filled_price.between_time('9:00', '17:00', include_end=False)
    start_idxs = session_price.index[session_price.index.hour == 9]
    end_idxs = session_price.index[session_price.index.hour == 16]
    price_per_session, _ = session_price.vbt(freq='1H').range_split(
        start_idxs=start_idxs, end_idxs=end_idxs
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import vectorbt as vbt

import logging

logger = logging.getLogger(__name__)


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
    # Optional per-day time windows (weekday -> (start_minutes, end_minutes)).
    # When provided, overrides start_hour/start_minute/end_hour/end_minute for
    # those specific days. Used for sessions like btcusd_weekend that have
    # different hours on different days (Fri 22:00+, Sat all day, Sun <21:00).
    day_windows: Dict[int, Tuple[int, int]] = field(default_factory=dict)


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
        key="weekend", name="BTCUSD Weekend", days=[4, 5, 6],
        start_hour=0, start_minute=0, end_hour=24, end_minute=0, kind="micro",
        description="BTCUSD weekend: Fri 22:00 - Sun 21:00 UTC (crypto never sleeps)",
        day_windows={
            4: (22 * 60, 24 * 60),  # Friday: 22:00 - 24:00
            5: (0, 24 * 60),          # Saturday: all day
            6: (0, 21 * 60),          # Sunday: 00:00 - 21:00
        },
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


def get_session_boundaries(
    df: pd.DataFrame, session_key: str,
) -> Tuple[Optional[pd.DatetimeIndex], Optional[pd.DatetimeIndex]]:
    """Get the start and end indices for each session occurrence using native conventions.

    Finds ONE start index (first bar of the session window) and ONE end index
    (last bar of the session window) per session occurrence (e.g. per day).
    These indexes are suitable for feeding directly into VectorBT's native
    ``range_split``.

    Returns:
        (start_idxs, end_idxs) as pandas Indexes (one entry per session occurrence),
        or (None, None) if no sessions found. Returned indexes preserve the original
        index timezone.
    """
    session = get_session(session_key)
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        raise TypeError("get_session_boundaries requires a DatetimeIndex")

    # Normalise to UTC-naive for hour/minute/weekday comparison.
    if idx.tz is not None:
        idx_norm = idx.tz_convert("UTC").tz_localize(None)
    else:
        idx_norm = idx

    weekday = idx_norm.weekday
    minutes = idx_norm.hour * 60 + idx_norm.minute

    # Build per-bar time mask, supporting per-day windows (e.g. btcusd_weekend).
    time_mask = pd.Series(False, index=idx_norm)
    for day_idx in session.days:
        day_sel = weekday == day_idx
        if day_idx in session.day_windows:
            start_m, end_m = session.day_windows[day_idx]
        else:
            start_m = _minutes_of_day(session.start_hour, session.start_minute)
            end_m = _minutes_of_day(session.end_hour, session.end_minute)
        if end_m == 24 * 60:
            time_mask = time_mask | (day_sel & (minutes >= start_m))
        elif start_m < end_m:
            time_mask = time_mask | (day_sel & (minutes >= start_m) & (minutes < end_m))
        else:
            time_mask = time_mask | (day_sel & ((minutes >= start_m) | (minutes < end_m)))

    # Get the integer positions of session bars in the ORIGINAL index.
    positions = np.where(time_mask)[0]
    if len(positions) == 0:
        return None, None

    # Map normalized times back to original index for grouping.
    session_times = idx_norm[positions]
    sessions_df = pd.DataFrame({"pos": positions, "time": session_times}, index=session_times)

    # Group bars into session occurrences. For single-day sessions, group by date.
    # For multi-day sessions (e.g. btcusd_weekend spanning Fri-Sun), group by
    # occurrence: each occurrence starts at the first bar of the session's first day.
    if len(session.days) == 1 or not session.day_windows:
        # Single-day sessions: each date is one occurrence.
        sessions_df["occurrence"] = sessions_df.index.date
    else:
        # Multi-day sessions: identify occurrence starts (first day of the session).
        first_day = min(session.days)
        # A new occurrence starts on each date that has bars on the first day.
        first_day_dates = set(
            sessions_df.index[sessions_df.index.weekday == first_day].date
        )
        # Assign each bar to the most recent occurrence start (backward fill).
        sessions_df["occurrence"] = None
        current_occurrence = None
        for ts in sessions_df.index:
            if ts.date() in first_day_dates and ts.weekday() == first_day:
                current_occurrence = ts.date()
            sessions_df.loc[ts, "occurrence"] = current_occurrence
        # Drop bars before the first occurrence start (shouldn't happen, but safety).
        sessions_df = sessions_df.dropna(subset=["occurrence"])

    start_positions = sessions_df.groupby("occurrence")["pos"].first().values
    end_positions = sessions_df.groupby("occurrence")["pos"].last().values

    if len(start_positions) == 0 or len(end_positions) == 0:
        return None, None

    # Return indexes from the ORIGINAL (possibly tz-aware) index.
    start_idxs = pd.DatetimeIndex(idx[start_positions])
    end_idxs = pd.DatetimeIndex(idx[end_positions])

    return start_idxs, end_idxs


def _range_split_series(
    series: pd.Series, start_idxs: pd.DatetimeIndex, end_idxs: pd.DatetimeIndex, freq: str,
) -> pd.DataFrame:
    """Apply VectorBT's native range_split to a single Series."""
    try:
        per_session, _ = series.vbt(freq=freq).range_split(
            start_idxs=start_idxs, end_idxs=end_idxs
        )
        return per_session
    except Exception as e:  # noqa: BLE001
        logger.debug(f"range_split failed for {series.name}: {e}")
        return None


def split_sessions_native(
    df: pd.DataFrame, session_key: str, freq: str = "1min",
) -> Optional[Dict[str, pd.DataFrame]]:
    """Split OHLCV data into per-session ranges using VectorBT's native ``range_split``.

    This is the native VectorBT approach (from ``TradingSessions.ipynb``): instead of
    filtering to a single session's bars, it returns a dict of DataFrames (one per
    OHLCV column) where each COLUMN is one occurrence of the session (e.g. one day's
    London session). Indicators can then be run across all occurrences at once via
    VectorBT's vectorized ``.run()``, passing the split columns as inputs.

    Example (native flow):
        ohlcv = split_sessions_native(df, "london", freq="1min")
        rsi = vbt.pandas_ta('RSI').run(close=ohlcv["close"], length=14)
        entries = rsi.rsi.vbt.below(30)
        exits = rsi.rsi.vbt.above(70)
        pf = vbt.Portfolio.from_signals(ohlcv["close"], entries, exits, freq="1min")

    Args:
        df: DataFrame with a tz-aware (or naive-UTC) DatetimeIndex and OHLCV columns.
        session_key: Session key from SESSION_DEFINITIONS.
        freq: Bar frequency string for the VectorBT wrapper (e.g. "1min", "1H").

    Returns:
        A dict {"close": df, "high": df, "low": df, "open": df, "volume": df}
        where each DataFrame has one column per session occurrence, or None if no
        sessions found. Shorter sessions are padded with NaN (VectorBT convention).
    """
    start_idxs, end_idxs = get_session_boundaries(df, session_key)
    if start_idxs is None or end_idxs is None:
        return None

    result: Dict[str, pd.DataFrame] = {}
    for col in ("close", "high", "low", "open", "volume"):
        if col not in df.columns:
            continue
        split = _range_split_series(df[col], start_idxs, end_idxs, freq)
        if split is None:
            return None
        result[col] = split

    if not result:
        return None
    return result


__all__ = [
    "Session",
    "SESSION_DEFINITIONS",
    "SESSION_ORDER",
    "get_session",
    "all_session_keys",
    "get_session_boundaries",
    "split_sessions_native",
    "load_session_ohlcv",
]


def load_session_ohlcv(
    symbol: str, timeframe: str, session_key: str, count: int = 5000,
) -> Optional[Dict[str, pd.DataFrame]]:
    """Load OHLCV and split into per-session ranges using native VectorBT.

    This is the native replacement for ``filter_session``: instead of filtering
    to a single session's bars, it returns a dict of DataFrames (one per OHLCV
    column) where each COLUMN is one occurrence of the session. Indicators and
    portfolio backtesting can then be run across all occurrences at once via
    VectorBT's vectorized engine.

    Args:
        symbol: MT5 symbol.
        timeframe: MT5 timeframe string.
        session_key: Session key from SESSION_DEFINITIONS.
        count: Number of OHLCV bars to load.

    Returns:
        A dict {"close": df, "high": df, "low": df, "open": df, "volume": df}
        where each DataFrame has one column per session occurrence, or None if
        no sessions found.
    """
    from src.onboarding.data import load_ohlcv

    try:
        df = load_ohlcv(symbol, timeframe, count=count)
    except Exception:  # noqa: BLE001
        return None
    if len(df) < 50:
        return None
    return split_sessions_native(df, session_key)
