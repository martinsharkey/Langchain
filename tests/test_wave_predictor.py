"""
Tests for the whale wave predictor / confidence model (#26). Mock whale RAG.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cryptorti.wave_predictor import WhaleWavePredictor


class _RAG:
    def __init__(self, hits): self._hits = hits
    def lookup(self, usd, exchange, direction, n_results=3): return self._hits


class _EmptyStore:
    """Isolate the RAG logic from the machine's live/seeded outcome store (#46 blend)."""
    def confidence_for(self, usd): return 0.0


def _predictor(hits):
    p = WhaleWavePredictor(whale_rag=_RAG(hits))
    p._outcome_store = _EmptyStore()   # no learned blend -> tests pure RAG confidence
    return p


def test_confirmed_pattern_high_confidence():
    hits = [{"similarity": 0.9, "metadata": {
        "hit_rate": 100, "avg_n_large": 6, "avg_lag_min": 30,
        "avg_peak_bps": 40, "samples": 1, "source": "confirmed"}}]
    p = _predictor(hits)
    r = p.predict(usd=6_000_000, exchange="binance", direction="sell", stage="selling_confirmed")
    assert r["action"] == "sell"
    assert r["confidence"] >= 0.6, r
    assert r["n_chunks"] == 6


def test_thin_mined_profile_discounted():
    hits = [{"similarity": 0.5, "metadata": {
        "hit_rate": 40, "avg_n_large": 2, "avg_lag_min": 45,
        "avg_peak_bps": 15, "samples": 2, "source": "miner"}}]
    p = _predictor(hits)
    r = p.predict(usd=1_200_000, exchange="okx", direction="sell", stage="sell_window_open")
    # thin sample + unconfirmed stage -> heavily discounted
    assert r["confidence"] < 0.3, r


def test_no_match_zero_confidence():
    p = WhaleWavePredictor(whale_rag=_RAG([]))
    r = p.predict(usd=5_000_000, exchange="binance", direction="sell")
    assert r["confidence"] == 0.0 and r["action"] is None


def test_no_rag_is_safe():
    class _NoRag(WhaleWavePredictor):
        def _rag_or_none(self): return None
    r = _NoRag().predict(usd=1e6, exchange="x", direction="sell")
    assert r["confidence"] == 0.0


if __name__ == "__main__":
    test_confirmed_pattern_high_confidence()
    test_thin_mined_profile_discounted()
    test_no_match_zero_confidence()
    test_no_rag_is_safe()
    print("wave predictor tests passed")
