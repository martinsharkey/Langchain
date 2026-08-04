"""
Strategy Registry — Dynamic Strategy Discovery and Selection.

This module provides a registry of all available trading strategies,
each implemented as a standalone indicator-based strategy. The registry
allows the meta-strategy agent to:
1. Discover all available strategies
2. Query which strategies are suitable for current market conditions
3. Get performance history for each strategy
4. Select the best strategy or combination for the current market

Each strategy is a lightweight function that takes indicator data and
returns a signal, making them easy to add, test, and compare.
"""

import logging
from typing import Callable, Optional
from dataclasses import dataclass, field
from datetime import datetime

from src.strategies.base import Signal

logger = logging.getLogger("learning.strategy_registry")


# ═══════════════════════════════════════════════════════════════════════════════
#  STRATEGY DEFINITION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StrategyDefinition:
    """
    Definition of a single trading strategy.
    
    Attributes:
        name: Unique strategy name (e.g., "RSI_MeanReversion").
        description: Human-readable description.
        indicators_used: List of indicator names this strategy uses.
        suitable_regimes: List of market regimes this strategy works in.
        signal_fn: Function that generates a Signal from indicator data.
        params: Default parameters for this strategy.
        min_confidence: Minimum confidence threshold.
        weight: Priority weight (higher = preferred when equally scored).
    """
    name: str
    description: str
    indicators_used: list[str]
    suitable_regimes: list[str]
    signal_fn: Callable
    params: dict = field(default_factory=dict)
    min_confidence: float = 0.5
    weight: float = 1.0
    status: str = "active"  # active | testing | disabled


# ═══════════════════════════════════════════════════════════════════════════════
#  INDIVIDUAL STRATEGY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════
#
# Each function takes a dict of pre-calculated indicators and returns a Signal.
# This makes them composable — the meta-agent can run any combination.
# ═══════════════════════════════════════════════════════════════════════════════


def rsi_mean_reversion(indicators: dict, params: dict) -> Signal:
    """
    RSI Mean Reversion Strategy.
    
    Buys when RSI is oversold (<30), sells when overbought (>70).
    Works best in ranging markets.
    """
    rsi_val = indicators.get("rsi")
    close = indicators.get("close")
    
    if rsi_val is None or close is None:
        return Signal(action="hold", reason="Missing RSI or price data", confidence=0.0)
    
    oversold = params.get("rsi_oversold", 30)
    overbought = params.get("rsi_overbought", 70)
    
    if rsi_val < oversold:
        confidence = min((oversold - rsi_val) / oversold + 0.5, 1.0)
        return Signal(
            action="buy",
            confidence=confidence,
            price=close,
            reason=f"RSI Mean Reversion: RSI={rsi_val:.1f} (oversold)",
        )
    elif rsi_val > overbought:
        confidence = min((rsi_val - overbought) / (100 - overbought) + 0.5, 1.0)
        return Signal(
            action="sell",
            confidence=confidence,
            price=close,
            reason=f"RSI Mean Reversion: RSI={rsi_val:.1f} (overbought)",
        )
    
    return Signal(action="hold", reason=f"RSI neutral: {rsi_val:.1f}", confidence=0.0)


def ema_trend_follow(indicators: dict, params: dict) -> Signal:
    """
    EMA Trend Following Strategy.
    
    Buys when fast EMA crosses above slow EMA (golden cross).
    Sells when fast EMA crosses below slow EMA (death cross).
    Works best in trending markets.
    """
    ema_fast = indicators.get("ema_fast")
    ema_slow = indicators.get("ema_slow")
    close = indicators.get("close")
    trend = indicators.get("trend", "neutral")
    
    if ema_fast is None or ema_slow is None or close is None:
        return Signal(action="hold", reason="Missing EMA data", confidence=0.0)
    
    min_conf = params.get("min_confidence", 0.5)
    
    if trend in ("bullish_crossover",):
        return Signal(
            action="buy",
            confidence=0.7,
            price=close,
            reason=f"EMA Golden Cross: Fast={ema_fast:.2f}, Slow={ema_slow:.2f}",
        )
    elif trend in ("bearish_crossover",):
        return Signal(
            action="sell",
            confidence=0.7,
            price=close,
            reason=f"EMA Death Cross: Fast={ema_fast:.2f}, Slow={ema_slow:.2f}",
        )
    elif trend == "bullish":
        # Strong uptrend
        distance = (ema_fast - ema_slow) / ema_slow
        confidence = min(distance * 5 + 0.5, 0.8)
        if confidence >= min_conf:
            return Signal(
                action="buy",
                confidence=confidence,
                price=close,
                reason=f"EMA Trend Follow: Bullish trend, spread={distance:.4f}",
            )
    elif trend == "bearish":
        distance = (ema_slow - ema_fast) / ema_slow
        confidence = min(distance * 5 + 0.5, 0.8)
        if confidence >= min_conf:
            return Signal(
                action="sell",
                confidence=confidence,
                price=close,
                reason=f"EMA Trend Follow: Bearish trend, spread={distance:.4f}",
            )
    
    return Signal(action="hold", reason=f"EMA trend: {trend}", confidence=0.0)


def macd_momentum(indicators: dict, params: dict) -> Signal:
    """
    MACD Momentum Strategy.
    
    Buys when MACD histogram turns positive (increasing momentum).
    Sells when MACD histogram turns negative (decreasing momentum).
    Works in both trending and ranging markets.
    """
    macd_hist = indicators.get("macd_histogram")
    close = indicators.get("close")
    
    if macd_hist is None or close is None:
        return Signal(action="hold", reason="Missing MACD data", confidence=0.0)
    
    min_conf = params.get("min_confidence", 0.5)
    strength = abs(macd_hist)
    confidence = min(strength * 10 + 0.3, 0.9)
    
    if macd_hist > 0 and confidence >= min_conf:
        return Signal(
            action="buy",
            confidence=confidence,
            price=close,
            reason=f"MACD Momentum: Positive histogram ({macd_hist:.2f})",
        )
    elif macd_hist < 0 and confidence >= min_conf:
        return Signal(
            action="sell",
            confidence=confidence,
            price=close,
            reason=f"MACD Momentum: Negative histogram ({macd_hist:.2f})",
        )
    
    return Signal(action="hold", reason=f"MACD neutral: {macd_hist:.2f}", confidence=0.0)


def bollinger_bounce(indicators: dict, params: dict) -> Signal:
    """
    Bollinger Band Bounce Strategy.
    
    Buys when price touches or crosses below the lower band.
    Sells when price touches or crosses above the upper band.
    Works best in ranging/mean-reverting markets.
    """
    close = indicators.get("close")
    bb_upper = indicators.get("bb_upper")
    bb_lower = indicators.get("bb_lower")
    bb_middle = indicators.get("bb_middle")
    
    if any(v is None for v in [close, bb_upper, bb_lower, bb_middle]):
        return Signal(action="hold", reason="Missing Bollinger Band data", confidence=0.0)
    
    min_conf = params.get("min_confidence", 0.5)
    bb_range = bb_upper - bb_lower
    bb_position = (close - bb_lower) / bb_range if bb_range > 0 else 0.5
    
    # Buy when price is near or below lower band
    if close <= bb_lower:
        confidence = min((bb_lower - close) / max(bb_range * 0.1, 0.01) + 0.6, 0.95)
        if confidence >= min_conf:
            return Signal(
                action="buy",
                confidence=confidence,
                price=close,
                reason=f"BB Bounce: Price at lower band (pos={bb_position:.2f})",
            )
    
    # Sell when price is near or above upper band
    elif close >= bb_upper:
        confidence = min((close - bb_upper) / max(bb_range * 0.1, 0.01) + 0.6, 0.95)
        if confidence >= min_conf:
            return Signal(
                action="sell",
                confidence=confidence,
                price=close,
                reason=f"BB Bounce: Price at upper band (pos={bb_position:.2f})",
            )
    
    return Signal(action="hold", reason=f"BB position: {bb_position:.2f}", confidence=0.0)


def support_resistance_breakout(indicators: dict, params: dict) -> Signal:
    """
    Support/Resistance Breakout Strategy.
    
    Buys when price breaks above resistance (bullish breakout).
    Sells when price breaks below support (bearish breakout).
    Works best in volatile/trending markets.
    """
    close = indicators.get("close")
    support = indicators.get("support_levels", [])
    resistance = indicators.get("resistance_levels", [])
    atr_val = indicators.get("atr", 0) or 0
    
    if close is None:
        return Signal(action="hold", reason="Missing price data", confidence=0.0)
    
    min_conf = params.get("min_confidence", 0.5)
    breakout_threshold = atr_val * 0.3 if atr_val > 0 else close * 0.002
    
    # Check resistance breakout (bullish)
    if resistance:
        nearest_resistance = min(resistance)
        if close > nearest_resistance + breakout_threshold:
            distance = (close - nearest_resistance) / nearest_resistance
            confidence = min(distance * 20 + 0.5, 0.9)
            if confidence >= min_conf:
                return Signal(
                    action="buy",
                    confidence=confidence,
                    price=close,
                    reason=f"Resistance Breakout: Price=${close:.2f} > Resistance=${nearest_resistance:.2f}",
                )
    
    # Check support breakdown (bearish)
    if support:
        nearest_support = max(support)
        if close < nearest_support - breakout_threshold:
            distance = (nearest_support - close) / nearest_support
            confidence = min(distance * 20 + 0.5, 0.9)
            if confidence >= min_conf:
                return Signal(
                    action="sell",
                    confidence=confidence,
                    price=close,
                    reason=f"Support Breakdown: Price=${close:.2f} < Support=${nearest_support:.2f}",
                )
    
    return Signal(action="hold", reason="No breakout detected", confidence=0.0)


def atr_volatility_breakout(indicators: dict, params: dict) -> Signal:
    """
    ATR Volatility Breakout Strategy.
    
    Detects when volatility expands significantly, indicating a potential
    breakout move. Uses ATR expansion relative to recent average.
    Works best in volatile markets.
    """
    close = indicators.get("close")
    atr_val = indicators.get("atr", 0) or 0
    trend = indicators.get("trend", "neutral")
    
    if close is None or atr_val == 0:
        return Signal(action="hold", reason="Missing ATR or price data", confidence=0.0)
    
    min_conf = params.get("min_confidence", 0.5)
    atr_pct = atr_val / close * 100  # ATR as percentage of price
    
    # High volatility breakout
    if atr_pct > 0.3:  # ATR > 0.3% of price = high volatility
        confidence = min(atr_pct / 0.5, 0.85)
        
        if trend in ("bullish", "bullish_crossover") and confidence >= min_conf:
            return Signal(
                action="buy",
                confidence=confidence,
                price=close,
                reason=f"ATR Breakout: High volatility ({atr_pct:.2f}%) with bullish trend",
            )
        elif trend in ("bearish", "bearish_crossover") and confidence >= min_conf:
            return Signal(
                action="sell",
                confidence=confidence,
                price=close,
                reason=f"ATR Breakout: High volatility ({atr_pct:.2f}%) with bearish trend",
            )
    
    return Signal(action="hold", reason=f"ATR normal: {atr_pct:.2f}%", confidence=0.0)


def multi_indicator_confluence(indicators: dict, params: dict) -> Signal:
    """
    Multi-Indicator Confluence Strategy.
    
    Combines RSI, MACD, EMA trend, and Bollinger Bands for a
    high-confidence signal. Only trades when multiple indicators agree.
    This is the most conservative strategy.
    """
    close = indicators.get("close")
    rsi_val = indicators.get("rsi")
    macd_hist = indicators.get("macd_histogram")
    trend = indicators.get("trend", "neutral")
    bb_upper = indicators.get("bb_upper")
    bb_lower = indicators.get("bb_lower")
    
    if close is None:
        return Signal(action="hold", reason="Missing price data", confidence=0.0)
    
    min_conf = params.get("min_confidence", 0.6)
    
    bullish_count = 0
    bearish_count = 0
    reasons = []
    
    # RSI check
    if rsi_val is not None:
        if rsi_val < 40:
            bullish_count += 1
            reasons.append(f"RSI bullish: {rsi_val:.1f}")
        elif rsi_val > 60:
            bearish_count += 1
            reasons.append(f"RSI bearish: {rsi_val:.1f}")
    
    # MACD check
    if macd_hist is not None:
        if macd_hist > 0:
            bullish_count += 1
            reasons.append("MACD positive")
        elif macd_hist < 0:
            bearish_count += 1
            reasons.append("MACD negative")
    
    # Trend check
    if trend in ("bullish", "bullish_crossover"):
        bullish_count += 1
        reasons.append(f"Trend: {trend}")
    elif trend in ("bearish", "bearish_crossover"):
        bearish_count += 1
        reasons.append(f"Trend: {trend}")
    
    # Bollinger Bands check
    if bb_upper is not None and bb_lower is not None:
        if close <= bb_lower:
            bullish_count += 1
            reasons.append("Price at lower BB")
        elif close >= bb_upper:
            bearish_count += 1
            reasons.append("Price at upper BB")
    
    total_checks = 4
    if bullish_count >= 3:
        confidence = min(bullish_count / total_checks, 1.0)
        if confidence >= min_conf:
            return Signal(
                action="buy",
                confidence=confidence,
                price=close,
                reason="Confluence BUY: " + " | ".join(reasons),
            )
    elif bearish_count >= 3:
        confidence = min(bearish_count / total_checks, 1.0)
        if confidence >= min_conf:
            return Signal(
                action="sell",
                confidence=confidence,
                price=close,
                reason="Confluence SELL: " + " | ".join(reasons),
            )
    
    return Signal(
        action="hold",
        confidence=0.0,
        price=close,
        reason=f"Confluence: Bullish={bullish_count}, Bearish={bearish_count}",
    )


# ── Extended strategy library (unlocked by the enriched indicator set) ──────────
# These use the real indicators now computed in compute_full_indicators():
# stochastic, ADX, Williams %R, CCI, OBV, volatility ratio, EMA200, SMA50, etc.

def stochastic_reversal(indicators: dict, params: dict) -> Signal:
    """Stochastic oversold/overbought reversal (ranging markets)."""
    k = indicators.get("stoch_k")
    d = indicators.get("stoch_d")
    close = indicators.get("close")
    if k is None or d is None or close is None:
        return Signal(action="hold", reason="Missing stochastic", confidence=0.0)
    if k < 20 and k > d:
        return Signal(action="buy", confidence=min((20 - k) / 20 + 0.5, 0.9), price=close,
                      reason=f"Stochastic reversal up: K={k:.0f}")
    if k > 80 and k < d:
        return Signal(action="sell", confidence=min((k - 80) / 20 + 0.5, 0.9), price=close,
                      reason=f"Stochastic reversal down: K={k:.0f}")
    return Signal(action="hold", reason=f"Stochastic neutral: K={k:.0f}", confidence=0.0)


def adx_trend_strength(indicators: dict, params: dict) -> Signal:
    """Trade in the trend direction only when ADX confirms a strong trend."""
    adx_v = indicators.get("adx")
    trend = indicators.get("trend", "neutral")
    close = indicators.get("close")
    if adx_v is None or close is None:
        return Signal(action="hold", reason="Missing ADX", confidence=0.0)
    if adx_v >= 25:
        conf = min(adx_v / 50, 0.9)
        if trend == "bullish":
            return Signal(action="buy", confidence=conf, price=close, reason=f"ADX strong trend {adx_v:.0f} bullish")
        if trend == "bearish":
            return Signal(action="sell", confidence=conf, price=close, reason=f"ADX strong trend {adx_v:.0f} bearish")
    return Signal(action="hold", reason=f"ADX weak: {adx_v:.0f}", confidence=0.0)


def williams_r_reversal(indicators: dict, params: dict) -> Signal:
    """Williams %R reversal from extremes."""
    wr = indicators.get("williams_r")
    close = indicators.get("close")
    if wr is None or close is None:
        return Signal(action="hold", reason="Missing Williams %R", confidence=0.0)
    if wr <= -80:
        return Signal(action="buy", confidence=min((abs(wr) - 80) / 20 + 0.5, 0.85), price=close,
                      reason=f"Williams %R oversold: {wr:.0f}")
    if wr >= -20:
        return Signal(action="sell", confidence=min((20 - abs(wr)) / 20 + 0.5, 0.85), price=close,
                      reason=f"Williams %R overbought: {wr:.0f}")
    return Signal(action="hold", reason=f"Williams %R neutral: {wr:.0f}", confidence=0.0)


def cci_breakout(indicators: dict, params: dict) -> Signal:
    """CCI breakout beyond +/-100."""
    cci_v = indicators.get("cci")
    close = indicators.get("close")
    if cci_v is None or close is None:
        return Signal(action="hold", reason="Missing CCI", confidence=0.0)
    if cci_v > 100:
        return Signal(action="buy", confidence=min(cci_v / 300 + 0.5, 0.85), price=close,
                      reason=f"CCI breakout up: {cci_v:.0f}")
    if cci_v < -100:
        return Signal(action="sell", confidence=min(abs(cci_v) / 300 + 0.5, 0.85), price=close,
                      reason=f"CCI breakout down: {cci_v:.0f}")
    return Signal(action="hold", reason=f"CCI neutral: {cci_v:.0f}", confidence=0.0)


def golden_cross_50_200(indicators: dict, params: dict) -> Signal:
    """Long-term trend via price vs EMA200 / SMA50 alignment."""
    close = indicators.get("close")
    ema200 = indicators.get("ema_200")
    sma50 = indicators.get("sma_50")
    if close is None or ema200 is None or sma50 is None:
        return Signal(action="hold", reason="Missing MAs", confidence=0.0)
    if close > sma50 > ema200:
        return Signal(action="buy", confidence=0.6, price=close, reason="Price>SMA50>EMA200 (uptrend)")
    if close < sma50 < ema200:
        return Signal(action="sell", confidence=0.6, price=close, reason="Price<SMA50<EMA200 (downtrend)")
    return Signal(action="hold", reason="MAs not aligned", confidence=0.0)


def bollinger_squeeze_breakout(indicators: dict, params: dict) -> Signal:
    """Low-volatility squeeze then breakout in trend direction."""
    close = indicators.get("close")
    bb_u = indicators.get("bb_upper")
    bb_l = indicators.get("bb_lower")
    vr = indicators.get("volatility_ratio", 1.0)
    trend = indicators.get("trend", "neutral")
    if close is None or bb_u is None or bb_l is None:
        return Signal(action="hold", reason="Missing BB", confidence=0.0)
    # squeeze = volatility contracting
    if vr < 0.9:
        if close >= bb_u and trend != "bearish":
            return Signal(action="buy", confidence=0.65, price=close, reason="BB squeeze breakout up")
        if close <= bb_l and trend != "bullish":
            return Signal(action="sell", confidence=0.65, price=close, reason="BB squeeze breakout down")
    return Signal(action="hold", reason=f"No squeeze breakout (vr={vr:.2f})", confidence=0.0)


def macd_cross(indicators: dict, params: dict) -> Signal:
    """MACD line vs signal line crossover."""
    line = indicators.get("macd_line")
    sig = indicators.get("macd_signal")
    close = indicators.get("close")
    if line is None or sig is None or close is None:
        return Signal(action="hold", reason="Missing MACD", confidence=0.0)
    diff = line - sig
    if diff > 0:
        return Signal(action="buy", confidence=min(abs(diff) * 5 + 0.45, 0.8), price=close,
                      reason="MACD line above signal")
    if diff < 0:
        return Signal(action="sell", confidence=min(abs(diff) * 5 + 0.45, 0.8), price=close,
                      reason="MACD line below signal")
    return Signal(action="hold", reason="MACD flat", confidence=0.0)


def volume_breakout(indicators: dict, params: dict) -> Signal:
    """Breakout confirmed by above-average volume."""
    close = indicators.get("close")
    vol = indicators.get("volume", 0) or 0
    vol_sma = indicators.get("volume_sma", 0) or 0
    trend = indicators.get("trend", "neutral")
    if close is None or vol_sma <= 0:
        return Signal(action="hold", reason="Missing volume", confidence=0.0)
    if vol > vol_sma * 1.5:
        conf = min(vol / (vol_sma * 3) + 0.4, 0.8)
        if trend == "bullish":
            return Signal(action="buy", confidence=conf, price=close, reason="Volume surge + uptrend")
        if trend == "bearish":
            return Signal(action="sell", confidence=conf, price=close, reason="Volume surge + downtrend")
    return Signal(action="hold", reason="Volume normal", confidence=0.0)


def rsi_divergence_momentum(indicators: dict, params: dict) -> Signal:
    """RSI momentum with mid-line (50) as trend filter."""
    rsi_val = indicators.get("rsi")
    close = indicators.get("close")
    macd_hist = indicators.get("macd_histogram", 0) or 0
    if rsi_val is None or close is None:
        return Signal(action="hold", reason="Missing RSI", confidence=0.0)
    if rsi_val > 50 and macd_hist > 0:
        return Signal(action="buy", confidence=min((rsi_val - 50) / 50 + 0.45, 0.8), price=close,
                      reason=f"RSI momentum up {rsi_val:.0f} + MACD+")
    if rsi_val < 50 and macd_hist < 0:
        return Signal(action="sell", confidence=min((50 - rsi_val) / 50 + 0.45, 0.8), price=close,
                      reason=f"RSI momentum down {rsi_val:.0f} + MACD-")
    return Signal(action="hold", reason=f"RSI/MACD mixed: {rsi_val:.0f}", confidence=0.0)


def macd_osma_power_confluence(indicators: dict, params: dict) -> Signal:
    """
    RETIRED (1b): no longer registered as a live strategy. Kept ONLY as a
    reference for the DELIBERATE Bulls/Bears zero-line math (see memory
    `bulls_bears_power_logic`). The live confluence is OsMA_Confluence
    (src/strategies/osma_confluence.py -> confluence_signal.py).

    ⚠️ Bulls/Bears zero-line logic is DELIBERATE and CORRECT — DO NOT flip the
    operators (LLMs tend to "fix" these back to the legacy bug).

    LONG when:  MACD line > 0  AND  OsMA > 0  AND  Bears Power >= 0.0
    SHORT when: MACD line < 0  AND  OsMA < 0  AND  Bulls Power <= 0.0
    """
    close = indicators.get("close")
    macd_line = indicators.get("macd_line")
    osma = indicators.get("osma")
    bulls = indicators.get("bulls_power")
    bears = indicators.get("bears_power")
    if None in (close, macd_line, osma, bulls, bears):
        return Signal(action="hold", reason="Missing confluence inputs", confidence=0.0)

    # LONG: momentum up (MACD>0, OsMA>0) with bears neutralised (>= 0.0)  [CORRECT: >= not <]
    if macd_line > 0 and osma > 0 and bears >= 0.0:
        conf = min(0.6 + min(osma, 1.0) * 0.2 + (0.1 if bulls > 0 else 0), 0.9)
        return Signal(action="buy", confidence=conf, price=close,
                      reason=f"Confluence LONG: MACD>0, OsMA>0, Bears={bears:.2f}>=0 (neutralised)")

    # SHORT: momentum down (MACD<0, OsMA<0) with bulls neutralised (<= 0.0)  [CORRECT: <= not >]
    if macd_line < 0 and osma < 0 and bulls <= 0.0:
        conf = min(0.6 + min(abs(osma), 1.0) * 0.2 + (0.1 if bears < 0 else 0), 0.9)
        return Signal(action="sell", confidence=conf, price=close,
                      reason=f"Confluence SHORT: MACD<0, OsMA<0, Bulls={bulls:.2f}<=0 (neutralised)")

    return Signal(action="hold", reason="No MACD/OsMA/Power confluence", confidence=0.0)


# ═══════════════════════════════════════════════════════════════════════════════
#  STRATEGY REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════
class StrategyRegistry:
    """
    Registry of all available trading strategies.
    
    Provides dynamic discovery, querying, and selection of strategies
    based on market conditions and historical performance.
    
    Usage:
        registry = StrategyRegistry()
        
        # Get all strategies
        all_strats = registry.get_all()
        
        # Find strategies suitable for current market
        suitable = registry.find_suitable(indicators)
        
        # Get best strategy based on historical performance
        best = registry.get_best_strategy(indicators, vector_store)
    """
    
    def __init__(self):
        self._strategies: dict[str, StrategyDefinition] = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register all built-in strategies."""
        self.register(StrategyDefinition(
            name="RSI_MeanReversion",
            description="RSI-based mean reversion: buy oversold, sell overbought",
            indicators_used=["rsi", "close"],
            suitable_regimes=["ranging", "quiet"],
            signal_fn=rsi_mean_reversion,
            params={"rsi_oversold": 30, "rsi_overbought": 70},
            min_confidence=0.5,
            weight=1,
        ))
        
        self.register(StrategyDefinition(
            name="EMA_TrendFollow",
            description="EMA crossover trend following: golden cross / death cross",
            indicators_used=["ema_fast", "ema_slow", "close", "trend"],
            suitable_regimes=["trending"],
            signal_fn=ema_trend_follow,
            params={"min_confidence": 0.5},
            min_confidence=0.5,
            weight=2,
        ))
        
        self.register(StrategyDefinition(
            name="MACD_Momentum",
            description="MACD histogram momentum: trade with momentum direction",
            indicators_used=["macd_histogram", "close"],
            suitable_regimes=["trending", "ranging"],
            signal_fn=macd_momentum,
            params={"min_confidence": 0.5},
            min_confidence=0.4,
            weight=1,
        ))
        
        self.register(StrategyDefinition(
            name="BB_Bounce",
            description="Bollinger Band bounce: mean reversion at band extremes",
            indicators_used=["bb_upper", "bb_lower", "bb_middle", "close"],
            suitable_regimes=["ranging", "quiet"],
            signal_fn=bollinger_bounce,
            params={"min_confidence": 0.5},
            min_confidence=0.5,
            weight=1,
        ))
        
        self.register(StrategyDefinition(
            name="SR_Breakout",
            description="Support/Resistance breakout: trade breakouts of key levels",
            indicators_used=["close", "support_levels", "resistance_levels", "atr"],
            suitable_regimes=["volatile", "trending"],
            signal_fn=support_resistance_breakout,
            params={"min_confidence": 0.5},
            min_confidence=0.5,
            weight=2,
        ))
        
        self.register(StrategyDefinition(
            name="ATR_Breakout",
            description="ATR volatility breakout: trade when volatility expands with trend",
            indicators_used=["atr", "close", "trend"],
            suitable_regimes=["volatile"],
            signal_fn=atr_volatility_breakout,
            params={"min_confidence": 0.5},
            min_confidence=0.5,
            weight=1,
        ))
        
        self.register(StrategyDefinition(
            name="Multi_Confluence",
            description="Multi-indicator confluence: highest confidence, most conservative",
            indicators_used=["rsi", "macd_histogram", "trend", "bb_upper", "bb_lower", "close"],
            suitable_regimes=["trending", "ranging", "volatile", "quiet"],
            signal_fn=multi_indicator_confluence,
            params={"min_confidence": 0.6},
            min_confidence=0.6,
            weight=3,
        ))

        # ── Extended library (enabled by the enriched indicator set) ──
        self.register(StrategyDefinition(
            name="Stochastic_Reversal",
            description="Stochastic oversold/overbought reversal",
            indicators_used=["stoch_k", "stoch_d", "close"],
            suitable_regimes=["ranging", "quiet"],
            signal_fn=stochastic_reversal, min_confidence=0.5, weight=1,
        ))
        self.register(StrategyDefinition(
            name="ADX_TrendStrength",
            description="Trade with trend only when ADX confirms strength",
            indicators_used=["adx", "trend", "close"],
            suitable_regimes=["trending", "volatile"],
            signal_fn=adx_trend_strength, min_confidence=0.5, weight=2,
        ))
        self.register(StrategyDefinition(
            name="WilliamsR_Reversal",
            description="Williams %R reversal from extremes",
            indicators_used=["williams_r", "close"],
            suitable_regimes=["ranging", "quiet"],
            signal_fn=williams_r_reversal, min_confidence=0.5, weight=1,
        ))
        self.register(StrategyDefinition(
            name="CCI_Breakout",
            description="CCI breakout beyond +/-100",
            indicators_used=["cci", "close"],
            suitable_regimes=["trending", "volatile"],
            signal_fn=cci_breakout, min_confidence=0.5, weight=1,
        ))
        self.register(StrategyDefinition(
            name="GoldenCross_50_200",
            description="Long-term trend via price/SMA50/EMA200 alignment",
            indicators_used=["close", "sma_50", "ema_200"],
            suitable_regimes=["trending"],
            signal_fn=golden_cross_50_200, min_confidence=0.5, weight=2,
        ))
        self.register(StrategyDefinition(
            name="BB_SqueezeBreakout",
            description="Low-volatility squeeze then breakout",
            indicators_used=["bb_upper", "bb_lower", "volatility_ratio", "trend", "close"],
            suitable_regimes=["quiet", "volatile"],
            signal_fn=bollinger_squeeze_breakout, min_confidence=0.5, weight=2,
        ))
        self.register(StrategyDefinition(
            name="MACD_Cross",
            description="MACD line vs signal crossover",
            indicators_used=["macd_line", "macd_signal", "close"],
            suitable_regimes=["trending", "ranging"],
            signal_fn=macd_cross, min_confidence=0.45, weight=1,
        ))
        self.register(StrategyDefinition(
            name="Volume_Breakout",
            description="Breakout confirmed by above-average volume",
            indicators_used=["volume", "volume_sma", "trend", "close"],
            suitable_regimes=["volatile", "trending"],
            signal_fn=volume_breakout, min_confidence=0.5, weight=1,
        ))
        self.register(StrategyDefinition(
            name="RSI_Momentum",
            description="RSI mid-line momentum with MACD filter",
            indicators_used=["rsi", "macd_histogram", "close"],
            suitable_regimes=["trending"],
            signal_fn=rsi_divergence_momentum, min_confidence=0.45, weight=1,
        ))
        # NOTE (1b): MACD_OsMA_Power_Confluence was RETIRED. It was a third,
        # lighter-weight confluence (MACD/OsMA/Bulls/Bears only, no EMA/ATR/RSI).
        # The single source of truth is now OsMA_Confluence (src/strategies/
        # osma_confluence.py -> confluence_signal.py).
        #
        # (1c) Register OsMA_Confluence HERE too, not only at engine start, so that
        # ANY registry (optimizer, edge-discovery, backtester, tests) can resolve the
        # focused pocket and walkforward_focused actually simulates the tuned params.
        # Without this, focused_rules() -> OsMA_Confluence would be unresolvable in a
        # bare registry and the optimizer would silently validate nothing.
        try:
            from src.strategies.osma_confluence import register as _register_osma
            _register_osma(self)
        except Exception as _e:  # pragma: no cover - defensive
            logger.warning(f"OsMA_Confluence default registration skipped: {_e}")
    
    def register(self, strategy: StrategyDefinition):
        """Register a new strategy."""
        self._strategies[strategy.name] = strategy
        logger.info(f"Registered strategy: {strategy.name}")

    def register_custom(
        self,
        name: str,
        signal_fn: Callable,
        description: str = "",
        indicators_used: Optional[list] = None,
        suitable_regimes: Optional[list] = None,
        params: Optional[dict] = None,
        min_confidence: float = 0.5,
        weight: float = 1.0,
        status: str = "testing",
    ) -> StrategyDefinition:
        """
        Dynamically register a NEW strategy at runtime.

        This is the extensibility hook: reflection/strategy-search (or a human)
        can add new strategies without editing this file. New strategies default
        to status="testing" so they are evaluated but can be gated from live
        weighting until validated.
        """
        sd = StrategyDefinition(
            name=name,
            description=description or f"Custom strategy {name}",
            indicators_used=indicators_used or [],
            suitable_regimes=suitable_regimes or ["trending", "ranging", "volatile", "quiet"],
            signal_fn=signal_fn,
            params=params or {},
            min_confidence=min_confidence,
            weight=weight,
            status=status,
        )
        self.register(sd)
        return sd

    def set_status(self, name: str, status: str):
        """Set a strategy's status: active | testing | disabled."""
        if name in self._strategies:
            self._strategies[name].status = status
            logger.info(f"Strategy {name} status -> {status}")

    def active_count(self) -> int:
        """Number of non-disabled strategies."""
        return sum(1 for s in self._strategies.values() if getattr(s, "status", "active") != "disabled")
    
    def get_all(self) -> list[StrategyDefinition]:
        """Get all registered strategies."""
        return list(self._strategies.values())
    
    def get(self, name: str) -> Optional[StrategyDefinition]:
        """Get a specific strategy by name."""
        return self._strategies.get(name)
    
    def get_names(self) -> list[str]:
        """Get names of all registered strategies."""
        return list(self._strategies.keys())
    
    def find_suitable(self, indicators: dict) -> list[StrategyDefinition]:
        """
        Find strategies suitable for the current market regime.
        
        Analyzes indicators to determine the current market regime,
        then returns strategies that work well in that regime.
        """
        regime = self._detect_market_regime(indicators)
        suitable = [
            s for s in self._strategies.values()
            if regime in s.suitable_regimes
        ]
        logger.info(f"Market regime: {regime}, suitable strategies: {[s.name for s in suitable]}")
        return suitable
    
    def _detect_market_regime(self, indicators: dict) -> str:
        """
        Detect the current market regime from indicators.
        
        Returns one of: "trending", "ranging", "volatile", "quiet"
        """
        atr_val = indicators.get("atr", 0) or 0
        close = indicators.get("close", 0) or 0
        rsi_val = indicators.get("rsi", 50) or 50
        trend = indicators.get("trend", "neutral")
        
        # Calculate ATR as percentage of price
        atr_pct = atr_val / close * 100 if close > 0 else 0
        
        # Detect volatility
        if atr_pct > 0.3:
            volatility = "high"
        elif atr_pct > 0.15:
            volatility = "medium"
        else:
            volatility = "low"
        
        # Detect trend strength
        has_trend = trend in ("bullish", "bearish", "bullish_crossover", "bearish_crossover")
        
        # Detect if ranging (RSI in middle, no strong trend)
        is_ranging = 35 <= rsi_val <= 65 and not has_trend
        
        # Determine regime
        if volatility == "high" and has_trend:
            return "volatile"
        elif has_trend:
            return "trending"
        elif is_ranging:
            return "ranging"
        else:
            return "quiet"
    
    def get_best_strategy(
        self,
        indicators: dict,
        vector_store=None,
    ) -> Optional[StrategyDefinition]:
        """
        Get the best strategy for current market conditions.
        
        Uses a combination of:
        1. Market regime detection (filters suitable strategies)
        2. Historical performance from vector store (prefers winning strategies)
        3. Strategy weight (prefers higher-weight strategies when tied)
        
        Args:
            indicators: Current technical indicators.
            vector_store: Optional PatternVectorStore for historical performance.
        
        Returns:
            The best StrategyDefinition, or None if no strategy is suitable.
        """
        suitable = self.find_suitable(indicators)
        if not suitable:
            logger.warning("No suitable strategies found for current market regime")
            return None
        
        # If we have historical data, use it to rank strategies
        if vector_store:
            best_strategies = vector_store.get_best_strategies(min_samples=1)
            strategy_win_rates = {s["strategy"]: s["win_rate"] for s in best_strategies}
            
            # Score each suitable strategy
            scored = []
            for s in suitable:
                score = s.weight * 10  # Base score from weight
                
                # Bonus from historical win rate
                win_rate = strategy_win_rates.get(s.name, 50.0)
                score += win_rate * 0.5  # Win rate contributes up to 50 points
                
                scored.append((score, s))
            
            scored.sort(key=lambda x: x[0], reverse=True)
            best = scored[0][1]
            logger.info(f"Best strategy (scored): {best.name} (score={scored[0][0]:.1f})")
            return best
        
        # Without historical data, use weight and suitability
        suitable.sort(key=lambda s: s.weight, reverse=True)
        best = suitable[0]
        logger.info(f"Best strategy (weight): {best.name}")
        return best
    
    def run_strategy(
        self,
        strategy_name: str,
        indicators: dict,
    ) -> Signal:
        """
        Run a specific strategy and get its signal.
        
        Args:
            strategy_name: Name of the strategy to run.
            indicators: Current technical indicators.
        
        Returns:
            Signal from the strategy.
        """
        strategy = self._strategies.get(strategy_name)
        if not strategy:
            return Signal(action="hold", reason=f"Unknown strategy: {strategy_name}", confidence=0.0)
        
        return strategy.signal_fn(indicators, strategy.params)
    
    def run_all_strategies(
        self,
        indicators: dict,
    ) -> list[tuple[str, Signal]]:
        """
        Run all strategies and return their signals.
        
        Used by the meta-strategy agent to evaluate all approaches.
        
        Args:
            indicators: Current technical indicators.
        
        Returns:
            List of (strategy_name, Signal) tuples.
        """
        results = []
        for name, strategy in self._strategies.items():
            try:
                signal = strategy.signal_fn(indicators, strategy.params)
                results.append((name, signal))
            except Exception as e:
                logger.error(f"Error running strategy {name}: {e}")
                results.append((name, Signal(action="hold", reason=f"Error: {e}", confidence=0.0)))
        
        return results
    
    def get_focused_signal(self, indicators: dict, params: dict = None):
        """
        FOCUSED high-edge entry: only fire when a validated (strategy x regime)
        pocket triggers for this symbol. Returns a Signal or None.

        `params` (the engine's per-symbol TUNED params incl. LEARNED STRENGTH FLOORS
        osma_min_long/dom_min/runway_min/etc.) is passed straight through to the
        strategy signal_fn. WITHOUT this, the confluence evaluator receives {} and the
        strength gates stay OFF live even when the optimizer/learner found floors — the
        last missing link in the strength wiring.
        """
        from src.strategies.base import Signal
        symbol = indicators.get("symbol", "")
        try:
            from src.learning.edge_weights import focused_rules
        except Exception:
            return None
        rules = focused_rules(symbol)
        if not rules:
            return None
        regime = self._detect_market_regime(indicators)
        close = indicators.get("close")
        last_reason = None
        for name, allowed_regimes in rules:
            if regime not in allowed_regimes:
                continue
            sd = self._strategies.get(name)
            if sd is None or getattr(sd, "status", "active") in ("disabled", "testing"):
                continue
            try:
                # merge the engine's tuned/learned params OVER the strategy defaults so
                # strength floors (and tuned periods) actually reach the confluence.
                call_params = dict(sd.params or {})
                if params:
                    call_params.update(params)
                sig = sd.signal_fn(indicators, call_params)
            except Exception:
                continue
            if sig.action in ("buy", "sell"):
                sig.reason = f"FOCUSED {name}@{regime}: {sig.reason}"
                return sig
            last_reason = getattr(sig, "reason", None)   # capture the real hold reason
        # reached only when the pocket strategy returned hold — surface its ACTUAL
        # reason (e.g. 'no OsMA cross') not a misleading 'no pocket' message.
        return Signal(action="hold", confidence=0.0, price=close,
                      reason=(last_reason or f"no focused pocket in {regime}"))

    def get_ensemble_signal(
        self,
        indicators: dict,
        min_agreement: int = 2,
    ) -> Signal:
        """
        Get an ensemble signal by combining all strategies.
        
        Uses a voting mechanism: if enough strategies agree on a direction,
        generate a signal with confidence proportional to agreement.
        
        Args:
            indicators: Current technical indicators.
            min_agreement: Minimum number of strategies that must agree.
        
        Returns:
            Ensemble Signal.
        """
        results = self.run_all_strategies(indicators)

        # Weighted voting: each strategy's vote is scaled by its learned weight
        # (adapted from real performance) so strategies that actually win count
        # more. Confidence reflects weighted agreement.
        buys = 0
        sells = 0
        w_buy = 0.0
        w_sell = 0.0
        total_confidence_buy = 0.0
        total_confidence_sell = 0.0
        reasons = []

        # per-symbol edge multipliers (edge is symbol-specific — a combo that
        # wins on gold can lose on an index), applied on top of learned weights.
        _sym = indicators.get("symbol", "")
        _regime = self._detect_market_regime(indicators)
        try:
            from src.learning.edge_weights import edge_weight, regime_edge_weight
        except Exception:
            edge_weight = regime_edge_weight = None

        for name, signal in results:
            strat = self._strategies.get(name)
            # Skip disabled AND testing strategies — synthesized candidates
            # (status='testing') must NOT influence live trades until the
            # backtester promotes them to 'active'. This is the promotion gate.
            if strat is not None and getattr(strat, "status", "active") in ("disabled", "testing"):
                continue
            w = getattr(strat, "weight", 1.0) if strat else 1.0
            if edge_weight is not None and _sym:
                # symbol edge x regime-conditioned edge (edge often lives in one regime)
                w *= edge_weight(_sym, name) * regime_edge_weight(_sym, name, _regime)
            if signal.action == "buy":
                buys += 1
                w_buy += w
                total_confidence_buy += signal.confidence * w
                reasons.append(f"{name}: BUY ({signal.confidence:.0%}, w={w:.2f})")
            elif signal.action == "sell":
                sells += 1
                w_sell += w
                total_confidence_sell += signal.confidence * w
                reasons.append(f"{name}: SELL ({signal.confidence:.0%}, w={w:.2f})")

        close = indicators.get("close")

        # ── Conviction-based decision (fixes structural long/side bias) ──
        # Raw weighted-majority always favours the larger camp (we have many more
        # trend-followers than mean-reversion strategies), which structurally
        # buries valid counter-trend / trend-short signals. Instead we score each
        # side by CONVICTION = average weighted confidence (rewards a few
        # high-confidence votes) with a mild breadth bonus. A strong minority can
        # therefore win. Learned weights still matter (they scale each vote).
        import os
        bias_dampen = float(os.getenv("ENSEMBLE_BIAS_DAMPEN", "1.0"))  # 1.0 = neutral

        def conviction(total_conf_w, w_side, n_side):
            if w_side <= 0 or n_side <= 0:
                return 0.0
            avg_conf = total_conf_w / w_side          # avg confidence, weight-adjusted
            breadth = min(n_side / 3.0, 1.0)           # up to 3 agreeing = full breadth
            return avg_conf * (0.7 + 0.3 * breadth)    # mostly conviction, some breadth

        buy_score = conviction(total_confidence_buy, w_buy, buys)
        sell_score = conviction(total_confidence_sell, w_sell, sells) * bias_dampen

        if buys >= min_agreement and buy_score >= sell_score and buy_score > 0:
            return Signal(
                action="buy",
                confidence=min(buy_score, 1.0),
                price=close,
                reason=f"Ensemble BUY (score {buy_score:.2f} vs {sell_score:.2f}): " + " | ".join(reasons),
            )
        elif sells >= min_agreement and sell_score > buy_score and sell_score > 0:
            return Signal(
                action="sell",
                confidence=min(sell_score, 1.0),
                price=close,
                reason=f"Ensemble SELL (score {sell_score:.2f} vs {buy_score:.2f}): " + " | ".join(reasons),
            )

        return Signal(
            action="hold",
            confidence=0.0,
            price=close,
             reason=f"Ensemble: Buy={buys}({buy_score:.2f}), Sell={sells}({sell_score:.2f})",
        )
    
    # ← FIX #4: UPDATE WEIGHTS FROM PERFORMANCE
    def update_weights_from_performance(self, performance_data: dict):
        """
        Update strategy weights based on historical performance.
        
        Win rate directly affects weight:
        - 60% win rate → weight 1.2x (20% boost)
        - 50% win rate → weight 1.0x (neutral)
        - 40% win rate → weight 0.8x (20% penalty)
        
        Args:
            performance_data: Dict from ExperienceDatabase.get_strategy_performance()
        """
        for strategy_name, metrics in performance_data.items():
            if strategy_name not in self._strategies:
                continue
            
            win_rate = metrics.get("win_rate", 50.0)
            
            # Calculate weight factor: (win_rate - 50) / 50 normalized
            # This gives -1.0 to +1.0 range
            factor = (win_rate - 50.0) / 50.0
            
            # Convert to weight multiplier: 0.5x to 1.5x
            # 0% WR → 0.5x, 50% WR → 1.0x, 100% WR → 1.5x
            weight = 1.0 + (factor * 0.5)
            
            # Clamp between 0.2x and 2.0x (allow significant variation)
            weight = max(0.2, min(2.0, weight))

            # Only move weight once a strategy has a minimum sample (shrinkage),
            # so we don't over-react to 2-3 trades.
            trades = metrics.get("trade_count", metrics.get("total_trades", 0)) or 0
            if trades < 10:
                # blend toward neutral proportional to how little data we have
                weight = 1.0 + (weight - 1.0) * (trades / 10.0)

            self._strategies[strategy_name].weight = round(weight, 3)

            logger.info(
                f"Updated {strategy_name}: win_rate={win_rate:.1f}% "
                f"({trades} trades) → weight={self._strategies[strategy_name].weight:.2f}x"
            )
    
    @property
    def count(self) -> int:
        """Number of registered strategies."""
        return len(self._strategies)
