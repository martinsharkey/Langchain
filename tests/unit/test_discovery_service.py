"""
Unit tests for Discovery Service.

Tests core discovery engine functionality without external dependencies.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestDiscoveryEngine:
    """Test discovery engine core logic."""

    def test_discovery_initialization(self):
        """Test discovery engine can be initialized."""
        from src.modules.discovery import DiscoveryEngine
        
        engine = DiscoveryEngine(symbol="BTCUSD", session="London")
        assert engine.symbol == "BTCUSD"
        assert engine.session == "London"

    def test_discovery_with_valid_config(self, sample_strategy_config):
        """Test discovery with valid configuration."""
        from src.modules.discovery import DiscoveryEngine
        
        engine = DiscoveryEngine(
            symbol=sample_strategy_config["symbol"],
            session=sample_strategy_config["session"]
        )
        assert engine.symbol == "BTCUSD"
        assert engine.session == "London"

    def test_discovery_validates_symbol(self):
        """Test discovery validates symbol input."""
        from src.modules.discovery import DiscoveryEngine
        
        with pytest.raises(ValueError):
            DiscoveryEngine(symbol="", session="London")

    def test_discovery_validates_session(self):
        """Test discovery validates session input."""
        from src.modules.discovery import DiscoveryEngine
        
        with pytest.raises(ValueError):
            DiscoveryEngine(symbol="BTCUSD", session="")

    def test_discovery_validates_indicators(self):
        """Test discovery validates indicator list."""
        from src.modules.discovery import DiscoveryEngine
        
        engine = DiscoveryEngine(symbol="BTCUSD", session="London")
        
        # Empty indicators should fail
        with pytest.raises(ValueError):
            engine.set_indicators([])

    def test_discovery_results_structure(self, sample_discovery_result):
        """Test discovery results have correct structure."""
        results = sample_discovery_result
        
        assert "task_id" in results
        assert "symbol" in results
        assert "session" in results
        assert "discoveries" in results
        assert len(results["discoveries"]) > 0

    def test_discovery_result_ranking(self, sample_discovery_result):
        """Test discoveries are ranked by performance."""
        results = sample_discovery_result["discoveries"]
        
        # Should be ranked by profit factor
        pfs = [d["performance"]["profit_factor"] for d in results]
        assert pfs == sorted(pfs, reverse=True)

    def test_discovery_performance_metrics(self, sample_discovery_result):
        """Test discovery results include required metrics."""
        result = sample_discovery_result["discoveries"][0]
        perf = result["performance"]
        
        required_metrics = [
            "profit_factor",
            "win_rate",
            "total_return",
            "max_drawdown",
            "sharpe_ratio",
            "trades"
        ]
        
        for metric in required_metrics:
            assert metric in perf
            assert perf[metric] is not None

    def test_discovery_indicator_parameters(self, sample_discovery_result):
        """Test discovery includes indicator parameters."""
        result = sample_discovery_result["discoveries"][0]
        
        assert "parameters" in result
        assert len(result["parameters"]) > 0
        
        # Should have parameter values
        for param, value in result["parameters"].items():
            assert value is not None
            assert isinstance(value, (int, float, str))


class TestDiscoveryValidation:
    """Test discovery input validation."""

    @pytest.mark.parametrize("symbol,session", [
        ("BTCUSD", "London"),
        ("EURUSD", "New York"),
        ("XAUUSD", "Tokyo"),
    ])
    def test_valid_symbol_session_pairs(self, symbol, session):
        """Test discovery with valid symbol/session pairs."""
        from src.modules.discovery import DiscoveryEngine
        
        engine = DiscoveryEngine(symbol=symbol, session=session)
        assert engine.symbol == symbol
        assert engine.session == session

    @pytest.mark.parametrize("timeframe", ["M1", "M5", "M15", "H1", "H4", "D1"])
    def test_valid_timeframes(self, timeframe):
        """Test discovery supports various timeframes."""
        from src.modules.discovery import DiscoveryEngine
        
        engine = DiscoveryEngine(symbol="BTCUSD", session="London")
        engine.set_timeframe(timeframe)
        assert engine.timeframe == timeframe

    def test_backtest_period_validation(self):
        """Test backtest period validation."""
        from src.modules.discovery import DiscoveryEngine
        
        engine = DiscoveryEngine(symbol="BTCUSD", session="London")
        
        # Valid periods
        engine.set_backtest_period("1y")
        engine.set_backtest_period("6m")
        engine.set_backtest_period("1d")
        
        # Invalid period should raise
        with pytest.raises(ValueError):
            engine.set_backtest_period("invalid")


class TestDiscoveryPerformance:
    """Test discovery performance characteristics."""

    def test_discovery_result_metrics_ranges(self, sample_discovery_result):
        """Test discovery metrics are in valid ranges."""
        result = sample_discovery_result["discoveries"][0]
        perf = result["performance"]
        
        # Profit factor should be positive
        assert perf["profit_factor"] > 0
        
        # Win rate should be between 0 and 1
        assert 0 <= perf["win_rate"] <= 1
        
        # Drawdown should be negative or zero
        assert perf["max_drawdown"] <= 0
        
        # Sharpe ratio can be any real number
        assert isinstance(perf["sharpe_ratio"], (int, float))
        
        # Trades should be positive integer
        assert perf["trades"] > 0

    def test_discovery_multiple_discoveries(self, sample_discovery_result):
        """Test discovery returns multiple ranked strategies."""
        results = sample_discovery_result["discoveries"]
        
        # Should have at least one discovery
        assert len(results) >= 1
        
        # Each discovery should have rank
        for i, discovery in enumerate(results):
            assert discovery["rank"] == i + 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
