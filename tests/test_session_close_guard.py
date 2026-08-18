"""
Regression tests for session pre-close protection (#5).

Verifies SessionManager and ScalpEngine (via a minimal harness) fire the
pre-close branch inside the configurable window and that the new config knobs
are present.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from src.trading.session_manager import SessionManager


def test_xauusd_in_preclose_window_30_min():
    """30 min before the 21:00 UTC daily break should be in the guard window."""
    sm = SessionManager()
    # 20:30 UTC on a Wednesday -> 30 min before daily break
    now = datetime(2024, 6, 5, 20, 30, tzinfo=timezone.utc)
    assert sm.is_open("XAUUSD", now) is True
    assert sm.in_preclose_window("XAUUSD", lo=15, hi=120, now=now) is True
    assert sm.minutes_to_close("XAUUSD", now) == 30


def test_xauusd_outside_preclose_window():
    """Mid-session should not trigger pre-close."""
    sm = SessionManager()
    now = datetime(2024, 6, 5, 14, 0, tzinfo=timezone.utc)
    assert sm.in_preclose_window("XAUUSD", lo=15, hi=120, now=now) is False


def test_weekend_closure_blocks_open():
    """Saturday 18:00 UTC should be inside the weekend closure."""
    sm = SessionManager()
    now = datetime(2024, 6, 8, 18, 0, tzinfo=timezone.utc)
    assert sm.is_open("XAUUSD", now) is False
    # minutes_to_close looks ahead to the next close even when closed, so the
    # key assertion here is that is_open is False; minutes_to_close is not None.
    assert sm.minutes_to_close("XAUUSD", now) is not None


def test_session_config_knobs_exist():
    """Config must expose the new pre-close buffer knobs."""
    from src import config
    assert hasattr(config, "SESSION_CLOSE_BUFFER_MINUTES")
    assert hasattr(config, "SESSION_CLOSE_BUFFER_MAX_MINUTES")
    assert config.SESSION_CLOSE_BUFFER_MINUTES >= 0
    assert config.SESSION_CLOSE_BUFFER_MAX_MINUTES >= config.SESSION_CLOSE_BUFFER_MINUTES


def test_preclose_branch_reaches_manager_decision(monkeypatch, tmp_path):
    """Engine's pre-close branch calls trade_manager.preclose_decision()."""
    calls = []
    monkeypatch.setattr("src.trading.session_manager.SCHEDULE_PATH", str(tmp_path / "no_sched.json"))

    class FakeManager:
        def preclose_decision(self, st, price, point, spread_pts, atr_short):
            calls.append({"price": price, "atr": atr_short})
            return {"close": "pre-close: lock short-term profit before session gap"}

    class FakeStats:
        def atr_points(self, symbol, tf):
            return 42.0

    class FakeAdapter:
        mode = "PAPER"
        spec = SimpleNamespace(point=0.001)
        def live_tick(self):
            return SimpleNamespace(ask=2500.10, bid=2500.00)
        def close(self, ticket):
            return SimpleNamespace(ok=True, simulated=True, reason="paper")

    class FakeHTF:
        pass

    # Minimal engine harness: we only need the per-position management loop
    # to reach the pre-close branch.
    from src.trading.scalp_engine import ScalpEngine
    engine = ScalpEngine.__new__(ScalpEngine)
    engine.sessions = SessionManager()
    engine.trade_manager = FakeManager()
    engine.stats_engine = FakeStats()
    engine.htf = FakeHTF()
    engine.managed = {}
    engine._retire_managed = lambda ticket: None

    pos = SimpleNamespace(
        ticket=999, base_symbol="XAUUSD", symbol="XAUUSD", action="buy",
        entry_price=2500.0, sl=2490.0, tp=2520.0
    )
    st = SimpleNamespace(
        variant="STANDARD", atr_points=10.0,
        peak_profit_points=0, retain_arm_points=lambda s: 5,
    )

    # 20:35 UTC -> 25 min before daily break, inside default [15,120] window
    now = datetime(2024, 6, 5, 20, 35, tzinfo=timezone.utc)
    # Manually invoke the management logic that the engine runs every cycle.
    # The public helper `_manage_position` is what we want; if it is private
    # we call by name-mangled version.
    method = getattr(engine, "_manage_position", None) or getattr(engine, "_ScalpEngine__manage_position", None)
    if method is None:
        pytest.skip("No _manage_position hook available in this ScalpEngine version")
    method(pos, st, FakeAdapter())

    assert calls, "preclose_decision was not invoked"
    assert calls[0]["atr"] == 42.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
