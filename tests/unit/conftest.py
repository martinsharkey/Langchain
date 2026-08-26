"""
Pytest configuration for unit tests.

Unit tests verify individual components in isolation.
They are fast, deterministic, and require no external services.
"""
import pytest


@pytest.fixture
def unit_test_marker():
    """Mark for unit tests."""
    return {"type": "unit", "speed": "fast"}


@pytest.fixture
def isolated_component():
    """Create an isolated component for testing."""
    class MockComponent:
        def __init__(self):
            self.state = {}

        def set_state(self, key, value):
            self.state[key] = value

        def get_state(self, key):
            return self.state.get(key)

        def reset(self):
            self.state = {}

    return MockComponent()
