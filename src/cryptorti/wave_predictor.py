"""
Whale wave predictor / confidence model (#26).

Turns a LIVE CryptoRTI whale signal into a CONFIDENCE-TO-ENTER for BTCUSD, using
the historic patterns trained into the whale RAG (the confirmed ~$6M -> ~6 x $1M
chunk -> ~6 large M1 candle wave, plus the mined correlation profiles).

Key context (cryptorti/martin_qna.md Q10): of 455 whale deposits >= $1M, ZERO
reached selling_confirmed on the raw signal alone — so the RAW deposit is NOT
tradeable by itself. The tradeable edge is the HISTORIC-TRAINED response: given a
signal's size/exchange/direction/stage, what is the probability (hit_rate) and
shape (n_large chunks, lag, peak_bps) of a real move, and therefore our confidence.

This supersedes the static current_short_bias() confidence in strategy.py.
Order-flow (MT5_OLD_EAs) can later be layered as an extra confirmation input.
"""

from __future__ import annotations

from typing import Optional
from src.utils.logger import get_logger

logger = get_logger("cryptorti.wave_predictor")


class WhaleWavePredictor:
    def __init__(self, whale_rag=None):
        self._rag = whale_rag  # lazily constructed if None

    def _rag_or_none(self):
        if self._rag is not None:
            return self._rag
        try:
            from src.cryptorti.whale_rag import WhalePatternRAG
            self._rag = WhalePatternRAG()
        except Exception as e:
            logger.debug(f"whale RAG unavailable: {e}")
            self._rag = None
        return self._rag

    def predict(self, usd: float, exchange: str, direction: str,
                stage: Optional[str] = None) -> dict:
        """
        Return a prediction dict:
          {"confidence": 0..1, "action": "buy"|"sell"|None, "n_chunks", "lag_min",
           "peak_bps", "hit_rate", "similarity", "source", "reason"}
        Confidence blends historic hit_rate, retrieval similarity, sample source
        (a human-CONFIRMED pattern outranks a thin mined profile) and stage
        (only a confirmed/selling stage should carry full weight).
        """
        rag = self._rag_or_none()
        if rag is None:
            return {"confidence": 0.0, "action": None, "reason": "no whale RAG"}
        try:
            hits = rag.lookup(usd=usd, exchange=exchange or "unknown",
                              direction=direction or "sell", n_results=3)
        except Exception as e:
            return {"confidence": 0.0, "action": None, "reason": f"lookup failed: {e}"}
        if not hits:
            return {"confidence": 0.0, "action": None, "reason": "no historic match"}

        top = hits[0]
        m = top.get("metadata", {}) or {}
        similarity = float(top.get("similarity", 0.0) or 0.0)
        hit_rate = float(m.get("hit_rate", 0) or 0)          # 0..100
        n_large = float(m.get("avg_n_large", 0) or 0)
        lag = float(m.get("avg_lag_min", 45) or 45)
        peak_bps = float(m.get("avg_peak_bps", 0) or 0)
        samples = float(m.get("samples", 0) or 0)
        source = str(m.get("source", "miner"))

        # base confidence from historic hit rate (probability the move is real)
        conf = hit_rate / 100.0
        # weight by how well the live event matches a historic one
        conf *= (0.5 + 0.5 * max(0.0, min(similarity, 1.0)))
        # a human-CONFIRMED pattern is trustworthy even with few samples
        if source == "confirmed":
            conf = max(conf, 0.6 * (0.5 + 0.5 * similarity))
        else:
            # thin mined profiles are discounted until enough samples accrue
            if samples and samples < 5:
                conf *= 0.6
        # stage gate: raw 'sell_window_open' is not tradeable; require confirmation
        if stage and stage not in ("selling_confirmed", "selling", "confirmed"):
            conf *= 0.5

        conf = round(max(0.0, min(conf, 1.0)), 3)
        action = "sell" if (direction or "sell").lower().startswith("s") else "buy"
        reason = (f"whale wave: {source} match sim={similarity:.2f} hit_rate={hit_rate:.0f}% "
                  f"~{n_large:.0f} chunks lag~{lag:.0f}m peak~{peak_bps:.0f}bps -> conf {conf}")
        return {"confidence": conf, "action": action, "n_chunks": n_large,
                "lag_min": lag, "peak_bps": peak_bps, "hit_rate": hit_rate,
                "similarity": similarity, "source": source, "samples": samples,
                "reason": reason}
