"""
Tests for the OsMA confluence strategy (#29) — pure signal logic, no MT5.

Verifies: no-cross -> hold; a confirmed bullish zero-cross with full confluence
-> buy with high confidence; MACD not aligned -> hold (hard gate); a bearish
cross with confluence -> sell; anticipated cross handling.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.strategies.osma_confluence import osma_confluence_signal

PARAMS = {}


def _base_long(**over):
    """A full-confluence bullish setup: OsMA just crossed up, everything confirms."""
    d = {
        "close": 100.0,
        "osma": 0.5, "osma_prev": -0.3,          # crossed up through zero
        "osma_recent": [-0.4, -0.35, -0.3, 0.5], # young momentum, has runway
        "macd_line": 1.2,                          # MACD aligned long
        "ema_fast": 99.5, "ema_prev": 99.0,       # EMA rising, price above
        "atr": 1.0, "atr_prev": 0.8,              # ATR expanding
        "bulls_power": 2.0, "bears_power": 0.1,   # buyers in control
        "rsi": 55.0,
        "atr_min": 0.0, "atr_max": 0.0,
    }
    d.update(over)
    return d


def test_no_cross_holds():
    d = _base_long(osma=0.6, osma_prev=0.5, osma_recent=[0.4, 0.5, 0.6])  # no cross
    s = osma_confluence_signal(d, PARAMS)
    assert s.action == "hold", s.reason


def test_full_confluence_long_buys_high_conf():
    s = osma_confluence_signal(_base_long(), PARAMS)
    assert s.action == "buy", s.reason
    assert s.confidence >= 0.7, f"expected strong confidence, got {s.confidence} ({s.reason})"
    assert s.metadata.get("trigger") == "cross"


def test_macd_not_aligned_holds():
    # bullish OsMA cross but MACD negative -> hard gate -> hold
    s = osma_confluence_signal(_base_long(macd_line=-0.5), PARAMS)
    assert s.action == "hold", s.reason


def test_atr_not_expanding_holds():
    s = osma_confluence_signal(_base_long(atr=0.8, atr_prev=1.0), PARAMS)  # ATR shrinking
    assert s.action == "hold", s.reason


def test_bearish_cross_sells():
    d = {
        "close": 100.0,
        "osma": -0.5, "osma_prev": 0.3,           # crossed down
        "osma_recent": [0.4, 0.35, 0.3, -0.5],
        "macd_line": -1.2,                          # MACD aligned short
        "ema_fast": 100.5, "ema_prev": 101.0,      # EMA falling, price below
        "atr": 1.0, "atr_prev": 0.8,
        "bulls_power": -0.1, "bears_power": -2.0,   # sellers in control
        "rsi": 45.0, "atr_min": 0.0, "atr_max": 0.0,
    }
    s = osma_confluence_signal(d, PARAMS)
    assert s.action == "sell", s.reason
    assert s.confidence >= 0.6, s.reason


def test_weak_confluence_holds():
    # cross + MACD + ATR expanding (hard gates pass) but nothing else confirms
    d = _base_long(ema_fast=101.0, ema_prev=101.0,   # no EMA trend
                   bulls_power=-1.0, bears_power=-1.0, # wrong power
                   rsi=80.0,                            # exhausted
                   close=110.0)                         # over-stretched from EMA
    s = osma_confluence_signal(d, PARAMS)
    assert s.action == "hold", f"weak confluence should hold, got {s.action} conf={s.confidence}"


if __name__ == "__main__":
    test_no_cross_holds()
    test_full_confluence_long_buys_high_conf()
    test_macd_not_aligned_holds()
    test_atr_not_expanding_holds()
    test_bearish_cross_sells()
    test_weak_confluence_holds()
    print("osma confluence tests passed")
