"""Tests for ChangeValidator cold-start acceptance and session-scored proposals."""
import sys, os
import json
import pytest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.change_validator import ChangeValidator


def _mock_bt(session_scores=None):
    """Backtest that generalizes with aggregate PF 1.03."""
    sess = session_scores or {
        "Asian": {"trades": 30, "wins": 10, "losses": 20, "gross_win_r": 15.0, "gross_loss_r": 20.0, "pf": 0.75, "wr": 33.3},
        "London": {"trades": 80, "wins": 40, "losses": 40, "gross_win_r": 50.0, "gross_loss_r": 40.0, "pf": 1.25, "wr": 50.0},
        "NewYork": {"trades": 50, "wins": 28, "losses": 22, "gross_win_r": 32.0, "gross_loss_r": 22.0, "pf": 1.45, "wr": 56.0},
    }

    def bt(symbol, params, sl_atr=1.0, tp_rr=2.0):
        return {
            "pfs": [1.05, 1.08, 1.03],
            "wrs": [52.0, 54.0, 51.0],
            "n_total": 160,
            "generalizes": True,
            "score": 1.03,
            "session_scores": sess,
        }
    return bt


def test_validate_cold_start_accepts_first_generalizing(tmp_path):
    """With no best-ever recorded, a generalizing candidate should pass."""
    cv = ChangeValidator(backtest_fn=_mock_bt())
    cv._path = str(tmp_path / "best.json")
    cv._best = {}

    out = cv.validate("XAUUSD", {"osma_fast": 12}, source="cold_start_test")
    assert out["passed"] is True
    assert out["score"] == 1.03
    assert out["reason"] == "cold-start accept (no valid incumbent)"


def test_validate_rejects_when_no_best_but_does_not_generalize(tmp_path):
    """Cold-start only helps if the candidate actually generalizes."""
    def bad_bt(symbol, params, sl_atr=1.0, tp_rr=2.0):
        return {"pfs": [0.9, 0.95, 0.92], "wrs": [45.0, 47.0, 46.0],
                "n_total": 100, "generalizes": False, "score": 0.9,
                "session_scores": {}}

    cv = ChangeValidator(backtest_fn=bad_bt)
    cv._path = str(tmp_path / "best.json")
    cv._best = {}

    out = cv.validate("XAUUSD", {"osma_fast": 12}, source="bad_candidate")
    assert out["passed"] is False
    assert "does not generalize" in out["reason"]


def test_validate_session_scoped_rejects_weak_session(tmp_path):
    """A session-scoped proposal whose session PF < 1 must be rejected, even if
    the aggregate forward PF is healthy."""
    cv = ChangeValidator(backtest_fn=_mock_bt())
    cv._path = str(tmp_path / "best.json")
    # Seed a best-ever so cold-start doesn't mask the session check
    cv._best = {"XAUUSD": {"score": 1.0, "source": "seed",
                           "at": datetime.now(timezone.utc).isoformat()}}

    out = cv.validate("XAUUSD", {"session_Asian": {"osma_min_long": 0.5}},
                      source="session_asian")
    assert out["passed"] is False
    assert out["session_primary"] == "Asian"
    assert "Asian PF 0.75 < 1" in out["reason"]


def test_validate_session_scoped_passes_strong_session(tmp_path):
    """A session-scoped proposal whose session PF >= 1 and beats best-ever passes."""
    cv = ChangeValidator(backtest_fn=_mock_bt())
    cv._path = str(tmp_path / "best.json")
    cv._best = {"XAUUSD": {"score": 1.0, "source": "seed",
                           "at": datetime.now(timezone.utc).isoformat()}}

    out = cv.validate("XAUUSD", {"session_London": {"osma_min_long": 0.5}},
                      source="session_london")
    assert out["passed"] is True
    assert out["session_primary"] == "London"
    assert out["score"] == 1.25


def test_validate_session_scoped_cold_start(tmp_path):
    """Session-scoped proposal with no best-ever should cold-start accept."""
    cv = ChangeValidator(backtest_fn=_mock_bt())
    cv._path = str(tmp_path / "best.json")
    cv._best = {}

    out = cv.validate("XAUUSD", {"session_NewYork": {"osma_min_long": 0.5}},
                      source="session_ny")
    assert out["passed"] is True
    assert out["session_primary"] == "NewYork"
    assert "cold-start" in out["reason"]


def test_validate_session_scoped_case_insensitive(tmp_path):
    """Session name matching should be case-insensitive (session_asian -> Asian).
    Use London (PF 1.25) so the proposal passes and we can verify session_primary."""
    cv = ChangeValidator(backtest_fn=_mock_bt())
    cv._path = str(tmp_path / "best.json")
    cv._best = {}

    out = cv.validate("XAUUSD", {"session_london": {"osma_min_long": 0.5}},
                      source="session_lower")
    assert out["passed"] is True
    assert out["session_primary"] == "London"


def test_validate_cold_start_when_best_ever_does_not_generalize(tmp_path):
    """If the stored best-ever params fail generalizes, treat as cold-start
    and accept the first generalizing candidate."""
    def weak_bt(symbol, params, sl_atr=1.0, tp_rr=2.0):
        # Best-ever params (osma_fast=12) don't generalize; candidate (osma_fast=15) does
        if params.get("osma_fast") == 12:
            return {
                "pfs": [0.9, 0.95, 0.92],
                "wrs": [45.0, 47.0, 46.0],
                "n_total": 100,
                "generalizes": False,
                "score": 0.9,
                "session_scores": {},
            }
        return {
            "pfs": [1.05, 1.08, 1.03],
            "wrs": [52.0, 54.0, 51.0],
            "n_total": 160,
            "generalizes": True,
            "score": 1.03,
            "session_scores": {
                "Asian": {"trades": 30, "wins": 10, "losses": 20, "gross_win_r": 15.0, "gross_loss_r": 20.0, "pf": 0.75, "wr": 33.3},
                "London": {"trades": 80, "wins": 40, "losses": 40, "gross_win_r": 50.0, "gross_loss_r": 40.0, "pf": 1.25, "wr": 50.0},
                "NewYork": {"trades": 50, "wins": 28, "losses": 22, "gross_win_r": 32.0, "gross_loss_r": 22.0, "pf": 1.45, "wr": 56.0},
            },
        }

    cv = ChangeValidator(backtest_fn=weak_bt)
    cv._path = str(tmp_path / "best.json")
    # Seed a best-ever with a non-generalizing config
    cv._best = {"XAUUSD": {"score": 0.9, "source": "seed",
                           "at": datetime.now(timezone.utc).isoformat(),
                           "params": {"osma_fast": 12}}}

    # Now a generalizing candidate should be accepted (cold-start)
    out = cv.validate("XAUUSD", {"osma_fast": 15}, source="cold_start_fix")
    assert out["passed"] is True
    assert "cold-start" in out["reason"]


def test_validate_rejects_when_best_ever_valid_and_candidate_weak(tmp_path):
    """If best-ever generalizes and candidate doesn't, reject normally."""
    def weak_bt(symbol, params, sl_atr=1.0, tp_rr=2.0):
        return {
            "pfs": [0.9, 0.95, 0.92],
            "wrs": [45.0, 47.0, 46.0],
            "n_total": 100,
            "generalizes": False,
            "score": 0.9,
            "session_scores": {},
        }

    cv = ChangeValidator(backtest_fn=weak_bt)
    cv._path = str(tmp_path / "best.json")
    cv._best = {"XAUUSD": {"score": 1.05, "source": "seed",
                           "at": datetime.now(timezone.utc).isoformat(),
                           "params": {"osma_fast": 12}}}

    out = cv.validate("XAUUSD", {"osma_fast": 15}, source="weak_candidate")
    assert out["passed"] is False
    assert "does not generalize" in out["reason"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
