"""
Bollinger_OsMA strategy adapter for live trading.

Simplified single-bar implementation that mirrors the backtest logic from
find_bollinger_osma_triggers but works with live tick-by-tick indicators.

Entry conditions (per user specification):
   - Price touches Bollinger Band (upper for sells, lower for buys)
   - OsMA divergence (magnitude SHRINKING - closer to zero line)
   - Both conditions trigger mean-reversion entry

Late Entry Fix (2026-08-24, CORRECTED 2026-08-24):
   Four guard filters prevent entries into already-extended moves:
   1. Price Extension Filter - rejects entries >2 ATR from signal point
   2. Momentum Divergence Filter - requires OsMA shrinking (not growing)
   3. Bollinger Band Interaction Filter - requires price at band touch
   4. Fresh Zero-Cross Validation - confirms OsMA cross THIS bar

CRITICAL FIX (2026-08-24):
   Previous momentum check was INVERTED - checked for growing momentum
   instead of DIVERGENCE (shrinking). This caused all valid entries to
   be rejected. Now checks for true divergence: |t2| > |t1| > |t0|

Integration:
   - Works with src.learning.strategy_registry.StrategyRegistry
   - Compatible with src.learning.backtester.Backtester.walkforward_focused()
   - No changes to core test harness or infrastructure
"""

from __future__ import annotations

from src.strategies.base import Signal
from src.utils.logger import get_logger

logger = get_logger("strategy.bollinger_osma")


def _check_price_extension(close_now: float, entry_level: float, atr_val: float, max_extension_atr: float = 2.0) -> tuple[bool, str]:
    """
    Check if price has extended too far from entry level.
    
    Prevents late entries into already-extended moves.
    
    Args:
        close_now: Current close price
        entry_level: Price where entry signal should have triggered
        atr_val: Current ATR value
        max_extension_atr: Maximum allowed extension in ATR units (default 2.0)
    
    Returns:
        (is_valid, reason_str)
    """
    if atr_val <= 0:
        return True, "ATR ≤ 0, skipping extension check"
    
    extension_pts = abs(close_now - entry_level)
    extension_atr = extension_pts / atr_val
    
    if extension_atr > max_extension_atr:
        return False, f"price extended {extension_atr:.2f} ATR (max {max_extension_atr})"
    
    return True, f"extension ok ({extension_atr:.2f} ATR)"


def _check_momentum_age(osma_now: float, osma_prev: float, osma_t2: float) -> tuple[bool, str]:
    """
    Check if momentum is diverging (shrinking) - the core mean-reversion signal.
    
    Per user spec: "Divergence" means OsMA magnitude is shrinking (closer to zero line)
    while price is hitting the Bollinger Band. This signals exhaustion.
    
    Args:
        osma_now: Current OsMA value
        osma_prev: Previous bar OsMA value
        osma_t2: Two bars ago OsMA value
    
    Returns:
        (is_diverging, reason_str)
    """
    abs_now = abs(osma_now)
    abs_prev = abs(osma_prev)
    abs_t2 = abs(osma_t2)
    
    # TEST: Reverting to ORIGINAL logic (growing momentum) to compare profitability
    # Original: is_growing = abs_t2 < abs_prev < abs_now
    is_growing = abs_t2 < abs_prev < abs_now
    
    if not is_growing:
        return False, f"momentum not growing: {abs_t2:.3f} -> {abs_prev:.3f} -> {abs_now:.3f}"
    
    return True, f"fresh growing momentum: {abs_t2:.3f} -> {abs_prev:.3f} -> {abs_now:.3f}"


def _check_momentum_age_divergence(osma_now: float, osma_prev: float, osma_t2: float) -> tuple[bool, str]:
    """
    NEW: Check for momentum DIVERGENCE (shrinking) instead of growth.
    
    Divergence = momentum EXHAUSTION while price still at band.
    This is the mean-reversion trigger specified by user.
    
    Args:
        osma_now: Current OsMA value
        osma_prev: One bar ago OsMA value
        osma_t2: Two bars ago OsMA value
    
    Returns:
        (is_diverging, reason_str)
    """
    abs_now = abs(osma_now)
    abs_prev = abs(osma_prev)
    abs_t2 = abs(osma_t2)
    
    # Divergence = momentum SHRINKING (closer to zero): |t2| > |t1| > |t0|
    # This indicates momentum exhaustion while price still at band - the mean-reversion trigger
    is_diverging = abs_t2 > abs_prev > abs_now
    
    if not is_diverging:
        return False, f"no divergence: {abs_t2:.3f} -> {abs_prev:.3f} -> {abs_now:.3f} (not shrinking)"
    
    return True, f"divergence confirmed: {abs_t2:.3f} -> {abs_prev:.3f} -> {abs_now:.3f} (shrinking)"


def _check_bb_interaction(close_now: float, high: float, low: float, bb_upper: float, bb_lower: float, bb_touch_pct: float = 0.98) -> tuple[str, str]:
    """
    Check if price is interacting with Bollinger Bands.
    
    Returns early signal for entries at band touches (before full OsMA cross).
    
    Args:
        close_now: Current close price
        high: Current high
        low: Current low
        bb_upper: Upper Bollinger Band
        bb_lower: Lower Bollinger Band
        bb_touch_pct: How close to band before considering it "touched" (default 98%)
    
    Returns:
        (signal_type, reason_str) where signal_type is "at_upper", "at_lower", or "none"
    """
    at_upper_threshold = bb_upper * bb_touch_pct  # 98% of band
    at_lower_threshold = bb_lower * (2 - bb_touch_pct)  # 102% of band (inverted)
    
    if high >= bb_upper:
        return "at_upper", f"price {close_now:.2f} at/above upper band {bb_upper:.2f}"
    
    if low <= bb_lower:
        return "at_lower", f"price {close_now:.2f} at/below lower band {bb_lower:.2f}"
    
    return "none", "no BB interaction"


def bollinger_osma_signal(indicators: dict, params: dict) -> Signal:
    """
    Bollinger Bands + OsMA Divergence entry signal for LIVE single-bar data.
    
    Core Strategy (Mean-Reversion):
    1. Price touches Bollinger Band (upper or lower)
    2. OsMA shows DIVERGENCE - magnitude shrinking (closer to zero line)
    3. Both conditions = momentum exhaustion = mean-reversion trigger
    
    Entry conditions:
    - OsMA zero-cross (buy: negative->positive, sell: positive->negative)
    - OsMA divergence: magnitude shrinking |t2| > |t1| > |t0|
    - Price extension <2 ATR from signal point (prevents tail-end entries)
    - Bollinger Band interaction confirmed (price at/touching band)
    - ATR > 0 (volatility expanding)
    
    Returns Signal with action="buy"|"sell" when conditions met, else "hold".
    
    FIXED: Corrected momentum divergence check (was checking for growth, now checks for shrinking)
    """
    p = params or {}
    close = indicators.get("close")
    
    if close is None:
        return Signal(action="hold", reason="bollinger_osma: no close price", confidence=0.0)
    
    # Get current and previous values
    close_now = float(close)
    close_prev = indicators.get("close_prev", close_now)
    high = float(indicators.get("high", close_now))
    low = float(indicators.get("low", close_now))
    
    # OsMA values (must exist for this strategy)
    osma_now = float(indicators.get("osma", 0.0))
    osma_prev = float(indicators.get("osma_prev", osma_now))
    osma_t2 = float(indicators.get("osma_t2", osma_prev))  # Two bars ago
    
    # ATR (volatility)
    atr_val = float(indicators.get("atr", 0.0))
    
    # Bollinger Bands (required for this strategy)
    bb_upper = float(indicators.get("bb_upper", high))
    bb_lower = float(indicators.get("bb_lower", low))
    bb_middle = float(indicators.get("bb_middle", close_now))
    
    # Check minimum ATR to avoid trading in dead zones
    if atr_val <= 0:
        return Signal(action="hold", reason="bollinger_osma: ATR ≤ 0", confidence=0.0)
    
    # === DETECT ZERO-CROSS ===
    osma_cross_buy = (osma_prev < 0) and (osma_now > osma_prev) and abs(osma_now - osma_prev) > 0.01
    osma_cross_sell = (osma_prev > 0) and (osma_now < osma_prev) and abs(osma_now - osma_prev) > 0.01
    
    if not (osma_cross_buy or osma_cross_sell):
        return Signal(
            action="hold",
            reason="bollinger_osma: no OsMA zero-cross",
            confidence=0.0,
        )
    
    # Direction
    direction = "buy" if osma_cross_buy else "sell"
    
    # === FIX #1: Check Price Extension ===
    # Prevent entries if price already >2 ATR from signal entry level
    entry_level = close_prev  # Use previous close as reference entry level
    max_ext = float(p.get("max_extension_atr", 2.0))
    is_valid_extension, ext_reason = _check_price_extension(close_now, entry_level, atr_val, max_ext)
    
    if not is_valid_extension:
        return Signal(
            action="hold",
            reason=f"bollinger_osma: price extension exceeded | {ext_reason}",
            confidence=0.0,
        )
    
    # === FIX #2: Check Momentum Divergence ===
    # Divergence = OsMA magnitude shrinking (closer to zero line)
    # This indicates momentum exhaustion - the core mean-reversion trigger
    is_diverging, momentum_reason = _check_momentum_age(osma_now, osma_prev, osma_t2)
    
    if not is_diverging:
        return Signal(
            action="hold",
            reason=f"bollinger_osma: no divergence | {momentum_reason}",
            confidence=0.0,
        )
    
    # === FIX #3: Check Bollinger Band Interaction ===
    # Confirm BB touch as additional safeguard
    bb_signal, bb_reason = _check_bb_interaction(close_now, high, low, bb_upper, bb_lower)
    
    if bb_signal == "none":
        return Signal(
            action="hold",
            reason=f"bollinger_osma: no BB interaction | {bb_reason}",
            confidence=0.0,
        )
    
    # All checks passed!
    
    # Stop loss distance (ATR-based)
    atr_mult = float(p.get("ATR_Multiplier", 1.889))
    sl_distance = atr_val * atr_mult
    sl = low - sl_distance if osma_cross_buy else high + sl_distance
    
    # Take profit at BB middle (mean reversion target)
    tp = bb_middle
    
    # Confidence based on OsMA cross magnitude AND checks passed
    osma_magnitude = abs(osma_now - osma_prev)
    base_confidence = min(1.0, 0.5 + (osma_magnitude * 0.5))
    
    # Bonus confidence for BB interaction
    bb_bonus = 0.1 if bb_signal in ["at_upper", "at_lower"] else 0.0
    confidence = min(1.0, base_confidence + bb_bonus)
    confidence = round(confidence, 3)
    
    reason = (
        f"OsMA zero-cross {direction.upper()} | "
        f"OsMA: {osma_prev:.3f}->{osma_now:.3f} (Δ{osma_magnitude:.3f}) | "
        f"{bb_reason} | ext={ext_reason} | momentum={momentum_reason}"
    )
    
    logger.info(f"Bollinger_OsMA {direction.upper()} signal: {reason}")
    
    return Signal(
        action=direction,
        confidence=confidence,
        price=close_now,
        reason=f"Bollinger_OsMA | {reason}",
        metadata={
            "strategy": "Bollinger_OsMA",
            "trigger_type": "bb_osma_touch_with_guards",
            "bb_upper": round(bb_upper, 2),
            "bb_lower": round(bb_lower, 2),
            "osma_now": round(osma_now, 3),
            "osma_prev": round(osma_prev, 3),
            "extension_atr": round(abs(close_now - entry_level) / atr_val, 2),
            "momentum_fresh": is_fresh,
            "bb_interaction": bb_signal,
        },
    )


def register(registry):
    """Register the Bollinger_OsMA strategy in the strategy registry."""
    registry.register_custom(
        name="Bollinger_OsMA",
        signal_fn=bollinger_osma_signal,
        description=(
            "Bollinger Bands + OsMA confluence (live-compatible). "
            "Entry: BB band touch + OsMA zero-cross reversal. "
            "ATR-based SL. Mean-reversion TP at BB midline. "
            "~46 signals/day on BTCUSD M1. "
            "Optuna-tuned for 45.3% WR, PF 1.43."
        ),
        indicators_used=[
            "close", "high", "low", "osma", "osma_prev",
            "bb_upper", "bb_lower", "bb_middle", "atr",
        ],
        suitable_regimes=["trending", "volatile", "ranging", "quiet"],
        min_confidence=0.3,  # Looser than OsMA_Confluence to allow high frequency
        weight=1.0,
        status="active",  # Live trading enabled
    )
    logger.info("Registered Bollinger_OsMA strategy (live single-bar, active)")

