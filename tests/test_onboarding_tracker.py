"""Tests for onboarding_tracker.py."""
import sys, os
import json
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.onboarding_tracker import OnboardingTracker


def test_onboarding_tracker_update_and_status(isolated_data_dir):
    tracker = OnboardingTracker()
    tracker.update("XAUUSD", "backtesting", n_cycles=10)
    rec = tracker.status("XAUUSD")
    assert rec is not None
    assert rec["stage"] == "backtesting"
    assert rec["n_cycles"] == 10


def test_onboarding_tracker_is_done(isolated_data_dir):
    tracker = OnboardingTracker()
    tracker.update("BTCUSD", "baseline_set", hard_sl_points=500.0)
    assert tracker.is_done("BTCUSD") is True
    assert tracker.is_done("ETHUSD") is False


def test_onboarding_tracker_in_progress(isolated_data_dir):
    tracker = OnboardingTracker()
    tracker.update("GER40", "sampling_cycles", n_cycles=5)
    assert tracker.in_progress("GER40") is True
    assert tracker.is_done("GER40") is False


def test_onboarding_tracker_history_cap(isolated_data_dir):
    tracker = OnboardingTracker()
    for i in range(50):
        tracker.update("AUDCAD", "backtesting", n_cycles=i)
    rec = tracker.status("AUDCAD")
    assert len(rec.get("history", [])) <= 40


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
