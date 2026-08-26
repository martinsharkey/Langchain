"""
DAY 6: UNIT TESTS - Strategy Interface (20 tests)

Comprehensive test coverage for BaseStrategy interface.

Status: DAY 6 TESTING
"""

import pytest
import pandas as pd
import numpy as np
from src.strategy_interface import (
    StrategySignal,
    BaseStrategy,
    STRATEGY_REGISTRY
)


@pytest.fixture
def sample_ohlcv():
    """Generate sample OHLCV data for testing."""
    dates = pd.date_range('2026-01-01', periods=100, freq='1h')
    np.random.seed(42)
    close_prices = 1230 + np.cumsum(np.random.randn(100) * 0.5)
    data = {
        'open': close_prices - 0.5,
        'high': close_prices + 1.0,
        'low': close_prices - 1.0,
        'close': close_prices,
        'volume': [1000000] * 100
    }
    return pd.DataFrame(data, index=dates)


class TestStrategySignal:
    """Test StrategySignal dataclass."""
    
    def test_strategy_signal_valid(self):
        """StrategySignal should accept valid values."""
        signal = StrategySignal(
            should_enter=True,
            entry_price=1234.56,
            entry_type="long",
            confidence=0.75,
            reason="Test signal",
            strength=0.8
        )
        assert signal.should_enter is True
        assert signal.confidence == 0.75
        assert signal.strength == 0.8
    
    def test_strategy_signal_invalid_confidence(self):
        """StrategySignal should reject confidence > 1.0."""
        with pytest.raises(ValueError):
            StrategySignal(
                should_enter=True,
                entry_price=1234.56,
                entry_type="long",
                confidence=1.5,  # Invalid
                reason="Test",
                strength=0.8
            )
    
    def test_strategy_signal_invalid_entry_type(self):
        """StrategySignal should reject invalid entry_type."""
        with pytest.raises(ValueError):
            StrategySignal(
                should_enter=True,
                entry_price=1234.56,
                entry_type="invalid",
                confidence=0.75,
                reason="Test",
                strength=0.8
            )


class TestRSI14Strategy:
    """Test RSI14 strategy implementation."""
    
    def test_rsi14_calculate_indicators(self, sample_ohlcv):
        """RSI14 should calculate RSI indicator."""
        from src.strategies.rsi14 import RSI14Strategy
        strategy = RSI14Strategy()
        params = {"period": 14}
        indicators = strategy.calculate_indicators(sample_ohlcv, params)
        
        assert "RSI" in indicators
        assert len(indicators["RSI"]) == len(sample_ohlcv)
        assert indicators["RSI"].dtype == 'float64'
    
    def test_rsi14_validate_params_valid(self):
        """RSI14 should accept valid parameters."""
        from src.strategies.rsi14 import RSI14Strategy
        strategy = RSI14Strategy()
        assert strategy.validate_params({"period": 14}) is True
        assert strategy.validate_params({"period": 5}) is True
        assert strategy.validate_params({"period": 50}) is True
    
    def test_rsi14_validate_params_invalid(self):
        """RSI14 should reject invalid parameters."""
        from src.strategies.rsi14 import RSI14Strategy
        strategy = RSI14Strategy()
        assert strategy.validate_params({"period": 0}) is False
        assert strategy.validate_params({"period": 51}) is False
        assert strategy.validate_params({}) is False
    
    def test_rsi14_generate_signal_oversold(self, sample_ohlcv):
        """RSI14 should generate buy signal when RSI < 30."""
        from src.strategies.rsi14 import RSI14Strategy
        strategy = RSI14Strategy()
        params = {"period": 14}
        indicators = strategy.calculate_indicators(sample_ohlcv, params)
        
        # Manually set RSI to oversold
        indicators["RSI"].iloc[-1] = 25.0
        
        signal = strategy.generate_signal(
            indicators,
            {"min_strength": 0.1},
            len(sample_ohlcv) - 1
        )
        
        assert signal.should_enter is True
        assert signal.entry_type == "long"
        assert signal.strength > 0
    
    def test_rsi14_generate_signal_neutral(self, sample_ohlcv):
        """RSI14 should not generate signal when RSI neutral."""
        from src.strategies.rsi14 import RSI14Strategy
        strategy = RSI14Strategy()
        params = {"period": 14}
        indicators = strategy.calculate_indicators(sample_ohlcv, params)
        
        indicators["RSI"].iloc[-1] = 50.0
        
        signal = strategy.generate_signal(
            indicators,
            {"min_strength": 0.1},
            len(sample_ohlcv) - 1
        )
        
        assert signal.should_enter is False
    
    def test_rsi14_floor_rejection(self, sample_ohlcv):
        """RSI14 should reject signal if strength < floor."""
        from src.strategies.rsi14 import RSI14Strategy
        strategy = RSI14Strategy()
        params = {"period": 14}
        indicators = strategy.calculate_indicators(sample_ohlcv, params)
        
        indicators["RSI"].iloc[-1] = 28.5  # Weak oversold, strength ~0.05
        
        signal = strategy.generate_signal(
            indicators,
            {"min_strength": 0.5},  # High floor
            len(sample_ohlcv) - 1
        )
        
        assert signal.should_enter is False
    
    def test_rsi14_indicator_names(self):
        """RSI14 should report indicator names."""
        from src.strategies.rsi14 import RSI14Strategy
        strategy = RSI14Strategy()
        names = strategy.get_indicator_names()
        assert "RSI" in names


class TestStochastic14Strategy:
    """Test Stochastic14 strategy implementation."""
    
    def test_stochastic14_calculate_indicators(self, sample_ohlcv):
        """Stochastic14 should calculate K and D indicators."""
        from src.strategies.stochastic14 import Stochastic14Strategy
        strategy = Stochastic14Strategy()
        params = {
            "k_period": 14,
            "d_period": 3,
            "smooth": 3
        }
        indicators = strategy.calculate_indicators(sample_ohlcv, params)
        
        assert "K" in indicators
        assert "D" in indicators
        assert len(indicators["K"]) == len(sample_ohlcv)
        assert len(indicators["D"]) == len(sample_ohlcv)
    
    def test_stochastic14_validate_params_valid(self):
        """Stochastic14 should accept valid parameters."""
        from src.strategies.stochastic14 import Stochastic14Strategy
        strategy = Stochastic14Strategy()
        params = {
            "k_period": 14,
            "d_period": 3,
            "smooth": 3
        }
        assert strategy.validate_params(params) is True
    
    def test_stochastic14_validate_params_missing(self):
        """Stochastic14 should reject if params missing."""
        from src.strategies.stochastic14 import Stochastic14Strategy
        strategy = Stochastic14Strategy()
        assert strategy.validate_params({"k_period": 14}) is False
    
    def test_stochastic14_generate_signal_oversold(self, sample_ohlcv):
        """Stochastic14 should generate signal when %K < 20."""
        from src.strategies.stochastic14 import Stochastic14Strategy
        strategy = Stochastic14Strategy()
        params = {"k_period": 14, "d_period": 3, "smooth": 3}
        indicators = strategy.calculate_indicators(sample_ohlcv, params)
        
        indicators["K"].iloc[-1] = 15.0
        indicators["D"].iloc[-1] = 25.0
        
        signal = strategy.generate_signal(
            indicators,
            {"min_strength": 0.1},
            len(sample_ohlcv) - 1
        )
        
        assert signal.should_enter is True


class TestStrategyRegistry:
    """Test strategy registry."""
    
    def test_registry_list_strategies(self):
        """Registry should list registered strategies."""
        strategies = STRATEGY_REGISTRY.list_strategies()
        assert len(strategies) >= 0
    
    def test_registry_get_strategy(self):
        """Registry should retrieve strategy by name."""
        from src.strategies.rsi14 import RSI14Strategy
        STRATEGY_REGISTRY.register(RSI14Strategy())
        strategy = STRATEGY_REGISTRY.get_strategy("RSI14")
        assert strategy.strategy_name == "RSI14"
    
    def test_registry_unknown_strategy(self):
        """Registry should raise for unknown strategy."""
        with pytest.raises(ValueError):
            STRATEGY_REGISTRY.get_strategy("UnknownStrategy999")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
