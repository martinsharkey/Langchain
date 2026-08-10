"""
Tests for the learning kill-switch (#27): when LEARNING_ADAPTATION_ENABLED is
false, the bot must NOT bias itself from historical performance.

We test the pure, construction-free pieces:
  * _variant_weights_for returns UNIFORM weights when adaptation is frozen
    (so variant selection is pure exploration, not biased by net-negative history).
  * returns NON-uniform (learned) weights when adaptation is enabled and a
    variant perf cache exists.

These avoid constructing a full ScalpEngine (which loads heavy deps); we bind the
unbound method to a lightweight stub carrying only the attributes it reads.
"""
import sys, os, types
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.trading.scalp_engine import ScalpEngine
from src.trading.trade_manager import VARIANTS


class _Stub:
    """Minimal stand-in exposing only what _variant_weights_for reads."""
    def __init__(self, cache):
        self._variant_perf_cache = cache


def _weights_for(cache, base="BTCUSD"):
    stub = _Stub(cache)
    # call the real method logic against the stub
    return ScalpEngine._variant_weights_for(stub, base)


def test_frozen_adaptation_gives_uniform_variant_weights():
    prev = config.LEARNING_ADAPTATION_ENABLED
    try:
        config.LEARNING_ADAPTATION_ENABLED = False
        # even with a strong learned bias in the cache, frozen -> uniform
        cache = {"BTCUSD": {"BE_PLUS_TRAIL": {"trades": 20, "win_rate": 5, "net_pnl": -50}}}
        w = _weights_for(cache)
        assert set(w.keys()) == set(VARIANTS)
        assert len(set(w.values())) == 1, f"expected uniform weights when frozen, got {w}"
    finally:
        config.LEARNING_ADAPTATION_ENABLED = prev


def test_enabled_adaptation_biases_from_history():
    prev = config.LEARNING_ADAPTATION_ENABLED
    try:
        config.LEARNING_ADAPTATION_ENABLED = True
        # a variant with >=3 trades and a strong win rate should move off the floor
        cache = {"BTCUSD": {"SCALP_FIXED": {"trades": 10, "win_rate": 70, "net_pnl": 5}}}
        w = _weights_for(cache)
        assert len(set(w.values())) > 1, f"expected learned (non-uniform) weights, got {w}"
    finally:
        config.LEARNING_ADAPTATION_ENABLED = prev


if __name__ == "__main__":
    test_frozen_adaptation_gives_uniform_variant_weights()
    test_enabled_adaptation_biases_from_history()
    print("learning kill-switch tests passed")
