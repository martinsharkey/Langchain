"""
Stochastic14 Strategy - Stochastic Oscillator momentum strategy

Example concrete strategy implementing BaseStrategy interface.

Status: IMPLEMENTATION (Day 4)
"""

import pandas as pd
import numpy as np
from typing import Dict

from src.strategy_interface import BaseStrategy, StrategySignal


class Stochastic14Strategy(BaseStrategy):
    """Stochastic oscillator strategy - buys when %K < 20 (oversold)."""
    
    def __init__(self):
        super().__init__(strategy_name="Stochastic14", strategy_type="momentum")
    
    def calculate_indicators(
        self,
        ohlcv: pd.DataFrame,
        params: Dict[str, float]
    ) -> Dict[str, pd.Series]:
        """
        Calculate Stochastic indicator (%K, %D).
        
        Args:
            ohlcv: DataFrame with 'high', 'low', 'close' columns
            params: {"k_period": 14, "d_period": 3, "smooth": 3}
        
        Returns:
            {"K": Series of %K values, "D": Series of %D values}
        """
        if not self.validate_params(params):
            raise ValueError(f"Invalid params for Stochastic14: {params}")
        
        k_period = int(params.get("k_period", 14))
        d_period = int(params.get("d_period", 3))
        smooth = int(params.get("smooth", 3))
        
        high = ohlcv['high']
        low = ohlcv['low']
        close = ohlcv['close']
        
        # Calculate lowest low and highest high over k_period
        lowest_low = low.rolling(window=k_period, min_periods=1).min()
        highest_high = high.rolling(window=k_period, min_periods=1).max()
        
        # Calculate raw %K
        hl_range = highest_high - lowest_low
        k_raw = 100 * (close - lowest_low) / (hl_range + 1e-10)
        
        # Smooth %K
        k_smooth = k_raw.rolling(window=smooth, min_periods=1).mean()
        
        # Calculate %D (SMA of smoothed %K)
        d = k_smooth.rolling(window=d_period, min_periods=1).mean()
        
        return {
            "K": k_smooth,
            "D": d
        }
    
    def generate_signal(
        self,
        indicators: Dict[str, pd.Series],
        entry_floors: Dict[str, float],
        current_bar_idx: int
    ) -> StrategySignal:
        """
        Generate entry signal when %K < 20 (oversold).
        
        Args:
            indicators: {"K": Series(...), "D": Series(...)}
            entry_floors: {"min_strength": 0.3}
            current_bar_idx: Current bar index
        
        Returns:
            StrategySignal with entry if Stochastic oversold
        """
        k_series = indicators.get("K")
        d_series = indicators.get("D")
        
        # Validate inputs
        if (k_series is None or d_series is None or 
            len(k_series) <= current_bar_idx):
            return StrategySignal(
                should_enter=False,
                entry_price=0,
                entry_type="long",
                confidence=0.0,
                reason="Stochastic not available",
                strength=0.0
            )
        
        current_k = k_series.iloc[current_bar_idx]
        current_d = d_series.iloc[current_bar_idx]
        
        # Check if values are NaN
        if pd.isna(current_k) or pd.isna(current_d):
            return StrategySignal(
                should_enter=False,
                entry_price=0,
                entry_type="long",
                confidence=0.0,
                reason="Stochastic not yet calculated",
                strength=0.0
            )
        
        min_strength = entry_floors.get("min_strength", 0.0)
        
        # Oversold: %K < 20 → buy signal
        if current_k < 20:
            # Calculate strength: 0 at K=20, 1 at K=0
            strength = (20 - current_k) / 20
            
            # Preferentially enter when %K crosses above %D
            if current_bar_idx > 0:
                prev_k = k_series.iloc[current_bar_idx - 1]
                prev_d = d_series.iloc[current_bar_idx - 1]
                
                if not pd.isna(prev_k) and not pd.isna(prev_d):
                    if prev_k <= prev_d and current_k > current_d:
                        strength = min(1.0, strength * 1.2)  # Boost for crossover
            
            if strength >= min_strength:
                return StrategySignal(
                    should_enter=True,
                    entry_price=0,
                    entry_type="long",
                    confidence=strength,
                    reason=f"Stochastic oversold (%K={current_k:.1f}, %D={current_d:.1f})",
                    strength=strength
                )
        
        # No signal
        return StrategySignal(
            should_enter=False,
            entry_price=0,
            entry_type="long",
            confidence=0.0,
            reason=f"Stochastic neutral (%K={current_k:.1f})",
            strength=0.0
        )
    
    def validate_params(self, params: Dict[str, float]) -> bool:
        """
        Validate Stochastic parameters.
        
        Args:
            params: {"k_period": 14, "d_period": 3, "smooth": 3}
        
        Returns:
            True if valid, False otherwise
        """
        required = ["k_period", "d_period", "smooth"]
        for key in required:
            if key not in params:
                return False
        
        try:
            k_period = int(params["k_period"])
            d_period = int(params["d_period"])
            smooth = int(params["smooth"])
            
            if not (1 <= k_period <= 50):
                return False
            if not (1 <= d_period <= 10):
                return False
            if not (1 <= smooth <= 10):
                return False
            
            return True
        except (ValueError, TypeError):
            return False
    
    def get_indicator_names(self) -> list:
        """Return indicator names."""
        return ["K", "D"]


# Register strategy
def register_stochastic14():
    """Register Stochastic14 strategy with global registry."""
    from src.strategy_interface import STRATEGY_REGISTRY
    STRATEGY_REGISTRY.register(Stochastic14Strategy())


__all__ = ['Stochastic14Strategy', 'register_stochastic14']
