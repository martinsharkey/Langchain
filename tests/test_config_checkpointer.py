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


def test_stale_best_is_demoted_when_now_losing():
    """A best-known captured in a lucky window must not trap the bot: if we are
    ON the best-known config and it is now itself losing, demote it."""
    with tempfile.TemporaryDirectory() as d:
        cp = _cp(os.path.join(d, "cp.json"))
        cfg = {"sl_atr": 1.0, "tp_rr": 2.0, "giveback": 0.6}
        cp.evaluate("BTCUSD", cfg, current_expectancy=0.0947, n=20)   # lucky-window best
        # same config, now losing live -> must demote, not hold
        r = cp.evaluate("BTCUSD", cfg, current_expectancy=-0.090, n=40)
        assert r["action"] == "demoted_stale_best", r
        assert cp.best_expectancy("BTCUSD") is None
        # a fresh config can now become the new baseline
        r2 = cp.evaluate("BTCUSD", {"sl_atr": 2.0, "tp_rr": 0.8}, current_expectancy=0.05, n=40)
        assert r2["action"] == "checkpointed", r2


def test_no_revert_to_a_losing_best():
    """Never force a revert TO a best-known that is itself unprofitable."""
    with tempfile.TemporaryDirectory() as d:
        cp = _cp(os.path.join(d, "cp.json"))
        best = {"sl_atr": 1.0, "tp_rr": 2.0}
        # seed a (barely) positive best, then it decays via the stale guard path is
        # avoided here: directly make best <=0 by checkpointing a tiny-positive then
        # evaluating a different worse config against a now-losing best.
        cp.evaluate("GER40", best, current_expectancy=0.001, n=20)
        # force best expectancy to a losing value to simulate a decayed checkpoint
        cp._sym("GER40")["best"]["expectancy"] = -0.05
        r = cp.evaluate("GER40", {"sl_atr": 0.8, "tp_rr": 1.0}, current_expectancy=-0.20, n=20)
        assert r["action"] == "hold", r
        assert "not reverting" in r["reason"] or "losing" in r["reason"]


if __name__ == "__main__":
    test_first_config_becomes_baseline_and_best()
    test_improvement_updates_best()
    test_degradation_reverts_and_learns()
    test_within_noise_band_holds()
    test_insufficient_sample_holds()
    test_stale_best_is_demoted_when_now_losing()
    test_no_revert_to_a_losing_best()
    print("config checkpointer tests passed")
