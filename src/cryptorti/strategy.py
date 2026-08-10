"""
CryptoRTI whale-signal strategy.

A registry strategy that turns the (validated) CryptoRTI whale-deposit + VPIN
signal into a BTCUSD directional bias. Registered at runtime via
StrategyRegistry.register_custom() with status="testing" until it has live
closed-trade evidence.

Validation (see CRYPTORTI_INTEGRATION.md §6): the signal is a ~1h SHORT bias
(≈47% down-rate vs ≈39% base) when whale deposit ≥ $1M + elevated VPIN + selling.
It is a confidence-weighted contributor, NOT a high-conviction standalone trade.
"""

from __future__ import annotations

from src.strategies.base import Signal
from src.cryptorti import signal_client
from src.cryptorti.wave_predictor import WhaleWavePredictor
from src.utils.logger import get_logger

logger = get_logger("cryptorti.strategy")

# Only applies to BTC symbols
_BTC_HINTS = ("BTC",)

# Shared predictor (lazily builds the whale RAG once)
_PREDICTOR = WhaleWavePredictor()


def cryptorti_whale_signal(indicators: dict, params: dict) -> Signal:
    """
    Emit a BTCUSD signal when a live CryptoRTI whale signal is active, with the
    confidence DERIVED FROM HISTORIC DATA (#26): the whale wave predictor looks
    up the event (size/exchange/direction) in the whale RAG and returns a
    confidence-to-enter based on historic hit_rate / similarity / source, instead
    of a static bias. Falls back to the raw signal-client bias if the RAG is empty.

    `indicators` may carry the symbol under 'symbol'; non-BTC symbols hold.
    """
    close = indicators.get("close")
    symbol = str(indicators.get("symbol", "") or "").upper()

    # only trade BTC; for non-BTC this strategy is silent
    if symbol and not any(h in symbol for h in _BTC_HINTS):
        return Signal(action="hold", reason="CryptoRTI: not a BTC symbol", confidence=0.0)

    bias = signal_client.current_short_bias()
    if not bias:
        return Signal(action="hold", reason="CryptoRTI: no active whale signal", confidence=0.0)

    # #26: historic-trained confidence from the whale RAG (supersedes static bias)
    usd = float(bias.get("amount_usd", 0) or 0)
    exchange = str(bias.get("exchange", "") or "")
    direction = "sell" if bias.get("action") == "sell" else "buy"
    stage = bias.get("stage") or bias.get("status")
    try:
        pred = _PREDICTOR.predict(usd=usd, exchange=exchange, direction=direction, stage=stage)
    except Exception as e:
        pred = {"confidence": 0.0, "action": None, "reason": f"predictor error: {e}"}

    if pred.get("confidence", 0) > 0 and pred.get("action"):
        return Signal(
            action=pred["action"],
            confidence=float(pred["confidence"]),
            price=close,
            reason=f"CryptoRTI {pred['reason']}",
            metadata={"cryptorti_signal_id": bias.get("signal_id"),
                      "whale_n_chunks": pred.get("n_chunks"),
                      "whale_lag_min": pred.get("lag_min"),
                      "whale_source": pred.get("source"),
                      "historic_confidence": True},
        )

    # fallback: raw signal-client bias (RAG empty / no historic match)
    return Signal(
        action=bias["action"],
        confidence=bias["confidence"],
        price=close,
        reason=bias["reason"] + " (fallback: no historic match)",
        metadata={"cryptorti_signal_id": bias.get("signal_id"), "historic_confidence": False},
    )


def register(registry):
    """Register the CryptoRTI strategy into a StrategyRegistry (status=testing)."""
    registry.register_custom(
        name="CryptoRTI_WhaleSignal",
        signal_fn=cryptorti_whale_signal,
        description="BTC short bias from CryptoRTI whale-deposit + VPIN signal (1h horizon, validated bias)",
        indicators_used=["close", "symbol"],
        suitable_regimes=["trending", "volatile", "ranging", "quiet"],
        min_confidence=0.45,
        weight=1.0,
        status="active",
    )
    logger.info("Registered CryptoRTI_WhaleSignal strategy (status=active)")
