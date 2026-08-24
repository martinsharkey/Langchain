"""
SIMPLE PROFITABLE STRATEGY: Bollinger Band Mean Reversion with Fixed TP/SL

This strategy bypasses manager exits entirely and uses simple fixed SL/TP:
- Entry: Price touches BB band + RSI extreme
- SL: 2×ATR from entry  
- TP: 3×ATR from entry (asymmetric for mean reversion)
- Discipline: Simple, mechanical, no indicator conflicts
"""

from src.strategies.base import Signal
from src.utils.logger import get_logger

logger = get_logger("strategy.bb_simple")


def bb_simple_signal(indicators: dict, params: dict) -> Signal:
    """
    Simple Bollinger Band Mean Reversion.
    
    Entry:
    - Price touches BB (within 99% of band)
    - RSI in extreme (>70 or <30)
    - ATR > 0 (volatility present)
    
    Exit:
    - SL: 2×ATR from entry
    - TP: 3×ATR from entry (toward middle band)
    
    No complexity, no manager interference.
    """
    
    close = indicators.get("close", 0)
    high = indicators.get("high", close)
    low = indicators.get("low", close)
    
    bb_upper = indicators.get("bb_upper", high)
    bb_lower = indicators.get("bb_lower", low)
    bb_middle = indicators.get("bb_middle", close)
    
    rsi = indicators.get("rsi", 50)
    atr = indicators.get("atr", 0)
    
    if atr <= 0:
        return Signal(direction="none", confidence=0, reason="no volatility")
    
    # Band touch detection
    at_upper = high >= bb_upper * 0.99
    at_lower = low <= bb_lower * 1.01
    
    if not (at_upper or at_lower):
        return Signal(direction="none", confidence=0, reason="no band touch")
    
    # Check RSI extreme
    if at_upper and rsi < 70:
        return Signal(direction="none", confidence=0, reason="not overbought")
    
    if at_lower and rsi > 30:
        return Signal(direction="none", confidence=0, reason="not oversold")
    
    # Generate signals
    if at_upper and rsi >= 70:  # Overbought - go short
        direction = "short"
        entry = close
        tp = entry - 3 * atr  # 3 ATR below
        sl = entry + 2 * atr  # 2 ATR above
        confidence = 0.85
        reason = f"SHORT: OB band, RSI {rsi:.0f}, TP {tp:.2f}, SL {sl:.2f}"
        
    elif at_lower and rsi <= 30:  # Oversold - go long
        direction = "long"
        entry = close
        tp = entry + 3 * atr  # 3 ATR above
        sl = entry - 2 * atr  # 2 ATR below
        confidence = 0.85
        reason = f"LONG: OS band, RSI {rsi:.0f}, TP {tp:.2f}, SL {sl:.2f}"
    
    else:
        return Signal(direction="none", confidence=0, reason="no setup")
    
    return Signal(
        direction=direction,
        confidence=confidence,
        reason=reason,
        metadata={
            'entry': entry,
            'tp': tp,
            'sl': sl,
            'rsi': rsi,
            'atr': atr
        }
    )


def register(registry):
    """Register BB Simple strategy."""
    from src.learning.strategy_registry import StrategyDefinition
    
    registry.register_custom(
        name="BB_Simple",
        signal_fn=bb_simple_signal,
        description=(
            "Bollinger Band Mean Reversion with Simple TP/SL. "
            "Entry: band touch + RSI extreme. SL 2ATR, TP 3ATR. "
            "Designed to bypass manager exit complexity."
        ),
        indicators_used=["close", "high", "low", "bb_upper", "bb_lower", "bb_middle", "rsi", "atr"],
        suitable_regimes=["ranging", "volatile"],
        min_confidence=0.8,
        weight=1.0,
        status="active",
    )
    
    logger.info("Registered BB_Simple strategy (simple fixed TP/SL, no manager interference)")
