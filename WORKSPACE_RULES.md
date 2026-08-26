# 🚫 WORKSPACE_RULES.md - STRICT FILE PLACEMENT ENFORCEMENT

**Status**: ENFORCED  
**Version**: 1.0  
**Last Updated**: August 25, 2026  

---

## ⚠️ CRITICAL: READ BEFORE COMMITTING

This workspace has STRICT rules about file placement. Violating these rules will:
1. ❌ Be rejected by pre-commit hooks
2. ❌ Block pull request merging
3. ❌ Trigger CI/CD pipeline failure
4. ❌ Result in commit rejection

---

## 📋 ALLOWED FILES AT ROOT (14 ONLY)

### Essential Configuration (DO NOT MOVE)
```
.env                              ✅ Environment variables (gitignored)
.env.example                      ✅ Environment template
.gitignore                        ✅ Git ignore rules
.pre-commit-config.yaml           ✅ Git hooks configuration
pytest.ini                        ✅ Testing configuration
```

### Build & Project Configuration (DO NOT MOVE)
```
Makefile                          ✅ Development commands
pyproject.toml                    ✅ Python project metadata
requirements.txt                  ✅ Main dependencies
requirements-dev.txt              ✅ Development dependencies
```

### VS Code & IDE Configuration (DO NOT MOVE)
```
langchain-workspace.code-workspace ✅ VS Code workspace config
.flake8                           ✅ Linting configuration
```

### Documentation Entry Points (DO NOT MOVE)
```
README.md                         ✅ Project overview
WORKSPACE_RULES.md               ✅ THIS FILE - Strict rules
```

**Total**: 14 files ONLY. Nothing else at root level.

---

## 🚫 FORBIDDEN AT ROOT

### ❌ Python Scripts
```
❌ shared_models.py               → MUST BE: src/core/models.py
❌ *.py files                     → MUST BE: In src/ or services/
❌ test_*.py files               → MUST BE: In tests/
❌ analyze_*.py                  → MUST BE: In tools/ or scripts/
```

### ❌ Data & Configuration Files
```
❌ *.json (except package.json)  → MUST BE: In appropriate module
❌ *.sql                         → MUST BE: In infrastructure/db/
❌ *.csv                         → MUST BE: In data/
❌ config-*.yml                  → MUST BE: In infrastructure/
```

### ❌ Screenshots & Images
```
❌ *.png                         → MUST BE: In docs/images/
❌ *.jpg                         → MUST BE: In docs/images/
❌ *.gif                         → MUST BE: In docs/images/
❌ *.svg                         → MUST BE: In architecture/diagrams/
```

### ❌ Test & Analysis Files
```
❌ test_*.py                     → MUST BE: In tests/
❌ debug_*.py                    → MUST BE: In tools/debug/
❌ analyze_*.py                  → MUST BE: In tools/analysis/
❌ *_test.py                     → MUST BE: In tests/
```

### ❌ Personal Notes & Logs
```
❌ LEARNING_LOG.md               → MUST BE: In docs/learning/ or archive/
❌ SESSION_*.md                  → MUST BE: In docs/sessions/ or archive/
❌ *.log files                   → MUST BE: In logs/
❌ trace_*.py                    → MUST BE: In tools/debug/
```

---

## 📁 PROPER FILE PLACEMENT GUIDE

### src/ - Core Application Code
```
src/
├── __init__.py
├── core/                         # Core shared code
│   ├── __init__.py
│   ├── models.py                 # ✅ Moved from root
│   ├── schemas.py
│   └── __lld__.md                # LOW LEVEL DESIGN
│
├── config/                       # Configuration
│   ├── __init__.py
│   ├── settings.py
│   └── __lld__.md
│
├── integrations/                 # External integrations
│   ├── __init__.py
│   ├── mt5/
│   ├── database/
│   └── __lld__.md
│
└── utils/                        # Utilities
    ├── __init__.py
    ├── logging.py
    └── __lld__.md

RULE: All shared code in src/
```

### services/ - Microservices
```
services/
├── discovery-service/
│   ├── app/                      # API layer
│   │   ├── main.py
│   │   ├── api/
│   │   └── __lld__.md
│   ├── core/                     # Business logic
│   │   ├── discovery_engine.py
│   │   └── __lld__.md
│   ├── models/                   # Data models
│   │   └── __lld__.md
│   ├── tests/
│   ├── __lld__.md                # SERVICE DESIGN
│   ├── API_SPEC.md               # SERVICE API
│   ├── Dockerfile
│   └── requirements.txt
│
└── [other services...]

RULE: Each service self-contained with __lld__.md
```

### tests/ - Test Suite
```
tests/
├── unit/                         # ✅ Unit tests here
├── integration/                  # ✅ Integration tests here
├── e2e/                         # ✅ E2E tests here
├── performance/                 # ✅ Performance tests here
└── conftest.py

RULE: ALL tests in tests/ directory
```

### docs/ - Documentation
```
docs/
├── ARCHITECTURE.md
├── API.md
├── DEVELOPMENT_GUIDE.md
├── images/                       # ✅ All images here
│   ├── screenshots/
│   └── diagrams/
├── learning/                     # ✅ Learning logs here
│   └── LEARNING_LOG.md
└── sessions/                     # ✅ Session notes here

RULE: All documentation organized in docs/
```

### tools/ - Development Utilities
```
tools/
├── debug/                        # ✅ Debug scripts
│   ├── debug_discovery.py
│   └── trace_analyzer.py
├── analysis/                     # ✅ Analysis scripts
│   ├── analyze_performance.py
│   └── analyze_indicators.py
├── scripts/                      # ✅ Utility scripts
│   ├── reproduce_issue.py
│   └── test_reproduction.py
└── __init__.py

RULE: All dev tools in tools/
```

### architecture/ - System Design
```
architecture/
├── ADRs/                         # Architecture Decision Records
│   ├── ADR-001-*.md
│   └── ADR-*.md
├── HLD/                          # High Level Design
│   ├── HLD.md
│   ├── diagrams/
│   └── data-architecture.md
├── Module-Specs/                 # Module specifications
│   ├── discovery-service.md
│   └── ...
└── Standards/                    # Technical standards
    ├── coding-standards.md
    ├── api-standards.md
    └── deployment-standards.md

RULE: ALL architectural docs here
```

### infrastructure/ - Deployment Configs
```
infrastructure/
├── docker-compose.yml
├── docker-compose-prod.yml
├── nginx.conf
├── prometheus.yml
├── alerts.yml
├── db/
│   └── init-db.sql
└── k8s/
    └── *.yaml

RULE: NO Python scripts here
```

---

## 🔐 LOCKED DIRECTORIES (PROTECTED)

These directories have strict governance:

### ✅ src/ (Protected)
- **Rule**: Only organized Python modules
- **Allowed**: Organized Python code, __init__.py, __lld__.md
- **Forbidden**: Random scripts, data files, images

### ✅ services/ (Protected)
- **Rule**: Only microservices with standard structure
- **Allowed**: service-name/ with app/, core/, models/, tests/
- **Forbidden**: Random files, legacy code

### ✅ tests/ (Protected)
- **Rule**: Only test files and conftest.py
- **Allowed**: test_*.py, conftest.py, fixtures
- **Forbidden**: Production code, scripts

### ✅ docs/ (Protected)
- **Rule**: Only documentation and images
- **Allowed**: *.md files, images/, diagrams/
- **Forbidden**: Source code, random files

### ✅ architecture/ (Protected)
- **Rule**: Only system design and architecture
- **Allowed**: ADRs, HLD, specifications, standards
- **Forbidden**: Source code, temporary files

---

## 🛡️ ENFORCEMENT MECHANISMS

### Pre-commit Hooks
```bash
make setup-pre-commit
```
These hooks check:
- ✅ No rogue files at root
- ✅ Proper file extensions in directories
- ✅ Proper module structure
- ✅ Forbidden file patterns

### CI/CD Validation
Every commit triggers:
- ✅ File placement validation
- ✅ Module structure validation
- ✅ Forbidden pattern detection
- ✅ Directory rule enforcement

### Automated Blocking
```
FORBIDDEN at root:
  ❌ *.py (except listed)
  ❌ *.json (except config)
  ❌ *.png, *.jpg
  ❌ *.log
  
RESULT: Pre-commit hook FAILS → Commit REJECTED
```

---

## 📋 CHECKLIST BEFORE COMMITTING

Before you commit, ask yourself:

### ✅ File Placement
- [ ] Are all Python files in src/ or services/ or tests/?
- [ ] Are all images in docs/images/?
- [ ] Are all tools in tools/?
- [ ] Are all tests in tests/?
- [ ] Is root directory still 14 files only?

### ✅ Module Structure
- [ ] Does my module have __init__.py?
- [ ] Does my module have __lld__.md?
- [ ] Are imports organized properly?
- [ ] Are tests in tests/ directory?

### ✅ Documentation
- [ ] Did I update __lld__.md for my module?
- [ ] Did I update API documentation if needed?
- [ ] Did I add images to docs/images/?
- [ ] Did I update CONTRIBUTING.md if needed?

### ✅ Standards Compliance
- [ ] Does my code follow coding standards?
- [ ] Are type hints present?
- [ ] Is documentation complete?
- [ ] Are tests passing?

---

## 🚨 VIOLATIONS & PENALTIES

### Violation Examples

**Example 1: Python file at root**
```
❌ my_script.py at root
✅ Correct: tools/analysis/my_script.py
PENALTY: Commit rejected by pre-commit hook
```

**Example 2: Screenshot at root**
```
❌ screenshot.png at root
✅ Correct: docs/images/screenshots/screenshot.png
PENALTY: Commit rejected by pre-commit hook
```

**Example 3: Test data at root**
```
❌ test_data.json at root
✅ Correct: tests/fixtures/data/test_data.json
PENALTY: Commit rejected by pre-commit hook
```

---

## 📚 NEW DEVELOPER ONBOARDING

### Step 1: Read This File
Before you make ANY changes, read this entire file.

### Step 2: Understand File Placement
Learn where your changes should go.

### Step 3: Install Pre-commit Hooks
```bash
make setup-pre-commit
```

### Step 4: Ask Before Committing
If unsure, check the mapping in this file.

### Step 5: Let Hooks Validate
Pre-commit hooks will guide you.

---

## ✅ QUESTIONS? REFER HERE

**"Where do I put my Python script?"**
→ tools/analysis/ (if analysis) or tools/debug/ (if debug)

**"Where do I put test data?"**
→ tests/fixtures/ or tests/data/

**"Where do I put screenshots?"**
→ docs/images/

**"Where do I put my module code?"**
→ src/ (shared) or services/service-name/ (service-specific)

**"Where do I put database scripts?"**
→ infrastructure/db/

**"Where do I put my notes?"**
→ docs/learning/ or archive/ (never at root)

---

## 🎯 GOAL

**Result**: A workspace where:
- ✅ New developers CANNOT mess up file placement
- ✅ Every file has a clear, logical location
- ✅ Pre-commit hooks enforce discipline
- ✅ CI/CD pipeline validates structure
- ✅ The system remains professional and organized

---

**Status**: ENFORCED  
**Violations**: AUTOMATICALLY REJECTED  
**Questions**: Ask tech lead or check this file

🚫 **YOUR COMMIT WILL BE REJECTED IF IT VIOLATES THESE RULES** 🚫
