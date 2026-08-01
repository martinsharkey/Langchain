"""
Tests for #25 ReAct alt-tuning: optimizer draws an mql5-grounded candidate and
avoids checkpointer failed directions. Pure logic with mock backtest + mql5.
"""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Reg:
    def get(self, n): return None


class _MQL5:
    def research(self, q, n_results=2):
        return [{"text": "Lower the OsMA fast period to react faster and catch the cross earlier.",
                 "metadata": {"title": "iOsMA"}}]


def _opt(tmp, backtest_fn, is_failed_fn=None, mql5=None):
    from src.learning.param_optimizer import ParameterOptimizer, TUNED_PATH
    import src.learning.param_optimizer as pom
    pom.TUNED_PATH = os.path.join(tmp, "tuned.json")
    o = ParameterOptimizer(_Reg(), backtest_fn, mql5_knowledge=mql5, is_failed_fn=is_failed_fn)
    return o


def test_mql5_guided_candidate_lowers_osma_fast():
    d = tempfile.mkdtemp()
    try:
        o = _opt(d, lambda *a, **k: None, mql5=_MQL5())
        base = dict(o.current_params("XYZ"))
        cand = o._mql5_guided_candidate("XYZ", base)
        assert cand is not None
        assert cand["osma_fast"] < base["osma_fast"], (base, cand)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_failed_direction_is_skipped():
    d = tempfile.mkdtemp()
    try:
        calls = {"n": 0}
        def backtest(symbol, params, sl_atr, tp_rr):
            calls["n"] += 1
            return {"pfs": [1.3, 1.2, 1.4], "wrs": [50, 50, 50], "n_total": 100,
                    "generalizes": True, "score": 1.2}
        # mark EVERYTHING failed -> only the baseline backtest runs, no candidates
        o = _opt(d, backtest, is_failed_fn=lambda s, p: True)
        r = o.optimize("XYZ", iterations=5)
        # baseline is evaluated once; all mutated/guided candidates are skipped
        assert calls["n"] == 1, f"only baseline should run, got {calls['n']} backtests"
        assert r.get("improved") in (False, None), r
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    test_mql5_guided_candidate_lowers_osma_fast()
    test_failed_direction_is_skipped()
    print("react alt-tuning tests passed")
