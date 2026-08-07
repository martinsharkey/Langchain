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
        
        # Get the focused, high-edge entry (the single live entry: OsMA_Confluence)
        signal = registry.get_focused_signal(indicators, tuned_params)
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
            name="GoldenCross_50_200",
            description="Long-term trend via price/SMA50/EMA200 alignment",
            indicators_used=["close", "sma_50", "ema_200"],
            suitable_regimes=["trending"],
            signal_fn=golden_cross_50_200, min_confidence=0.5, weight=2,
        ))
        self.register(StrategyDefinition(
            name="Volume_Breakout",
            description="Breakout confirmed by above-average volume",
            indicators_used=["volume", "volume_sma", "trend", "close"],
            suitable_regimes=["volatile", "trending"],
            signal_fn=volume_breakout, min_confidence=0.5, weight=1,
        ))
        self.register(StrategyDefinition(
            name="MACD_Cross",
            description="MACD line vs signal crossover",
            indicators_used=["macd_line", "macd_signal", "close"],
            suitable_regimes=["trending", "ranging"],
            signal_fn=macd_cross, min_confidence=0.45, weight=1,
        ))
        # RETIRED: MACD_Momentum, CCI_Breakout, BB_SqueezeBreakout, RSI_Momentum and
        # MACD_OsMA_Power_Confluence have been REMOVED. The single, standardised entry
        # is OsMA_Confluence (src/strategies/osma_confluence.py -> confluence_signal.py).
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
    
    def get_names(self, include_disabled: bool = False) -> list[str]:
        """Get names of registered strategies.

        By default excludes RETIRED strategies (status='disabled') so that
        reflection/synthesis never proposes an entry the bot no longer trades.
        The live entry is OsMA_Confluence only.
        """
        return [
            name for name, s in self._strategies.items()
            if include_disabled or getattr(s, "status", "active") != "disabled"
        ]
    
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
