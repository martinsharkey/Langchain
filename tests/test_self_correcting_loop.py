"""Self-correcting loop: attribution + frequency-starvation revert."""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.learning.param_optimizer import ParameterOptimizer, DEFAULTS


class _RecallKS:
    def __init__(self): self.remembered = []
    def remember(self, **kw): self.remembered.append(kw)
    def recall(self, *a, **k): return []


def test_optimizer_attributes_the_winning_lever_and_mines_success(tmp_path, monkeypatch):
    import src.learning.param_optimizer as po
    monkeypatch.setattr(po, "TUNED_PATH", str(tmp_path / "t.json"))
    # backtest: score improves ONLY when bulls_min_long rises (so that's the edge lever)
    def bt(sym, params, sl_atr, tp_rr):
        score = 1.0 + 0.5 * float(params.get("bulls_min_long", 0))
        return {"score": score, "generalizes": True, "pfs": [score], "wrs": [50], "n_total": 100}
    opt = ParameterOptimizer(registry=None, backtest_fn=bt)
    opt.knowledge_store = _RecallKS()
    r = opt.optimize("XYZ", iterations=40)
    assert r["improved"] is True, r
    assert r.get("attribution"), r
    # the edge lever must be identified as bulls_min_long
    assert any(a["param"] == "bulls_min_long" for a in r["attribution"]), r["attribution"]
    # and the success was mined into the RAG
    assert any(m.get("topic") == "param_tuning" for m in opt.knowledge_store.remembered)


if __name__ == "__main__":
    import pytest, sys as _s
    _s.exit(pytest.main([__file__, "-q"]))
