"""
Grid-sweep test: proves the optimiser can REACH the proven high-floor cluster
(e.g. osma_min_long ~1.4) from a stuck-at-zero start — the defect the owner
identified, where the directed +/-0.04 coordinate search could only wiggle near
the current value and never discover the real edge the MT5 optimiser XMLs found.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.param_optimizer import ParameterOptimizer, DEFAULTS
from src.learning.strategy_registry import StrategyRegistry


def _peaked_backtest(peak):
    """Fake walk-forward whose PF peaks at osma_min_long == peak (mirrors XMLs)."""
    def bt(symbol, params, sl=1.0, tp=2.0):
        o = params.get("osma_min_long", 0.0)
        pf = 1.0 + max(0.0, 3.0 - abs(o - peak) * 2.5)
        return {"pfs": [pf, pf, pf], "wrs": [0.6] * 3, "n_total": 50,
                "generalizes": pf >= 1.0, "score": pf}
    return bt


def test_grid_sweep_reaches_high_floor_from_zero():
    po = ParameterOptimizer(registry=StrategyRegistry(), backtest_fn=_peaked_backtest(1.4))
    base = dict(DEFAULTS); base["osma_min_long"] = 0.0     # stuck at zero (the live bug)
    gs = po.grid_sweep("XAUUSD", base=base, sweep_keys=["osma_min_long"])
    got = gs["swept"].get("osma_min_long")
    assert got is not None and abs(got - 1.4) <= 0.1, f"sweep should reach ~1.4, got {got}"
    assert gs["score"] > 3.0, f"PF at the proven floor should be high: {gs['score']}"


def test_directed_search_cannot_reach_from_zero():
    """Contrast: the OLD directed search only steps +/-0.04, so from 0.0 it cannot
    reach 1.4 in one pass — this is WHY the bot never found the baseline."""
    po = ParameterOptimizer(registry=StrategyRegistry(), backtest_fn=_peaked_backtest(1.4))
    base = dict(DEFAULTS); base["osma_min_long"] = 0.0
    reached = [c.get("osma_min_long", 0.0) for _, c in po._directed_candidates(base)]
    assert max(reached) < 0.5, "directed search should NOT reach the 1.4 edge from zero"


def test_grid_sweep_keeps_zero_when_zero_is_best():
    """If the edge really is at zero (gate off), the sweep must not force a floor."""
    po = ParameterOptimizer(registry=StrategyRegistry(), backtest_fn=_peaked_backtest(0.0))
    base = dict(DEFAULTS); base["osma_min_long"] = 0.0
    gs = po.grid_sweep("XAUUSD", base=base, sweep_keys=["osma_min_long"])
    # no improvement to record (already optimal) -> not in swept, or ~0
    assert gs["swept"].get("osma_min_long", 0.0) <= 0.2
