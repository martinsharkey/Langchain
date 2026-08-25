"""
Discovery Service Tests
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from core.discovery_engine import DiscoveryEngine


@pytest.fixture
def sample_ohlcv_data():
    """Generate sample OHLCV data for testing."""
    dates = pd.date_range(start='2024-01-01', periods=200, freq='15min')
    np.random.seed(42)
    
    close = 100 + np.cumsum(np.random.randn(200) * 0.5)
    high = close + np.abs(np.random.randn(200) * 0.3)
    low = close - np.abs(np.random.randn(200) * 0.3)
    
    data = pd.DataFrame({
        'timestamp': dates,
        'open': close - np.abs(np.random.randn(200) * 0.2),
        'high': high,
        'low': low,
        'close': close,
        'volume': np.random.randint(1000, 10000, 200)
    })
    
    return data


@pytest.fixture
def discovery_engine(sample_ohlcv_data):
    """Create discovery engine instance."""
    return DiscoveryEngine(
        symbol="XAUUSD",
        timeframe="M15",
        ohlcv_data=sample_ohlcv_data,
        entry_floors={'asia': 0.5, 'london': 0.6, 'newyork': 0.7},
        min_trades=5
    )


class TestDiscoveryEngine:
    """Test DiscoveryEngine."""
    
    def test_initialization(self, discovery_engine):
        """Test engine initialization."""
        assert discovery_engine.symbol == "XAUUSD"
        assert discovery_engine.timeframe == "M15"
        assert len(discovery_engine.ohlcv_data) == 200
    
    def test_invalid_ohlcv_data(self):
        """Test with invalid OHLCV data."""
        invalid_data = pd.DataFrame({
            'open': [100],
            'high': [101],
            'low': [99],
            'close': [100]
        })
        
        with pytest.raises(ValueError, match="Insufficient OHLCV data"):
            DiscoveryEngine(
                symbol="XAUUSD",
                timeframe="M15",
                ohlcv_data=invalid_data,
                entry_floors={'asia': 0.5}
            )
    
    def test_missing_ohlcv_columns(self, sample_ohlcv_data):
        """Test with missing OHLCV columns."""
        incomplete_data = sample_ohlcv_data.drop('volume', axis=1)
        
        with pytest.raises(ValueError, match="OHLCV missing columns"):
            DiscoveryEngine(
                symbol="XAUUSD",
                timeframe="M15",
                ohlcv_data=incomplete_data,
                entry_floors={'asia': 0.5}
            )
    
    def test_get_default_params(self, discovery_engine):
        """Test default parameter retrieval."""
        params = discovery_engine._get_default_params("RSI14")
        assert params == {'period': 14}
        
        params = discovery_engine._get_default_params("OsMA_Confluence")
        assert 'osma_fast' in params
        assert params['osma_fast'] == 12


class TestDiscoveryIntegration:
    """Integration tests for discovery service."""
    
    @pytest.mark.asyncio
    async def test_discovery_flow(self, discovery_engine):
        """Test complete discovery flow."""
        # Mock strategy registry
        class MockStrategy:
            strategy_name = "RSI14"
            strategy_type = "momentum"
            
            def calculate_indicators(self, data, params):
                return {}
            
            def generate_signal(self, indicators, config, idx):
                # Mock signal
                class Signal:
                    should_enter = False
                    entry_type = "long"
                return Signal()
        
        class MockRegistry:
            def list_strategies(self):
                return ["RSI14"]
            
            def get_strategy(self, name):
                return MockStrategy()
        
        registry = MockRegistry()
        results = await discovery_engine.discover_for_session("asia", registry)
        
        # Results may be empty if backtest doesn't generate trades
        assert isinstance(results, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
