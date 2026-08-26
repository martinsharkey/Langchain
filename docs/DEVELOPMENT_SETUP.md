# Development Environment Setup

Complete guide to setting up the professional development environment for StrategyOps v2.0.

---

## Quick Start (5 minutes)

### 1. Clone and Navigate
```bash
git clone https://github.com/martinsharkey/Langchain.git
cd langchain/langchain
```

### 2. Create Virtual Environment
```bash
python -m venv venv

# Activate (macOS/Linux)
source venv/bin/activate

# Activate (Windows)
.\venv\Scripts\activate
```

### 3. Install Dependencies
```bash
make install
```

### 4. Start Development Environment
```bash
make dev
```

**Done!** Services running at:
- API Gateway: http://localhost:8000
- Discovery Service: http://localhost:8001
- Optimization Service: http://localhost:8002
- Dashboard: http://localhost:3000

---

## Makefile Commands

### Essential Commands

```bash
# View all available commands
make help

# Install dependencies
make install

# Start development environment
make dev

# Run all tests
make test

# Format code
make format

# Lint code
make lint

# View service logs
make logs

# Stop services
make down

# Clean build artifacts
make clean
```

### Testing Commands

```bash
# Run all tests with coverage
make test

# Run unit tests only (fast)
make test-unit

# Run integration tests
make test-integration

# Run end-to-end tests
make test-e2e

# Watch mode (auto-run tests on file change)
make test-watch

# Generate detailed coverage report
make test-coverage
```

### Code Quality Commands

```bash
# Run all checks (format, lint, type)
make lint

# Check formatting
make format-check

# Format code
make format

# Type checking with mypy
make type-check

# Security check with bandit
make security-check

# Flake8 linting
make lint-flake8

# Pylint linting
make lint-pylint

# Run all checks
make check-all
```

### Docker Commands

```bash
# Start all services
make up

# Stop all services
make down

# Restart services
make restart

# View logs
make logs

# View logs for specific service
make logs-service SERVICE=discovery-service

# Build images
make build

# Show running services
make ps
```

### Development Commands

```bash
# Start discovery service with hot-reload
make dev-discovery

# Start optimization service with hot-reload
make dev-optimization

# Show all dev service commands
make dev-all
```

---

## VS Code Setup

### 1. Open Workspace
```bash
code langchain-workspace.code-workspace
```

### 2. Install Recommended Extensions
When prompted, click "Install" to install recommended extensions:
- Python
- Pylance
- Ruff
- GitLens
- Copilot
- Docker
- Kubernetes
- YAML

### 3. Configure Python Interpreter
1. Press `Cmd+Shift+P` (macOS) or `Ctrl+Shift+P` (Windows/Linux)
2. Type "Python: Select Interpreter"
3. Choose `./venv/bin/python`

### 4. Testing in VS Code
- Press `Ctrl+Shift+D` to open Debug view
- Select "Python: Run Tests" to run test suite
- Use Test Explorer (left sidebar) to run individual tests

### 5. Debugging
- Set breakpoints by clicking line numbers
- Press `F5` to start debugging current file
- Use Debug Console to inspect variables

---

## Pre-commit Hooks

### Installation
```bash
# Install pre-commit hooks
make setup-pre-commit

# Or manually
pip install pre-commit
pre-commit install
```

### What Happens
Before each commit, pre-commit will:
1. ✅ Format code with black and isort
2. ✅ Check formatting with flake8
3. ✅ Validate type hints with mypy
4. ✅ Check for security issues with bandit
5. ✅ Scan for secrets with gitleaks
6. ✅ Fix common issues automatically

### Running Manually
```bash
# Run on all files
pre-commit run --all-files

# Update hooks
pre-commit autoupdate
```

---

## Code Formatting

### Black (Code Formatter)
```bash
# Format all code
make format

# Check without formatting
make format-check
```

**Configuration**: See `pyproject.toml`
- Line length: 100 characters
- Python target: 3.10+

### isort (Import Sorting)
```bash
# Auto-sort imports
make format
```

**Configuration**: Uses black-compatible profile

### Automatic Formatting
Code is automatically formatted:
- On save in VS Code (configured)
- Before each commit (pre-commit hook)
- When you run `make format`

---

## Linting and Type Checking

### Flake8 (PEP 8 Linter)
```bash
make lint-flake8
```

**Rules**:
- Max line length: 100 characters
- Ignored: E203, W503, E501

### Pylint (Code Analyzer)
```bash
make lint-pylint
```

**Configuration**: See `pyproject.toml`

### MyPy (Type Checker)
```bash
make type-check
```

**Configuration**: Checks untyped definitions, no implicit optional

### All Checks
```bash
# Run all quality checks
make check-all
```

---

## Testing

### Quick Start
```bash
# Run all tests
make test

# Run unit tests only (fast)
make test-unit

# Watch mode (rerun on file change)
make test-watch
```

### Test Organization
```
tests/
├── unit/          Fast, isolated tests
├── integration/   Service communication tests
├── e2e/          Complete workflow tests
└── performance/  Benchmark tests
```

### Coverage Report
```bash
# Generate coverage report
make test-coverage

# View HTML report
open htmlcov/index.html
```

---

## Database Operations

### Migrations
```bash
# Run migrations
make db-migrate

# Reset database
make db-reset

# Seed test data
make db-seed
```

### Database Shell
```bash
# Open PostgreSQL shell
make db-shell
```

---

## Project Dependencies

### Main Dependencies (requirements.txt)
- FastAPI: Web framework
- Pydantic: Data validation
- SQLAlchemy: ORM
- NumPy/Pandas: Data processing
- VectorBT: Backtesting
- Optuna: Hyperparameter optimization

### Dev Dependencies (requirements-dev.txt)
- pytest: Testing framework
- black: Code formatting
- mypy: Type checking
- flake8: Linting
- pre-commit: Git hooks

### Adding Dependencies
```bash
# Add new dependency
pip install new-package

# Update requirements
make requirements

# Commit changes
git add requirements.txt requirements-dev.txt
```

---

## Common Development Tasks

### Creating a New Feature

1. **Create feature branch**:
```bash
git checkout -b feature/your-feature-name
```

2. **Make changes** in your editor
   - Code is automatically formatted on save
   - Type hints are checked

3. **Run tests**:
```bash
make test
```

4. **Format and lint**:
```bash
make lint format
```

5. **Commit**:
```bash
git add .
git commit -m "feat: add new feature"
# Pre-commit hooks run automatically
```

6. **Push**:
```bash
git push origin feature/your-feature-name
```

### Adding a New Test

1. Create test file in appropriate directory:
   - Unit test: `tests/unit/test_*.py`
   - Integration test: `tests/integration/test_*.py`
   - E2E test: `tests/e2e/test_*.py`

2. Write test:
```python
def test_my_feature():
    """Test description."""
    assert result == expected
```

3. Run tests:
```bash
make test
```

### Debugging

**VS Code Debugger**:
1. Set breakpoint (click line number)
2. Press `F5` to debug
3. Use Debug Console to inspect variables

**Interactive Debugger**:
```python
import pdb
pdb.set_trace()  # Execution pauses here
```

**Print Debugging**:
```bash
# Run tests with print statements
make test-unit -- -s
```

---

## Troubleshooting

### Virtual Environment Issues

**Problem**: Python modules not found
```bash
# Reactivate virtual environment
source venv/bin/activate  # macOS/Linux
.\venv\Scripts\activate   # Windows
```

**Problem**: "command not found: python"
```bash
# Use python3 explicitly
python3 -m venv venv
python3 -m pip install -r requirements.txt
```

### Docker Issues

**Problem**: Port already in use
```bash
# Change port in docker-compose.yml
# Or kill process using port:
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows
```

**Problem**: Services won't start
```bash
# Check logs
make logs

# Rebuild images
make build

# Restart services
make restart
```

### Import Errors

**Problem**: "ModuleNotFoundError: No module named 'src'"
```bash
# Make sure you're in langchain/langchain directory
cd langchain/langchain

# Set PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Formatting Conflicts

**Problem**: Pre-commit rejects formatting
```bash
# Run formatter
make format

# Re-stage changes
git add .

# Try commit again
git commit -m "message"
```

---

## IDE Configuration

### VS Code (Recommended)
- Open `langchain-workspace.code-workspace`
- Extensions auto-installed
- Python interpreter auto-configured
- Debugging ready with F5

### PyCharm
1. Open project
2. Configure Python interpreter:
   - Settings → Project → Python Interpreter
   - Select `./venv/bin/python`
3. Enable code style:
   - Settings → Tools → Python Integrated Tools
   - Select black as formatter
4. Run tests:
   - Right-click test file → Run

### Vim/Neovim
```bash
# Install language server
pip install python-lsp-server python-lsp-black

# Configure LSP in your editor
# Use coc.nvim or nvim-lsp
```

---

## Performance Tips

1. **Use unit tests for development**:
```bash
make test-unit  # Fast feedback loop
```

2. **Watch mode for development**:
```bash
make test-watch  # Auto-rerun on file change
```

3. **Format only changed files**:
```bash
# Before committing
make format
```

4. **Use pytest markers to skip slow tests**:
```bash
pytest -m "not slow"  # Skip slow tests
```

---

## Next Steps

1. ✅ Set up development environment
2. ✅ Install recommended VS Code extensions
3. ✅ Create feature branch
4. ✅ Start developing!

---

**Setup Version**: 1.0  
**Last Updated**: August 25, 2026  
**Status**: Ready for Development
