"""Wick-aware trail helpers + GS_PROVEN BE/trail + no-opposite-direction guard.

The wick helpers (_wick_points / _be_trigger_points / _trail_points) are retained
and still learnable per symbol even though the legacy BE_PLUS_TRAIL/TRAIL_ONLY
management branches were removed (the single live model is GS_PROVEN)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.trading.trade_manager import TradeManager, ManagedState


def _st(action="buy", entry=2000.0, atr_points=300.0, variant="GS_PROVEN"):
    return ManagedState(ticket=1, symbol="XAUUSD-ECN", base_symbol="XAUUSD", action=action,
                        entry=entry, volume=0.01, sl=0.0, tp=0.0, point=0.01,
                        atr_points=atr_points, variant=variant, opened_at=0.0, best_price=entry)


def test_wick_trail_is_tighter_than_raw_atr():
    """Responsive wick trail must be TIGHTER than the old raw-ATR*0.6 trail."""
    tm = TradeManager(); st = _st()
    wick = tm._wick_points(st)                 # ~0.35*300 = 105
    trail = tm._trail_points(st, spread_points=5, wick=wick)   # ~1.3*105 = 136
    old_atr_trail = max(300 * 0.6, 25)         # 180 (old behaviour)
    assert trail < old_atr_trail, (trail, old_atr_trail)


def test_be_trigger_clears_wick_noise():
    """BE trigger must be beyond the wick so we don't get wicked out at BE."""
    tm = TradeManager(); st = _st()
    wick = tm._wick_points(st)
    be = tm._be_trigger_points(st, spread_points=5, wick=wick)
    assert be >= wick, (be, wick)   # must clear the wick


def test_gs_proven_be_then_trail_moves_stop_up():
    """GS_PROVEN: past the BE trigger it locks BE+, then a higher peak trails the stop up."""
    tm = TradeManager(); st = _st(atr_points=100.0)
    point = 0.01
    # GS_PROVEN default be_trigger is 200 pts -> drive to +250 to lock BE+
    r = tm.evaluate(st, price=2000.0 + 250 * point, point=point, spread_points=5)
    assert r and "modify_sl" in r and r.get("remove_tp"), r   # BE+ lock, TP removed
    # then a higher peak should trail the stop up (73pt trail behind best_price)
    r2 = tm.evaluate(st, price=2000.0 + 500 * point, point=point, spread_points=5)
    assert r2 and "modify_sl" in r2 and r2["modify_sl"] > r["modify_sl"], (r, r2)


if __name__ == "__main__":
    test_wick_trail_is_tighter_than_raw_atr()
    test_be_trigger_clears_wick_noise()
    test_gs_proven_be_then_trail_moves_stop_up()
    print("wick trail tests passed")

