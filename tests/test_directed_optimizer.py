"""The optimizer must SYSTEMATICALLY explore strength floors + periods (directed
coordinate search), not random-sample 2 of 24 params."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.learning.param_optimizer import ParameterOptimizer, DEFAULTS


def test_directed_search_covers_strength_floors_and_periods():
    opt = ParameterOptimizer(registry=None, backtest_fn=lambda *a, **k: None)
    base = dict(DEFAULTS)
    touched = set()
    for pname, cand in opt._directed_candidates(base):
        touched.add(pname)
    # every signed strength floor must be explored
    for k in ("osma_min_long","osma_max_short","macd_min_long","macd_max_short",
              "bulls_min_long","bears_min_long","bears_max_short","bulls_max_short"):
        assert k in touched, f"directed search never explored {k}"
    # and the periods
    for k in ("osma_fast","osma_slow","osma_signal","ema_period","atr_period","power_period","rsi_period"):
        assert k in touched, f"directed search never explored period {k}"


def test_directed_candidates_actually_change_the_value():
    opt = ParameterOptimizer(registry=None, backtest_fn=lambda *a, **k: None)
    base = dict(DEFAULTS)
    # a strength floor at 0 should get pushed to non-zero candidates
    osma_vals = {c["osma_min_long"] for p, c in opt._directed_candidates(base) if p == "osma_min_long"}
    assert any(v > 0 for v in osma_vals), osma_vals


if __name__ == "__main__":
    test_directed_search_covers_strength_floors_and_periods()
    test_directed_candidates_actually_change_the_value()
    print("directed search tests passed")
