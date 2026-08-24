"""
NEW: OsMA_Regime_Adaptive Strategy

Based on analysis findings:
1. Window 2 consolidation causes all strategies to fail
2. Need to skip entries in weak-trend environments (ADX < 20)
3. Need improved exit logic (ATR-based TP with higher targeting)
4. Accept shrinking OsMA (divergence) only in trending markets

This strategy should achieve PF > 1.15 by:
- Skipping false signals in consolidation
- Using better exits that capture more of the mean-reversion move
- Tighter win rate with better entry filters
"""

from src.strategies.base import Signal
from src.utils.logger import get_logger

logger = get_logger("strategy.osma_regime_adaptive")


def osma_regime_adaptive_signal(indicators: dict, params: dict) -> Signal:
    """
    OsMA Regime-Adaptive Strategy with Window 2 Consolidation Avoidance.
    
    Key improvements:
    1. ADX-based trend filtering (skip entries when trend is weak)
    2. Higher profit targets (ATR * 2.0 instead of 1.5)
    3. Divergence + band touch confirmation
    4. Better win rate through stricter filters
    """
    
    # Get indicators
    close = indicators.get("close", 0)
    high = indicators.get("high", close)
    low = indicators.get("low", close)
    
    osma = indicators.get("osma", 0)
    osma_prev = indicators.get("osma_prev", 0)
    osma_t2 = indicators.get("osma_t2", 0)
    
    bb_upper = indicators.get("bb_upper", high)
    bb_lower = indicators.get("bb_lower", low)
    bb_middle = indicators.get("bb_middle", close)
    
    atr = indicators.get("atr", 0)
    adx = indicators.get("adx", 25)  # Default: assume trending
    
    # Regime filter: Skip entries in consolidation (ADX < 20)
    if adx < 20:
        return Signal(
            direction="none",
            confidence=0,
            reason=f"consolidation detected (ADX={adx:.1f}), skip entry"
        )
    
    # Check band touches
    at_upper = high >= bb_upper
    at_lower = low <= bb_lower
    
    if not (at_upper or at_lower):
        return Signal(
            direction="none",
            confidence=0,
            reason="no band touch"
        )
    
    # Check OsMA divergence (shrinking)
    abs_now = abs(osma)
    abs_prev = abs(osma_prev)
    abs_t2 = abs(osma_t2)
    
    is_diverging = abs_t2 > abs_prev > abs_now
    
    if not is_diverging:
        return Signal(
            direction="none",
            confidence=0,
            reason="no divergence"
        )
    
    # Determine direction with higher profit targets
    if at_lower and osma > 0:
        direction = "long"
        entry_price = close
        # Higher TP: ATR * 2.0 (vs original 1.5)
        tp_distance = atr * 2.0 if atr > 0 else 0
        sl_distance = atr * 1.5  # Tighter SL
        
        reason = f"LONG: lower band + divergence (ADX={adx:.1f}), TP {entry_price + tp_distance:.2f}"
        confidence = 0.7
        
    elif at_upper and osma < 0:
        direction = "short"
        entry_price = close
        tp_distance = atr * 2.0
        sl_distance = atr * 1.5
        
        reason = f"SHORT: upper band + divergence (ADX={adx:.1f}), TP {entry_price - tp_distance:.2f}"
        confidence = 0.7
    
    else:
        return Signal(
            direction="none",
            confidence=0,
            reason="direction mismatch"
        )
    
    return Signal(
        direction=direction,
        confidence=confidence,
        reason=reason,
        metadata={
            'entry_price': entry_price,
            'tp_distance': tp_distance,
            'sl_distance': sl_distance,
            'adx': adx
        }
    )


def register(registry):
    """Register OsMA_Regime_Adaptive in strategy registry."""
    from src.learning.strategy_registry import StrategyDefinition
    
    registry.register_custom(
        name="OsMA_RegimeAdaptive",
        signal_fn=osma_regime_adaptive_signal,
        description=(
            "OsMA + Bollinger Bands with regime detection (ADX-based). "
            "Skips entries in consolidation (ADX<20). "
            "Higher profit targets (ATR*2.0). "
            "Mean-reversion with trend filtering. "
            "Designed to pass Window 2 consolidation without major drawdown."
        ),
        indicators_used=[
            "close", "high", "low", "osma", "osma_prev", "osma_t2",
            "bb_upper", "bb_lower", "bb_middle", "atr", "adx"
        ],
        suitable_regimes=["trending", "volatile"],
        min_confidence=0.5,
        weight=1.0,
        status="active",
    )
    
    logger.info("Registered OsMA_RegimeAdaptive strategy (regime detection, active)")
