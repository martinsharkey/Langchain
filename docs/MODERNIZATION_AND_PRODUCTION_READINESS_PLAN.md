# StrategyOps v2.0 - Workspace Modernization & Production Readiness Plan

**Date**: August 25, 2026  
**Status**: Phase 1 Complete, Planning Phase 2+  
**Target**: Clean, professional development environment ready for production

---

## EXECUTIVE SUMMARY

The microservices architecture (Phase 1) is now operational with all 6 services running and healthy. However, the VS Code workspace is cluttered with 109 root-level files and legacy code that contradicts the modular v2.0 design. This plan addresses:

1. **Workspace Cleanup** - Eliminate legacy files and organize professionally
2. **Documentation Modernization** - Update v2.0 design docs to match reality
3. **Test Suite Standardization** - Unified testing framework for all services
4. **Development Environment** - Clean workspace structure for team collaboration
5. **Production Readiness** - Validated deployment pipeline and documentation

**Timeline**: 2-3 weeks to production ready  
**Effort**: Distributed across cleanup, testing, and hardening phases

---

## PHASE 2: WORKSPACE MODERNIZATION (Week 1)

### 2.1 Root Directory Cleanup

**Current State**: 109 files at root level (scripts, configs, analysis, legacy code)

**Target State**: Clean root with only essential files

#### Actions Required:

**2.1.1 Archive Legacy Files**
```
Archive → /archive/legacy-phase-1/
├── scalp_engine.py (pre-v2.0)
├── vectorbt_optimizer.py (pre-v2.0)
├── optuna_floor_optimizer.py (pre-v2.0)
├── All analysis/*.py files
├── All test_*.py files (except in /tests/)
├── All debug_*.py files
├── All discover_*.py files
├── All optimize_*.py files
└── All backtest_*.py files
```

**Files to Archive** (50+ files):
- `scalp_engine.py`
- `vectorbt_optimizer.py`
- `optuna_floor_optimizer.py`
- `analyze_*.py` (6 files)
- `backtest_*.py` (4 files)
- `debug_*.py` (3 files)
- `discover_*.py` (2 files)
- `optimize_*.py` (3 files)
- `test_*.py` (7 files at root)
- `find_*.py` (2 files)
- `brute_force_optimizer.py`
- `fast_optimizer.py`
- `vectorbt_expanded_results.txt`
- `btcusd_optimization_run.txt`
- `session_filter_results*.txt`
- `profiling_results.json`
- All legacy analysis results

**2.1.2 Keep at Root** (10-15 files)
```
Root Directory (Clean)
├── docker-compose.yml ✅
├── docker-compose-prod.yml ✅
├── nginx.conf ✅
├── pytest.ini ✅
├── .env (example) ✅
├── .env.example ✅
├── .gitignore ✅
├── .pre-commit-config.yaml ✅
├── requirements.txt (root-level if shared) ✅
├── README.md (main project readme) ✅
├── DEPLOYMENT_GUIDE.md ✅
├── CONTRIBUTING.md (new)
├── LICENSE (new)
└── Makefile (new - build commands)
```

**2.1.3 Delete Unnecessary Files**
- `app.py` (old monolithic app)
- `live_monitor.py` (pre-service architecture)
- `whale_monitor.py` (pre-service architecture)
- `housekeeping.py` (pre-service architecture)
- All `.txt` result files
- All `.code-workspace` files except main one
- All old implementation summary files (DAY1_*.md, DAY2_*.md, etc.)

**2.1.4 Documentation Consolidation**

**Delete These** (Old Implementation Docs - 20+ files):
```
DELETE:
├── DAYS1-6_IMPLEMENTATION_COMPLETE.md
├── DAY1_IMPLEMENTATION_SUMMARY.md
├── DAY2_IMPLEMENTATION_SUMMARY.md
├── DAY3_IMPLEMENTATION_SUMMARY.md
├── DAY4_IMPLEMENTATION_SUMMARY.md
├── DAY5_IMPLEMENTATION_SUMMARY.md
├── DAY6_TESTING_PROGRESS.md
├── DAYS6-7_FINAL_VALIDATION_COMPLETE.md
├── PROJECT_COMPLETE_FINAL.md
├── PROJECT_COMPLETION_SUMMARY.md
├── FINAL_PROJECT_SUMMARY.md
├── PHASE1_FINAL_HANDOFF.md
├── PHASE1_STATUS.txt
├── SETUP_COMPLETE.md
├── SETUP_STATUS.txt
├── DOCKER_STARTUP_IN_PROGRESS.md
├── DOCKER_WSL_INTEGRATION_FIX.md
├── RESTART_REQUIRED.md
├── DEPLOYMENT_GUIDE.md (old version)
├── DEPLOYMENT.md
├── QUICK_REFERENCE.md
├── ACTION_ITEMS.md
├── TESTING_QUICK_START.txt
├── START_HERE.txt
├── COMMIT_SUCCESSFUL.md
├── COMPLETE_IMPLEMENTATION_SUMMARY.md
├── CODE_REVIEW_VECTORBT_OPTUNA_PIPELINE.md
├── ARCHITECTURAL_REVIEW_RECOMMENDATIONS.md
└── Many others...
```

**Keep These** (Current v2.0 Docs):
```
KEEP:
├── ARCHITECTURE_REVIEW_SUMMARY.md ✅
├── ARCHITECTURE_REVIEW_AND_TESTING_PLAN.md ✅
├── ARCHITECTURE_VISUAL_GUIDE.md ✅
├── QUICK_START_FIX_GUIDE.md ✅
├── DOCUMENTATION_INDEX.md ✅
├── V2.0_ARCHITECTURE_STRUCTURE.md ✅
├── V2.0_IMPLEMENTATION_ROADMAP.md ✅
├── V2.0_PHASE1_COMPLETION.md ✅
├── V2.0_PHASE1_HANDOFF.md ✅
├── V2.0_PHASE1_KICKOFF.md ✅
└── (others that directly reference v2.0)
```

### 2.2 Create Clean Directory Structure

```
langchain/
├── .github/                      # CI/CD workflows
│   ├── workflows/
│   │   ├── test.yml
│   │   ├── lint.yml
│   │   └── deploy.yml
│   └── ISSUE_TEMPLATE/
│
├── .kilo/                        # Kilo configuration
│   ├── agent/
│   ├── command/
│   └── agent-manager.json
│
├── .vscode/                      # VS Code workspace config
│   ├── settings.json
│   ├── extensions.json
│   ├── launch.json
│   └── tasks.json
│
├── services/                     # 6 microservices (existing)
│   ├── discovery-service/
│   ├── optimization-service/
│   ├── validation-service/
│   ├── deployment-service/
│   ├── orchestration-service/
│   └── execution-service/
│
├── shared/                       # Shared code (existing)
│   ├── models/
│   ├── utils/
│   └── config/
│
├── tests/                        # Unified test suite (reorganized)
│   ├── conftest.py
│   ├── requirements.txt
│   ├── unit/
│   │   ├── services/
│   │   ├── models/
│   │   └── utils/
│   ├── integration/
│   │   ├── test_discovery_optimization.py
│   │   ├── test_optimization_validation.py
│   │   ├── test_deployment_execution.py
│   │   └── test_full_pipeline.py
│   ├── performance/
│   │   ├── test_load.py
│   │   ├── test_resilience.py
│   │   └── test_throughput.py
│   └── e2e/
│       ├── test_workflow_btcusd.py
│       ├── test_workflow_eurusd.py
│       └── test_workflow_multi_session.py
│
├── infrastructure/               # Deployment configs
│   ├── docker/
│   │   ├── Dockerfile.base
│   │   └── docker-compose.prod.yml
│   ├── kubernetes/               # (future)
│   │   ├── services/
│   │   └── ingress/
│   └── terraform/                # (future)
│       ├── aws/
│       └── gcp/
│
├── scripts/                      # Utility scripts
│   ├── setup/
│   │   ├── setup-dev.sh
│   │   ├── setup-prod.sh
│   │   └── setup-windows.ps1
│   ├── ops/
│   │   ├── health-check.sh
│   │   ├── backup.sh
│   │   ├── migrate.sh
│   │   └── rollback.sh
│   └── dev/
│       ├── format-code.sh
│       ├── lint.sh
│       └── run-tests.sh
│
├── docs/                         # Comprehensive documentation
│   ├── architecture/
│   │   ├── microservices.md
│   │   ├── data-flow.md
│   │   └── deployment.md
│   ├── api/
│   │   ├── discovery-service.md
│   │   ├── optimization-service.md
│   │   ├── validation-service.md
│   │   ├── deployment-service.md
│   │   ├── orchestration-service.md
│   │   └── execution-service.md
│   ├── guides/
│   │   ├── getting-started.md
│   │   ├── development.md
│   │   ├── testing.md
│   │   ├── deployment.md
│   │   └── troubleshooting.md
│   ├── operations/
│   │   ├── monitoring.md
│   │   ├── logging.md
│   │   ├── backup-recovery.md
│   │   └── scaling.md
│   └── CHANGELOG.md
│
├── config/                       # Configuration files
│   ├── development.env
│   ├── staging.env
│   ├── production.env
│   ├── logging.yaml
│   └── feature-flags.yaml
│
├── data/                         # Data directories (gitignored)
│   ├── cache/
│   ├── backups/
│   └── metrics/
│
├── logs/                         # Log files (gitignored)
│
├── build/                        # Build artifacts (gitignored)
│
├── archive/                      # Legacy code archive
│   └── legacy-phase-1/
│       ├── phase-1-scripts/
│       ├── phase-1-analysis/
│       └── README.md
│
├── Makefile                      # Build commands
├── docker-compose.yml            # Dev environment
├── docker-compose.prod.yml       # Prod environment
├── nginx.conf                    # API Gateway config
├── pytest.ini                    # Test configuration
├── .env.example                  # Environment template
├── .gitignore                    # Git ignore rules
├── .pre-commit-config.yaml       # Pre-commit hooks
├── README.md                     # Main project README
├── CONTRIBUTING.md               # Contribution guidelines
├── LICENSE                       # License
└── Langchain Bot.code-workspace  # VS Code workspace (updated)
```

---

## PHASE 3: DOCUMENTATION MODERNIZATION (Week 1)

### 3.1 Create v2.0 Architecture Documentation

**File**: `docs/architecture/microservices.md`

```markdown
# StrategyOps v2.0 Microservices Architecture

## Overview
- 6 independent microservices
- Event-driven workflow pipeline
- Session-aware parameter application
- Docker containerization with Kubernetes-ready design

## Services

### 1. Discovery Service (Port 8001)
- Vectorbt-based strategy discovery
- Per-symbol, per-session indicator analysis
- Outputs: list of viable indicators

### 2. Optimization Service (Port 8002)
- Optuna-based parameter tuning
- Input: discovered indicators from Discovery Service
- Outputs: optimized parameter sets per session

### 3. Validation Service (Port 8003)
- Walk-forward validation
- Profit factor comparison against baseline
- Approval/rejection decision

### 4. Deployment Service (Port 8004)
- Strategy deployment management
- Paper trading mode support
- Live deployment orchestration

### 5. Orchestration Service (Port 8005)
- Workflow coordination
- Job dependency management
- Multi-stage pipeline execution

### 6. Execution Service (Port 8006)
- Real-time trade execution
- MT5 API integration
- Order management and monitoring

## Data Flow Pipeline

Discovery → Optimization → Validation → Deployment → Execution

## Session-Aware Processing
All services understand session context (London, Tokyo, New York, etc.)
```

### 3.2 Create API Documentation

**Files**: `docs/api/*.md`

Each service gets a comprehensive API doc with:
- Endpoints
- Request/response schemas
- Error codes
- Example requests/responses
- Rate limits
- Authentication (if applicable)

### 3.3 Update Guides

**Files**: `docs/guides/*.md`

1. **getting-started.md** - New developer onboarding
2. **development.md** - Development workflow, architecture decisions
3. **testing.md** - How to write and run tests
4. **deployment.md** - How to deploy to staging/production
5. **troubleshooting.md** - Common issues and solutions

### 3.4 Create README

**File**: `README.md`

Professional project README with:
- Project description
- Quick start (5 min)
- Architecture overview
- Links to detailed docs
- Contributing guidelines
- Support/contact information

---

## PHASE 4: TEST SUITE STANDARDIZATION (Week 1-2)

### 4.1 Unified Test Structure

**Location**: `tests/`

```
tests/
├── conftest.py                   # Shared pytest fixtures
├── requirements.txt              # Test dependencies
│
├── unit/                         # Unit tests (fast)
│   ├── services/
│   │   ├── test_discovery_service.py
│   │   ├── test_optimization_service.py
│   │   ├── test_validation_service.py
│   │   ├── test_deployment_service.py
│   │   ├── test_orchestration_service.py
│   │   └── test_execution_service.py
│   ├── models/
│   │   └── test_shared_models.py
│   └── utils/
│       └── test_utilities.py
│
├── integration/                  # Integration tests (medium speed)
│   ├── test_discovery_optimization.py
│   ├── test_optimization_validation.py
│   ├── test_deployment_execution.py
│   ├── test_full_pipeline.py
│   └── test_error_handling.py
│
├── performance/                  # Performance tests (slower)
│   ├── test_load.py
│   ├── test_resilience.py
│   ├── test_throughput.py
│   └── test_memory_usage.py
│
├── e2e/                          # End-to-end tests (full workflow)
│   ├── test_workflow_btcusd.py
│   ├── test_workflow_eurusd.py
│   ├── test_workflow_multi_session.py
│   └── test_workflow_error_recovery.py
│
└── fixtures/                     # Test data and fixtures
    ├── market_data.json
    ├── strategy_configs.json
    └── expected_results.json
```

### 4.2 Test Configuration

**File**: `pytest.ini`

```ini
[pytest]
minversion = 7.0
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    unit: Unit tests
    integration: Integration tests
    performance: Performance tests
    e2e: End-to-end tests
    slow: Slow running tests
    requires_docker: Tests requiring Docker
addopts = 
    -v
    --strict-markers
    --tb=short
    --cov=services
    --cov=shared
    --cov-report=html:reports/coverage
```

### 4.3 GitHub Actions CI/CD

**File**: `.github/workflows/test.yml`

```yaml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11']
    
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install dependencies
        run: |
          pip install -r tests/requirements.txt
      - name: Run unit tests
        run: pytest tests/unit -v
      - name: Run integration tests
        run: pytest tests/integration -v
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

---

## PHASE 5: DEVELOPMENT ENVIRONMENT SETUP (Week 2)

### 5.1 VS Code Workspace Configuration

**File**: `Langchain Bot.code-workspace` (Updated)

```json
{
  "folders": [
    {
      "path": ".",
      "name": "StrategyOps v2.0"
    },
    {
      "path": "services/discovery-service",
      "name": "Discovery Service"
    },
    {
      "path": "services/optimization-service",
      "name": "Optimization Service"
    },
    {
      "path": "services/validation-service",
      "name": "Validation Service"
    },
    {
      "path": "services/deployment-service",
      "name": "Deployment Service"
    },
    {
      "path": "services/orchestration-service",
      "name": "Orchestration Service"
    },
    {
      "path": "services/execution-service",
      "name": "Execution Service"
    }
  ],
  "settings": {
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true,
    "python.formatting.provider": "black",
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests"],
    "files.exclude": {
      "**/__pycache__": true,
      "**/*.pyc": true,
      "archive/**": true,
      ".pytest_cache": true
    },
    "[python]": {
      "editor.formatOnSave": true,
      "editor.defaultFormatter": "ms-python.python"
    }
  },
  "extensions": {
    "recommendations": [
      "ms-python.python",
      "ms-python.vscode-pylance",
      "ms-vscode.makefile-tools",
      "ms-azuretools.vscode-docker",
      "eamodio.gitlens"
    ]
  }
}
```

### 5.2 Makefile for Common Tasks

**File**: `Makefile`

```makefile
.PHONY: help setup dev prod test lint format clean docker-build docker-up docker-down

help:
	@echo "StrategyOps v2.0 - Available commands:"
	@echo "  make setup       - Initial setup (one-time)"
	@echo "  make dev         - Start development environment"
	@echo "  make prod        - Start production environment"
	@echo "  make test        - Run all tests"
	@echo "  make test-unit   - Run unit tests only"
	@echo "  make test-e2e    - Run end-to-end tests"
	@echo "  make lint        - Run code linter"
	@echo "  make format      - Auto-format code"
	@echo "  make clean       - Clean build artifacts"
	@echo "  make docker-build - Build Docker images"
	@echo "  make docker-up   - Start Docker containers"
	@echo "  make docker-down - Stop Docker containers"

setup:
	pip install -r requirements.txt
	pip install -r tests/requirements.txt
	docker compose build

dev:
	docker compose up -d

prod:
	docker compose -f docker-compose.prod.yml up -d

test:
	pytest tests/ -v

test-unit:
	pytest tests/unit -v

test-e2e:
	pytest tests/e2e -v

lint:
	pylint services/ shared/
	flake8 services/ shared/

format:
	black services/ shared/ tests/
	isort services/ shared/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf build/ dist/ .pytest_cache/ reports/

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down
```

---

## PHASE 6: PRODUCTION READINESS (Week 2-3)

### 6.1 Deployment Pipeline

**Stages**:
1. **Local Development** → `make dev`
2. **Local Testing** → `make test`
3. **Staging Deployment** → Manual PR approval
4. **Production Deployment** → Automated after staging validation

### 6.2 Health Checks & Monitoring

**File**: `scripts/ops/health-check.sh`

```bash
#!/bin/bash

echo "Checking service health..."

services=(
  "discovery-service:8001"
  "optimization-service:8002"
  "validation-service:8003"
  "deployment-service:8004"
  "orchestration-service:8005"
  "execution-service:8006"
)

for service in "${services[@]}"; do
  host="${service%:*}"
  port="${service#*:}"
  
  if curl -s "http://localhost:$port/health" > /dev/null; then
    echo "✅ $host ($port) - Healthy"
  else
    echo "❌ $host ($port) - Unhealthy"
    exit 1
  fi
done

echo "All services healthy!"
```

### 6.3 Logging & Observability

**File**: `config/logging.yaml`

```yaml
version: 1
disable_existing_loggers: false

formatters:
  standard:
    format: '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
  json:
    class: pythonjsonlogger.jsonlogger.JsonFormatter
    format: '%(timestamp)s %(level)s %(message)s'

handlers:
  console:
    class: logging.StreamHandler
    level: INFO
    formatter: standard
  
  file:
    class: logging.handlers.RotatingFileHandler
    filename: logs/strategyops.log
    maxBytes: 10485760  # 10MB
    backupCount: 10
    formatter: json

root:
  level: INFO
  handlers: [console, file]
```

---

## CLEANUP ACTION PLAN

### Week 1: Workspace Cleanup (3 days)

```
Day 1:
□ Archive 50+ legacy Python scripts
□ Delete outdated documentation files
□ Create clean directory structure

Day 2:
□ Move test files to unified tests/ directory
□ Organize documentation
□ Create Makefile

Day 3:
□ Update VS Code workspace configuration
□ Create .gitignore rules
□ Verify all services still run
```

### Week 1: Documentation (2 days)

```
Day 4:
□ Write architecture documentation
□ Create API documentation templates
□ Write development guides

Day 5:
□ Create comprehensive README.md
□ Write contributing guidelines
□ Create troubleshooting guide
```

### Week 2: Testing & CI/CD (3 days)

```
Day 6:
□ Reorganize test suite
□ Create pytest configuration
□ Write unit tests for each service

Day 7:
□ Write integration tests
□ Set up GitHub Actions workflows
□ Configure code coverage

Day 8:
□ Write performance tests
□ Create E2E test scenarios
□ Test all CI/CD pipelines
```

### Week 2: Environment & Docs (2 days)

```
Day 9:
□ Configure VS Code workspace
□ Create Makefile with all commands
□ Document development workflow

Day 10:
□ Create deployment documentation
□ Write monitoring & logging guide
□ Create operational runbooks
```

---

## SUCCESS CRITERIA

### Clean Workspace ✅
- [ ] Root directory has <20 files
- [ ] All legacy code archived
- [ ] Clear structure for new developers
- [ ] Professional VS Code workspace

### Comprehensive Documentation ✅
- [ ] Architecture docs complete
- [ ] API docs for all 6 services
- [ ] Development guides written
- [ ] Deployment procedures documented
- [ ] Troubleshooting guide complete

### Production-Ready Testing ✅
- [ ] Unit test coverage >80%
- [ ] Integration tests for all workflows
- [ ] Performance baselines established
- [ ] E2E tests for critical paths
- [ ] CI/CD pipelines automated
- [ ] All tests passing in CI/CD

### Development Environment ✅
- [ ] VS Code workspace optimized
- [ ] Makefile with all common commands
- [ ] Local dev environment setup documented
- [ ] Pre-commit hooks configured
- [ ] Code formatting standardized

---

## NEXT STEPS AFTER CLEANUP

### Phase 7: Advanced Features (Week 3+)
- [ ] Service mesh (Istio)
- [ ] Advanced monitoring (Prometheus/Grafana)
- [ ] Distributed tracing (Jaeger)
- [ ] Database persistence layer
- [ ] Message queue (RabbitMQ/Kafka)
- [ ] Advanced caching (Redis)

### Phase 8: Production Hardening (Week 4+)
- [ ] Security audit
- [ ] Rate limiting & DDoS protection
- [ ] Backup & disaster recovery procedures
- [ ] Load balancing strategy
- [ ] Auto-scaling configuration
- [ ] Security scanning in CI/CD

### Phase 9: Team Enablement (Week 5+)
- [ ] Team onboarding documentation
- [ ] Code review guidelines
- [ ] Architecture decision records (ADRs)
- [ ] Performance tuning guide
- [ ] Incident response procedures
- [ ] Post-mortem templates

---

## ESTIMATED EFFORT

| Phase | Duration | Effort |
|-------|----------|--------|
| Workspace Cleanup | 3 days | 24 hours |
| Documentation | 5 days | 40 hours |
| Test Suite | 3 days | 24 hours |
| CI/CD Setup | 2 days | 16 hours |
| Environment Setup | 2 days | 16 hours |
| **Total** | **~2 weeks** | **~120 hours** |

---

## RISKS & MITIGATION

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Breaking running services | HIGH | Work in clean branch, verify locally first |
| Legacy code needed later | MEDIUM | Archive, don't delete; keep in git history |
| Documentation becomes outdated | MEDIUM | Enforce docs-in-code, review in PRs |
| Test suite becomes bloated | MEDIUM | Strict test organization, clear guidelines |
| Team can't use new setup | HIGH | Comprehensive onboarding docs + training |

---

## TRANSITION PLAN

### Before Cleanup
1. Create `cleanup` branch
2. Tag current commit as `pre-cleanup-v2.0`
3. Document any edge cases

### During Cleanup
1. Work on cleanup branch
2. Test frequently
3. Keep main branch stable

### After Cleanup
1. Comprehensive testing on cleanup branch
2. Code review of all changes
3. Merge to main
4. Tag as `v2.0-clean`

---

## TEAM COMMUNICATION

**Announcement**: "We're modernizing our development environment to match our professional microservices architecture. This will streamline development, improve documentation, and enable better team collaboration."

**Impact**:
- Cleaner, easier-to-navigate codebase
- Better IDE support with organized workspace
- Comprehensive documentation
- Automated testing pipeline
- Professional development workflow

**Timeline**: 2 weeks, with main branch stable throughout

---

**Status**: Ready for approval and execution  
**Next Step**: Begin Phase 2 workspace cleanup

