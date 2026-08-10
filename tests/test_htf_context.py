"""
Tests for HTFContext — multi-timeframe alignment + blip-vs-reversal classification.
Uses synthetic bar series (no MT5) so it's deterministic.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.htf_context import HTFContext


def _uptrend(n=120, start=4000.0, step=1.5):
    return [{"close": start + i * step, "high": start + i * step + 0.5,
             "low": start + i * step - 0.5, "open": start + i * step} for i in range(n)]

def _downtrend(n=120, start=4200.0, step=1.5):
    return [{"close": start - i * step, "high": start - i * step + 0.5,
             "low": start - i * step - 0.5, "open": start - i * step} for i in range(n)]


def _fake_rates(mapping):
    """mapping: {tf: bars}. Returns a get_rates(symbol, timeframe, count)."""
    def _g(symbol, timeframe="M15", count=120):
        return mapping.get(timeframe, [])
    return _g


def test_all_htf_aligned_buy():
    tfs_bars = {tf: _uptrend() for tf in ("M5", "M15", "M30", "H1")}
    h = HTFContext(_fake_rates(tfs_bars))
    r = h.read("XAUUSD-ECN", "buy")
    assert r.aligned is True
    assert r.alignment > 0.8      # strong agreement
    assert r.momentum_flipped is False

def test_buy_into_downtrend_flags_reversal():
    tfs_bars = {tf: _downtrend() for tf in ("M5", "M15", "M30", "H1")}
    h = HTFContext(_fake_rates(tfs_bars))
    r = h.read("XAUUSD-ECN", "buy")
    assert r.aligned is False
    assert r.momentum_flipped is True   # HTF momentum is down while we're long

def test_blip_classification_when_aligned():
    # long, all HTF up -> a sudden adverse tick is a BLIP (give room)
    tfs_bars = {tf: _uptrend() for tf in ("M5", "M15", "M30", "H1")}
    h = HTFContext(_fake_rates(tfs_bars))
    assert h.blip_or_reversal("XAUUSD-ECN", "buy") == "blip"

def test_reversal_classification_when_htf_flipped():
    tfs_bars = {tf: _downtrend() for tf in ("M5", "M15", "M30", "H1")}
    h = HTFContext(_fake_rates(tfs_bars))
    assert h.blip_or_reversal("XAUUSD-ECN", "buy") == "reversal"

def test_mixed_htf_is_neutralish():
    tfs_bars = {"M5": _uptrend(), "M15": _uptrend(), "M30": _downtrend(), "H1": _downtrend()}
    h = HTFContext(_fake_rates(tfs_bars))
    r = h.read("XAUUSD-ECN", "buy")
    # split -> not strongly aligned either way
    assert -0.6 <= r.alignment <= 0.6


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"])
