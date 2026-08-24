# Cleanup Plan: Remove Old Code, Keep Pipeline Only

**Date**: 2026-08-24  
**Goal**: Remove everything that doesn't contribute to vectorbt→optuna→validation pipeline

---

## KEEP (Core Pipeline)

### Source Code
```
src/
├── learning/
│   ├── param_optimizer.py                    ✅ KEEP - Core Optuna integration
│   ├── vectorbt_optimizer.py                 ✅ KEEP - Discovery phase
│   ├── vectorbt_backtester.py                ✅ KEEP - Backtest engine
│   ├── change_validator.py                   ✅ KEEP - Validation gate
│   ├── adaptive_loop.py                      ✅ KEEP - Learning orchestration
│   ├── entry_strength.py                     ✅ KEEP - Entry floor discovery
│   ├── experience_db.py                      ✅ KEEP - Trade persistence
│   └── [other learning modules]              ⚠️ REVIEW - Keep if used by above
│
├── trading/
│   ├── scalp_engine.py                       ✅ KEEP - Live trading
│   └── [trading modules]                     ⚠️ REVIEW - Keep if used by pipeline
│
├── dashboard/
│   ├── optimization_api_endpoints.py         ✅ KEEP - API for phases
│   ├── optimization_results_component.py     ✅ KEEP - Result structures
│   └── routes_v2.py                          ✅ KEEP - Dashboard routes
│
├── ui/
│   ├── backend.py                            ✅ KEEP - Flask app
│   └── App.jsx                               ✅ KEEP - Frontend
│
├── data_acquisition/                         ✅ KEEP - Historical data needed
├── mt5/                                      ✅ KEEP - MT5 integration needed
└── utils/                                    ✅ KEEP - Logger, helpers

❌ DELETE:
├── agents/                                   - Old research agents
├── core/                                     - Experimental framework
├── orchestration/                            - Old orchestration
├── research_agent.py, environment_setup_agent.py, etc. - Unused agents
```

### Tests
```
tests/
├── test_change_validator.py                  ✅ KEEP
├── test_directed_optimizer.py                ✅ KEEP
├── test_edge_discovery.py                    ✅ KEEP
├── test_dashboard_api_v2.py                  ✅ KEEP
├── test_dashboard_integration.py             ✅ KEEP
├── test_entry_strength.py                    ✅ KEEP
├── test_closed_loop.py                       ✅ KEEP
├── test_focused_optimizer_alignment.py       ✅ KEEP
├── conftest.py                               ✅ KEEP
└── [other tests related to pipeline]         ✅ KEEP

❌ DELETE:
├── test_research_*.py                        - Old research tests
├── test_agent_*.py                           - Old agent tests
├── test_experimental_*.py                    - Experimental tests
└── [tests for deleted modules]
```

### Documentation
```
KEEP:
├── CODE_REVIEW_VECTORBT_OPTUNA_PIPELINE.md   ✅ KEEP
├── TEST_HARNESS_DOCUMENTATION.md             ✅ KEEP
├── SESSION_LOG_2026_08_24.md                 ✅ KEEP
├── DOCUMENTATION_INDEX.md                    ✅ KEEP
├── README.md                                 ✅ KEEP (if exists and relevant)
├── WORKSPACE_RULES.md                        ✅ KEEP
├── RULES.md                                  ✅ KEEP
└── Architecture docs related to trading      ✅ KEEP

❌ DELETE:
├── OPTIMIZATION_DASHBOARD_*.md               - Old dashboard attempts
├── END_TO_END_*.md                           - Duplicate documentation
├── FEEDBACK_LOOP_ARCHITECTURE.md             - Superseded by review
├── VECTORBT_OPTUNA_RESEARCH.md               - Old research notes
├── OPTUNA_*.md                               - Old optuna docs
├── COMPLETE_END_TO_END_SUMMARY.md            - Duplicate
├── PF_ANALYSIS_*.md                          - Old analysis
├── QMMP_*.md                                 - Old pipeline docs
└── [all other old documentation]
```

### Data
```
data/
├── tuned_params.json                         ✅ KEEP - Live params
├── trading_experience.db                     ✅ KEEP - Trade history
└── [active trading data]                     ✅ KEEP

❌ DELETE:
├── backups/                                  - Clean if > 30 days old
├── archives/                                 - Clean if > 90 days old
├── old_results/                              - Delete
└── [stale data files]
```

### Configuration
```
.github/
├── workflows/ci.yml                          ✅ KEEP
├── workflows/nightly.yml                     ⚠️ CREATE - For pipeline scheduling

.kilo/                                        ✅ KEEP - Kilo configuration
ci_templates/                                 ✅ KEEP - CI templates
.gitignore                                    ✅ KEEP
README.md                                     ✅ KEEP

❌ DELETE:
├── Old workflow files                        - If obsolete
└── Experimental config files
```

### Scripts
```
scripts/
├── nightly_orchestrator.py                   ⚠️ CREATE - Need this!
├── profile_vectorbt_optuna.py                ✅ KEEP - Performance profiling
└── [other pipeline utilities]                ✅ KEEP

❌ DELETE:
├── Old experiment scripts
├── Old research scripts
└── [non-pipeline utilities]
```

---

## DELETE (Old Code)

### High Priority (100+ lines each)
- `src/agents/` - All old research agents
- `src/core/` - Experimental framework
- `src/orchestration/` - Old orchestration
- `dashboard/` - Old dashboard attempts
- `dashboard-frontend/` - Old frontend
- `litellm_providers/` - External provider code
- `review/` - Old review files
- `claude_reviews/` - Old review archives
- `examples/` - Old example code
- `docs/` - Old documentation (unless architecture-critical)

### Medium Priority (stale documentation)
- All `OPTIMIZATION_DASHBOARD_*.md` files (7 files)
- All `END_TO_END_*.md` files (duplicates)
- All `OPTUNA_*.md` files (old docs)
- All `FEEDBACK_LOOP_*.md` files (superseded)
- All `PF_ANALYSIS_*.md` files (research, not pipeline)
- All `QMMP_*.md` files (old pipeline docs)
- All `COMPLETE_*.md` files (duplicates)

### Low Priority (housekeeping)
- `__pycache__/` - Python cache
- `.pytest_cache/` - Test cache
- `logs/` - Rotate old logs (keep current)
- `venv/` - Virtual environment (don't delete, just ignore)

---

## Specific Files to Delete

### Documentation Files (COUNT: 50+)
```
OPTIMIZATION_DASHBOARD_COMPLETE.md
OPTIMIZATION_DASHBOARD_COMPLETE_IMPLEMENTATION.md
OPTIMIZATION_DASHBOARD_QUICKREF.md
OPTIMIZATION_DASHBOARD_ARCHITECTURE.md
DEPLOYMENT_GUIDE_OPTIMIZATION_DASHBOARD.md
DEPLOYMENT_REPORT_2026_08_24.md
END_TO_END_PIPELINE_DESIGN.md
END_TO_END_TESTING_GUIDE.md
COMPLETE_END_TO_END_SUMMARY.md
QUICK_REFERENCE.md
FEEDBACK_LOOP_ARCHITECTURE.md
VECTORBT_OPTUNA_RESEARCH.md
OPTUNA_PROGRESS_REPORT.md
OPTUNA_INVESTIGATION.md
PF_ANALYSIS_*.md (7 files)
QMMP_*.md (6 files)
... and similar files
```

### Source Code Directories
```
src/agents/                  ❌ DELETE
src/core/                    ❌ DELETE
src/orchestration/           ❌ DELETE (orchestration logic moved to param_optimizer)
```

### Old Experiment/Example Code
```
examples/                    ❌ DELETE
dashboard/                   ❌ DELETE (old implementation)
dashboard-frontend/          ❌ DELETE (old implementation)
litellm_providers/           ❌ DELETE (not part of core)
tools/                       ⚠️ REVIEW
review/                      ❌ DELETE (old reviews)
claude_reviews/              ❌ DELETE (archive)
ci_templates/                ⚠️ REVIEW (keep if active)
```

---

## Cleanup Checklist

### STEP 1: Delete Old Documentation (50+ files)
- [ ] Delete all `OPTIMIZATION_DASHBOARD_*.md`
- [ ] Delete all `END_TO_END_*.md`
- [ ] Delete all `FEEDBACK_LOOP_*.md`
- [ ] Delete all `OPTUNA_*.md`
- [ ] Delete all `PF_ANALYSIS_*.md`
- [ ] Delete all `QMMP_*.md`
- [ ] Delete all `COMPLETE_*.md`
- [ ] Delete `QUICK_REFERENCE.md`
- [ ] Delete `VECTORBT_OPTUNA_RESEARCH.md`

### STEP 2: Delete Old Source Code Directories
- [ ] Delete `src/agents/`
- [ ] Delete `src/core/`
- [ ] Delete `src/orchestration/`
- [ ] Delete `examples/`
- [ ] Delete `dashboard/` (old implementation)
- [ ] Delete `dashboard-frontend/` (old implementation)
- [ ] Delete `litellm_providers/`
- [ ] Delete `review/`
- [ ] Delete `claude_reviews/`

### STEP 3: Delete Old Tests
- [ ] Delete all `test_agent_*.py`
- [ ] Delete all `test_research_*.py`
- [ ] Delete all `test_experimental_*.py`
- [ ] Delete tests for deleted modules

### STEP 4: Clean Cache and Temp
- [ ] Delete `__pycache__/`
- [ ] Delete `.pytest_cache/`
- [ ] Clean old logs (> 30 days)
- [ ] Clean `data/backups/` (> 30 days)
- [ ] Clean `data/archives/` (> 90 days)

### STEP 5: Verify
- [ ] Run full test suite: `pytest tests/ -v`
- [ ] Check git status: `git status`
- [ ] Verify core files remain:
  - `src/learning/param_optimizer.py`
  - `src/dashboard/optimization_api_endpoints.py`
  - `tests/test_change_validator.py`
  - Documentation index files

### STEP 6: Commit
- [ ] `git add -A`
- [ ] `git commit -m "cleanup: remove old code, keep only vectorbt-optuna-validation pipeline"`
- [ ] `git push origin main`

---

## Expected Result

**Before Cleanup**: 335 commits, 50+ doc files, multiple old implementations, 20+ old tests  
**After Cleanup**: ~340 commits (10 new), 5-7 doc files (core only), 1 implementation, 20+ focused tests

**Clean Repository**:
- ✅ Single, focused implementation of vectorbt→optuna→validation
- ✅ Clear documentation (review + test harness + index)
- ✅ No duplicate code
- ✅ No orphaned tests
- ✅ No stale documentation confusing developers

**Size Reduction**: ~30-40% smaller repository

---

## Files to Preserve (Reference)

After cleanup, you'll have:

```
langchain/
├── .github/
│   └── workflows/ci.yml                      # CI pipeline
├── .kilo/                                    # Kilo config
├── src/
│   ├── learning/                             # Core pipeline
│   ├── trading/                              # Live trading
│   ├── dashboard/                            # API
│   ├── ui/                                   # Frontend
│   ├── data_acquisition/                     # Data source
│   ├── mt5/                                  # MT5 integration
│   └── utils/                                # Utilities
├── tests/                                    # Focused tests only
├── scripts/                                  # Utility scripts
├── data/                                     # Live data
├── logs/                                     # Runtime logs
│
├── CODE_REVIEW_VECTORBT_OPTUNA_PIPELINE.md  # Reference
├── TEST_HARNESS_DOCUMENTATION.md            # Reference
├── SESSION_LOG_2026_08_24.md                # Status
├── DOCUMENTATION_INDEX.md                   # Navigation
├── README.md                                # Project overview
├── WORKSPACE_RULES.md                       # Development rules
├── RULES.md                                 # Trading rules
└── requirements.txt                         # Dependencies
```

Total: Clean, focused, production-ready codebase for the pipeline.

---

## Ready to Proceed?

Confirm and I will:
1. Delete all files listed above
2. Clean cache/temp
3. Run tests to verify nothing broke
4. Commit cleanup
5. Verify git push succeeds

**Estimated time**: 5-10 minutes
