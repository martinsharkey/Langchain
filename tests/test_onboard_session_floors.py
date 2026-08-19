"""Regression test that onboarding still fits genuinely different per-session floors.

This test only applies to the historical-fit output of the onboarding pipeline,
BEFORE the live-checkpoint bridge flattens it. A live_checkpoint-sourced model.json
is expected to show identical values across sessions because the live engine may not
yet have per-session floors.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from scripts.qmmp import onboard_pipeline as op


def _make_R():
    """Minimal rows DataFrame with enough per-session winners/losers to pass thresholds.

    The floor algorithm computes (mean winner + mean loser)/2 per session and keeps
    it only if applying that floor in the test fold raises net$/trade. We therefore
    craft the data so that filtering out "weak" osma values removes net-negative
    trades in each fold.
    """
    import pandas as pd
    rows = []
    base_t = 1700000000
    # Asian session: UTC hour 1 — winners have high osma, losers low osma.
    # The floor will land between 1.5 and 1.8, keeping winners and dropping losers.
    for i in range(300):
        winner = i % 2 == 0
        rows.append({
            "t": base_t + i * 3600,
            "session": "Asian",
            "side": "long",
            "win": 1 if winner else 0,
            "osma_mag": 2.0 if winner else 0.8,
            "ema_align": 1.0,
            "bulls": 3.0 if winner else 0.0,
            "bears": -0.5,
            "atr": 1.5,
            "usd": 12.0 if winner else -10.0,
        })
    # London session: UTC hour 10 — different distribution so floor differs.
    for i in range(300):
        winner = i % 2 == 0
        rows.append({
            "t": base_t + 10 * 3600 + i * 3600,
            "session": "London",
            "side": "long",
            "win": 1 if winner else 0,
            "osma_mag": 1.2 if winner else -0.3,
            "ema_align": 0.5,
            "bulls": 1.5 if winner else -1.0,
            "bears": -1.0,
            "atr": 1.5,
            "usd": 12.0 if winner else -10.0,
        })
    return pd.DataFrame(rows)


def test_validate_floor_produces_different_session_values():
    """Historical fit must produce different per-session floor values for osma_mag."""
    R = _make_R()
    verdict = op._validate_floor(R, "osma_mag", folds=3)
    val = verdict["value"]
    assert isinstance(val, dict), f"expected dict floor values, got {val!r}"
    assert "Asian" in val and "London" in val, "missing session keys"
    assert val["Asian"] != val["London"], (
        f"per-session floors flattened: Asian={val['Asian']}, London={val['London']}"
    )


def test_onboard_model_floors_detail_source_is_not_live_checkpoint_when_historical():
    """When run from historical data, floors_detail source must not be live_checkpoint."""
    R = _make_R()
    verdict = op._validate_floor(R, "osma_mag", folds=3)
    # The pipeline stores floors_detail under 'floors_detail'; when historical, there is no
    # explicit source key. A live_checkpoint bridge would set source='live_checkpoint'.
    assert verdict.get("source", "historical") != "live_checkpoint"


def test_session_of_uses_canonical_precedence():
    """Ensure onboard session_of matches the canonical session_of precedence."""
    from src.strategies.sessions import session_of as canonical_session_of
    # base is 2023-11-14 22:00 UTC; add offsets so the UTC hour equals the canonical hour
    base = 1700000000
    for canonical_hour in (15, 12, 7, 2):
        # compute epoch offset that yields that UTC hour from the base timestamp
        offset = (canonical_hour - datetime.fromtimestamp(base, timezone.utc).hour) % 24
        ep = base + offset * 3600
        assert datetime.fromtimestamp(ep, timezone.utc).hour == canonical_hour
        assert op.session_of(ep) == canonical_session_of(canonical_hour)
