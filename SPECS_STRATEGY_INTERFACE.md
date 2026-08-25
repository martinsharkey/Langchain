# STRATEGY INTERFACE SPECIFICATION

**Document:** Generic Strategy Interface Contract
**Date:** 2026-08-25
**Status:** SPECIFICATION

---

## Overview

All 40+ strategies (OsMA, RSI, Stochastic, MACD, Bollinger, ATR, etc.) implement a common interface. This enables Phase 1 discovery to test any strategy without hardcoding logic.

---

## Core Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional
import pandas as pd

@dataclass
class StrategySignal:
    """Unified signal output from any strategy."""
    should_enter: bool          # True if entry conditions met
    entry_price: float          # Price at which to enter (bid/ask)
    entry_type: str             # "long" or "short"
    confidence: float           # 0.0-1.0 (used for position sizing)
    reason: str                 # "RSI oversold", "MACD positive crossover", etc.
    strength: float             # 0.0-1.0 indicator strength (may be filtered by floor)

@dataclass
class IndicatorValues:
    """Holds all calculated indicators for current bar."""
    timestamp: int              # Unix timestamp
    ohlcv_index: int            # OHLCV dataframe index
    values: Dict[str, float]    # All indicator values: {"RSI": 25.5, "SMA20": 1234.56, ...}

class BaseStrategy(ABC):
    """Abstract base class for all strategies."""
    
    def __init__(self, strategy_name: str, strategy_type: str):
        self.strategy_name = strategy_name  # e.g., "RSI14"
        self.strategy_type = strategy_type  # e.g., "momentum"
    
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
            params: Strategy-specific parameters (e.g., {"period": 14})
        
        Returns:
            Dict mapping indicator names to pd.Series
            Example: {
                "RSI": Series([28.5, 29.1, 27.8, ...]),
                "MA20": Series([1234.56, 1234.78, ...])
            }
        
        Raises:
            ValueError if params missing or invalid
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
            entry_floors: Per-symbol entry strength floors (e.g., {"min_strength": 0.3})
            current_bar_idx: Index of current bar (last row in indicators)
        
        Returns:
            StrategySignal with should_enter, entry_price, entry_type, confidence, reason
        
        Rules:
            - MUST check: current bar index valid
            - MUST set: confidence based on indicator strength
            - MUST check: strength >= entry_floors.get("min_strength", 0.0)
            - MUST include reason string for entry (for logging)
        
        Raises:
            IndexError if current_bar_idx out of range
        """
        pass
    
    @abstractmethod
    def validate_params(self, params: Dict[str, float]) -> bool:
        """
        Validate strategy parameters before use.
        
        Args:
            params: Parameters to validate
        
        Returns:
            True if valid, False otherwise
        
        Example (RSI):
            - "period" must be int, 1-50
            - "overbought" must be float, 50-100
            - "oversold" must be float, 0-50
        """
        pass
    
    def get_indicator_names(self) -> list:
        """
        Return list of all indicator names this strategy calculates.
        Used for validation and logging.
        
        Returns: ["RSI", "SMA20"] for RSI strategy
        """
        return []  # Override in subclasses
```

---

## Concrete Example: RSI14 Strategy

```python
class RSI14Strategy(BaseStrategy):
    """RSI Relative Strength Index momentum strategy."""
    
    def __init__(self):
        super().__init__(strategy_name="RSI14", strategy_type="momentum")
    
    def calculate_indicators(
        self, 
        ohlcv: pd.DataFrame,
        params: Dict[str, float]
    ) -> Dict[str, pd.Series]:
        """Calculate RSI indicator."""
        if not self.validate_params(params):
            raise ValueError(f"Invalid params for RSI14: {params}")
        
        period = int(params.get("period", 14))
        
        close = ohlcv['close']
        delta = close.diff()
        
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        rs = avg_gain / (avg_loss + 1e-10)  # avoid division by zero
        rsi = 100 - (100 / (1 + rs))
        
        return {
            "RSI": rsi
        }
    
    def generate_signal(
        self,
        indicators: Dict[str, pd.Series],
        entry_floors: Dict[str, float],
        current_bar_idx: int
    ) -> StrategySignal:
        """Generate buy/sell signals based on RSI."""
        rsi = indicators.get("RSI")
        
        if rsi is None or len(rsi) <= current_bar_idx:
            return StrategySignal(
                should_enter=False,
                entry_price=0,
                entry_type="long",
                confidence=0.0,
                reason="RSI not available",
                strength=0.0
            )
        
        current_rsi = rsi.iloc[current_bar_idx]
        min_strength = entry_floors.get("min_strength", 0.0)
        
        # Oversold: RSI < 30 → buy signal
        if current_rsi < 30:
            strength = (30 - current_rsi) / 30  # 0.0-1.0
            
            if strength >= min_strength:
                return StrategySignal(
                    should_enter=True,
                    entry_price=0,  # ScalpEngine fills actual price
                    entry_type="long",
                    confidence=strength,
                    reason=f"RSI oversold ({current_rsi:.1f})",
                    strength=strength
                )
        
        return StrategySignal(
            should_enter=False,
            entry_price=0,
            entry_type="long",
            confidence=0.0,
            reason=f"RSI neutral ({current_rsi:.1f})",
            strength=0.0
        )
    
    def validate_params(self, params: Dict[str, float]) -> bool:
        """Validate RSI parameters."""
        period = params.get("period")
        if period is None or not (1 <= period <= 50):
            return False
        return True
    
    def get_indicator_names(self) -> list:
        return ["RSI"]
```

---

## Concrete Example: OsMA_Confluence Strategy

```python
class OsMAConfluenceStrategy(BaseStrategy):
    """OsMA + MA confluence strategy."""
    
    def __init__(self):
        super().__init__(strategy_name="OsMA_Confluence", strategy_type="confluence")
    
    def calculate_indicators(
        self,
        ohlcv: pd.DataFrame,
        params: Dict[str, float]
    ) -> Dict[str, pd.Series]:
        """Calculate OsMA, MACD, and moving averages."""
        if not self.validate_params(params):
            raise ValueError(f"Invalid params: {params}")
        
        osma_fast = int(params.get("osma_fast", 12))
        osma_slow = int(params.get("osma_slow", 26))
        osma_signal = int(params.get("osma_signal", 9))
        ma_period = int(params.get("ma_period", 20))
        
        close = ohlcv['close']
        
        # MACD
        ema_fast = close.ewm(span=osma_fast).mean()
        ema_slow = close.ewm(span=osma_slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=osma_signal).mean()
        osma = macd_line - signal_line
        
        # Moving average
        ma = close.rolling(window=ma_period).mean()
        
        return {
            "OSMA": osma,
            "MACD": macd_line,
            "Signal": signal_line,
            "MA": ma
        }
    
    def generate_signal(
        self,
        indicators: Dict[str, pd.Series],
        entry_floors: Dict[str, float],
        current_bar_idx: int
    ) -> StrategySignal:
        """Generate signals: OsMA positive + price > MA."""
        osma = indicators.get("OSMA")
        ma = indicators.get("MA")
        
        if osma is None or ma is None or len(osma) <= current_bar_idx:
            return StrategySignal(should_enter=False, entry_price=0, entry_type="long",
                                confidence=0.0, reason="Indicators unavailable", strength=0.0)
        
        # This would be implemented in the concrete strategy
        return StrategySignal(should_enter=False, entry_price=0, entry_type="long",
                            confidence=0.0, reason="No signal", strength=0.0)
    
    def validate_params(self, params: Dict[str, float]) -> bool:
        """Validate OsMA parameters."""
        return all(key in params for key in ["osma_fast", "osma_slow", "osma_signal", "ma_period"])
    
    def get_indicator_names(self) -> list:
        return ["OSMA", "MACD", "Signal", "MA"]
```

---

## Strategy Registry

```python
class StrategyRegistry:
    """Registry of all available strategies."""
    
    def __init__(self):
        self._strategies = {}
    
    def register(self, strategy: BaseStrategy):
        """Register a strategy by its name."""
        self._strategies[strategy.strategy_name] = strategy
    
    def get_strategy(self, strategy_name: str) -> BaseStrategy:
        """Retrieve strategy by name."""
        if strategy_name not in self._strategies:
            raise ValueError(f"Unknown strategy: {strategy_name}")
        return self._strategies[strategy_name]
    
    def list_strategies(self) -> list:
        """Return list of registered strategy names."""
        return list(self._strategies.keys())

# Global registry
STRATEGY_REGISTRY = StrategyRegistry()

# Register all strategies at startup
STRATEGY_REGISTRY.register(RSI14Strategy())
STRATEGY_REGISTRY.register(OsMAConfluenceStrategy())
# ... register 38+ more strategies
```

---

## Usage in Phase 1 (Discovery)

```python
def discover_strategies_for_session(
    symbol: str,
    session: str,
    timeframe: str,
    ohlcv: pd.DataFrame,
    entry_floors: Dict[str, float]
) -> List[DiscoveredStrategy]:
    """Test all strategies, return ranked by Profit Factor."""
    
    results = []
    
    for strategy_name in STRATEGY_REGISTRY.list_strategies():
        strategy = STRATEGY_REGISTRY.get_strategy(strategy_name)
        
        # Use default params for discovery phase
        default_params = get_default_params(strategy_name)
        
        # Calculate indicators
        try:
            indicators = strategy.calculate_indicators(ohlcv, default_params)
        except Exception as e:
            logger.warning(f"{strategy_name}: {e}, skipping")
            continue
        
        # Backtest on this session
        pf, wr, sharpe, trades = backtest_strategy(
            ohlcv, strategy, indicators, entry_floors, session
        )
        
        discovered = DiscoveredStrategy(
            session=session,
            timeframe=timeframe,
            strategy_name=strategy_name,
            strategy_type=strategy.strategy_type,
            indicator_params=default_params,
            baseline_pf=pf,
            baseline_wr=wr,
            baseline_sharpe=sharpe,
            baseline_trades=trades
        )
        results.append(discovered)
    
    # Sort by Profit Factor (highest first)
    results.sort(key=lambda x: x.baseline_pf, reverse=True)
    return results
```

---

## Usage in ScalpEngine (Live Trading)

```python
def _evaluate_and_trade(self, base, adapter):
    """Live trading entry decision."""
    
    current_session = get_current_session_utc(datetime.now(timezone.utc))
    
    # Load tuned strategy for this session
    strategy_config = self._load_tuned_strategy(base, current_session)
    strategy = STRATEGY_REGISTRY.get_strategy(strategy_config['strategy_name'])
    
    # Get latest OHLCV (4 bars for indicators)
    latest_ohlcv = adapter.get_rates(base, timeframe, 4)
    
    # Calculate indicators
    indicators = strategy.calculate_indicators(
        latest_ohlcv,
        strategy_config['indicator_params']
    )
    
    # Generate signal
    signal = strategy.generate_signal(
        indicators,
        strategy_config['entry_floors'],
        current_bar_idx=len(latest_ohlcv) - 1
    )
    
    if signal.should_enter:
        logger.info(f"{base}: {signal.reason}, confidence={signal.confidence:.2%}")
        self._open_trade(base, signal, strategy_config)
```

---

## Validation Checklist

**Every Strategy Must:**
- ✅ Inherit from `BaseStrategy`
- ✅ Implement `calculate_indicators(ohlcv, params) → Dict[str, Series]`
- ✅ Implement `generate_signal(indicators, entry_floors, current_bar_idx) → StrategySignal`
- ✅ Implement `validate_params(params) → bool`
- ✅ Return valid `StrategySignal` with required fields
- ✅ Handle edge cases (insufficient data, invalid indices)
- ✅ Be registered in `STRATEGY_REGISTRY` at startup

**Phase 1 Usage:**
- ✅ Iterate all registered strategies
- ✅ Test with default params and historical data
- ✅ Rank by Profit Factor
- ✅ Return top strategy

**Phase 2-3 Usage:**
- ✅ Accept `strategy_name` + tuned `indicator_params`
- ✅ Pass to registry to get strategy object
- ✅ Optimize params with Optuna

**Live Trading Usage:**
- ✅ Load strategy by name from tuned_params.json
- ✅ Calculate indicators and generate signal
- ✅ Entry decision based on signal

---

**Status:** SPECIFICATION COMPLETE - Ready for implementation
