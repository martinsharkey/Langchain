"""
Test ExcursionAnalyzer (#41): measures OsMA-cycle peak/trough/wick per symbol and
returns a symbol-specific exit recommendation. Synthetic oscillating rates; no MT5.
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.excursion_analyzer import ExcursionAnalyzer


def _rates(n=3000):
    out = []
    price = 1000.0
    for i in range(n):
        price = max(1.0, price + math.sin(i / 30.0) * 4.0 + math.sin(i / 2.0) * 0.6)
        out.append({"time": i * 60, "open": price - 0.2, "high": price + 2.0,
                    "low": price - 2.0, "close": price})
    return out


class _RP:
    def __call__(self, symbol, timeframe="M1", count=1000):
        return _rates(count)


def test_measure_returns_excursion_and_recommendation():
    ea = ExcursionAnalyzer(_RP())
    r = ea.measure("SYNTH", point=0.01, bars=3000)
    assert r["found"], r
    assert r["osma_cycles"] >= 5
    assert r["median_peak_pts"] > 0 and r["median_trough_pts"] >= 0
    rec = r["recommendation"]
    assert rec["suggested_stop_pts"] > 0
    assert rec["suggested_sl_atr"] is not None and rec["suggested_tp_rr"] is not None


def test_insufficient_rates():
    class _Empty:
        def __call__(self, s, timeframe="M1", count=1000): return []
    r = ExcursionAnalyzer(_Empty()).measure("SYNTH")
    assert r["found"] is False


def test_point_inference():
    assert ExcursionAnalyzer._infer_point("BTCUSD", [63000]) == 0.01
    assert ExcursionAnalyzer._infer_point("EURUSD", [1.08]) == 0.0001
    assert ExcursionAnalyzer._infer_point("USDJPY", [150.0]) == 0.001


if __name__ == "__main__":
    test_measure_returns_excursion_and_recommendation()
    test_insufficient_rates()
    test_point_inference()
    print("excursion analyzer tests passed")
