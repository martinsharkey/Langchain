"""
Tests for the volatility-scaled trailing stop (the #1 post-mortem fix:
"STOPPED THEN RECOVERED — SL too tight"). Pure TradeManager logic, no MT5/DB.

Verifies:
  * The trail distance respects a volatility floor (SCALP_TRAIL_MIN_ATR x ATR),
    so it can never be tighter than that fraction of ATR — giving a trade the
    breathing room to survive a normal wick and recover.
  * A wider SCALP_TRAIL_MIN_ATR produces a wider trail (tunable lever works).
  * The wick-based distance still wins when it is larger than the ATR floor.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.trading.trade_manager import TradeManager, ManagedState


def _state(atr_points=100.0, action="buy"):
    return ManagedState(
        ticket=1, symbol="TEST", base_symbol="TEST", action=action,
        entry=100.0, volume=0.01, sl=88.0, tp=112.0, point=1.0,
        atr_points=atr_points, variant="TRAIL_ONLY", opened_at=0.0,
        best_price=100.0,
    )


def test_trail_respects_atr_floor():
    """With a tiny wick, the ATR floor (0.5 x ATR) must set the trail distance."""
    mgr = TradeManager()
    st = _state(atr_points=100.0)
    # wick tiny (5), spread tiny (2). Floor = 0.5*100 = 50 should dominate.
    dist = mgr._trail_points(st, spread_points=2.0, wick=5.0)
    assert dist >= 50.0, f"trail {dist} ignored the 0.5xATR=50 volatility floor"


def test_trail_floor_is_tunable(monkeypatch):
    """Raising SCALP_TRAIL_MIN_ATR widens the trail (the optimiser lever)."""
    mgr = TradeManager()
    st = _state(atr_points=100.0)
    monkeypatch.setattr(config, "SCALP_TRAIL_MIN_ATR", 0.9, raising=False)
    dist = mgr._trail_points(st, spread_points=2.0, wick=5.0)
    assert dist >= 90.0, f"trail {dist} did not widen to the tuned 0.9xATR=90 floor"


def test_large_wick_still_wins():
    """When the wick-based distance exceeds the ATR floor, it is used."""
    mgr = TradeManager()
    st = _state(atr_points=100.0)
    # wick 80 * mult 1.3 = 104 > floor 50
    dist = mgr._trail_points(st, spread_points=2.0, wick=80.0)
    assert dist >= 100.0, f"trail {dist} should follow the larger wick-based distance"


def test_personality_override_beats_config(monkeypatch):
    """A learned per-symbol trail_min_atr personality overrides the config default."""
    mgr = TradeManager()
    st = _state(atr_points=100.0)
    monkeypatch.setattr(mgr, "_personality", lambda s: {"trail_min_atr": 1.0}, raising=False)
    dist = mgr._trail_points(st, spread_points=2.0, wick=5.0)
    assert dist >= 100.0, f"trail {dist} ignored personality trail_min_atr=1.0"
