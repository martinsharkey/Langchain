"""
GS_PROVEN exit-model coverage (replaces the obsolete generic-giveback tests).

The legacy A/B management arms and the generic retention-ratchet / signal-driven /
giveback guards were REMOVED during the exit-model standardisation. The single
live management model is GS_PROVEN:
  * a WIDE broker SL is set on entry (by the engine);
  * at +be_trigger pts, SL moves to BE + a small locked profit and the broker TP
    is removed (runner uncapped);
  * from then on SL TRAILS behind best_price, only ever tightening (a ratchet).
Plus the always-on hard-adverse ("violent reversal") exit that applies to ALL
variants (NOT gated by variant).

Pure TradeManager.evaluate() logic — no MT5, no DB.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.trading.trade_manager import TradeManager, ManagedState


def _state(entry=2000.0, tp=2100.0, atr_points=100.0, action="buy"):
    return ManagedState(
        ticket=1, symbol="XAUUSD-ECN", base_symbol="XAUUSD", action=action,
        entry=entry, volume=0.01, sl=0.0, tp=tp, point=0.01,
        atr_points=atr_points, variant="GS_PROVEN", opened_at=0.0,
        best_price=entry,
    )


def _mgr():
    # no personality / no experience db -> uses GS_PROVEN defaults
    return TradeManager()


def test_gs_proven_below_be_trigger_does_nothing():
    """Below the BE trigger (200 pts default), GS_PROVEN leaves the broker SL alone."""
    mgr = _mgr()
    st = _state()
    point = 0.01
    intent = mgr.evaluate(st, price=2000.0 + 100 * point, point=point, spread_points=5)
    assert intent is None, intent
    assert not st.moved_to_be


def test_gs_proven_locks_be_and_removes_tp():
    """At/after +be_trigger pts, GS_PROVEN moves SL to BE+ and removes the TP."""
    mgr = _mgr()
    st = _state()
    point = 0.01
    intent = mgr.evaluate(st, price=2000.0 + 250 * point, point=point, spread_points=5)
    assert intent and "modify_sl" in intent and intent.get("remove_tp") is True, intent
    assert st.moved_to_be and st.trail_active
    # BE+ locks a small profit above entry (be_lock 50 pts default)
    assert intent["modify_sl"] > st.entry


def test_gs_proven_trail_only_tightens():
    """After BE lock, a higher peak trails the SL up; a lower peak never loosens it."""
    mgr = _mgr()
    st = _state()
    point = 0.01
    r1 = mgr.evaluate(st, price=2000.0 + 250 * point, point=point, spread_points=5)  # BE lock
    r2 = mgr.evaluate(st, price=2000.0 + 600 * point, point=point, spread_points=5)  # trail up
    assert r2 and "modify_sl" in r2 and r2["modify_sl"] > r1["modify_sl"], (r1, r2)
    prev_sl = st.sl
    # a pullback must NOT move the stop backwards (ratchet)
    r3 = mgr.evaluate(st, price=2000.0 + 500 * point, point=point, spread_points=5)
    assert st.sl == prev_sl, (prev_sl, st.sl, r3)


def test_violent_reversal_hard_exit_applies_to_gs_proven():
    """The always-on hard-adverse failsafe (NOT gated by variant) cuts a TRUE catastrophe,
    but must NOT fire earlier than the intended stop. When no broker SL is set it falls back
    to a WIDE ATR floor (3*ATR) — deliberately wider than normal adverse excursion so it does
    not re-introduce the 'cut losers early / stopped-then-recovered' leak."""
    mgr = _mgr()
    point = 0.01
    # (a) no SL set: a move within the wide ATR floor (3*ATR=300pts) must NOT cut.
    st = _state(atr_points=100.0)
    within = mgr.evaluate(st, price=2000.0 - 250 * point, point=point, spread_points=5)
    assert not (within and "close" in (within or {})), within
    # (b) a genuine catastrophe past the 3*ATR floor DOES cut.
    st2 = _state(atr_points=100.0)
    intent = mgr.evaluate(st2, price=2000.0 - 400 * point, point=point, spread_points=5)
    assert intent and "close" in intent and "violent" in intent["close"], intent


def test_violent_reversal_respects_wide_broker_sl():
    """When an evidence-derived WIDE broker SL is set, the failsafe must NOT fire before it.
    Regression for the 1.5*ATR guard cutting a BTCUSD trade (~3492pts) before its 5405pt SL."""
    mgr = _mgr()
    point = 0.01
    # sell with a wide SL 5405 pts away (evidence-derived); ATR 2328.
    st = ManagedState(
        ticket=9, symbol="BTCUSD", base_symbol="BTCUSD", action="sell",
        entry=63043.71, volume=0.01, sl=63043.71 + 5405 * point, tp=62996.67,
        point=point, atr_points=2328.0, variant="GS_PROVEN", opened_at=0.0,
        best_price=63043.71,
    )
    # 3492 pts adverse (old 1.5*ATR threshold) must NOT cut — inside the wide SL.
    early = mgr.evaluate(st, price=63043.71 + 3492 * point, point=point, spread_points=1700)
    assert not (early and "close" in (early or {})), early
    # only a true overshoot past 1.25*SL (~6756 pts) trips the failsafe.
    st2 = ManagedState(
        ticket=10, symbol="BTCUSD", base_symbol="BTCUSD", action="sell",
        entry=63043.71, volume=0.01, sl=63043.71 + 5405 * point, tp=62996.67,
        point=point, atr_points=2328.0, variant="GS_PROVEN", opened_at=0.0,
        best_price=63043.71,
    )
    catastrophe = mgr.evaluate(st2, price=63043.71 + 7000 * point, point=point, spread_points=1700)
    assert catastrophe and "close" in catastrophe and "violent" in catastrophe["close"], catastrophe


if __name__ == "__main__":
    test_gs_proven_below_be_trigger_does_nothing()
    test_gs_proven_locks_be_and_removes_tp()
    test_gs_proven_trail_only_tightens()
    test_violent_reversal_hard_exit_applies_to_gs_proven()
    print("GS_PROVEN exit tests passed")
