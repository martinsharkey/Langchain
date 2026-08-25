"""
Strategy Interface - Generic Strategy Contract

All strategies (40+) implement this interface.
Enables Phase 1 discovery to test any strategy without hardcoding.

Status: IMPLEMENTATION (Day 3)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional
import pandas as pd


@dataclass
class StrategySignal:
    """Unified signal output from any strategy."""
    
    should_enter: bool              # True if entry conditions met
    entry_price: float              # Price at which to enter (bid/ask)
    entry_type: str                 # "long" or "short"
    confidence: float               # 0.0-1.0 (used for position sizing)
    reason: str                     # "RSI oversold", "MACD positive crossover", etc.
    strength: float                 # 0.0-1.0 indicator strength (may be filtered by floor)
    
    def __post_init__(self):
        """Validate signal."""
        if not isinstance(self.should_enter, bool):
            raise ValueError("should_enter must be bool")
        if not (0 <= self.confidence <= 1):
            raise ValueError(f"confidence {self.confidence} not in [0, 1]")
        if not (0 <= self.strength <= 1):
            raise ValueError(f"strength {self.strength} not in [0, 1]")
        if self.entry_type not in ['long', 'short']:
            raise ValueError(f"entry_type must be 'long' or 'short', got {self.entry_type}")


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    All 40+ strategies inherit from this and implement the three core methods.
    """
    
    def __init__(self, strategy_name: str, strategy_type: str):
        """
        Initialize strategy.
        
        Args:
            strategy_name: unique name (e.g., "RSI14", "OsMA_Confluence")
            strategy_type: category (e.g., "momentum", "confluence", "volatility")
        """
        self.strategy_name = strategy_name
        self.strategy_type = strategy_type
    
    @abstractmethod
    def calculate_indicators(
        self,
        ohlcv: pd.DataFrame,
        params: Dict[str, float]
    ) -> Dict[str, pd.Series]:
        """
        Calculate all indicators for the strategy.
        
        Args:
            ohlcv: DataFrame with columns [open, high, low, close, volume]
                   Index can be datetime or integer
            params: Strategy-specific parameters
                    Example: {"period": 14, "overbought": 70}
        
        Returns:
            Dict mapping indicator names to pd.Series
            
            Example return value:
            {
                "RSI": pd.Series([28.5, 29.1, 27.8, ...]),
                "SMA20": pd.Series([1234.56, 1234.78, ...]),
                "EMA50": pd.Series([1234.00, 1234.10, ...])
            }
        
        Raises:
            ValueError: if params missing or invalid
            KeyError: if OHLCV columns missing
        
        Notes:
            - All returned Series must have same length as ohlcv
            - NaN values acceptable for early bars (not enough data for indicator)
            - Returned Series alignment must match ohlcv index
        """
        pass
    
    @abstractmethod
    def generate_signal(
        self,
        indicators: Dict[str, pd.Series],
        entry_floors: Dict[str, float],
        current_bar_idx: int
    ) -> StrategySignal:
        """
        Generate entry signal based on current bar indicators.
        
        Args:
            indicators: Output from calculate_indicators()
                        Example: {"RSI": Series([...]), "SMA": Series([...])}
            
            entry_floors: Per-symbol entry strength floors
                          Example: {"min_strength": 0.3}
                          These come from symbol config or tuned_params.json
            
            current_bar_idx: Index of current bar (last row in indicators)
                             Used to access current and previous values
                             Example: len(ohlcv) - 1 = 99 (bar 100 out of 0-99)
        
        Returns:
            StrategySignal with:
            - should_enter: True only if signal meets strength floor
            - entry_type: "long" or "short"
            - confidence: strength value used in position sizing
            - reason: human-readable reason (for logging)
            - strength: indicator strength (0.0-1.0)
        
        Raises:
            IndexError: if current_bar_idx out of range
        
        Contract:
            1. MUST check if current_bar_idx is valid
            2. MUST return should_enter=False if insufficient data
            3. MUST calculate strength based on indicators
            4. MUST apply floor filter: only enter if strength >= floor
            5. MUST always return StrategySignal (never None)
            6. MUST include descriptive reason string
        
        Example (RSI):
            if current_rsi < 30:
                strength = (30 - current_rsi) / 30  # 0.0-1.0
                if strength >= entry_floors.get("min_strength", 0.0):
                    return StrategySignal(
                        should_enter=True,
                        entry_type="long",
                        confidence=strength,
                        reason=f"RSI oversold ({current_rsi:.1f})",
                        strength=strength
                    )
            return StrategySignal(should_enter=False, ...)
        """
        pass
    
    @abstractmethod
    def validate_params(self, params: Dict[str, float]) -> bool:
        """
        Validate strategy parameters before use.
        
        Args:
            params: Parameters to validate
        
        Returns:
            True if params valid and complete, False otherwise
        
        Raises:
            No exceptions; return False for any validation failure
        
        Notes:
            - All required param keys must be present
            - Values must be within valid ranges
            - No partial params accepted
        
        Example (RSI):
            def validate_params(self, params: Dict[str, float]) -> bool:
                if 'period' not in params:
                    return False
                period = params['period']
                if not (1 <= period <= 50):
                    return False
                return True
        """
        pass
    
    def get_indicator_names(self) -> list:
        """
        Return list of all indicator names this strategy calculates.
        Used for validation and logging.
        
        Returns:
            List of indicator names (strings)
        
        Example:
            >>> strategy = RSI14Strategy()
            >>> strategy.get_indicator_names()
            ['RSI']
            
            >>> strategy = OsMAConfluenceStrategy()
            >>> strategy.get_indicator_names()
            ['OSMA', 'MACD', 'Signal', 'MA']
        """
        return []


class StrategyRegistry:
    """
    Registry of all available strategies.
    
    Singleton pattern - all strategies registered at startup.
    Used by Phase 1 discovery to iterate all strategies.
    """
    
    def __init__(self):
        """Initialize empty registry."""
        self._strategies: Dict[str, BaseStrategy] = {}
    
    def register(self, strategy: BaseStrategy) -> None:
        """
        Register a strategy by its name.
        
        Args:
            strategy: BaseStrategy instance
        
        Raises:
            ValueError: if strategy_name already registered
        """
        if strategy.strategy_name in self._strategies:
            raise ValueError(f"Strategy already registered: {strategy.strategy_name}")
        self._strategies[strategy.strategy_name] = strategy
    
    def get_strategy(self, strategy_name: str) -> BaseStrategy:
        """
        Retrieve strategy by name.
        
        Args:
            strategy_name: name of strategy (e.g., "RSI14")
        
        Returns:
            BaseStrategy instance
        
        Raises:
            ValueError: if strategy not found
        """
        if strategy_name not in self._strategies:
            raise ValueError(
                f"Unknown strategy: {strategy_name}. "
                f"Available: {list(self._strategies.keys())}"
            )
        return self._strategies[strategy_name]
    
    def list_strategies(self) -> list:
        """Return list of registered strategy names."""
        return list(self._strategies.keys())
    
    def list_strategies_by_type(self, strategy_type: str) -> list:
        """
        Return list of strategy names of a specific type.
        
        Args:
            strategy_type: e.g., "momentum", "confluence", "volatility"
        
        Returns:
            List of strategy names
        """
        return [
            name for name, strategy in self._strategies.items()
            if strategy.strategy_type == strategy_type
        ]
    
    def get_all_types(self) -> list:
        """Return list of all unique strategy types."""
        return list(set(s.strategy_type for s in self._strategies.values()))


# Global registry instance
STRATEGY_REGISTRY = StrategyRegistry()


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def register_all_strategies() -> None:
    """
    Register all built-in strategies.
    Called at application startup.
    """
    # Import all strategy modules
    # This will be populated with actual strategy registrations
    # during Days 4-5 implementation
    pass


__all__ = [
    'StrategySignal',
    'BaseStrategy',
    'StrategyRegistry',
    'STRATEGY_REGISTRY',
    'register_all_strategies',
]
