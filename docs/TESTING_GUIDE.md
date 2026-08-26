# Test Suite Documentation

Comprehensive guide to running, writing, and maintaining tests in StrategyOps v2.0.

---

## Table of Contents

1. [Test Structure](#test-structure)
2. [Running Tests](#running-tests)
3. [Writing Tests](#writing-tests)
4. [Test Fixtures](#test-fixtures)
5. [Coverage Goals](#coverage-goals)
6. [CI/CD Integration](#cicd-integration)

---

## Test Structure

### Directory Organization

```
tests/
├── __init__.py
├── conftest.py                 # Global pytest configuration and fixtures
│
├── unit/                       # Fast, isolated unit tests (~5-30 seconds)
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_discovery_service.py      # Discovery service unit tests
│   ├── test_optimization_service.py   # Optimization service unit tests
│   ├── test_validation_service.py
│   ├── test_deployment_service.py
│   ├── test_orchestration_service.py
│   └── test_execution_service.py
│
├── integration/                # Integration tests, requires services (~1-5 minutes)
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_discovery_optimization.py
│   ├── test_optimization_validation.py
│   ├── test_api_endpoints.py
│   └── test_service_communication.py
│
├── e2e/                        # End-to-end workflow tests (~5-30 minutes)
│   ├── __init__.py
│   ├── conftest.py
│   └── test_complete_pipeline.py
│
├── performance/                # Performance and benchmark tests
│   ├── __init__.py
│   ├── conftest.py
│   └── test_performance_benchmarks.py
│
└── fixtures/                   # Shared test data and fixtures
    ├── __init__.py
    ├── sample_data.py
    └── mock_services.py
```

### Test Categories

#### Unit Tests
- **Location**: `tests/unit/`
- **Speed**: Fast (< 1 second each)
- **Dependencies**: None (mocked)
- **Purpose**: Test individual components in isolation
- **Coverage Target**: 100% line coverage
- **Count**: 15-20 tests per service

#### Integration Tests
- **Location**: `tests/integration/`
- **Speed**: Medium (1-5 seconds each)
- **Dependencies**: Docker services running
- **Purpose**: Test interactions between services
- **Coverage Target**: Critical paths only
- **Count**: 5-10 tests per workflow

#### End-to-End Tests
- **Location**: `tests/e2e/`
- **Speed**: Slow (5-30 seconds each)
- **Dependencies**: Complete system running
- **Purpose**: Test complete workflows
- **Coverage Target**: Happy paths + main error scenarios
- **Count**: 3-5 tests per major workflow

#### Performance Tests
- **Location**: `tests/performance/`
- **Speed**: Variable (1-60 seconds)
- **Dependencies**: Real data/services
- **Purpose**: Benchmark and track performance
- **Coverage Target**: Critical path performance
- **Count**: 2-3 per major component

---

## Running Tests

### Run All Tests

```bash
# Run all tests (unit + integration)
pytest

# Run with verbose output
pytest -v

# Run with print statements
pytest -s

# Run with coverage report
pytest --cov=src --cov-report=html
```

### Run by Category

```bash
# Unit tests only (fast)
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# E2E tests (slow)
pytest tests/e2e/ -v

# Performance tests
pytest tests/performance/ -v
```

### Run by Marker

```bash
# Run all integration tests
pytest -m integration

# Run all unit tests
pytest -m unit

# Run all E2E tests
pytest -m e2e

# Exclude slow tests
pytest -m "not slow"

# Run only live tests
pytest -m live
```

### Run Specific Test

```bash
# Specific test file
pytest tests/unit/test_discovery_service.py

# Specific test class
pytest tests/unit/test_discovery_service.py::TestDiscoveryEngine

# Specific test function
pytest tests/unit/test_discovery_service.py::TestDiscoveryEngine::test_discovery_initialization

# Run with keyword
pytest -k "test_discovery" -v
```

### Run with Filters

```bash
# Run tests matching pattern
pytest -k "test_optimization" -v

# Run first 5 failing tests
pytest --lf -x

# Run last failed tests
pytest --lf

# Run tests in specific order
pytest tests/unit/ tests/integration/ tests/e2e/
```

### Parallel Test Execution

```bash
# Install pytest-xdist
pip install pytest-xdist

# Run tests in parallel (4 processes)
pytest -n 4

# Auto-detect CPU count
pytest -n auto
```

---

## Writing Tests

### Test File Naming

```python
# Module under test: src/modules/discovery.py
# Test file: tests/unit/test_discovery_service.py

# Always follow: test_*.py pattern
```

### Test Function Naming

```python
# ✅ Good: Clear, describes what is tested
def test_discovery_validates_symbol():
    pass

def test_optimization_improves_over_baseline():
    pass

# ❌ Bad: Vague or not descriptive
def test_it_works():
    pass

def test_func1():
    pass
```

### Basic Test Structure

```python
"""
Unit tests for Discovery Service.

Brief description of what these tests cover.
"""
import pytest
from src.modules.discovery import DiscoveryEngine


class TestDiscoveryEngine:
    """Group related tests in classes."""

    def test_initialization(self):
        """Test engine can be initialized."""
        engine = DiscoveryEngine(symbol="BTCUSD")
        assert engine.symbol == "BTCUSD"

    def test_parameter_validation(self):
        """Test invalid parameters are rejected."""
        with pytest.raises(ValueError):
            DiscoveryEngine(symbol="")

    @pytest.mark.integration
    def test_with_real_service(self, api_base_urls):
        """Test integration with real service."""
        # Only runs with -m integration
        pass
```

### Using Fixtures

```python
@pytest.fixture
def sample_config():
    """Reusable test configuration."""
    return {
        "symbol": "BTCUSD",
        "session": "London"
    }

def test_with_fixture(sample_config):
    """Use fixture in test."""
    assert sample_config["symbol"] == "BTCUSD"
```

### Parametrized Tests

```python
@pytest.mark.parametrize("symbol,session", [
    ("BTCUSD", "London"),
    ("EURUSD", "New York"),
    ("XAUUSD", "Tokyo"),
])
def test_multiple_symbols(symbol, session):
    """Test with multiple input combinations."""
    engine = DiscoveryEngine(symbol=symbol, session=session)
    assert engine.symbol == symbol
    assert engine.session == session
```

### Mocking External Dependencies

```python
from unittest.mock import Mock, patch

def test_with_mock():
    """Test with mocked dependency."""
    with patch('src.modules.discovery.DataFetcher') as mock_fetcher:
        mock_fetcher.return_value.get_data.return_value = []
        
        engine = DiscoveryEngine(symbol="BTCUSD")
        result = engine.run()
        
        mock_fetcher.return_value.get_data.assert_called_once()
```

### Async Tests

```python
@pytest.mark.asyncio
async def test_async_discovery():
    """Test async discovery execution."""
    engine = DiscoveryEngine(symbol="BTCUSD")
    result = await engine.run_async()
    assert result is not None
```

### Exception Testing

```python
def test_handles_errors():
    """Test error handling."""
    # Should raise specific exception
    with pytest.raises(ValueError) as exc_info:
        DiscoveryEngine(symbol="")
    
    # Check exception message
    assert "symbol required" in str(exc_info.value)
```

---

## Test Fixtures

### Global Fixtures (conftest.py)

```python
@pytest.fixture
def sample_strategy_config():
    """Reusable strategy configuration."""
    return {
        "symbol": "BTCUSD",
        "session": "London",
        "indicators": ["Bollinger_Bands", "OsMA"]
    }

@pytest.fixture
def mock_http_client():
    """Mock HTTP client for API testing."""
    class MockClient:
        def get(self, url):
            return {"status": "ok"}
    return MockClient()
```

### Service-Specific Fixtures

```python
# tests/unit/conftest.py
@pytest.fixture
def discovery_engine():
    """Create discovery engine for testing."""
    return DiscoveryEngine(symbol="BTCUSD")
```

### Fixture Scope

```python
# Function scope (default, recreated for each test)
@pytest.fixture(scope="function")
def fresh_engine():
    return DiscoveryEngine()

# Session scope (created once for entire session)
@pytest.fixture(scope="session")
def database_connection():
    conn = connect_db()
    yield conn
    conn.close()

# Module scope (created once per module)
@pytest.fixture(scope="module")
def shared_data():
    return load_data()
```

---

## Coverage Goals

### Coverage Targets

| Category | Target | Tool |
|----------|--------|------|
| Overall | 80%+ | coverage.py |
| Unit tests | 100% | Line coverage |
| Integration | 60% | Path coverage |
| Critical paths | 100% | Manual review |

### Generate Coverage Report

```bash
# Generate HTML coverage report
pytest --cov=src --cov-report=html

# Open report
open htmlcov/index.html  # macOS
start htmlcov/index.html # Windows
xdg-open htmlcov/index.html # Linux
```

### Coverage Configuration

Edit `pytest.ini`:
```ini
[coverage:run]
branch = True
omit =
    */tests/*
    */venv/*

[coverage:report]
exclude_lines =
    pragma: no cover
    def __repr__
    if __name__ == .__main__.:
```

---

## CI/CD Integration

### GitHub Actions Workflow

Create `.github/workflows/test.yml`:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:13
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: "3.10"
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio
      
      - name: Run tests
        run: pytest tests/unit tests/integration --cov=src --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
```

### Running in CI

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run all tests
pytest --cov=src --cov-report=xml

# Check coverage threshold
pytest --cov=src --cov-fail-under=80
```

---

## Best Practices

1. **Test Names**: Use descriptive names that explain what is tested
2. **One Assertion Per Test**: Keep tests focused and simple
3. **Arrange-Act-Assert**: Organize tests clearly
4. **DRY**: Use fixtures to avoid duplication
5. **Isolation**: Each test should be independent
6. **Speed**: Unit tests should run in milliseconds
7. **Coverage**: Aim for high coverage of critical paths
8. **Documentation**: Comment complex test logic

---

## Troubleshooting

### Test Fails Locally but Passes in CI

```bash
# Run test in isolated environment
pytest -x -v test_name

# Check for random/timing issues
pytest --randomly-seed=12345 test_name

# Verbose output
pytest -vv -s test_name
```

### Tests Are Too Slow

```bash
# Profile tests
pytest --durations=10

# Run only unit tests
pytest tests/unit/ -v

# Use pytest-xdist for parallel execution
pytest -n auto
```

### Mock Issues

```python
# Ensure mock is in correct path
with patch('module.where.it.is.used') as mock:  # ✅ Correct
    pass

with patch('module.where.defined') as mock:  # ❌ Wrong
    pass
```

---

**Test Suite Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Production Ready
