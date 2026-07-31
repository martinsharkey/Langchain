"""
Tests for ConfigCheckpointer (#27/#25): revert-to-best + learn-from-failure.

Pure logic, no MT5/model. Uses a temp checkpoint file and a stub knowledge store.
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.config_checkpointer import ConfigCheckpointer


class _KS:
    """Stub KnowledgeStore capturing remember() calls."""
    def __init__(self):
        self.remembered = []
    def remember(self, **kw):
        self.remembered.append(kw)
        return kw.get("key", "x")


def _cp(tmp, ks=None):
    return ConfigCheckpointer(knowledge_store=ks, path=tmp, min_sample=10, revert_margin=0.05)


def test_first_config_becomes_baseline_and_best():
    with tempfile.TemporaryDirectory() as d:
        cp = _cp(os.path.join(d, "cp.json"))
        r = cp.evaluate("XAUUSD", {"sl_atr": 1.0, "tp_rr": 2.0}, current_expectancy=0.10, n=20)
        assert r["action"] == "checkpointed"
        assert abs(cp.best_expectancy("XAUUSD") - 0.10) < 1e-9


def test_improvement_updates_best():
    with tempfile.TemporaryDirectory() as d:
        cp = _cp(os.path.join(d, "cp.json"))
        cp.evaluate("XAUUSD", {"tp_rr": 2.0}, 0.10, 20)
        r = cp.evaluate("XAUUSD", {"tp_rr": 2.5}, 0.20, 20)
        assert r["action"] == "checkpointed"
        assert abs(cp.best_expectancy("XAUUSD") - 0.20) < 1e-9


def test_degradation_reverts_and_learns():
    with tempfile.TemporaryDirectory() as d:
        ks = _KS()
        cp = _cp(os.path.join(d, "cp.json"), ks=ks)
        good = {"sl_atr": 1.0, "tp_rr": 2.0, "giveback": 0.6}
        bad = {"sl_atr": 0.4, "tp_rr": 1.0, "giveback": 0.15}
        cp.evaluate("XAUUSD", good, current_expectancy=0.117, n=20)   # best-known
        r = cp.evaluate("XAUUSD", bad, current_expectancy=-0.669, n=20)  # degraded
        assert r["action"] == "revert", r
        # revert returns the profitable config to restore
        assert r["best_config"]["tp_rr"] == 2.0 and r["best_config"]["giveback"] == 0.6
        # the failed direction is REMEMBERED (learned from)
        assert cp.is_failed("XAUUSD", bad)
        assert ks.remembered and ks.remembered[0]["kind"] == "correction"


def test_within_noise_band_holds():
    with tempfile.TemporaryDirectory() as d:
        cp = _cp(os.path.join(d, "cp.json"))
        cp.evaluate("BTCUSD", {"tp_rr": 2.0}, 0.10, 20)
        r = cp.evaluate("BTCUSD", {"tp_rr": 2.1}, 0.07, 20)  # worse but within margin 0.05
        assert r["action"] == "hold", r


def test_insufficient_sample_holds():
    with tempfile.TemporaryDirectory() as d:
        cp = _cp(os.path.join(d, "cp.json"))
        r = cp.evaluate("BTCUSD", {"tp_rr": 2.0}, 0.10, n=3)
        assert r["action"] == "hold"


if __name__ == "__main__":
    test_first_config_becomes_baseline_and_best()
    test_improvement_updates_best()
    test_degradation_reverts_and_learns()
    test_within_noise_band_holds()
    test_insufficient_sample_holds()
    print("config checkpointer tests passed")
