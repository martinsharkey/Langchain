"""
Tests for the learning kill-switch (#27) after the exit-model standardisation.

The bot now uses a SINGLE proven management model (GS_PROVEN); the old A/B
management arms have been removed. GS_PROVEN is deliberately excluded from the
exploratory variant-weight pool (it is the pinned proven model, not an arm to
explore), so the exploratory pool is now EMPTY and _variant_weights_for returns
no exploratory weights regardless of the adaptation flag.

We test the pure, construction-free piece: _variant_weights_for. We avoid
constructing a full ScalpEngine (which loads heavy deps) by binding the unbound
method to a lightweight stub carrying only the attributes it reads.
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


def test_variants_standardised_to_gs_proven_only():
    """The legacy A/B arms are removed; GS_PROVEN is the single model."""
    assert VARIANTS == ("GS_PROVEN",), VARIANTS


def test_exploratory_pool_empty_when_frozen():
    prev = config.LEARNING_ADAPTATION_ENABLED
    try:
        config.LEARNING_ADAPTATION_ENABLED = False
        # even with a learned bias in the cache, GS_PROVEN is excluded from the
        # exploratory pool -> no exploratory arms remain.
        cache = {"BTCUSD": {"GS_PROVEN": {"trades": 20, "win_rate": 55, "net_pnl": 10}}}
        w = _weights_for(cache)
        assert w == {}, f"expected empty exploratory pool (GS_PROVEN only), got {w}"
    finally:
        config.LEARNING_ADAPTATION_ENABLED = prev


def test_exploratory_pool_empty_when_enabled():
    prev = config.LEARNING_ADAPTATION_ENABLED
    try:
        config.LEARNING_ADAPTATION_ENABLED = True
        # adaptation on still yields no exploratory arms — GS_PROVEN is pinned, not explored.
        cache = {"BTCUSD": {"GS_PROVEN": {"trades": 10, "win_rate": 70, "net_pnl": 5}}}
        w = _weights_for(cache)
        assert w == {}, f"expected empty exploratory pool (GS_PROVEN only), got {w}"
    finally:
        config.LEARNING_ADAPTATION_ENABLED = prev


if __name__ == "__main__":
    test_variants_standardised_to_gs_proven_only()
    test_exploratory_pool_empty_when_frozen()
    test_exploratory_pool_empty_when_enabled()
    print("learning kill-switch tests passed")
