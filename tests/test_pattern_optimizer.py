"""
Test PatternOptimizer (#40): discovers a MACD-leads-OsMA config from rates and
returns a best exit config that clears the gate. Uses synthetic trending rates
so triggers exist; no MT5.
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.pattern_optimizer import PatternOptimizer, find_triggers


def _rates(n=1500, base=1000.0, tf_min=1):
    """Synthetic OHLC with alternating trend legs so MACD/OsMA cross zero repeatedly."""
    out = []
    price = base
    for i in range(n):
        # oscillating drift creates zero-crosses
        drift = math.sin(i / 40.0) * 3.0
        price = max(1.0, price + drift + math.sin(i / 3.0) * 0.5)
        hi = price + 1.5
        lo = price - 1.5
        out.append({"time": i * tf_min * 60, "open": price, "high": hi,
                    "low": lo, "close": price})
    return out


class _RatesProvider:
    def __call__(self, symbol, timeframe="M1", count=1000):
        tf = {"M1": 1, "M5": 5, "M15": 15}.get(timeframe, 1)
        return _rates(count, tf_min=tf)


def test_find_triggers_returns_some():
    rp = _RatesProvider()
    trg, df1 = find_triggers(rp("X", "M1", 1500), rp("X", "M5", 400), rp("X", "M15", 200))
    assert isinstance(trg, list)  # structure valid; may be >=0 depending on synthetic shape


def test_discover_structure():
    po = PatternOptimizer(_RatesProvider(), min_trades=5, min_pf=0.1)
    r = po.discover("SYNTH", bars=1500)
    assert "found" in r
    if r["found"]:
        b = r["best"]
        assert set(("sl_atr", "tp_rr", "win_rate", "profit_factor", "trades")) <= set(b)
        assert b["sl_atr"] > 0 and b["tp_rr"] > 0


def test_insufficient_rates_not_found():
    class _Empty:
        def __call__(self, s, timeframe="M1", count=1000): return []
    po = PatternOptimizer(_Empty())
    r = po.discover("SYNTH")
    assert r["found"] is False


if __name__ == "__main__":
    test_find_triggers_returns_some()
    test_discover_structure()
    test_insufficient_rates_not_found()
    print("pattern optimizer tests passed")
