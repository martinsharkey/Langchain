# Test Execution Guide - Clean Workspace

**Goal**: Run tests without cluttering your workspace. All test artifacts go to `test-output/` folder.

---

## 🚀 Quick Start

### Run All Tests
```bash
python run_tests.py
```

### Run E2E Tests Only
```bash
python run_tests.py -m e2e
```

### Run with Verbose Output
```bash
python run_tests.py -v
```

### Run and Stop on First Failure
```bash
python run_tests.py -x
```

### Run in Parallel (Fast)
```bash
python run_tests.py -n
```

### Run Specific Test
```bash
python run_tests.py -k "test_discovery"
```

---

## 📁 Test Output Structure

All test artifacts are organized in `test-output/`:

```
test-output/
├── reports/
│   ├── index.html          ← Open this to see test results
│   ├── junit.xml           ← For CI/CD pipelines
│   └── summary.md          ← Text summary
└── coverage/
    └── html/
        ├── index.html      ← Open this to see coverage details
        └── ...
```

**Your workspace stays clean!** ✨

---

## 📊 Available Test Markers

Run tests by category:

```bash
# E2E tests (complete pipeline)
python run_tests.py -m e2e

# Unit tests (fast, isolated)
python run_tests.py -m unit

# Integration tests (service interaction)
python run_tests.py -m integration

# Performance tests (benchmarks)
python run_tests.py -m performance

# Database tests (requires DB)
python run_tests.py -m database

# Live tests (requires MT5)
python run_tests.py -m live
```

---

## 🧹 Cleanup

### Remove all test output
```bash
rm -r test-output
```

### Keep only latest results
```bash
# Delete test outputs older than 7 days
find test-output -mtime +7 -delete
```

---

## 🔧 Advanced Options

```bash
# Show 20 slowest tests
python run_tests.py -d 20

# Run specific test file
python run_tests.py tests/e2e/test_complete_pipeline.py

# Run tests matching multiple keywords
python run_tests.py -k "test_discovery or test_optimization"

# Combine options
python run_tests.py -m e2e -v -n -d 5
```

---

## 📋 What Gets Generated

### reports/index.html
- Interactive test results
- Passed/failed/skipped counts
- Individual test details
- Execution times

### coverage/html/index.html
- Code coverage details
- Line coverage percentages
- Branch coverage
- Coverage trends

### reports/junit.xml
- Machine-readable test results
- Used by CI/CD systems (GitHub Actions, etc.)
- Can be parsed by other tools

---

## ✅ Configuration

All test output settings are in `pytest.ini`:

```ini
--cov-report=html:test-output/coverage/html
--html=test-output/reports/index.html
--junit-xml=test-output/reports/junit.xml
```

**No workspace pollution!** All artifacts contained in `test-output/`

---

## 🎯 Best Practice Workflow

1. **Run tests locally** → `python run_tests.py`
2. **View results** → Open `test-output/reports/index.html`
3. **Check coverage** → Open `test-output/coverage/html/index.html`
4. **On CI/CD** → Uses `test-output/reports/junit.xml`

Your workspace stays clean throughout! ✨

---

## 📝 Notes

- `.gitignore` is configured to skip `test-output/`
- Test outputs are NOT committed to git
- Safe to delete `test-output/` anytime (auto-recreates on next test run)
- `.pytest_cache/` and `.coverage` files also go to appropriate locations

---

**Next**: Use `python run_tests.py` for all test execution with organized outputs!
