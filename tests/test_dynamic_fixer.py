"""
Tests for the DynamicFixer (#36) intelligent per-symbol ReAct fix cycle.
Mock engine surface; verify escalation + live exit-override application.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.dynamic_fixer import DynamicFixer


class _Adapter:
    resolved_symbol = "BTCUSD"


class _PM:
    def analyze(self, symbol=None, limit=40):
        return {"directives": {"sl_atr": 0.2, "giveback": 0.15},
                "findings": ["43/72 losers stopped then recovered — SL too tight"]}


class _PMExt:
    """post-mortem that diagnoses ENTERING LATE -> entry_extension_filter directive."""
    def analyze(self, symbol=None, limit=40):
        return {"directives": {"entry_extension_filter": True},
                "findings": ["22/40 entries were into already-extended moves"]}


class _Engine:
    def __init__(self, exp=-0.19, n=95, pm=None):
        self.adapters = {"BTCUSD": _Adapter()}
        self.post_mortem = pm or _PM()
        self._exit_override = {}
        self._giveback_override = {}
        self._stretch_override = {}
        self.param_optimizer = None
        self.edge_discovery = None
        self.researcher = None
        self.knowledge_store = None
        self._exp = (exp, n)
    def _recent_expectancy(self, base): return self._exp
    def _tuned_params(self, resolved): return {"sl_atr": 1.0, "tp_rr": 2.0}


def test_entering_late_applies_live_stretch_ceiling():
    """entry_extension_filter (entering into extended moves) must apply a LIVE
    max_stretch_atr ceiling, not just stay a directive (blocker #2)."""
    e = _Engine(exp=-0.19, n=95, pm=_PMExt())
    fx = DynamicFixer(e)
    r = fx.fix_symbol("BTCUSD")
    assert r["action"] == "exit_fix", r
    assert "BTCUSD" in e._stretch_override, r
    assert e._stretch_override["BTCUSD"] <= 2.0 and e._stretch_override["BTCUSD"] >= 0.7


def test_losing_symbol_gets_exit_fix_applied_live():
    e = _Engine(exp=-0.19, n=95)
    fx = DynamicFixer(e)
    r = fx.fix_symbol("BTCUSD")
    assert r["action"] == "exit_fix", r
    # SL widened + giveback loosened LIVE (not stuck behind the backtest gate)
    assert e._exit_override["BTCUSD"]["sl_atr"] == 1.2
    assert e._giveback_override["BTCUSD"] == 0.75


def test_profitable_symbol_not_touched():
    e = _Engine(exp=0.3, n=95)
    fx = DynamicFixer(e)
    r = fx.fix_symbol("BTCUSD")
    assert r["action"] == "none"
    assert e._exit_override == {}


def test_small_sample_not_touched():
    e = _Engine(exp=-0.5, n=5)
    fx = DynamicFixer(e)
    r = fx.fix_symbol("BTCUSD")
    assert r["action"] == "none"


def test_escalates_when_exit_fix_already_tried():
    e = _Engine(exp=-0.19, n=95)
    fx = DynamicFixer(e)
    fx.fix_symbol("BTCUSD")                     # step 1: exit_fix
    r2 = fx.fix_symbol("BTCUSD")               # step 2: should escalate (no optimizer -> research)
    assert r2["action"] != "exit_fix", r2      # escalated past exit_fix


if __name__ == "__main__":
    test_losing_symbol_gets_exit_fix_applied_live()
    test_profitable_symbol_not_touched()
    test_small_sample_not_touched()
    test_escalates_when_exit_fix_already_tried()
    test_entering_late_applies_live_stretch_ceiling()
    print("dynamic fixer tests passed")
