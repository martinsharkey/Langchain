"""
XAUUSD-specific trading strategy implementation.
Combines multiple technical indicators for gold trading signals.
"""

import numpy as np
import pandas as pd
from typing import Optional

from src.strategies.base import BaseStrategy, Signal
from src.strategies.indicators import (
    ohlcv_to_dataframe,
    ema,
    rsi,
    macd,
    bollinger_bands,
    atr,
    support_resistance_levels,
)
from src.utils.logger import get_logger

logger = get_logger("strategy.xauusd")


class XAUUSDStrategy(BaseStrategy):
    """
    Multi-indicator trading strategy for XAUUSD (Gold vs USD).
    
    Combines:
    - EMA crossover (trend direction)
    - RSI (momentum/overbought-oversold)
    - MACD (trend confirmation)
    - Bollinger Bands (volatility)
    - Support/Resistance levels
    - ATR (volatility-based SL/TP)
    
    Default parameters optimized for H1 timeframe.
    """
    
    def __init__(self, params: dict = None):
        """
        Initialize the XAUUSD strategy.
        
        Default params:
        - ema_fast: 9 (fast EMA period)
        - ema_slow: 21 (slow EMA period)
        - rsi_period: 14
        - rsi_overbought: 70
        - rsi_oversold: 30
        - macd_fast: 12
        - macd_slow: 26
        - macd_signal: 9
        - bb_period: 20
        - bb_std: 2.0
        - atr_period: 14
        - sl_atr_multiplier: 1.5
        - tp_rr_ratio: 2.0
        - min_confidence: 0.6
        """
        default_params = {
            "ema_fast": 9,
            "ema_slow": 21,
            "rsi_period": 14,
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "bb_period": 20,
            "bb_std": 2.0,
            "atr_period": 14,
            "sl_atr_multiplier": 1.5,
            "tp_rr_ratio": 2.0,
            "min_confidence": 0.6,
        }
        
        if params:
            default_params.update(params)
        
        super().__init__("XAUUSD_Multi_Indicator", default_params)
        logger.info(f"Initialized {self.name} strategy with params: {self.params}")
    
    def calculate_indicators(self, data: list[dict]) -> dict:
        """
        Calculate all technical indicators for the strategy.
        
        Args:
            data: List of OHLCV candle dicts.
        
        Returns:
            Dict with all indicator values for the latest candle.
        """
        df = ohlcv_to_dataframe(data)
        close = df["close"]
        
        # Calculate indicators
        ema_fast_val = ema(close, self.params["ema_fast"])
        ema_slow_val = ema(close, self.params["ema_slow"])
        rsi_val = rsi(close, self.params["rsi_period"])
        macd_line, signal_line, histogram = macd(
            close,
            self.params["macd_fast"],
            self.params["macd_slow"],
            self.params["macd_signal"],
        )
        bb_upper, bb_middle, bb_lower = bollinger_bands(
            close,
            self.params["bb_period"],
            self.params["bb_std"],
        )
        atr_val = atr(df, self.params["atr_period"])
        support, resistance = support_resistance_levels(df)
        
        # Get latest values
        indicators = {
            "close": close.iloc[-1] if len(close) > 0 else None,
            "ema_fast": ema_fast_val.iloc[-1] if len(ema_fast_val) > 0 else None,
            "ema_slow": ema_slow_val.iloc[-1] if len(ema_slow_val) > 0 else None,
            "rsi": rsi_val.iloc[-1] if len(rsi_val) > 0 else None,
            "macd_line": macd_line.iloc[-1] if len(macd_line) > 0 else None,
            "macd_signal": signal_line.iloc[-1] if len(signal_line) > 0 else None,
            "macd_histogram": histogram.iloc[-1] if len(histogram) > 0 else None,
            "bb_upper": bb_upper.iloc[-1] if len(bb_upper) > 0 else None,
            "bb_middle": bb_middle.iloc[-1] if len(bb_middle) > 0 else None,
            "bb_lower": bb_lower.iloc[-1] if len(bb_lower) > 0 else None,
            "atr": atr_val.iloc[-1] if len(atr_val) > 0 else None,
            "support_levels": support,
            "resistance_levels": resistance,
            "trend": self._determine_trend(ema_fast_val, ema_slow_val),
        }
        
        return indicators
    
    def _determine_trend(
        self,
        ema_fast: pd.Series,
        ema_slow: pd.Series,
    ) -> str:
        """Determine the current trend direction."""
        if len(ema_fast) < 2 or len(ema_slow) < 2:
            return "neutral"
        
        current_fast = ema_fast.iloc[-1]
        current_slow = ema_slow.iloc[-1]
        prev_fast = ema_fast.iloc[-2]
        prev_slow = ema_slow.iloc[-2]
        
        # Bullish: fast EMA above slow EMA and rising
        if current_fast > current_slow and prev_fast > prev_slow:
            return "bullish"
        # Bearish: fast EMA below slow EMA and falling
        elif current_fast < current_slow and prev_fast < prev_slow:
            return "bearish"
        # Crossover or consolidation
        elif current_fast > current_slow and prev_fast <= prev_slow:
            return "bullish_crossover"
        elif current_fast < current_slow and prev_fast >= prev_slow:
            return "bearish_crossover"
        else:
            return "neutral"
    
    def generate_signals(self, data: list[dict]) -> Signal:
        """
        Generate trading signals based on indicator confluence.
        
        The strategy looks for confluence of:
        1. Trend direction (EMA)
        2. Momentum (RSI)
        3. Trend confirmation (MACD)
        4. Volatility context (Bollinger Bands)
        
        Args:
            data: List of OHLCV candle dicts.
        
        Returns:
            Signal with trading decision.
        """
        if len(data) < 50:  # Need enough data
            return Signal(
                action="hold",
                reason="Insufficient data for analysis",
                confidence=0.0,
            )
        
        indicators = self.calculate_indicators(data)
        close = indicators["close"]
        
        if close is None:
            return Signal(action="hold", reason="No price data", confidence=0.0)
        
        # Extract indicator values
        trend = indicators["trend"]
        rsi_val = indicators["rsi"]
        macd_hist = indicators["macd_histogram"]
        bb_upper = indicators["bb_upper"]
        bb_lower = indicators["bb_lower"]
        bb_middle = indicators["bb_middle"]
        atr_val = indicators["atr"]
        
        # Score for bullish and bearish cases
        bullish_score = 0
        bearish_score = 0
        reasons = []
        
        # 1. Trend Analysis (EMA)
        if trend in ("bullish", "bullish_crossover"):
            bullish_score += 2
            reasons.append(f"EMA trend: {trend}")
        elif trend in ("bearish", "bearish_crossover"):
            bearish_score += 2
            reasons.append(f"EMA trend: {trend}")
        
        # 2. RSI Analysis
        if rsi_val is not None:
            if rsi_val < self.params["rsi_oversold"]:
                bullish_score += 2
                reasons.append(f"RSI oversold: {rsi_val:.1f}")
            elif rsi_val > self.params["rsi_overbought"]:
                bearish_score += 2
                reasons.append(f"RSI overbought: {rsi_val:.1f}")
            elif 40 < rsi_val < 60:
                # Neutral RSI — no strong signal
                pass
            elif rsi_val < 40:
                bullish_score += 1
                reasons.append(f"RSI bearish zone: {rsi_val:.1f}")
            elif rsi_val > 60:
                bearish_score += 1
                reasons.append(f"RSI bullish zone: {rsi_val:.1f}")
        
        # 3. MACD Analysis
        if macd_hist is not None:
            if macd_hist > 0:
                bullish_score += 1
                reasons.append(f"MACD positive: {macd_hist:.2f}")
            elif macd_hist < 0:
                bearish_score += 1
                reasons.append(f"MACD negative: {macd_hist:.2f}")
        
        # 4. Bollinger Bands (price relative to bands)
        if bb_upper is not None and bb_lower is not None:
            if close <= bb_lower:
                bullish_score += 1
                reasons.append("Price at lower Bollinger Band")
            elif close >= bb_upper:
                bearish_score += 1
                reasons.append("Price at upper Bollinger Band")
        
        # Determine action
        min_conf = self.params["min_confidence"]
        max_score = 6  # Maximum possible score
        
        if bullish_score > bearish_score and bullish_score >= 3:
            confidence = min(bullish_score / max_score, 1.0)
            if confidence >= min_conf:
                # Calculate SL and TP
                sl, tp = self._calculate_sl_tp(close, "buy", atr_val, indicators)
                return Signal(
                    action="buy",
                    confidence=confidence,
                    price=close,
                    stop_loss=sl,
                    take_profit=tp,
                    reason=" | ".join(reasons),
                    metadata={"indicators": indicators},
                )
        
        elif bearish_score > bullish_score and bearish_score >= 3:
            confidence = min(bearish_score / max_score, 1.0)
            if confidence >= min_conf:
                sl, tp = self._calculate_sl_tp(close, "sell", atr_val, indicators)
                return Signal(
                    action="sell",
                    confidence=confidence,
                    price=close,
                    stop_loss=sl,
                    take_profit=tp,
                    reason=" | ".join(reasons),
                    metadata={"indicators": indicators},
                )
        
        # No clear signal
        return Signal(
            action="hold",
            confidence=0.0,
            price=close,
            reason=f"No strong signal. Bullish: {bullish_score}, Bearish: {bearish_score}",
        )
    
    def _calculate_sl_tp(
        self,
        price: float,
        action: str,
        atr_val: Optional[float],
        indicators: dict,
    ) -> tuple[Optional[float], Optional[float]]:
        """
        Calculate stop loss and take profit levels.
        
        Uses ATR-based distance with support/resistance levels as reference.
        """
        if atr_val is None or atr_val == 0:
            atr_val = price * 0.005  # Fallback: 0.5% of price
        
        sl_distance = atr_val * self.params["sl_atr_multiplier"]
        tp_distance = sl_distance * self.params["tp_rr_ratio"]
        
        if action == "buy":
            sl = price - sl_distance
            tp = price + tp_distance
            
            # Adjust SL to nearest support level if available
            support = indicators.get("support_levels", [])
            if support:
                nearest_support = max([s for s in support if s < price], default=None)
                if nearest_support and nearest_support > sl:
                    sl = nearest_support - (atr_val * 0.3)
        else:
            sl = price + sl_distance
            tp = price - tp_distance
            
            # Adjust SL to nearest resistance level if available
            resistance = indicators.get("resistance_levels", [])
            if resistance:
                nearest_resistance = min([r for r in resistance if r > price], default=None)
                if nearest_resistance and nearest_resistance < sl:
                    sl = nearest_resistance + (atr_val * 0.3)
        
        return round(sl, 2), round(tp, 2)
    
    def backtest(self, data: list[dict], initial_balance: float = 10000.0) -> dict:
        """
        Run a simple backtest of the strategy on historical data.
        
        Args:
            data: List of OHLCV candle dicts.
            initial_balance: Starting account balance.
        
        Returns:
            Dict with backtest results.
        """
        balance = initial_balance
        position = None  # {"type": "buy"/"sell", "entry": price, "sl": sl, "tp": tp}
        trades = []
        equity_curve = [balance]
        
        for i in range(50, len(data)):  # Start after we have enough data for indicators
            current_data = data[:i+1]
            signal = self.generate_signals(current_data)
            current_price = data[i]["close"]
            
            # Check if we have an open position
            if position is not None:
                # Check stop loss
                if position["type"] == "buy":
                    if current_price <= position["sl"]:
                        loss = (position["sl"] - position["entry"]) / position["entry"] * balance
                        balance += loss
                        trades.append({"type": "buy", "result": "sl_hit", "profit": loss})
                        position = None
                    elif current_price >= position["tp"]:
                        profit = (position["tp"] - position["entry"]) / position["entry"] * balance
                        balance += profit
                        trades.append({"type": "buy", "result": "tp_hit", "profit": profit})
                        position = None
                else:  # sell
                    if current_price >= position["sl"]:
                        loss = (position["entry"] - position["sl"]) / position["entry"] * balance
                        balance += loss
                        trades.append({"type": "sell", "result": "sl_hit", "profit": loss})
                        position = None
                    elif current_price <= position["tp"]:
                        profit = (position["entry"] - position["tp"]) / position["entry"] * balance
                        balance += profit
                        trades.append({"type": "sell", "result": "tp_hit", "profit": profit})
                        position = None
            
            # Open new position if signal is strong
            if position is None and signal.action in ("buy", "sell"):
                if signal.stop_loss and signal.take_profit:
                    position = {
                        "type": signal.action,
                        "entry": current_price,
                        "sl": signal.stop_loss,
                        "tp": signal.take_profit,
                    }
            
            equity_curve.append(balance)
        
        # Calculate metrics
        winning_trades = [t for t in trades if t["profit"] > 0]
        losing_trades = [t for t in trades if t["profit"] <= 0]
        
        total_profit = sum(t["profit"] for t in trades)
        max_drawdown = self._calculate_max_drawdown(equity_curve)
        
        return {
            "initial_balance": initial_balance,
            "final_balance": round(balance, 2),
            "total_return": round((balance - initial_balance) / initial_balance * 100, 2),
            "total_trades": len(trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": round(len(winning_trades) / max(len(trades), 1) * 100, 2),
            "max_drawdown": round(max_drawdown, 2),
            "profit_factor": self._calculate_profit_factor(trades),
            "trades": trades[-20:],  # Last 20 trades
        }
    
    def _calculate_max_drawdown(self, equity_curve: list[float]) -> float:
        """Calculate maximum drawdown from equity curve."""
        if not equity_curve:
            return 0.0
        
        peak = equity_curve[0]
        max_dd = 0.0
        
        for value in equity_curve:
            if value > peak:
                peak = value
            dd = (peak - value) / peak * 100
            if dd > max_dd:
                max_dd = dd
        
        return max_dd
    
    def _calculate_profit_factor(self, trades: list[dict]) -> float:
        """Calculate profit factor (gross profit / gross loss)."""
        gross_profit = sum(t["profit"] for t in trades if t["profit"] > 0)
        gross_loss = abs(sum(t["profit"] for t in trades if t["profit"] < 0))
        
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        
        return round(gross_profit / gross_loss, 2)
