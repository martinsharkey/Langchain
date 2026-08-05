"""
Tests for the CLOSED self-learning loop:
post-mortem directive -> optimizer applies it -> walk-forward gate keeps it.

Uses a fake backtest_fn so it's deterministic (no MT5). The fake rewards a
HIGHER sl_atr (simulating 'SL too tight' being the real problem), proving that a
reflection directive of {'sl_atr': +0.2} actually steers the optimizer to the
better params and that the walk-forward gate keeps it.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.param_optimizer import ParameterOptimizer, DEFAULTS


class _FakeRegistry:
    pass


def _fake_backtest(symbol, params, sl_atr, tp_rr):
    """
    Simulated edge that IMPROVES with larger sl_atr (the 'SL too tight' scenario
    the post-mortem would detect). PF scales with sl_atr; generalizes if PF>=1.
    """
    pf = round(0.9 + (sl_atr - 0.6) * 0.5, 3)   # sl_atr 1.0 -> 1.1, 1.4 -> 1.3
    pfs = [pf, pf - 0.05, pf + 0.05]
    return {"pfs": pfs, "wrs": [45, 44, 46], "n_total": 300,
            "generalizes": all(p >= 1.0 for p in pfs), "score": min(pfs)}


def test_reflection_directive_steers_and_is_kept(tmp_path, monkeypatch):
    # isolate the tuned-params file to a temp location
    import src.learning.param_optimizer as po
    monkeypatch.setattr(po, "TUNED_PATH", str(tmp_path / "tuned.json"))
    opt = ParameterOptimizer(_FakeRegistry(), _fake_backtest)

    # starting sl_atr from the (gold proven-edge) baseline. Post-mortem 'SL too tight': +0.2.
    start_sl = opt.current_params("XAUUSD-ECN")["sl_atr"]
    directives = {"sl_atr": +0.2}
    r = opt.optimize("XAUUSD-ECN", iterations=0, directives=directives)  # only the guided candidate

    assert r["improved"] is True, r
    assert r["from_reflection"] is True          # the reflection directive is what improved it
    assert opt.current_params("XAUUSD-ECN")["sl_atr"] > start_sl  # SL was widened from its start + kept


def test_bad_directive_rejected_by_gate(tmp_path, monkeypatch):
    """A directive that makes things worse must NOT be kept (walk-forward gate)."""
    import src.learning.param_optimizer as po
    monkeypatch.setattr(po, "TUNED_PATH", str(tmp_path / "tuned2.json"))

    def _fake_bad(symbol, params, sl_atr, tp_rr):
        # here SMALLER sl is better, so a +sl_atr directive should NOT be kept
        pf = round(1.3 - (sl_atr - 0.6) * 0.5, 3)
        pfs = [pf, pf, pf]
        return {"pfs": pfs, "wrs": [45,45,45], "n_total": 300,
                "generalizes": all(p >= 1.0 for p in pfs), "score": min(pfs)}

    opt = ParameterOptimizer(_FakeRegistry(), _fake_bad)
    base_sl = opt.current_params("XAUUSD-ECN")["sl_atr"]
    r = opt.optimize("XAUUSD-ECN", iterations=0, directives={"sl_atr": +0.4})
    # widening sl lowers pf here, so it should not improve/keep
    assert r["improved"] is False
    assert opt.current_params("XAUUSD-ECN")["sl_atr"] == base_sl


if __name__ == "__main__":
    import subprocess
    subprocess.run([sys.executable, "-m", "pytest", __file__, "-v"])
