"""
Combinatorial gate on/off search + confluence gate-toggle honouring.

Proves the owner's 'MT5-optimiser' vision: the optimiser can turn an indicator
gate OFF (not just tune its floor) to find the edge in a SUBSET of indicators, and
the confluence signal actually respects a disabled gate.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.param_optimizer import ParameterOptimizer, DEFAULTS
from src.learning.strategy_registry import StrategyRegistry
from src.strategies.confluence_signal import evaluate_confluence_bar


def _long_ind(**over):
    d = {
        "close": 100.0, "osma": 0.5, "osma_prev": -0.3,
        "osma_recent": [-0.4, -0.35, -0.3, 0.5],
        "macd_line": 1.2, "ema_fast": 99.5, "ema_prev": 99.0,
        "atr": 1.0, "atr_prev": 0.8, "bulls_power": 2.0, "bears_power": 0.1,
        "rsi": 55.0, "atr_min": 0.0, "atr_max": 0.0,
    }
    d.update(over)
    return d


def test_confluence_honours_gate_toggle_off():
    # a HUGE bulls floor would normally block the long...
    blocked = evaluate_confluence_bar(_long_ind(), {"bulls_min_long": 99.0,
                                                     "min_confluence": 1})
    assert blocked["action"] == "hold", "huge bulls floor should block"
    # ...but turning the bulls gate OFF must let it through (subset without bulls).
    allowed = evaluate_confluence_bar(_long_ind(), {"bulls_min_long": 99.0,
                                                     "use_bulls": 0, "min_confluence": 1})
    assert allowed["action"] == "buy", "use_bulls=0 must disable the bulls floor gate"


def test_combinatorial_search_turns_off_a_harmful_gate():
    # fake backtest: edge exists ONLY when use_bulls is OFF (bulls gate hurts here).
    def bt(symbol, params, sl=1.0, tp=2.0):
        pf = 1.6 if int(params.get("use_bulls", 1)) == 0 else 0.8
        return {"pfs": [pf, pf, pf], "wrs": [0.6]*3, "n_total": 60,
                "generalizes": pf >= 1.0, "score": pf}
    po = ParameterOptimizer(registry=StrategyRegistry(), backtest_fn=bt)
    base = dict(DEFAULTS)  # use_bulls defaults ON
    res = po.combinatorial_search("XAUUSD", base=base)
    assert res["toggled"].get("use_bulls") == 0, f"should disable the harmful bulls gate: {res}"
    assert res["score"] >= 1.6
