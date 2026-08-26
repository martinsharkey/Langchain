"""
Pytest configuration for performance tests.

Performance tests measure system performance and identify bottlenecks.
They use benchmarking tools to track metrics over time.
"""
import pytest
import time


@pytest.fixture
def performance_test_marker():
    """Mark for performance tests."""
    return {"type": "performance", "speed": "variable"}


@pytest.fixture
def performance_metrics():
    """Collect performance metrics."""
    class PerformanceMetrics:
        def __init__(self):
            self.metrics = {}

        def start_timer(self, name):
            self.metrics[name] = {"start": time.time()}

        def stop_timer(self, name):
            if name in self.metrics:
                self.metrics[name]["duration"] = time.time() - self.metrics[name]["start"]

        def record_metric(self, name, value):
            if name not in self.metrics:
                self.metrics[name] = []
            self.metrics[name].append(value)

        def get_metrics(self):
            return self.metrics

        def get_summary(self):
            summary = {}
            for name, data in self.metrics.items():
                if isinstance(data, dict) and "duration" in data:
                    summary[name] = {"duration_ms": data["duration"] * 1000}
                elif isinstance(data, list):
                    summary[name] = {
                        "count": len(data),
                        "avg": sum(data) / len(data) if data else 0,
                        "min": min(data) if data else 0,
                        "max": max(data) if data else 0
                    }
            return summary

    return PerformanceMetrics()


@pytest.fixture
def benchmark_thresholds():
    """Performance benchmarks that must not be exceeded."""
    return {
        "discovery_per_symbol": 1800,  # 30 minutes in seconds
        "optimization_per_trial": 60,   # 1 minute per trial
        "validation_walkforward": 900,  # 15 minutes
        "api_response_time_p95": 0.5,   # 500ms
        "database_query_p95": 0.1       # 100ms
    }
