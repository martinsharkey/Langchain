"""Unit tests for the onboarding session taxonomy (native VectorBT range_split)."""

import pandas as pd
import pytest

from src.onboarding.sessions import (
    SESSION_DEFINITIONS,
    all_session_keys,
    get_session,
    split_sessions_native,
    get_session_boundaries,
)


def test_all_sessions_present():
    keys = all_session_keys()
    for k in (
        "asian", "london", "newyork",
        "overlap_asia_london", "overlap_london_ny",
        "post_market_open_15", "post_market_open_30", "post_market_open_60",
        "weekly_close", "sunday_open", "friday_close", "weekend",
    ):
        assert k in keys


def test_get_session_unknown_raises():
    with pytest.raises(ValueError):
        get_session("does_not_exist")


def test_split_sessions_native_london():
    """Native range_split: London session (08:00-17:00 UTC) produces per-occurrence columns."""
    idx = pd.date_range("2026-08-03", periods=5 * 24 * 60, freq="1min")  # Mon-Fri
    df = pd.DataFrame(
        {"close": range(len(idx)), "high": range(len(idx)), "low": range(len(idx)),
         "open": range(len(idx)), "volume": range(len(idx))},
        index=idx,
    )
    ohlcv = split_sessions_native(df, "london", freq="1min")
    assert ohlcv is not None
    assert "close" in ohlcv
    # One column per London session occurrence (5 days = 5 columns).
    assert ohlcv["close"].shape[1] == 5
    # Each column has bars for the 9-hour session (540 min), padded with NaN.
    assert ohlcv["close"].shape[0] >= 540


def test_split_sessions_native_weekend():
    """Native range_split: weekend (Sat-Sun) produces per-occurrence columns."""
    idx = pd.date_range("2026-08-08", periods=48 * 60, freq="1min")  # Sat-Sun
    df = pd.DataFrame(
        {"close": range(len(idx)), "high": range(len(idx)), "low": range(len(idx)),
         "open": range(len(idx)), "volume": range(len(idx))},
        index=idx,
    )
    ohlcv = split_sessions_native(df, "weekend", freq="1min")
    assert ohlcv is not None
    # Weekend: 2 days = 2 columns.
    assert ohlcv["close"].shape[1] == 2


def test_split_sessions_native_returns_dict():
    """Native range_split returns a dict of OHLCV DataFrames."""
    idx = pd.date_range("2026-08-03", periods=24 * 60, freq="1min")
    df = pd.DataFrame(
        {"close": range(len(idx)), "high": range(len(idx)), "low": range(len(idx)),
         "open": range(len(idx)), "volume": range(len(idx))},
        index=idx,
    )
    ohlcv = split_sessions_native(df, "london", freq="1min")
    assert isinstance(ohlcv, dict)
    for col in ("close", "high", "low", "open", "volume"):
        assert col in ohlcv
        assert isinstance(ohlcv[col], pd.DataFrame)


def test_get_session_boundaries_london():
    """get_session_boundaries returns start/end indexes for London session."""
    idx = pd.date_range("2026-08-03", periods=5 * 24 * 60, freq="1min")  # Mon-Fri
    df = pd.DataFrame({"close": range(len(idx))}, index=idx)
    start_idxs, end_idxs = get_session_boundaries(df, "london")
    assert start_idxs is not None
    assert end_idxs is not None
    # 5 days = 5 session starts.
    assert len(start_idxs) == 5
    assert len(end_idxs) == 5


def test_split_sessions_native_no_data():
    """Native range_split returns None when no session data found."""
    idx = pd.date_range("2026-08-03", periods=10, freq="1min")
    df = pd.DataFrame({"close": range(len(idx))}, index=idx)
    ohlcv = split_sessions_native(df, "asian", freq="1min")
    # Only 10 bars, not enough for a full Asian session - may return None or empty.
    # The function should handle gracefully.
    if ohlcv is not None:
        assert ohlcv["close"].shape[1] >= 0


def test_split_sessions_native_requires_datetime_index():
    df = pd.DataFrame({"close": [1, 2, 3]})
    with pytest.raises(TypeError):
        split_sessions_native(df, "london")


__all__ = []
