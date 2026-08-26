# CONTRIBUTING.md - Contributing to StrategyOps v2.0

Welcome to StrategyOps v2.0! This guide will help you contribute effectively to our professional, enterprise-grade codebase.

---

## 📋 Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Before You Start](#before-you-start)
3. [Development Workflow](#development-workflow)
4. [File Placement Guide](#file-placement-guide)
5. [Code Standards](#code-standards)
6. [Testing Requirements](#testing-requirements)
7. [Pull Request Process](#pull-request-process)
8. [Commit Guidelines](#commit-guidelines)

---

## 🤝 Code of Conduct

We are committed to providing a welcoming and inspiring community.

### Our Standards
- ✅ Be respectful and inclusive
- ✅ Focus on constructive feedback
- ✅ Respect different opinions
- ✅ Be professional and courteous
- ✅ Report issues appropriately

---

## 🚀 Before You Start

### 1. Read WORKSPACE_RULES.md
**CRITICAL**: This file contains strict file placement rules. Read it completely.

```bash
# Read the rules
cat WORKSPACE_RULES.md

# Understand where files go
# - Python code → src/ or services/
# - Tests → tests/
# - Tools → tools/
# - Documentation → docs/
```

### 2. Set Up Your Environment
```bash
# Clone the repository
git clone https://github.com/yourusername/Langchain.git
cd langchain/langchain

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\activate on Windows

# Install dependencies
make install

# Install pre-commit hooks (MANDATORY)
make setup-pre-commit
```

### 3. Understand the Architecture
- Read `docs/ARCHITECTURE.md` - System overview
- Read `architecture/ADRs/ADR-001-006.md` - Design decisions
- Read `architecture/HLD/HLD.md` - High level design
- Review `WORKSPACE_RULES.md` - File placement rules

### 4. Check Prerequisites
```bash
# Verify services are running
make up

# Verify tests pass
make test

# Verify code formatting
make format-check
```

---

## 🔄 Development Workflow

### Step 1: Create Feature Branch
```bash
# Use descriptive branch names
git checkout -b feature/discovery-indicator-support
# or
git checkout -b bugfix/optimization-convergence
# or
git checkout -b docs/api-documentation
```

**Branch Naming Convention**:
- `feature/description` - New features
- `bugfix/description` - Bug fixes
- `docs/description` - Documentation
- `refactor/description` - Code refactoring
- `test/description` - Test improvements

### Step 2: Develop Your Feature
```bash
# Make your changes
# Code is auto-formatted on save in VS Code

# Run tests frequently
make test-unit

# Check formatting
make format-check

# Check types
make type-check
```

### Step 3: Run Full Test Suite
```bash
# Before committing, run full suite
make test

# Or run specific tests
make test-unit
make test-integration
```

### Step 4: Commit Your Changes
```bash
# Pre-commit hooks will run automatically
git add .
git commit -m "feat: add indicator discovery support"

# If pre-commit fails:
# 1. Read the error message
# 2. Fix the issue
# 3. Stage the fixes
# 4. Commit again
```

### Step 5: Push and Create PR
```bash
# Push your branch
git push origin feature/discovery-indicator-support

# Create PR on GitHub
# Fill in the PR template completely
```

---

## 📁 File Placement Guide

### ✅ ALLOWED Locations

| File Type | Location | Example |
|-----------|----------|---------|
| **Python Code** | `src/` or `services/` | `src/core/models.py` |
| **Tests** | `tests/` | `tests/unit/test_discovery.py` |
| **Documentation** | `docs/` | `docs/ARCHITECTURE.md` |
| **Images/Screenshots** | `docs/images/` | `docs/images/dashboard.png` |
| **Module Design** | `module/__lld__.md` | `src/core/__lld__.md` |
| **Tools/Scripts** | `tools/` | `tools/debug/debug_discovery.py` |
| **Infrastructure** | `infrastructure/` | `infrastructure/docker-compose.yml` |
| **Service Specs** | `architecture/Module-Specs/` | `architecture/Module-Specs/discovery.md` |

### ❌ FORBIDDEN at Root

```
❌ *.py files (except config files)
❌ *.png, *.jpg files
❌ *.json data files
❌ Personal scripts
❌ Test files
❌ Temporary files

→ These will be REJECTED by pre-commit hooks
```

---

## 💻 Code Standards

### Python Style Guide
We follow **PEP 8** with Black formatting.

```python
# ✅ Good: Clear, type-hinted, documented
def calculate_profit_factor(
    trades: List[Trade],
    min_trades: int = 10
) -> float:
    """
    Calculate profit factor from trades.
    
    Args:
        trades: List of Trade objects
        min_trades: Minimum trades required
        
    Returns:
        float: Profit factor (gross profit / gross loss)
        
    Raises:
        ValueError: If insufficient trades
    """
    if len(trades) < min_trades:
        raise ValueError(f"Need at least {min_trades} trades")
    
    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
    
    return gross_profit / gross_loss if gross_loss > 0 else 0.0
```

### Type Hints (Required)
```python
# ✅ All functions must have type hints
def discover_indicators(
    symbol: str,
    timeframe: str,
    indicators: List[str]
) -> Dict[str, PerformanceMetrics]:
    """Discover best performing indicators."""
    pass

# ❌ NOT ALLOWED
def discover_indicators(symbol, timeframe, indicators):
    """Discover best performing indicators."""
    pass
```

### Docstrings (Required)
```python
# ✅ All modules, classes, functions must have docstrings
class DiscoveryEngine:
    """
    Strategy discovery engine using vectorbt backtesting.
    
    Attributes:
        symbol: Trading symbol (e.g., 'BTCUSD')
        session: Trading session (e.g., 'London')
        indicators: List of indicators to test
    """
    
    def discover(self) -> List[DiscoveryResult]:
        """
        Execute discovery process.
        
        Returns:
            List of ranked discoveries with performance metrics
        """
        pass
```

### Module Structure
```python
# src/core/__init__.py - Proper module initialization
from .models import Strategy, PerformanceMetrics
from .schemas import StrategySchema

__all__ = [
    "Strategy",
    "PerformanceMetrics",
    "StrategySchema",
]
```

### Naming Conventions
```python
# ✅ Clear, descriptive names
class DiscoveryService:
    def calculate_profit_factor(self, trades: List[Trade]) -> float:
        max_drawdown = self._calculate_max_drawdown(trades)
        return max_drawdown

# ❌ Unclear names
class DS:
    def calc_pf(self, t):
        md = self._calc_md(t)
        return md
```

---

## 🧪 Testing Requirements

### Writing Tests

```python
# tests/unit/test_discovery.py
import pytest
from src.modules.discovery import DiscoveryEngine

class TestDiscoveryEngine:
    """Tests for discovery engine."""
    
    @pytest.fixture
    def engine(self):
        """Create discovery engine for testing."""
        return DiscoveryEngine(symbol="BTCUSD", session="London")
    
    def test_initialization(self, engine):
        """Test engine initialization."""
        assert engine.symbol == "BTCUSD"
        assert engine.session == "London"
    
    def test_validates_symbol(self):
        """Test symbol validation."""
        with pytest.raises(ValueError):
            DiscoveryEngine(symbol="", session="London")
    
    @pytest.mark.integration
    def test_discover_with_real_data(self, engine):
        """Test discovery with real data."""
        results = engine.discover()
        assert len(results) > 0
        assert all(r.profit_factor > 0 for r in results)
```

### Test Coverage Requirements
- **Unit tests**: Required for all new code
- **Integration tests**: Required for service interactions
- **Coverage target**: 80%+ minimum
- **All tests must pass**: Before PR approval

### Running Tests
```bash
# All tests
make test

# Unit tests only (fast)
make test-unit

# With coverage report
make test-coverage

# Watch mode (auto-rerun)
make test-watch
```

---

## 📤 Pull Request Process

### Before Creating PR
- [ ] Code passes all tests: `make test`
- [ ] Code is formatted: `make format`
- [ ] Linting passes: `make lint`
- [ ] Type checking passes: `make type-check`
- [ ] Branch is up to date with main
- [ ] All commits are logical and descriptive

### PR Template
```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Feature (new functionality)
- [ ] Bugfix (fixes existing issue)
- [ ] Documentation
- [ ] Refactoring

## Changes Made
- Point 1
- Point 2
- Point 3

## Testing Done
- [ ] Unit tests added
- [ ] Integration tests added
- [ ] Manual testing completed

## Files Changed
- File 1: Brief description
- File 2: Brief description

## Related Issues
Closes #123

## Additional Notes
Any other information helpful for review
```

### Code Review Checklist
Your PR will be reviewed for:
- ✅ Follows WORKSPACE_RULES.md
- ✅ Follows code standards
- ✅ Type hints present
- ✅ Docstrings complete
- ✅ Tests passing (80%+ coverage)
- ✅ No rogue files
- ✅ Proper file placement
- ✅ Documentation updated

---

## 💬 Commit Guidelines

### Commit Message Format
```
type(scope): subject

body

footer
```

### Types
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `style` - Code style (formatting)
- `refactor` - Code refactoring
- `test` - Test additions
- `chore` - Build/dependency changes

### Examples
```bash
# Good commits
git commit -m "feat(discovery): add indicator combination support"
git commit -m "fix(optimization): correct parameter bounds validation"
git commit -m "docs: update API documentation"
git commit -m "test(validation): add walkforward test cases"

# Bad commits
git commit -m "stuff"
git commit -m "more fixes"
git commit -m "working version"
```

### Commit Body Guidelines
- Explain WHAT changed and WHY
- Reference related issues: "Fixes #123"
- Keep lines under 72 characters
- Separate paragraphs with blank lines

```bash
git commit -m "feat(discovery): add bollinger bands indicator

- Implement BollingerBands class with period/deviation params
- Add volatility calculation for signal generation
- Update indicator registry with new indicator
- Add comprehensive tests with various market conditions

This enables strategies to use Bollinger Bands for
entry/exit signal generation.

Closes #156"
```

---

## 🔍 Common Issues & Solutions

### Pre-commit Hook Fails
```bash
# Read the error message carefully
# Usually fixable by running:
make format

# If it still fails:
1. Read the error message
2. Fix the issue manually
3. Stage the fix
4. Commit again
```

### Tests Failing Locally
```bash
# Ensure services are running
make up

# Run tests with verbose output
make test -- -v

# Run specific test
pytest tests/unit/test_discovery.py::test_initialization -v
```

### Formatting Conflicts
```bash
# Auto-format all code
make format

# Stage the formatted code
git add .

# Commit the formatting
git commit -m "style: auto-format code"
```

### Type Checking Errors
```bash
# Run type checker
make type-check

# Fix issues:
1. Add missing type hints
2. Import types from typing module
3. Use proper type annotations

# If external library lacks types:
# Add to pyproject.toml [tool.mypy]
[[tool.mypy.overrides]]
module = "external_lib"
ignore_missing_imports = true
```

---

## 📚 Helpful Resources

### Documentation
- [WORKSPACE_RULES.md](WORKSPACE_RULES.md) - Strict file placement rules
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture
- [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md) - Development guide
- [architecture/ADRs/](architecture/ADRs/) - Architecture decisions

### Commands
- `make help` - Show all available commands
- `make dev` - Start development environment
- `make test` - Run all tests
- `make lint` - Run all linters
- `make format` - Format code

### Tools
- **IDE**: VS Code with Python extension
- **Formatter**: Black
- **Linter**: Flake8, Pylint
- **Type Checker**: MyPy
- **Test Framework**: Pytest

---

## ❓ Questions?

1. **Where do I put my code?** → Read WORKSPACE_RULES.md
2. **How do I format code?** → Run `make format`
3. **How do I run tests?** → Run `make test`
4. **How do I create a branch?** → Follow naming convention above
5. **My pre-commit failed?** → Read the error, fix it, try again

---

## 🎯 Code Review Tips

### Write Better Code
- ✅ Break complex logic into small functions
- ✅ Add type hints to all functions
- ✅ Write docstrings for all modules/classes/functions
- ✅ Add tests for new functionality
- ✅ Reference issues in commit messages

### Respond to Feedback
- ✅ Be gracious - reviewers are helping you
- ✅ Ask questions if feedback isn't clear
- ✅ Acknowledge good points
- ✅ Explain your reasoning if you disagree
- ✅ Make changes promptly

### Give Good Feedback
- ✅ Be constructive and specific
- ✅ Suggest improvements, don't demand
- ✅ Acknowledge good work
- ✅ Approve when ready

---

## 🎉 Thank You!

Thank you for contributing to StrategyOps v2.0. Your contributions help make this project better for everyone!

Happy coding! 🚀

---

**Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Active
