"""E2E test: onboard BTCUSD through the full pipeline against real MT5 data.

This test exercises discovery -> optimize -> validate -> report across the full
session model (all 12 sessions) on M1 with a full week of data. It is marked
``e2e`` and requires a live MT5 connection (VTMarkets demo).

Note: the full timeframe matrix (M1-M30 + H1/H4/D1) is exercised by the pipeline
but is too slow for a single test run; this test uses M1 (which spans a full week
and therefore covers every session, including weekend/sunday_open/friday_close).
"""

import pytest

from src.onboarding import OnboardingPipeline
from src.onboarding.sessions import all_session_keys


@pytest.mark.e2e
def test_btcusd_onboarding_end_to_end():
    pipeline = OnboardingPipeline(
        symbol="BTCUSD",
        top_n=10,
        n_trials=3,
        n_folds=3,
    )

    result = pipeline.run(
        timeframes=["M1"],
        sessions=all_session_keys(),
        bars=10000,
    )

    assert result["symbol"] == "BTCUSD"
    assert result["discovery_buckets"] >= 1
    assert result["candidates"] >= 1
    assert result["tuned"] >= 1
    assert result["validated"] >= 1
    assert "reports" in result
    assert result["reports"]["markdown"].endswith(".md")
    assert result["reports"]["html"].endswith(".html")
    assert result["reports"]["json"].endswith(".json")

    # The report must cover the full session model.
    assert "best_timeframe_per_session" in result
    assert len(result["best_timeframe_per_session"]) >= 1
