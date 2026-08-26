"""
Pytest configuration for integration tests.

Integration tests verify interactions between multiple components.
They may require Docker services or external dependencies.
"""
import pytest
import os


@pytest.fixture
def integration_test_marker():
    """Mark for integration tests."""
    return {"type": "integration", "speed": "medium"}


@pytest.fixture
def services_running():
    """Check if Docker services are running."""
    services = ["discovery", "optimization", "validation", "deployment"]
    # In real tests, would check actual service health
    return {service: True for service in services}


@pytest.fixture
def api_base_urls():
    """Base URLs for microservices."""
    return {
        "discovery": "http://localhost:8001",
        "optimization": "http://localhost:8002",
        "validation": "http://localhost:8003",
        "deployment": "http://localhost:8004",
        "orchestration": "http://localhost:8005",
        "execution": "http://localhost:8006"
    }


@pytest.fixture
def database_connection():
    """Mock database connection."""
    class MockDB:
        def __init__(self):
            self.connected = True
            self.data = {}

        def query(self, sql):
            return []

        def execute(self, sql):
            return True

    return MockDB()
