"""
Guardrail (1c): the optimizer must tune a strategy the focused-pocket backtest
actually simulates.

The latent bug: ParameterOptimizer tunes osma_/ema_/atr_-family params via
walkforward_focused(), which only simulates whatever focused_rules(symbol) lists.
If a symbol's focused pocket does NOT contain a strategy that consumes those
params (the old XAUUSD pocket was Volume_Breakout/BB_Bounce/CCI_Breakout, none of
which read osma_fast/ema_period), the gate silently validates nothing.

These tests assert:
  1. Every symbol in FOCUSED_EDGE has OsMA_Confluence (the strategy that consumes
     the tuned osma_/ema_ params) in its pockets.
  2. OsMA_Confluence resolves in a BARE StrategyRegistry (not only after engine
     start), so walkforward_focused can build its signal fns.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.edge_weights import FOCUSED_EDGE
from src.learning.strategy_registry import StrategyRegistry
from src.learning.param_optimizer import PARAM_SPACE

# param families that only the 7-indicator confluence consumes
_CONFLUENCE_PARAM_MARKERS = {"osma_fast", "osma_slow", "ema_period"}
_TUNED_STRATEGY = "OsMA_Confluence"


def test_optimizer_tunes_confluence_params():
    """Sanity: the optimizer really does tune the confluence param family."""
    assert _CONFLUENCE_PARAM_MARKERS.issubset(set(PARAM_SPACE.keys())), (
        "optimizer PARAM_SPACE no longer tunes the osma/ema confluence family; "
        "update this guardrail if that is intentional")


def test_every_focused_symbol_includes_the_tuned_strategy():
    """Each focused pocket must contain the strategy that consumes tuned params,
    otherwise walkforward_focused cannot validate the optimizer's changes."""
    for symbol, pockets in FOCUSED_EDGE.items():
        names = {name for name, _regimes in pockets}
        assert _TUNED_STRATEGY in names, (
            f"{symbol} focused pocket {names} lacks {_TUNED_STRATEGY}; the optimizer "
            f"tunes {_CONFLUENCE_PARAM_MARKERS} but the backtest would simulate a "
            f"strategy that ignores them (silent mis-validation, bug 1c).")


def test_tuned_strategy_resolves_in_bare_registry():
    """OsMA_Confluence must exist in a fresh registry so the optimizer/edge-discovery
    (which may build their own) can resolve the focused pocket."""
    reg = StrategyRegistry()
    got = reg.get(_TUNED_STRATEGY)
    assert got is not None, (
        f"{_TUNED_STRATEGY} not in a bare StrategyRegistry — walkforward_focused "
        f"would return an empty signal set and validate nothing.")
    assert callable(got.signal_fn)


if __name__ == "__main__":
    test_optimizer_tunes_confluence_params()
    test_every_focused_symbol_includes_the_tuned_strategy()
    test_tuned_strategy_resolves_in_bare_registry()
    print("focused/optimizer alignment guardrail passed")

def test_empty_overlay_pocket_does_not_block_entry():
    """A failed edge-discovery sweep that wrote empty focused pockets must NOT kill
    trading - focused_rules must fall back to the static OsMA_Confluence rule."""
    import src.learning.edge_weights as ew
    saved = ew._OVERLAY
    try:
        ew._OVERLAY = {"focused_edge": {"XAUUSD": [], "BTCUSD": [], "GER40": []}}
        for s in ("XAUUSD-ECN", "BTCUSD", "GER40."):
            rules = ew.focused_rules(s)
            assert rules and rules[0][0] == "OsMA_Confluence", (s, rules)
    finally:
        ew._OVERLAY = saved


def test_tuned_strength_floor_reaches_confluence_via_get_focused_signal():
    """THE last-link fix: a strength floor in the tuned params passed to
    get_focused_signal must actually gate the confluence (was dropped: sd.params={})."""
    from src.learning.strategy_registry import StrategyRegistry
    reg = StrategyRegistry()
    # a valid fresh long that WOULD enter with no floor
    ind = {"symbol": "XAUUSD-ECN", "close": 2000.0, "osma": 0.6, "osma_prev": -0.1,
           "osma_closed": 0.6, "macd_line": 0.5, "macd_signal": -0.9,
           "ema_fast": 1999.5, "ema_prev": 1999.0, "atr": 3.0, "atr_prev": 2.9,
           "bulls_power": 2.0, "bears_power": 1.0, "rsi": 55.0, "med_atr": 3.0,
           "osma_recent": [-0.3, -0.1, 0.6]}
    # no tuned params -> enters
    s0 = reg.get_focused_signal(dict(ind), None)
    assert s0 is not None and s0.action == "buy", s0
    # tuned bulls_min_long 1.0 (ATR units) -> needs bulls >= 3.0; bulls=2.0 -> HOLD.
    # If the floor is dropped (old bug), this would WRONGLY still be buy.
    s1 = reg.get_focused_signal(dict(ind), {"bulls_min_long": 1.0})
    assert s1 is not None and s1.action == "hold", f"strength floor did NOT reach confluence: {s1}"
