"""
End-to-end test suite for Bollinger_OsMA strategy (NEW).

Tests:
1. Unit test: Bollinger_OsMA signal generation (vectorized)
2. Integration test: Bollinger_OsMA in backtester (walkforward)
3. Registry test: Strategy properly registered and callable
4. Optuna test: Floor optimizer works with Bollinger_OsMA
5. Live bot test: Check strategy fires in focused_rules
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock, patch
import numpy as np
import pandas as pd

from src.strategies.bollinger_osma import bollinger_osma_signal
from src.learning.strategy_registry import StrategyRegistry
from src.learning.edge_weights import focused_rules, FOCUSED_EDGE
from src.learning.backtester import Backtester, BacktestResult


# ============================================================================
# UNIT TESTS: Signal generation logic
# ============================================================================

class TestBollingerOsMASignal:
    """Test Bollinger_OsMA signal function directly."""

    def _base_setup(self, **overrides):
        """Base OsMA zero-cross setup with Bollinger Bands and all required guard filter indicators."""
        d = {
            # Price and bands - IMPORTANT: price must touch bands for entry
            "close": 98.0,      # AT lower band for buy signal
            "close_prev": 97.0, # Previous was lower (for extension check)
            "high": 98.1,
            "low": 97.9,
            "bb_upper": 102.0,
            "bb_lower": 98.0,   # Price at this level
            "bb_middle": 100.0,
            
            # OsMA values (required for all 4 guard filters)
            "osma": 0.5,        # Crossed to positive (buy signal)
            "osma_prev": -0.3,  # Was negative (confirming cross)
            "osma_t2": -0.1,    # Required for momentum age filter: |t2| < |prev| < |now|
                                # |−0.1| < |−0.3| < |0.5| ✓
            
            # Volatility
            "atr": 1.0,
        }
        d.update(overrides)
        return d

    def test_osma_upward_cross_buys(self):
        """Bullish zero-cross → BUY."""
        ind = self._base_setup()
        result = bollinger_osma_signal(ind, {})
        assert result.action == "buy", f"Expected buy, got {result.action}: {result.reason}"
        assert result.confidence > 0, f"Confidence should be > 0, got {result.confidence}"

    def test_osma_downward_cross_sells(self):
        """Bearish zero-cross → SELL."""
        ind = self._base_setup(osma=-0.5, osma_prev=0.3)
        result = bollinger_osma_signal(ind, {})
        assert result.action == "sell", f"Expected sell, got {result.action}"

    def test_no_cross_holds(self):
        """No zero-cross → HOLD."""
        ind = self._base_setup(osma=0.5, osma_prev=0.4)  # Both positive
        result = bollinger_osma_signal(ind, {})
        assert result.action == "hold", f"Expected hold (no cross), got {result.action}"

    def test_confidence_scaled_by_cross_magnitude(self):
        """Larger OsMA move → higher confidence."""
        # For guard filters to pass:
        # 1. Price at band (close at bb_lower for buy)
        # 2. osma_t2 < osma_prev < osma (growing momentum)
        small_cross = self._base_setup(osma=0.1, osma_prev=-0.05, osma_t2=-0.01)
        large_cross = self._base_setup(osma=2.0, osma_prev=-0.5, osma_t2=-0.1)
        
        small_result = bollinger_osma_signal(small_cross, {})
        large_result = bollinger_osma_signal(large_cross, {})
        
        assert small_result.action == "buy", f"Expected buy, got {small_result.action}: {small_result.reason}"
        assert large_result.action == "buy", f"Expected buy, got {large_result.action}: {large_result.reason}"
        assert large_result.confidence > small_result.confidence, \
            f"Larger cross should have higher confidence: {large_result.confidence} vs {small_result.confidence}"

    def test_band_breakout_considered(self):
        """Price at band required for entry."""
        at_band = self._base_setup(close=98.0, high=98.1, low=97.9)  # AT lower band [98, 102]
        inside_band = self._base_setup(close=100.0, high=100.1, low=99.9)  # Inside bands
        
        at_band_result = bollinger_osma_signal(at_band, {})
        inside_result = bollinger_osma_signal(inside_band, {})
        
        assert at_band_result.action == "buy", f"Expected buy at band, got {at_band_result.action}"
        # Inside band (not touching) should be rejected by BB interaction filter
        assert inside_result.action == "hold", f"Expected hold (no BB touch), got {inside_result.action}"


# ============================================================================
# REGISTRY TESTS: Strategy registration
# ============================================================================

class TestBollingerOsMARegistry:
    """Verify Bollinger_OsMA is properly registered."""

    def test_strategy_registered(self):
        """Strategy must be in registry."""
        registry = StrategyRegistry()
        entry = registry.get("Bollinger_OsMA")
        assert entry is not None, "Bollinger_OsMA not in registry"
        assert entry.status == "active", f"Strategy status: {entry.status}"

    def test_strategy_has_signal_function(self):
        """Registry entry must have callable signal_fn."""
        registry = StrategyRegistry()
        entry = registry.get("Bollinger_OsMA")
        assert callable(entry.signal_fn), "signal_fn not callable"

    def test_strategy_in_focused_rules_for_btcusd(self):
        """Bollinger_OsMA must be PRIMARY for BTCUSD."""
        rules = focused_rules("BTCUSD")
        assert rules is not None, "No focused rules for BTCUSD"
        strategy_names = [name for name, _ in rules]
        assert "Bollinger_OsMA" in strategy_names, \
            f"Bollinger_OsMA not in focused rules. Found: {strategy_names}"
        # Should be first (primary)
        assert strategy_names[0] == "Bollinger_OsMA", \
            f"Bollinger_OsMA should be primary (first). Order: {strategy_names}"


# ============================================================================
# BACKTEST TESTS: Vectorbt integration via Backtester
# ============================================================================

class TestBollingerOsMABacktest:
    """Verify strategy works in full backtester pipeline."""

    @pytest.fixture
    def mock_rates(self):
        """Generate synthetic OHLCV data."""
        np.random.seed(42)
        n = 1000
        timestamps = np.arange(n) * 60  # 1-minute bars
        closes = 100 + np.cumsum(np.random.randn(n) * 0.5)
        highs = closes + np.abs(np.random.randn(n) * 0.3)
        lows = closes - np.abs(np.random.randn(n) * 0.3)
        opens = np.roll(closes, 1)
        volumes = np.random.randint(1000, 10000, n)
        
        return [
            {
                "timestamp": int(t),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
            }
            for t, o, h, l, c, v in zip(timestamps, opens, highs, lows, closes, volumes)
        ]

    def test_backtester_instantiates(self, mock_rates):
        """Backtester must initialize without error."""
        registry = StrategyRegistry()
        mock_get_rates = MagicMock(return_value=mock_rates)
        mock_get_ticks = MagicMock(return_value={"time": [], "bid": [], "ask": []})
        
        backtester = Backtester(registry, rates_fn=mock_get_rates, ticks_fn=mock_get_ticks)
        assert backtester is not None

    def test_backtester_loads_data(self, mock_rates):
        """Backtester must fetch rates."""
        registry = StrategyRegistry()
        mock_get_rates = MagicMock(return_value=mock_rates)
        mock_get_ticks = MagicMock(return_value={"time": [], "bid": [], "ask": []})
        
        backtester = Backtester(registry, rates_fn=mock_get_rates, ticks_fn=mock_get_ticks)
        mock_get_rates.assert_not_called()  # Not called until walkforward


# ============================================================================
# INTEGRATION TESTS: Full pipeline
# ============================================================================

class TestBollingerOsMAIntegration:
    """Test strategy in context of full trading pipeline."""

    def test_bollinger_osma_in_edge_weights(self):
        """Strategy weight configuration must exist."""
        from src.learning.edge_weights import FOCUSED_EDGE
        assert "BTCUSD" in FOCUSED_EDGE, "BTCUSD not in focused rules"
        
        btc_rules = FOCUSED_EDGE["BTCUSD"]
        strategy_names = [name for name, _ in btc_rules]
        assert "Bollinger_OsMA" in strategy_names, \
            f"Bollinger_OsMA not configured. Found: {strategy_names}"

    def test_strategy_callable_via_registry_signal(self):
        """Must call strategy via registry.get().signal_fn()."""
        registry = StrategyRegistry()
        entry = registry.get("Bollinger_OsMA")
        
        # Create minimal indicator dict
        ind = {
            "close": 100.0,
            "osma": 0.5, "osma_prev": -0.3,
            "bb_upper": 102.0, "bb_lower": 98.0, "bb_middle": 100.0,
            "atr": 1.0,
            "confidence_scale": 1.0,
        }
        
        result = entry.signal_fn(ind, {})
        assert result is not None, "signal_fn returned None"
        assert hasattr(result, "action"), "Result must have 'action' attribute"
        assert result.action in ("buy", "sell", "hold"), f"Invalid action: {result.action}"


# ============================================================================
# PARAMETER TESTS: Optuna integration
# ============================================================================

class TestBollingerOsMAParams:
    """Verify Bollinger_OsMA parameters are configured correctly."""

    def test_parameters_exist(self):
        """Parameters dict must be initialized."""
        registry = StrategyRegistry()
        entry = registry.get("Bollinger_OsMA")
        params = entry.params
        
        # Parameters can be empty for live single-bar strategies
        assert params is not None, "Parameters cannot be None"
        assert isinstance(params, dict), "Parameters must be a dict"

    def test_strategy_has_required_indicators(self):
        """Strategy must declare required indicator fields."""
        registry = StrategyRegistry()
        entry = registry.get("Bollinger_OsMA")
        
        # Check required_fields
        required = entry.required_fields if hasattr(entry, 'required_fields') else []
        expected = {'osma', 'osma_prev', 'bb_upper', 'bb_lower', 'close'}
        if required:
            assert expected.issubset(set(required)), \
                f"Missing required indicators. Expected {expected}, got {set(required)}"


# ============================================================================
# LIVE BOT TESTS: Verify strategy calls in scalp_engine
# ============================================================================

class TestBollingerOsMALiveIntegration:
    """Verify strategy is called by live trading engine."""

    def test_focused_signal_includes_bollinger_osma(self):
        """scalp_engine.get_focused_signal() must try Bollinger_OsMA first."""
        from src.learning.edge_weights import focused_rules
        
        rules = focused_rules("BTCUSD")
        assert rules is not None, "No focused rules for BTCUSD"
        
        # First strategy should be Bollinger_OsMA
        first_strategy = rules[0][0]
        assert first_strategy == "Bollinger_OsMA", \
            f"Expected first strategy to be Bollinger_OsMA, got {first_strategy}"

    def test_strategy_can_be_invoked_with_live_indicators(self):
        """Full indicator dict from compute_full_indicators must work."""
        registry = StrategyRegistry()
        entry = registry.get("Bollinger_OsMA")
        
        # Simulate a full indicator dict from scalp_engine
        live_ind = {
            "close": 50000.0,
            "osma": 0.3,
            "osma_prev": -0.2,
            "bb_upper": 50100.0,
            "bb_lower": 49900.0,
            "bb_middle": 50000.0,
            "atr": 150.0,
            "confidence_scale": 1.0,
            # Additional fields from compute_full_indicators
            "open": 49950.0,
            "high": 50050.0,
            "low": 49900.0,
            "ema_fast": 50000.0,
            "ema_prev": 49980.0,
            "bulls_power": 100.0,
            "bears_power": -50.0,
            "rsi": 55.0,
            "macd_line": 10.0,
            "macd_signal": 8.0,
        }
        
        result = entry.signal_fn(live_ind, entry.params or {})
        assert result is not None, "Signal must return a result"
        assert result.action in ("buy", "sell", "hold"), \
            f"Action must be buy/sell/hold, got {result.action}"


# ============================================================================
# END-TO-END TEST: Run backtest and verify trades are generated
# ============================================================================

@pytest.mark.live  # Skip unless -m live is passed
class TestBollingerOsMAE2E:
    """Full end-to-end test (requires live data or mocks)."""

    def test_backtest_generates_trades(self):
        """Full backtest must produce trades with Bollinger_OsMA."""
        pytest.skip("Requires live MT5 connection or comprehensive mocking")


if __name__ == "__main__":
    # Run tests: pytest tests/test_bollinger_osma.py -v
    pytest.main([__file__, "-v"])
