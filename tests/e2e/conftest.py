"""
Pytest configuration for end-to-end (E2E) tests.

E2E tests verify complete workflows across all services.
They are slower but test real-world scenarios.
"""
import pytest


@pytest.fixture
def e2e_test_marker():
    """Mark for E2E tests."""
    return {"type": "e2e", "speed": "slow"}


@pytest.fixture
def complete_workflow_context():
    """Context for complete workflow testing."""
    return {
        "symbol": "BTCUSD",
        "session": "London",
        "timeframe": "M15",
        "backtest_period": "1y",
        "discovery_id": None,
        "optimization_id": None,
        "validation_id": None,
        "deployment_id": None
    }


@pytest.fixture
def workflow_state_tracker():
    """Track workflow state through E2E test."""
    class StateTracker:
        def __init__(self):
            self.states = []
            self.current_stage = None

        def record_state(self, stage, data):
            self.states.append({"stage": stage, "data": data})
            self.current_stage = stage

        def get_history(self):
            return self.states

        def stage_completed(self, stage):
            return any(s["stage"] == stage for s in self.states)

    return StateTracker()
