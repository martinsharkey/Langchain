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
from src.utils.logger import get_logger

logger = get_logger("cryptorti.strategy")

# Only applies to BTC symbols
_BTC_HINTS = ("BTC",)


def cryptorti_whale_signal(indicators: dict, params: dict) -> Signal:
    """
    Emit a BTCUSD short bias when a live CryptoRTI whale-sell signal is active.

    `indicators` may carry the symbol under 'symbol' (the engine passes the
    resolved symbol); if it's not a BTC symbol, this strategy holds.
    """
    close = indicators.get("close")
    symbol = str(indicators.get("symbol", "") or "").upper()

    # only trade BTC; for non-BTC this strategy is silent
    if symbol and not any(h in symbol for h in _BTC_HINTS):
        return Signal(action="hold", reason="CryptoRTI: not a BTC symbol", confidence=0.0)

    bias = signal_client.current_short_bias()
    if not bias:
        return Signal(action="hold", reason="CryptoRTI: no active whale short signal", confidence=0.0)

    return Signal(
        action=bias["action"],
        confidence=bias["confidence"],
        price=close,
        reason=bias["reason"],
        metadata={"cryptorti_signal_id": bias.get("signal_id")},
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
