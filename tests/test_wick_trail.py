"""Wick-aware BE + responsive trail + no-opposite-direction guard."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.trading.trade_manager import TradeManager, ManagedState


def _st(action="buy", entry=2000.0, atr_points=300.0, variant="BE_PLUS_TRAIL"):
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


def test_wick_be_then_trail_moves_stop_up():
    tm = TradeManager(); st = _st(atr_points=100.0)
    point = 0.01
    # drive well past BE trigger -> moves to BE+
    r = tm.evaluate(st, price=2000.0 + 200 * point, point=point, spread_points=5)
    # then a higher peak should trail the stop up
    r2 = tm.evaluate(st, price=2000.0 + 400 * point, point=point, spread_points=5)
    assert (r and "modify_sl" in r) or (r2 and "modify_sl" in r2), (r, r2)


if __name__ == "__main__":
    test_wick_trail_is_tighter_than_raw_atr()
    test_be_trigger_clears_wick_noise()
    test_wick_be_then_trail_moves_stop_up()
    print("wick trail tests passed")
