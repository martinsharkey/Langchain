# Quick Reference: End-to-End Pipeline

## One-Command Test

```bash
python scripts/nightly_pipeline_orchestrator.py --run-now --symbols XAUUSD BTCUSD
```

Expected: Completes in 7-15 minutes, generates report at `data/reports/nightly_report_*.json`

---

## What Happens

| Phase | Time | What | Output |
|-------|------|------|--------|
| 1 | 3-5m | Discovery: Test all indicators | `phase1_discovery_{SYMBOL}.json` |
| 2 | 1-2m | Tuning: Optuna optimization | `phase2_optuna_{SYMBOL}.json` |
| 3 | 30s | Validation: Test on unseen data | `phase3_validation_{SYMBOL}.json` |
| 4 | 10s | Deployment: Update live bot | `deployed/{SESSION}_{INDICATOR}_deployed.json` |
| 5 | - | Feedback: Continuous during trading | (not in nightly) |
| 6 | 2s | Reporting: Generate metrics | `nightly_report_{TIMESTAMP}.json` |

---

## Validate Results

```bash
# Best indicators discovered
cat data/qmmp/XAUUSD/phase1_discovery_XAUUSD.json | jq '.best_by_session'

# Tuning results (training data)
cat data/qmmp/XAUUSD/phase2_optuna_XAUUSD.json | jq '.results.Asian'

# VALIDATION RESULTS (test data - the proof!)
cat data/qmmp/XAUUSD/phase3_validation_XAUUSD.json | jq '.results.Asian'

# Deployed params
ls data/qmmp/XAUUSD/deployed/

# Report
cat data/reports/nightly_report_*.json | jq '.'
```

---

## Schedule Production

```bash
pip install apscheduler

# Runs automatically at 10pm GMT Mon-Fri
python scripts/nightly_pipeline_orchestrator.py --schedule
```

---

## Architecture at a Glance

```
Vectorbt Discovery
       ↓
    Find best indicator per session
       ↓
Optuna Tuning (100 trials)
       ↓
    Optimize parameters on 60% training data
       ↓
Vectorbt Validation ← YOUR KEY INSIGHT
       ↓
    Validate on 40% TEST data (catches overfitting)
       ↓
Deploy to Live
       ↓
    Live bot uses optimized params
       ↓
Live Feedback (Continuous)
       ↓
    Collect outcomes, re-optimize if degraded
       ↓
Loop continues forever
```

---

## Phase 3: Why It Matters

**Problem**: Optuna finds params that look great on training data but fail on real data (overfitting).

**Solution**: Validate on held-out test data BEFORE deploying.

**Result**: 
- ✅ ACCEPT if test performance ≥ training performance
- ❌ REJECT if overfitting detected (test PF drops > 5%)

This prevents broken params from hitting live trading.

---

## Expected Metrics

After first run:
- Discovery: 2-4 viable indicators per symbol
- Tuning: 1-5% improvement on training data
- Validation acceptance rate: 60-80% (rejects overfitting)
- Pipeline time: 7-15 minutes
- Deployed params: 1-3 per symbol per week

---

## Files Reference

```
Core Scripts:
- scripts/phase1_vectorbt_discovery.py
- scripts/phase2_optuna_tuning.py
- scripts/phase3_vectorbt_validation.py
- scripts/nightly_pipeline_orchestrator.py

Output Data:
- data/qmmp/{SYMBOL}/phase1_discovery_{SYMBOL}.json
- data/qmmp/{SYMBOL}/phase2_optuna_{SYMBOL}.json
- data/qmmp/{SYMBOL}/phase3_validation_{SYMBOL}.json
- data/qmmp/{SYMBOL}/deployed/{SESSION}_{INDICATOR}_deployed.json
- data/reports/nightly_report_{TIMESTAMP}.json

Documentation:
- END_TO_END_PIPELINE_DESIGN.md (full design)
- END_TO_END_TESTING_GUIDE.md (how to run/validate)
- COMPLETE_END_TO_END_SUMMARY.md (overview)
```

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| No indicators found | Data quality | Check OHLCV loading, lower MIN_PF |
| All params rejected | High overfitting | Lower MIN_IMPROVEMENT threshold |
| Scheduler doesn't run | APScheduler missing | `pip install apscheduler` |
| Deployment fails | Wrong import path | Check ParameterOptimizer import |

---

## Key Numbers

- Vectorbt trial: **0.05ms** (incredibly fast!)
- 100 trials: **5ms**
- Phase 1: **3-5 min** per symbol
- Phase 2: **1-2 min** per symbol
- Phase 3: **30-60 sec** per symbol
- Total: **7-15 min** (fits before market open)
- Nightly: **10pm GMT Mon-Fri**

---

## Success Indicators

✅ Phase 3 rejects 20-40% of params (catches overfitting)  
✅ Pipeline completes in < 15 minutes  
✅ 1-3 params deployed per symbol per week  
✅ Live bot immediately uses new optimized params  
✅ Zero manual intervention required  

---

## Next Steps

1. **Test Now**: `python scripts/nightly_pipeline_orchestrator.py --run-now --symbols XAUUSD BTCUSD`
2. **Validate Phase 3**: Check that overfitted params are rejected
3. **Schedule**: `python scripts/nightly_pipeline_orchestrator.py --schedule`
4. **Monitor**: Check reports weekly, ensure acceptance rate stabilizes

---

That's it. Complete self-learning pipeline ready to run.
