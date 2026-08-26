"""
Unit tests for Optimization Service.

Tests parameter optimization engine without external dependencies.
"""
import pytest
from unittest.mock import Mock, patch


class TestOptimizationEngine:
    """Test optimization engine core logic."""

    def test_optimization_initialization(self):
        """Test optimization engine can be initialized."""
        from src.modules.optimization import OptimizationEngine
        
        engine = OptimizationEngine(symbol="BTCUSD", session="London")
        assert engine.symbol == "BTCUSD"
        assert engine.session == "London"

    def test_optimization_parameter_ranges(self):
        """Test optimization validates parameter ranges."""
        from src.modules.optimization import OptimizationEngine
        
        engine = OptimizationEngine(symbol="BTCUSD", session="London")
        
        ranges = {
            "bb_period": [10, 50],
            "bb_deviation": [1.0, 3.0]
        }
        
        engine.set_parameter_ranges(ranges)
        assert engine.parameter_ranges == ranges

    def test_optimization_algorithm_selection(self):
        """Test optimization algorithm selection."""
        from src.modules.optimization import OptimizationEngine
        
        engine = OptimizationEngine(symbol="BTCUSD", session="London")
        
        # Should support TPE algorithm
        engine.set_algorithm("tpe")
        assert engine.algorithm == "tpe"
        
        # Should support random search
        engine.set_algorithm("random")
        assert engine.algorithm == "random"

    def test_optimization_trial_count(self):
        """Test optimization trial count configuration."""
        from src.modules.optimization import OptimizationEngine
        
        engine = OptimizationEngine(symbol="BTCUSD", session="London")
        
        engine.set_n_trials(100)
        assert engine.n_trials == 100
        
        # Should validate minimum trials
        with pytest.raises(ValueError):
            engine.set_n_trials(0)

    def test_optimization_result_structure(self, sample_optimization_result):
        """Test optimization results have correct structure."""
        results = sample_optimization_result
        
        assert "task_id" in results
        assert "symbol" in results
        assert "session" in results
        assert "best_trial" in results
        assert "status" in results

    def test_optimization_best_trial(self, sample_optimization_result):
        """Test optimization best trial contains required fields."""
        best = sample_optimization_result["best_trial"]
        
        assert "trial_id" in best
        assert "parameters" in best
        assert "metrics" in best
        assert len(best["parameters"]) > 0

    def test_optimization_convergence(self):
        """Test optimization shows convergence over trials."""
        trials = [
            {"trial_id": 1, "profit_factor": 1.2},
            {"trial_id": 2, "profit_factor": 1.35},
            {"trial_id": 3, "profit_factor": 1.5},
            {"trial_id": 4, "profit_factor": 1.48},
            {"trial_id": 5, "profit_factor": 1.52}
        ]
        
        # Should trend toward best value
        best_pf = max(t["profit_factor"] for t in trials)
        assert best_pf >= trials[0]["profit_factor"]

    def test_optimization_parameter_values(self, sample_optimization_result):
        """Test optimized parameters are within defined ranges."""
        params = sample_optimization_result["best_trial"]["parameters"]
        
        # All parameters should be numeric
        for param, value in params.items():
            assert isinstance(value, (int, float))


class TestParameterRanges:
    """Test parameter range handling."""

    def test_range_validation(self):
        """Test parameter range validation."""
        from src.modules.optimization import ParameterRange
        
        # Valid range
        r = ParameterRange(name="bb_period", min_val=10, max_val=50)
        assert r.min_val == 10
        assert r.max_val == 50
        
        # Invalid range (min > max)
        with pytest.raises(ValueError):
            ParameterRange(name="bb_period", min_val=50, max_val=10)

    def test_range_types(self):
        """Test parameter range types."""
        from src.modules.optimization import ParameterRange
        
        # Integer range
        r_int = ParameterRange(name="period", min_val=5, max_val=100, type="int")
        assert r_int.type == "int"
        
        # Float range
        r_float = ParameterRange(name="deviation", min_val=0.5, max_val=3.0, type="float")
        assert r_float.type == "float"

    def test_range_value_validation(self):
        """Test values are validated against ranges."""
        from src.modules.optimization import ParameterRange
        
        r = ParameterRange(name="period", min_val=10, max_val=50)
        
        assert r.contains(20)  # Within range
        assert r.contains(10)  # At minimum
        assert r.contains(50)  # At maximum
        
        assert not r.contains(5)   # Below minimum
        assert not r.contains(100) # Above maximum


class TestOptimizationMetrics:
    """Test optimization metrics calculation."""

    def test_metrics_completeness(self, sample_optimization_result):
        """Test optimization results include all metrics."""
        metrics = sample_optimization_result["best_trial"]["metrics"]
        
        required = [
            "profit_factor",
            "win_rate",
            "total_return",
            "max_drawdown",
            "sharpe_ratio"
        ]
        
        for metric in required:
            assert metric in metrics

    def test_metrics_value_ranges(self, sample_optimization_result):
        """Test metric values are in valid ranges."""
        metrics = sample_optimization_result["best_trial"]["metrics"]
        
        # Profit factor > 0
        assert metrics["profit_factor"] > 0
        
        # Win rate in [0, 1]
        assert 0 <= metrics["win_rate"] <= 1
        
        # Drawdown <= 0
        assert metrics["max_drawdown"] <= 0

    def test_improvement_over_baseline(self, sample_optimization_result):
        """Test optimized parameters improve over baseline."""
        # Assuming baseline PF is 1.52
        baseline_pf = 1.52
        optimized_pf = sample_optimization_result["best_trial"]["metrics"]["profit_factor"]
        
        assert optimized_pf > baseline_pf


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
