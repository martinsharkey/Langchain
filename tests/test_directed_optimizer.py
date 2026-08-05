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
    # and the newly-added tunables (RSI gate + MACD-lead window)
    for k in ("rsi_long_max","rsi_short_min","macd_lead_bars"):
        assert k in touched, f"directed search never explored {k}"


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


def test_gold_proven_edge_baseline_is_the_starting_point():
    """Gold must start from the mined GoldShark proven-edge baseline (non-zero strength
    floors + osma_slow 86), not generic zeros — so the directed optimizer refines a
    config that already had an edge."""
    from src.learning.param_optimizer import ParameterOptimizer, SYMBOL_BASELINES
    assert "XAUUSD" in SYMBOL_BASELINES
    o = ParameterOptimizer(registry=None, backtest_fn=lambda *a, **k: None)
    o.tuned = {}   # fresh clone, no tuned file
    p = o.current_params("XAUUSD-ECN")
    assert p["osma_slow"] == 26, p            # pass5469 proven period
    assert p["osma_min_long"] > 0, p          # non-zero strength floor (edge, not sign-only)
    assert p["bulls_min_long"] > 0, p
    assert p["osma_max_short"] < 0, p         # short floor is negative
    # a symbol without a baseline still gets generic defaults (floors off)
    # BTC magnitude floors stay per-symbol (0 until backtested) — gold's magnitudes are
    # XAUUSD-specific and must NOT be borrowed. It DOES inherit shared STRUCTURE.
    assert o.current_params("BTCUSD")["osma_min_long"] == 0.0
    assert o.current_params("BTCUSD")["min_confluence"] == SYMBOL_BASELINES["XAUUSD"]["min_confluence"]
