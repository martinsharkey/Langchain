"""
Tests for the profit-retention ratchet + reversal-signature capture/analysis.
Pure logic; no MT5.
"""
import sys, os, tempfile, sqlite3, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.trading.trade_manager import TradeManager, ManagedState
from src.learning.experience_db import ExperienceDatabase
from src.learning.reversal_signature import ReversalSignatureAnalyzer


def _state(action="buy", entry=2000.0, atr_points=300.0):
    return ManagedState(ticket=1, symbol="XAUUSD-ECN", base_symbol="XAUUSD", action=action,
                        entry=entry, volume=0.01, sl=0.0, tp=0.0, point=0.01,
                        atr_points=atr_points, variant="TRAIL_ONLY", opened_at=0.0,
                        best_price=entry)


def test_retention_ratchet_cuts_after_giving_back_floor():
    """Peak 400 pts (arm at 0.8*ATR=240), floor 0.5 -> must cut once profit <= 200 pts."""
    tm = TradeManager()
    st = _state()
    point = 0.01
    # drive to a 400-pt peak: price = entry + 400*point
    tm.evaluate(st, price=2000.0 + 400 * point, point=point, spread_points=5)
    assert st.peak_profit_points >= 400
    # still well above floor (300 pts) -> no ratchet exit
    r = tm.evaluate(st, price=2000.0 + 300 * point, point=point, spread_points=5)
    assert not (r and "retention" in str(r.get("close", "")))
    # drop to 150 pts (<= 200 floor) -> ratchet must fire
    r = tm.evaluate(st, price=2000.0 + 150 * point, point=point, spread_points=5)
    assert r and "close" in r and "retention" in r["close"], r


def test_retention_ratchet_does_not_arm_below_threshold():
    """A small peak (below 0.8*ATR) must not arm the ratchet."""
    tm = TradeManager()
    st = _state(atr_points=300.0)   # arm ~240 pts
    point = 0.01
    tm.evaluate(st, price=2000.0 + 100 * point, point=point, spread_points=5)  # peak 100 < 240
    r = tm.evaluate(st, price=2000.0 + 10 * point, point=point, spread_points=5)
    assert not (r and "retention" in str(r.get("close", ""))), r


def test_peak_indicator_snapshot_captured_on_new_peak():
    """evaluate() must snapshot the indicators at the moment of a new MFE peak."""
    tm = TradeManager()
    st = _state()
    point = 0.01
    tm.evaluate(st, price=2000.0 + 100 * point, point=point, spread_points=5,
                indicators={"osma": 0.9, "macd_histogram": 0.5, "rsi": 68, "bulls_power": 1.2,
                            "bears_power": 0.3, "macd_line": 0.7, "atr": 3.0})
    assert st.peak_indicators.get("osma") == 0.9
    # a LOWER-profit later bar must NOT overwrite the peak snapshot
    tm.evaluate(st, price=2000.0 + 50 * point, point=point, spread_points=5,
                indicators={"osma": 0.2, "rsi": 55})
    assert st.peak_indicators.get("osma") == 0.9   # unchanged
    assert st.last_indicators.get("osma") == 0.2   # last is updated


def test_signature_from_captured_reads_snapshots():
    """The analyzer aggregates entry/peak/exit snapshots from the DB."""
    with tempfile.TemporaryDirectory() as d:
        db = ExperienceDatabase(db_path=os.path.join(d, "t.db"))
        # record a trade with entry snapshot, then attach peak/exit signatures
        tid = db.record_trade(
            signal={"symbol": "XAUUSD", "action": "buy", "price": 2000, "strategy_used": "OsMA_Confluence"},
            indicators={"osma": 0.2, "macd_histogram": 0.1, "rsi": 55, "bulls_power": 0.5,
                        "bears_power": 0.1, "macd_line": 0.3, "atr": 3.0, "close": 2000},
            outcome="pending")
        db.update_trade_outcome(trade_id=tid, outcome="win", profit_loss=4.0, exit_price=2004.0,
                                mfe_points=400, mae_points=-30, exit_points=150)
        # at peak osma was high; at exit it shrank toward zero (the reversal tell)
        db.update_trade_signature(tid,
            peak_indicators={"osma": 1.1, "macd_histogram": 0.6, "rsi": 71, "bulls_power": 1.4,
                             "bears_power": 0.4, "macd_line": 0.9, "atr": 3.2},
            exit_indicators={"osma": 0.2, "macd_histogram": 0.1, "rsi": 58, "bulls_power": 0.5,
                             "bears_power": 0.2, "macd_line": 0.4, "atr": 3.1})
        an = ReversalSignatureAnalyzer(db, point_fn=lambda s: 0.01)
        sig = an.signature_from_captured("XAUUSD", min_mfe_points=100.0)
        assert sig["_meta"]["n_trades"] == 1
        # osma retained fraction at exit = |0.2| / |1.1| ~ 0.18 (shrank toward neutral)
        assert sig["osma"]["median_retained_frac"] is not None
        assert sig["osma"]["median_retained_frac"] < 0.5
        assert sig["osma"]["shrank_toward_neutral_pct"] == 100.0
        # per-symbol scale is captured (peak magnitude over ATR)
        assert sig["osma"]["median_peak_over_atr"] is not None
        # capture ratio = exit_points/mfe = 150/400
        assert abs(sig["_meta"]["median_capture_ratio"] - 0.375) < 1e-6


def _proven_signature(shrink_pct=80.0, retained=0.5):
    """A signature where osma + macd_histogram reliably shrink toward neutral at exit.
    Scale-free: median_retained_frac is THIS symbol's learned reversal depth."""
    return {
        "osma": {"shrank_toward_neutral_pct": shrink_pct, "median_retained_frac": retained, "n": 30},
        "macd_histogram": {"shrank_toward_neutral_pct": shrink_pct, "median_retained_frac": retained, "n": 30},
        "_meta": {"n_trades": 30, "median_capture_ratio": 0.4},
    }


def test_signal_exit_fires_when_momentum_rolls_over():
    """With a proven signature, if live OsMA/MACD-hist have collapsed from peak while
    still >50% of peak profit, take the signal exit (earlier than blind giveback)."""
    tm = TradeManager()
    st = _state(atr_points=300.0)
    point = 0.01
    # peak at 400 pts with strong momentum
    tm.evaluate(st, price=2000.0 + 400 * point, point=point, spread_points=5,
                indicators={"osma": 1.0, "macd_histogram": 0.6})
    # pull back to 280 pts (70% of peak, above the 50% ratchet floor) with momentum collapsed
    r = tm.evaluate(st, price=2000.0 + 280 * point, point=point, spread_points=5,
                    indicators={"osma": 0.2, "macd_histogram": 0.1},
                    reversal_signature=_proven_signature())
    assert r and "close" in r and "reversal signal" in r["close"], r


def test_signal_hold_when_momentum_still_supported():
    """If momentum is still near its peak, the trade should NOT signal-exit (ride)."""
    tm = TradeManager()
    st = _state(atr_points=300.0)
    point = 0.01
    tm.evaluate(st, price=2000.0 + 400 * point, point=point, spread_points=5,
                indicators={"osma": 1.0, "macd_histogram": 0.6})
    r = tm.evaluate(st, price=2000.0 + 360 * point, point=point, spread_points=5,
                    indicators={"osma": 0.95, "macd_histogram": 0.58},
                    reversal_signature=_proven_signature())
    assert not (r and "reversal signal" in str(r.get("close", ""))), r
    assert st.signal_hold is True


def test_signal_ignored_when_signature_unproven():
    """An unreliable signature (low shrink%) must NOT trigger a signal exit."""
    tm = TradeManager()
    st = _state(atr_points=300.0)
    point = 0.01
    tm.evaluate(st, price=2000.0 + 400 * point, point=point, spread_points=5,
                indicators={"osma": 1.0, "macd_histogram": 0.6})
    r = tm.evaluate(st, price=2000.0 + 280 * point, point=point, spread_points=5,
                    indicators={"osma": 0.2, "macd_histogram": 0.1},
                    reversal_signature=_proven_signature(shrink_pct=20.0))  # unreliable
    assert not (r and "reversal signal" in str(r.get("close", ""))), r


def test_reversal_tell_is_scale_free_across_symbols():
    """The SAME proportional reversal must read identically whether the indicators
    are on gold's scale (~1) or BTC's scale (~50). Proves per-symbol scale-independence."""
    tm = TradeManager()
    sig = _proven_signature(retained=0.5)
    # gold-scale: peak osma 1.0 -> live 0.2 (ratio 0.2, below 0.5 learned floor)
    st_g = _state(atr_points=300.0)
    tm.evaluate(st_g, price=2000.0 + 400 * 0.01, point=0.01, spread_points=5,
                indicators={"osma": 1.0, "macd_histogram": 0.6})
    tell_g = tm._reversal_tell(st_g, {"osma": 0.2, "macd_histogram": 0.12}, sig)
    # BTC-scale: peak osma 50 -> live 10 (SAME ratio 0.2)
    st_b = _state(atr_points=300.0)
    tm.evaluate(st_b, price=2000.0 + 400 * 0.01, point=0.01, spread_points=5,
                indicators={"osma": 50.0, "macd_histogram": 30.0})
    tell_b = tm._reversal_tell(st_b, {"osma": 10.0, "macd_histogram": 6.0}, sig)
    assert tell_g == tell_b == "rolling_over", (tell_g, tell_b)


if __name__ == "__main__":
    test_retention_ratchet_cuts_after_giving_back_floor()
    test_retention_ratchet_does_not_arm_below_threshold()
    test_peak_indicator_snapshot_captured_on_new_peak()
    test_signature_from_captured_reads_snapshots()
    test_signal_exit_fires_when_momentum_rolls_over()
    test_signal_hold_when_momentum_still_supported()
    test_signal_ignored_when_signature_unproven()
    test_reversal_tell_is_scale_free_across_symbols()
    print("reversal + ratchet tests passed")
