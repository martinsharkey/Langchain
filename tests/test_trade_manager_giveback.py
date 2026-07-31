"""
Tests for the giveback/exit fix (issue: winners cut early).

Pure TradeManager.evaluate() logic — no MT5, no DB. Verifies:
  * The giveback guard does NOT arm on a small profit (arm threshold raised to
    ~1.5x ATR), so normal trades are left to reach their TP.
  * A trade still well short of a large TP is not scratched on a moderate
    pullback (TP-awareness requires a big giveback below 60% of TP).
  * A genuinely large winner that gives back most of its peak IS closed.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.trading.trade_manager import TradeManager, ManagedState


def _state(entry=100.0, tp=112.0, atr_points=100.0, action="buy"):
    return ManagedState(
        ticket=1, symbol="TEST", base_symbol="TEST", action=action,
        entry=entry, volume=0.01, sl=88.0, tp=tp, point=1.0,
        atr_points=atr_points, variant="TRAIL_ONLY", opened_at=0.0,
        best_price=entry,
    )


def _mgr():
    # no personality / no experience db -> uses config defaults
    return TradeManager()


def test_small_profit_does_not_arm_giveback():
    """A modest profit (< arm threshold) must never trigger a giveback close."""
    mgr = _mgr()
    st = _state(atr_points=100.0)  # arm ~ 1.5*100 = 150 pts
    # push to +80pts peak then pull back to +30pts (a big % giveback, but small $)
    mgr.evaluate(st, price=180.0, point=1.0, spread_points=2.0)   # peak +80
    intent = mgr.evaluate(st, price=130.0, point=1.0, spread_points=2.0)  # back to +30
    assert not (intent and intent.get("close")), (
        f"giveback armed on a small (+80pt) peak below the ~150pt arm threshold: {intent}"
    )


def test_winner_short_of_tp_not_scratched_on_moderate_pullback():
    """A winner that peaked well short of a large TP keeps running on a moderate pullback."""
    mgr = _mgr()
    # TP is +1200pts away; ATR 100 -> arm ~150. Peak +300 (25% of TP), pull to +200.
    st = _state(entry=100.0, tp=1300.0, atr_points=100.0)
    mgr.evaluate(st, price=400.0, point=1.0, spread_points=2.0)   # peak +300
    intent = mgr.evaluate(st, price=300.0, point=1.0, spread_points=2.0)  # gave back 33%
    assert not (intent and intent.get("close")), (
        f"scratched a winner still far from TP on a 33% pullback: {intent}"
    )


def test_large_winner_giving_back_most_is_closed():
    """A big winner (peak >> arm, and gives back a large fraction) IS cut."""
    mgr = _mgr()
    # small TP so peak exceeds 60% of TP (TP-awareness relaxed), big giveback.
    st = _state(entry=100.0, tp=250.0, atr_points=100.0)  # TP +150pts
    mgr.evaluate(st, price=400.0, point=1.0, spread_points=2.0)   # peak +300 (>arm, >TP)
    intent = mgr.evaluate(st, price=180.0, point=1.0, spread_points=2.0)  # gave back 73%
    assert intent and intent.get("close"), (
        "a large winner that gave back 73% of a +300pt peak should be closed"
    )


if __name__ == "__main__":
    test_small_profit_does_not_arm_giveback()
    test_winner_short_of_tp_not_scratched_on_moderate_pullback()
    test_large_winner_giving_back_most_is_closed()
    print("all giveback tests passed")
