"""
Tests for TradePostMortem reflection maths (pure, no MT5/DB needed).

Verifies the excursion-based failure-mode detection:
  * exited-early detection (non-win but big MFE)
  * stopped-then-recovered
  * entered-late (adverse move dominates)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.post_mortem import TradePostMortem, TradeReflection


def _synthetic_after(action, entry, mfe_atr, mae_atr, atr):
    """Build M1 bars that produce a target MFE/MAE for a direction."""
    if action == "buy":
        hi = entry + mfe_atr * atr
        lo = entry - mae_atr * atr
    else:
        lo = entry - mfe_atr * atr
        hi = entry + mae_atr * atr
    # a few bars spanning that range
    return [{"time": i, "open": entry, "high": hi, "low": lo, "close": entry}
            for i in range(10)]


class _FakePM(TradePostMortem):
    """Override bar access to inject synthetic bars for deterministic tests."""
    def __init__(self, after_bars, atr):
        self._after = after_bars; self._atr = atr
    def _bars_range(self, symbol, tf_const, start_dt, end_dt):
        # 'after' window returns injected bars; before/htf minimal
        return self._after
    def _atr_estimate(self, bars):
        return self._atr


def _trade(action="buy", entry=4000.0, outcome="loss"):
    import datetime as dt
    return {"id": 1, "timestamp": dt.datetime(2026,7,31,12,0).isoformat(),
            "symbol": "XAUUSD-ECN", "action": action, "entry_price": entry, "outcome": outcome,
            "profit_loss": -1.0}


def test_exited_early_detected():
    atr = 2.0
    # loss but price ran 2.0 ATR our way afterwards -> exited early
    pm = _FakePM(_synthetic_after("buy", 4000, mfe_atr=2.0, mae_atr=0.5, atr=atr), atr)
    r = pm.reflect_trade(_trade("buy", 4000, "loss"))
    assert r.mfe_atr >= 1.5
    assert r.exited_early is True

def test_entered_late_detected():
    atr = 2.0
    # immediate big adverse move, little favourable -> entered late
    pm = _FakePM(_synthetic_after("buy", 4000, mfe_atr=0.2, mae_atr=2.0, atr=atr), atr)
    r = pm.reflect_trade(_trade("buy", 4000, "loss"))
    assert r.entered_late is True

def test_stopped_then_recovered():
    atr = 2.0
    pm = _FakePM(_synthetic_after("sell", 4000, mfe_atr=1.2, mae_atr=1.2, atr=atr), atr)
    r = pm.reflect_trade(_trade("sell", 4000, "loss"))
    assert r.stopped_then_recovered is True

def test_clean_winner_no_flags():
    atr = 2.0
    pm = _FakePM(_synthetic_after("buy", 4000, mfe_atr=2.5, mae_atr=0.2, atr=atr), atr)
    r = pm.reflect_trade(_trade("buy", 4000, "win"))
    assert r.exited_early is False   # it won, not an early-exit failure
    assert r.entered_late is False


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"])
