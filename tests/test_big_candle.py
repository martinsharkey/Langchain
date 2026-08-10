"""Test the big-candle driver analyzer (offline, injected rates)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.learning.big_candle import BigCandleAnalyzer


def _rates_with_big_up():
    bars, p = [], 2000.0
    for i in range(120):
        o = p
        c = p + (8.0 if i % 11 == 0 and i > 30 else 0.4)   # periodic big up candle
        bars.append({"time": str(i), "timestamp": i, "open": o,
                     "high": max(o, c) + 0.2, "low": min(o, c) - 0.2,
                     "close": c, "volume": 100, "spread": 1})
        p = c
    return bars


def test_big_candle_finds_and_ranks():
    a = BigCandleAnalyzer(lambda r, tf, n: _rates_with_big_up(), lambda s: 0.01).analyze("T", "T")
    assert a.get("n_bars", 0) > 0 and a.get("top_n") == 10
    # biggest candle is one of the +8.0 up moves
    assert a["top"][0]["dir"] == "up" and a["top"][0]["range_pts"] >= 800
    assert 0 <= a["aligned_pct"] <= 100


def test_big_candle_handles_no_rates():
    a = BigCandleAnalyzer(lambda r, tf, n: [], lambda s: 0.01).analyze("T", "T")
    assert "error" in a


if __name__ == "__main__":
    test_big_candle_finds_and_ranks()
    test_big_candle_handles_no_rates()
    print("big candle tests passed")
