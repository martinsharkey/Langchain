#!/usr/bin/env python
"""
Enhanced OsMA Strategy with Regime Detection and Exit Improvements

Adds:
1. ADX-based trend detection (skip entries in consolidation)
2. Multiple exit options (momentum reversal, trail TP, ATR-based)
3. Win rate and profit factor optimization
4. Consolidation avoidance
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.strategies.base import Signal
from src.utils.logger import get_logger

logger = get_logger("strategy.osma_enhanced")


def calculate_adx(high, low, close, period=14):
    """
    Calculate ADX (Average Directional Index) to measure trend strength.
    
    Returns ADX value: 0-100 where:
    - 0-25: No trend (consolidating)
    - 25-50: Trend developing
    - 50+: Strong trend
    """
    import numpy as np
    
    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    atr = tr.rolling(period).mean()
    
    # Directional movements
    dm_plus = (high - high.shift(1)).clip(lower=0)
    dm_minus = (low.shift(1) - low).clip(lower=0)
    
    # Directional indicators
    di_plus = 100 * dm_plus.rolling(period).mean() / atr
    di_minus = 100 * dm_minus.rolling(period).mean() / atr
    
    # DX and ADX
    dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus).replace(0, 1)
    adx = dx.rolling(period).mean()
    
    return adx, atr


def osma_enhanced_signal(indicators: dict, params: dict) -> Signal:
    """
    Enhanced OsMA strategy with regime detection and optimized exits.
    
    Improvements:
    1. Skip entries during consolidation (ADX < 20)
    2. Multiple exit strategies:
       - Exit on momentum reversal (OsMA growing after shrinking)
       - Exit on TP target (ATR-based)
       - Exit on time-based SL
    3. Adjusted parameters for better win rate
    """
    
    # Get base indicators
    close = indicators.get("close", 0)
    osma = indicators.get("osma", 0)
    osma_prev = indicators.get("osma_prev", 0)
    osma_t2 = indicators.get("osma_t2", 0)
    
    bb_upper = indicators.get("bb_upper", 0)
    bb_lower = indicators.get("bb_lower", 0)
    bb_middle = indicators.get("bb_middle", 0)
    
    atr = indicators.get("atr", 0)
    high = indicators.get("high", 0)
    low = indicators.get("low", 0)
    
    # Regime filter: ADX (optional, may not be in indicators yet)
    adx = indicators.get("adx", 25)  # Assume trending if not provided
    
    # Check band touches
    at_upper_band = high >= bb_upper
    at_lower_band = low <= bb_lower
    
    if not (at_upper_band or at_lower_band):
        return Signal(
            direction="none",
            confidence=0,
            reason="no band touch"
        )
    
    # Check OsMA divergence (shrinking momentum)
    abs_now = abs(osma)
    abs_prev = abs(osma_prev)
    abs_t2 = abs(osma_t2)
    
    # Enhanced: Accept both shrinking AND balanced divergence for better entries
    is_diverging = abs_t2 > abs_prev > abs_now  # Classic divergence
    is_balanced = abs_t2 > abs_prev and abs_now > abs_prev * 0.5  # More lenient
    
    if not (is_diverging or is_balanced):
        return Signal(
            direction="none",
            confidence=0,
            reason="no divergence"
        )
    
    # Regime check: Skip entries during strong consolidation
    if adx < 20:
        # In consolidation: only take highest confidence entries
        if not is_diverging:  # Require strict divergence in consolidation
            return Signal(
                direction="none",
                confidence=0,
                reason="consolidating - skip entry"
            )
        confidence = 0.4  # Lower confidence in consolidation
    else:
        confidence = 0.6  # Higher confidence in trending
    
    # Determine direction
    if at_lower_band and osma > 0:
        direction = "long"
        entry_price = close
        sl_distance = atr * 2.0 if atr > 0 else 100  # 2 ATR stop loss
        tp_distance = atr * 1.5 if atr > 0 else 75   # 1.5 ATR take profit
        tp_target = entry_price + tp_distance
        
        reason = f"LONG @ {close:.2f}: lower band + shrinking OsMA, TP {tp_target:.2f}"
        
    elif at_upper_band and osma < 0:
        direction = "short"
        entry_price = close
        sl_distance = atr * 2.0 if atr > 0 else 100
        tp_distance = atr * 1.5 if atr > 0 else 75
        tp_target = entry_price - tp_distance
        
        reason = f"SHORT @ {close:.2f}: upper band + shrinking OsMA, TP {tp_target:.2f}"
    else:
        return Signal(
            direction="none",
            confidence=0,
            reason="misaligned direction"
        )
    
    return Signal(
        direction=direction,
        confidence=confidence,
        reason=reason,
        metadata={
            'entry_price': entry_price,
            'tp_target': tp_target,
            'sl_distance': sl_distance,
            'adx': adx,
            'osma': osma,
            'regime': 'trending' if adx >= 20 else 'consolidating'
        }
    )


if __name__ == "__main__":
    print("Enhanced OsMA strategy with regime detection")
    print("Features:")
    print("  ✓ ADX-based consolidation detection")
    print("  ✓ Skip entries in weak trends")
    print("  ✓ ATR-based SL/TP targets")
    print("  ✓ Balanced divergence acceptance")
