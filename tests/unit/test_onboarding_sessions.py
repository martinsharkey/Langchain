"""Unit tests for the onboarding session taxonomy."""

import pandas as pd
import pytest

from src.onboarding.sessions import (
    SESSION_DEFINITIONS,
    all_session_keys,
    filter_session,
    get_session,
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


def test_filter_session_london():
    idx = pd.date_range("2026-08-03", periods=24 * 60, freq="1min")  # Monday
    df = pd.DataFrame({"close": range(len(idx))}, index=idx)
    sdf = filter_session(df, "london")
    assert len(sdf) == 540
    assert sdf.index.hour.min() >= 8
    assert sdf.index.hour.max() < 17


def test_filter_session_weekend():
    idx = pd.date_range("2026-08-08", periods=48 * 60, freq="1min")  # Sat-Sun
    df = pd.DataFrame({"close": range(len(idx))}, index=idx)
    sdf = filter_session(df, "weekend")
    assert len(sdf) == len(df)


def test_filter_session_sunday_open():
    # Sunday 22:00-24:00 UTC
    idx = pd.date_range("2026-08-09", periods=24 * 60, freq="1min")  # Sunday
    df = pd.DataFrame({"close": range(len(idx))}, index=idx)
    sdf = filter_session(df, "sunday_open")
    assert len(sdf) == 120  # 2 hours


def test_filter_session_friday_close():
    # Friday 21:00-22:00 UTC
    idx = pd.date_range("2026-08-07", periods=24 * 60, freq="1min")  # Friday
    df = pd.DataFrame({"close": range(len(idx))}, index=idx)
    sdf = filter_session(df, "friday_close")
    assert len(sdf) == 60  # 1 hour


def test_filter_session_requires_datetime_index():
    df = pd.DataFrame({"close": [1, 2, 3]})
    with pytest.raises(TypeError):
        filter_session(df, "london")


def test_post_market_open_15_minutes():
    # Monday 22:00-23:00 UTC, 1-minute bars.
    idx = pd.date_range("2026-08-03 22:00", periods=60, freq="1min")
    df = pd.DataFrame({"close": range(len(idx))}, index=idx)
    sdf = filter_session(df, "post_market_open_15")
    assert len(sdf) == 15
    assert sdf.index.minute.min() == 0
    assert sdf.index.minute.max() == 14


def test_post_market_open_30_minutes():
    idx = pd.date_range("2026-08-03 22:00", periods=60, freq="1min")
    df = pd.DataFrame({"close": range(len(idx))}, index=idx)
    sdf = filter_session(df, "post_market_open_30")
    assert len(sdf) == 30
    assert sdf.index.minute.max() == 29


def test_post_market_open_60_minutes():
    idx = pd.date_range("2026-08-03 22:00", periods=60, freq="1min")
    df = pd.DataFrame({"close": range(len(idx))}, index=idx)
    sdf = filter_session(df, "post_market_open_60")
    assert len(sdf) == 60


def test_post_market_open_variants_differ():
    idx = pd.date_range("2026-08-03 22:00", periods=60, freq="1min")
    df = pd.DataFrame({"close": range(len(idx))}, index=idx)
    assert len(filter_session(df, "post_market_open_15")) == 15
    assert len(filter_session(df, "post_market_open_30")) == 30
    assert len(filter_session(df, "post_market_open_60")) == 60
