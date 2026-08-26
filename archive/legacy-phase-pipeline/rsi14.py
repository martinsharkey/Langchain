"""
RSI14 Strategy - Relative Strength Index momentum strategy

Example concrete strategy implementing BaseStrategy interface.

Status: IMPLEMENTATION (Day 4)
"""

import pandas as pd
import numpy as np
from typing import Dict

from src.strategy_interface import BaseStrategy, StrategySignal


class RSI14Strategy(BaseStrategy):
    """RSI14 momentum strategy - buys when RSI < 30 (oversold)."""
    
    def __init__(self):
        super().__init__(strategy_name="RSI14", strategy_type="momentum")
    
    def calculate_indicators(
        self,
        ohlcv: pd.DataFrame,
        params: Dict[str, float]
    ) -> Dict[str, pd.Series]:
        """
        Calculate RSI indicator.
        
        Args:
            ohlcv: DataFrame with 'close' column
            params: {"period": 14}
        
        Returns:
            {"RSI": Series of RSI values}
        """
        if not self.validate_params(params):
            raise ValueError(f"Invalid params for RSI14: {params}")
        
        period = int(params.get("period", 14))
        close = ohlcv['close']
        
        # Calculate price changes
        delta = close.diff()
        
        # Separate gains and losses
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # Calculate average gain and loss
        avg_gain = gain.rolling(window=period, min_periods=1).mean()
        avg_loss = loss.rolling(window=period, min_periods=1).mean()
        
        # Calculate RS and RSI
        rs = avg_gain / (avg_loss + 1e-10)  # avoid division by zero
        rsi = 100 - (100 / (1 + rs))
        
        return {"RSI": rsi}
    
    def generate_signal(
        self,
        indicators: Dict[str, pd.Series],
        entry_floors: Dict[str, float],
        current_bar_idx: int
    ) -> StrategySignal:
        """
        Generate entry signal when RSI < 30 (oversold).
        
        Args:
            indicators: {"RSI": Series(...)}
            entry_floors: {"min_strength": 0.3}
            current_bar_idx: Current bar index
        
        Returns:
            StrategySignal with entry if RSI oversold
        """
        rsi_series = indicators.get("RSI")
        
        # Validate inputs
        if rsi_series is None or len(rsi_series) <= current_bar_idx:
            return StrategySignal(
                should_enter=False,
                entry_price=0,
                entry_type="long",
                confidence=0.0,
                reason="RSI not available",
                strength=0.0
            )
        
        current_rsi = rsi_series.iloc[current_bar_idx]
        
        # Check if RSI is NaN
        if pd.isna(current_rsi):
            return StrategySignal(
                should_enter=False,
                entry_price=0,
                entry_type="long",
                confidence=0.0,
                reason="RSI not yet calculated",
                strength=0.0
            )
        
        min_strength = entry_floors.get("min_strength", 0.0)
        
        # Oversold: RSI < 30 → buy signal
        if current_rsi < 30:
            # Calculate strength: 0 at RSI=30, 1 at RSI=0
            strength = (30 - current_rsi) / 30
            
            if strength >= min_strength:
                return StrategySignal(
                    should_enter=True,
                    entry_price=0,  # ScalpEngine fills actual price
                    entry_type="long",
                    confidence=strength,
                    reason=f"RSI oversold ({current_rsi:.1f})",
                    strength=strength
                )
        
        # No signal
        return StrategySignal(
            should_enter=False,
            entry_price=0,
            entry_type="long",
            confidence=0.0,
            reason=f"RSI neutral ({current_rsi:.1f})",
            strength=0.0
        )
    
    def validate_params(self, params: Dict[str, float]) -> bool:
        """
        Validate RSI parameters.
        
        Args:
            params: {"period": 14}
        
        Returns:
            True if valid, False otherwise
        """
        period = params.get("period")
        if period is None:
            return False
        
        try:
            period = int(period)
            if not (1 <= period <= 50):
                return False
            return True
        except (ValueError, TypeError):
            return False
    
    def get_indicator_names(self) -> list:
        """Return indicator names."""
        return ["RSI"]


# Register strategy
def register_rsi14():
    """Register RSI14 strategy with global registry."""
    from src.strategy_interface import STRATEGY_REGISTRY
    STRATEGY_REGISTRY.register(RSI14Strategy())


__all__ = ['RSI14Strategy', 'register_rsi14']
