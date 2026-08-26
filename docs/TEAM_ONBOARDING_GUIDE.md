# TEAM ONBOARDING GUIDE - StrategyOps v2.0

**Version**: 1.0  
**Status**: Production Ready  
**Last Updated**: August 25, 2026

---

## 🎯 Welcome to the Team!

This guide will get you productive with StrategyOps v2.0 in under 30 minutes.

---

## ⏱️ 5-MINUTE QUICK START

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/Langchain.git
cd langchain/langchain
```

### 2. Set Up Environment
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# or
.\venv\Scripts\activate   # Windows

# Install dependencies
make install

# Install pre-commit hooks (MANDATORY)
make setup-pre-commit
```

### 3. Start Services
```bash
# Start all services
make up

# Verify all services are healthy
make ps
```

### 4. Run Tests
```bash
# Run test suite
make test

# Should see: "X passed in Y.XXs"
```

### 5. Open in VS Code
```bash
code langchain-workspace.code-workspace
```

**Done!** You're ready to start developing. 🚀

---

## 📚 CRITICAL READING

Before you make ANY changes, read these files:

1. **[WORKSPACE_RULES.md](WORKSPACE_RULES.md)** - Strict file placement rules ⚠️
2. **[CONTRIBUTING.md](CONTRIBUTING.md)** - Development workflow
3. **[docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md)** - Detailed guide

These files are NOT optional. Violations will block your PR.

---

## 🏗️ PROJECT STRUCTURE

```
langchain/
├── src/                      # Core application code
│   ├── core/                 # Shared models & schemas
│   ├── config/              # Configuration management
│   ├── integrations/        # External integrations (MT5, DB)
│   └── utils/               # Helper functions
│
├── services/                # 6 Microservices (independent)
│   ├── discovery-service/
│   ├── optimization-service/
│   ├── validation-service/
│   ├── deployment-service/
│   ├── orchestration-service/
│   └── execution-service/
│
├── tests/                   # Test suite
│   ├── unit/               # Fast, isolated tests
│   ├── integration/        # Service interaction tests
│   └── e2e/               # Complete workflow tests
│
├── docs/                    # Professional documentation
├── architecture/            # System design & standards
├── infrastructure/         # Docker & Kubernetes
├── tools/                  # Development utilities
└── [14 root files]        # Essential config only
```

**KEY RULE**: Everything has a place. Don't create files at root!

---

## 🔄 DEVELOPMENT WORKFLOW

### Step 1: Create Branch
```bash
git checkout -b feature/your-feature-name

# Naming conventions:
# feature/indicator-support
# bugfix/timeout-issue
# docs/api-documentation
# test/discovery-coverage
```

### Step 2: Develop
```bash
# Your code is auto-formatted on save
# Type hints are required
# Tests are mandatory

# Check formatting
make format-check

# Run tests frequently
make test-unit
```

### Step 3: Commit
```bash
# Pre-commit hooks run automatically
git add .
git commit -m "feat: add indicator discovery support"

# If hooks fail: read error message, fix issue, try again
```

### Step 4: Push & Create PR
```bash
git push origin feature/your-feature-name

# Create PR on GitHub
# Fill in PR template completely
# Reference related issues
```

### Step 5: Code Review
- Respond to feedback professionally
- Make requested changes
- Re-push when ready
- Get approval from 1+ reviewers

---

## 💻 COMMON DEVELOPMENT TASKS

### Run Tests
```bash
make test              # All tests
make test-unit         # Fast unit tests only
make test-integration  # Integration tests
make test-watch        # Auto-rerun on file change
make test-coverage     # With coverage report
```

### Format Code
```bash
make format            # Auto-format code
make format-check      # Check without formatting
make lint             # Run all linters
make type-check       # Type hint validation
```

### Start Services
```bash
make up               # Start all services
make down             # Stop all services
make logs             # View logs
make restart          # Restart services
make ps               # Show running services
```

### Database
```bash
make db-migrate       # Run migrations
make db-seed         # Seed test data
make db-reset        # Reset database
make db-shell        # Open database shell
```

---

## 📝 CODE STANDARDS

### Type Hints (Required)
```python
# ✅ Good
def calculate_profit_factor(trades: List[Trade]) -> float:
    """Calculate profit factor."""
    pass

# ❌ Bad
def calculate_profit_factor(trades):
    pass
```

### Docstrings (Required)
```python
# ✅ Good
def get_strategy(symbol: str) -> Strategy:
    """
    Get strategy by symbol.
    
    Args:
        symbol: Trading symbol (e.g., 'BTCUSD')
    
    Returns:
        Strategy object with performance metrics
    
    Raises:
        NotFoundError: If strategy not found
    """
    pass

# ❌ Bad
def get_strategy(symbol):
    pass
```

### File Placement (STRICT)
```
✅ CORRECT:
  src/core/models.py          (shared code)
  services/discovery/app/     (service code)
  tests/unit/test_*.py        (tests)
  docs/ARCHITECTURE.md        (documentation)
  tools/debug/debug_*.py      (utilities)

❌ WRONG (will be rejected):
  my_script.py                (at root)
  shared_models.py            (should be in src/core/)
  test_discovery.py           (at root, should be in tests/)
  screenshot.png              (at root, should be in docs/images/)
```

---

## 🧪 TESTING CHECKLIST

Before committing, ensure:

- [ ] Unit tests written for new code
- [ ] Tests pass: `make test`
- [ ] Coverage > 80%: `make test-coverage`
- [ ] All linters pass: `make lint`
- [ ] Type checking passes: `make type-check`
- [ ] Code formatted: `make format-check`

---

## 🛡️ PRE-COMMIT HOOKS

Pre-commit hooks automatically run before each commit. They check:

- ✅ No rogue files at root
- ✅ File placement correctness
- ✅ Code formatting (black, isort)
- ✅ Type hints (mypy)
- ✅ Security issues (bandit)
- ✅ Linting (flake8)

**If hooks fail**:
1. Read the error message
2. Fix the issue
3. Stage the fixes
4. Commit again

---

## 📖 ARCHITECTURE OVERVIEW

### 6 Microservices

1. **Discovery Service** - Find indicators via backtesting
2. **Optimization Service** - Tune parameters with Optuna
3. **Validation Service** - Walk-forward validation
4. **Deployment Service** - Live strategy deployment
5. **Orchestration Service** - Workflow coordination
6. **Execution Service** - Trade execution

All services are:
- Independent (scale individually)
- Standardized (same structure)
- Documented (__lld__.md files)
- Tested (80%+ coverage)

---

## 📚 DOCUMENTATION

Read these in order:

1. **[WORKSPACE_RULES.md](WORKSPACE_RULES.md)** - File placement (MANDATORY)
2. **[CONTRIBUTING.md](CONTRIBUTING.md)** - Development process
3. **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System design
4. **[docs/API.md](docs/API.md)** - API reference
5. **[docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md)** - Dev guide
6. **Module __lld__.md files** - Detailed component docs

---

## 🤝 GETTING HELP

### Finding Information
- **File placement?** → See WORKSPACE_RULES.md
- **API reference?** → See docs/API.md
- **How to run tests?** → See this guide or `make help`
- **Architecture questions?** → See architecture/ADRs/
- **Deployment?** → See docs/DEPLOYMENT_PROCEDURES.md

### Getting Stuck
1. Search existing issues/PRs
2. Check documentation
3. Ask in Slack #development
4. Ask tech lead

### Reporting Issues
1. Search existing issues (avoid duplicates)
2. Provide clear description
3. Include reproduction steps
4. Attach logs/errors

---

## ✅ YOUR FIRST PR

### 1. Pick an Issue
Look for issues labeled:
- `good first issue`
- `help wanted`
- `documentation`

### 2. Create Branch
```bash
git checkout -b feature/issue-description
```

### 3. Make Changes
- Follow code standards
- Write tests
- Run `make test` frequently

### 4. Commit & Push
```bash
git commit -m "feat: describe your change"
git push origin feature/issue-description
```

### 5. Create PR
- Fill in PR template
- Reference issue: "Closes #123"
- Wait for code review

---

## 🎓 LEARNING RESOURCES

### Async/Await (Python)
- Used for all I/O operations
- Each service uses FastAPI async endpoints
- See `src/utils/decorators.py` for examples

### Pydantic (Data Validation)
- All API requests/responses validated
- See `src/core/schemas.py` for examples
- Provides OpenAPI docs automatically

### SQLAlchemy (Database)
- ORM for database operations
- See `src/integrations/database/` for examples
- Used for all data persistence

### FastAPI (Web Framework)
- Modern Python web framework
- Auto-generates Swagger/OpenAPI docs
- Used by all 6 services

### VectorBT (Backtesting)
- Used in Discovery Service
- Fast vectorized backtesting
- See `services/discovery-service/core/`

### Optuna (Optimization)
- Used in Optimization Service
- Hyperparameter optimization
- See `services/optimization-service/core/`

---

## 🚀 NEXT STEPS

1. ✅ Read WORKSPACE_RULES.md
2. ✅ Read CONTRIBUTING.md
3. ✅ Set up environment: `make install`
4. ✅ Start services: `make up`
5. ✅ Run tests: `make test`
6. ✅ Pick your first issue
7. ✅ Create a PR

---

## 💡 PRO TIPS

### VS Code Shortcuts
- `Ctrl+Shift+P` - Command palette
- `F5` - Start debugging
- `Ctrl+/` - Comment/uncomment
- `Shift+Alt+F` - Format document
- `Ctrl+Shift+X` - Extensions

### Makefile Commands
```bash
make help              # Show all commands
make dev              # Start development
make test             # Run tests
make format           # Format code
make lint             # Check code quality
make check-all        # Run all checks
```

### Git Tips
```bash
# Update branch from main
git fetch origin
git rebase origin/main

# Interactive rebase to clean history
git rebase -i HEAD~3

# Undo last commit (keep changes)
git reset --soft HEAD~1
```

---

## ⚠️ COMMON MISTAKES

### ❌ Mistake 1: Creating files at root
```
Wrong:  my_script.py
Right:  tools/scripts/my_script.py
```

### ❌ Mistake 2: Missing type hints
```
Wrong:  def get_value(x):
Right:  def get_value(x: int) -> int:
```

### ❌ Mistake 3: Skipping tests
```
Wrong:  Commit without tests
Right:  Write tests, run make test
```

### ❌ Mistake 4: Ignoring pre-commit failures
```
Wrong:  Force commit anyway
Right:  Fix issues, re-commit
```

---

## 🎉 WELCOME TO THE TEAM!

You're now equipped with everything you need to:
- ✅ Understand the project structure
- ✅ Follow development standards
- ✅ Contribute effectively
- ✅ Get your PRs approved

Happy coding! 🚀

---

**Need help?** Check the documentation or ask in Slack #development.

**Questions about this guide?** See the "Getting Help" section above.

**Ready to contribute?** Pick your first issue and create a PR!

---

**Onboarding Guide Version**: 1.0  
**Status**: Production Ready  
**Last Updated**: August 25, 2026
