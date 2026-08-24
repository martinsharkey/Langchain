# End-to-End Feedback Loop Testing Pipeline

**Objective**: Test complete workflow: Vectorbt discovery → Optuna tuning → Vectorbt validation → Live deployment

**Scope**: All symbols (XAUUSD, BTCUSD, etc.), all sessions (Asian, London, NewYork), all timeframes (M1-H4)

**Execution**: Nightly at 10pm GMT (Mon-Fri) during market closure

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    END-TO-END FEEDBACK LOOP PIPELINE                        │
└─────────────────────────────────────────────────────────────────────────────┘

PHASE 0: DATA PREPARATION
├─ Load historical OHLCV (M1 through H4)
├─ Session-filter per configured sessions
└─ Calculate all indicator families (OsMA, Bulls/Bears, ATR, EMA, etc.)

PHASE 1: VECTORBT DISCOVERY (Baseline)
├─ For each {symbol, session, timeframe}:
│  ├─ Test all indicator combinations
│  ├─ Rank by Profit Factor (PF)
│  ├─ Record: best_indicator, baseline_pf, baseline_params
│  └─ Save discovery_report_{symbol}_{session}_{timeframe}.json
├─ Across all timeframes (M1, M5, M15, H1, H4):
│  └─ Find best timeframe per session
└─ OUTPUT: Discovered indicators (e.g., "osma" for XAUUSD/asian/H4)

PHASE 2: OPTUNA TUNING
├─ For each discovered indicator from Phase 1:
│  ├─ Load baseline params
│  ├─ Define tunable parameter space
│  ├─ Run Optuna optimization (100 trials)
│  ├─ Record: best_tuned_params, tuned_pf_train
│  └─ Save optuna_study_{symbol}_{session}_{indicator}.db
└─ OUTPUT: Tuned parameters per {symbol, session, indicator}

PHASE 3: VECTORBT VALIDATION
├─ For each tuned parameter set:
│  ├─ Split data: 60% train, 40% test (out-of-sample)
│  ├─ Backtest tuned params on TEST data (unseen)
│  ├─ Calculate: tuned_pf_test
│  ├─ Check overfitting: Is tuned_pf_test >= baseline_pf * 0.95?
│  ├─ Check improvement: Is improvement >= 1%?
│  ├─ Decision: ACCEPT or REJECT
│  └─ Save validation_result_{symbol}_{session}_{indicator}.json
└─ OUTPUT: Validated params ready for deployment

PHASE 4: DEPLOYMENT
├─ For each ACCEPTED tuned param set:
│  ├─ Save to: data/qmmp/{SYMBOL}/deployed/{SESSION}_{INDICATOR}_deployed.json
│  ├─ Update live ParameterOptimizer.tuned[symbol]
│  ├─ Log to learning_log: "DEPLOYED {symbol}/{session}/{indicator}"
│  └─ Record: deployed_at, baseline_pf, tuned_pf_test, improvement%
├─ For each REJECTED tuned param set:
│  ├─ Keep baseline params
│  └─ Log reason: "REJECTED {symbol}/{session}/{indicator}: {reason}"
└─ OUTPUT: Live trading ready with new params

PHASE 5: LIVE FEEDBACK (Continuous, Not Part of Nightly Test)
├─ During live trading (ongoing):
│  ├─ Collect trade outcomes per {symbol, session}
│  ├─ Weekly aggregation
│  ├─ Compare: live_pf vs deployed_pf
│  └─ If degraded < 90%: Queue for re-optimization
└─ OUTPUT: Continuous improvement metrics

PHASE 6: REPORTING & MONITORING
├─ Compile results:
│  ├─ Discovery report: Which indicators won per session/timeframe
│  ├─ Optuna report: Tuning improvements (baseline → tuned)
│  ├─ Validation report: Which params passed/failed validation
│  ├─ Deployment report: What changed in live trading
│  └─ Performance report: Expected improvement metrics
├─ Send notifications:
│  ├─ Email: Summary of nightly results
│  ├─ Dashboard: Update live param status
│  └─ Logs: Detailed audit trail
└─ OUTPUT: Actionable insights + deployment status
```

---

## Phase 1: Vectorbt Discovery (Detailed)

### Input
- Historical OHLCV data for symbol at multiple timeframes (M1, M5, M15, H1, H4)
- Session definitions (Asian, London, NewYork)
- All indicator families to test

### Process

```python
def phase1_vectorbt_discovery(symbol, sessions, timeframes):
    """
    Test all indicator combinations across sessions and timeframes.
    Find the best indicator(s) for each session×timeframe combo.
    """
    
    results = {}
    
    for timeframe in timeframes:  # M1, M5, M15, H1, H4
        ohlcv = load_data(symbol, timeframe, bars=12000)
        
        for session in sessions:  # Asian, London, NewYork
            session_data = filter_by_session(ohlcv, session)
            indicators = calculate_all_indicators(session_data)
            
            # Test all indicator combinations
            best_indicator = None
            best_pf = 0
            best_params = None
            
            for indicator_name in ["osma", "bulls_bears", "atr", "ema", "confluence"]:
                # Get default params for this indicator
                params = get_default_params(indicator_name)
                
                # Generate signals
                signals = generate_signals(session_data, indicators, indicator_name, params)
                
                # Backtest
                pf, trades, wr = backtest(session_data, signals)
                
                if pf > best_pf and pf >= 1.2:  # Must exceed threshold
                    best_pf = pf
                    best_indicator = indicator_name
                    best_params = params
            
            # Save results for this session×timeframe
            results[f"{session}_{timeframe}"] = {
                "indicator": best_indicator,
                "baseline_pf": best_pf,
                "baseline_params": best_params,
                "trades": trades,
                "win_rate": wr,
            }
    
    # Find best timeframe per session
    best_by_session = {}
    for session in sessions:
        best_tf = None
        best_pf = 0
        for timeframe in timeframes:
            key = f"{session}_{timeframe}"
            if results[key]["baseline_pf"] > best_pf:
                best_pf = results[key]["baseline_pf"]
                best_tf = timeframe
        best_by_session[session] = {
            "timeframe": best_tf,
            "indicator": results[f"{session}_{best_tf}"]["indicator"],
            "baseline_pf": best_pf,
        }
    
    return results, best_by_session
```

### Output
```json
{
  "symbol": "XAUUSD",
  "phase1_discovery": {
    "Asian_M1": {
      "indicator": "osma",
      "baseline_pf": 8.2,
      "baseline_params": {"fast": 12, "slow": 26, "signal": 9},
      "trades": 156,
      "win_rate": 0.16
    },
    "Asian_M5": {
      "indicator": "osma",
      "baseline_pf": 9.1,
      ...
    },
    "Asian_H4": {
      "indicator": "osma",
      "baseline_pf": 10.24,  // ← Best for Asian session
      ...
    },
    "best_by_session": {
      "Asian": {
        "timeframe": "H4",
        "indicator": "osma",
        "baseline_pf": 10.24
      },
      "London": {
        "timeframe": "H1",
        "indicator": "bulls_bears",
        "baseline_pf": 7.8
      },
      "NewYork": {
        "timeframe": "H1",
        "indicator": "confluence",
        "baseline_pf": 6.5
      }
    }
  }
}
```

---

## Phase 2: Optuna Tuning (Detailed)

### Input
- Discovered indicators from Phase 1
- Baseline PF for each {symbol, session, indicator}
- Training data (first 60% of historical data)

### Process

```python
def phase2_optuna_tuning(symbol, discovered_indicators):
    """
    For each discovered indicator, run Optuna to find better params.
    """
    
    results = {}
    
    for session, indicator_info in discovered_indicators.items():
        indicator = indicator_info["indicator"]
        baseline_params = indicator_info["baseline_params"]
        baseline_pf = indicator_info["baseline_pf"]
        
        # Define search space for this indicator
        param_space = get_param_space(indicator)  # e.g., {"fast": (5, 34), "slow": (20, 144), ...}
        
        def optuna_objective(trial):
            # Suggest new parameters
            suggested_params = {}
            for param_name, (lo, hi) in param_space.items():
                if isinstance(lo, float):
                    suggested_params[param_name] = trial.suggest_float(param_name, lo, hi)
                else:
                    suggested_params[param_name] = trial.suggest_int(param_name, lo, hi)
            
            # Backtest with suggested params (on TRAINING data only)
            pf_train = backtest(training_data, signals_from_params(training_data, suggested_params))
            
            return pf_train
        
        # Run Optuna optimization
        sampler = optuna.samplers.TPESampler(seed=42)
        study = optuna.create_study(
            study_name=f"tune_{symbol}_{session}_{indicator}",
            storage=f"sqlite:///data/qmmp/{symbol}/optuna/study.db",
            sampler=sampler,
            direction="maximize",
            load_if_exists=True
        )
        study.optimize(optuna_objective, n_trials=100, show_progress_bar=False)
        
        best_params = study.best_params
        best_pf_train = study.best_value
        
        results[session] = {
            "indicator": indicator,
            "baseline_pf_train": baseline_pf,
            "tuned_pf_train": best_pf_train,
            "improvement_train": (best_pf_train - baseline_pf) / baseline_pf if baseline_pf > 0 else 0,
            "baseline_params": baseline_params,
            "tuned_params": best_params,
        }
    
    return results
```

### Output
```json
{
  "symbol": "XAUUSD",
  "phase2_optuna_tuning": {
    "Asian": {
      "indicator": "osma",
      "baseline_pf_train": 10.24,
      "tuned_pf_train": 10.48,
      "improvement_train": 0.0234,  // 2.34% improvement (on training data)
      "baseline_params": {"fast": 12, "slow": 26, "signal": 9},
      "tuned_params": {"fast": 15, "slow": 32, "signal": 11}  // ← Better on training data
    },
    "London": {
      "indicator": "bulls_bears",
      "baseline_pf_train": 7.8,
      "tuned_pf_train": 7.92,
      "improvement_train": 0.0154,
      ...
    }
  }
}
```

**⚠️ KEY POINT**: The improvement shown here is on TRAINING data only. We don't trust this yet - it could be overfitting. That's why Phase 3 validation is critical.

---

## Phase 3: Vectorbt Validation (Detailed)

### Input
- Tuned params from Phase 2
- HELD-OUT test data (last 40% of historical data - never seen by Optuna)

### Process

```python
def phase3_vectorbt_validation(symbol, tuned_params_from_phase2):
    """
    Validate tuned params on out-of-sample (test) data.
    This is the PROOF that tuning works in reality, not just in-sample.
    """
    
    results = {}
    
    for session, tuned_info in tuned_params_from_phase2.items():
        indicator = tuned_info["indicator"]
        baseline_params = tuned_info["baseline_params"]
        tuned_params = tuned_info["tuned_params"]
        baseline_pf_train = tuned_info["baseline_pf_train"]
        tuned_pf_train = tuned_info["tuned_pf_train"]
        
        # KEY: Use TEST data (unseen by Optuna)
        test_data = load_data(symbol, session)[-40%:]  # Last 40% = test set
        
        # Backtest baseline on test data
        baseline_pf_test = backtest(test_data, baseline_params)
        
        # Backtest tuned on test data
        tuned_pf_test = backtest(test_data, tuned_params)
        
        # Check acceptance criteria
        criteria = {
            "pf_improvement": tuned_pf_test > baseline_pf_test,
            "improvement_magnitude": (tuned_pf_test - baseline_pf_test) / baseline_pf_test >= 0.01,
            "no_overfitting": tuned_pf_test >= baseline_pf_test * 0.95,  # >5% drop = overfitting
            "minimum_threshold": tuned_pf_test >= 1.2,
        }
        
        accepted = all(criteria.values())
        
        results[session] = {
            "indicator": indicator,
            "baseline_pf_test": baseline_pf_test,
            "tuned_pf_test": tuned_pf_test,
            "improvement_test": (tuned_pf_test - baseline_pf_test) / baseline_pf_test if baseline_pf_test > 0 else 0,
            "baseline_params": baseline_params,
            "tuned_params": tuned_params,
            "validation_criteria": criteria,
            "accepted": accepted,
            "rejection_reason": "" if accepted else _get_rejection_reason(criteria),
            "train_vs_test_gap": (tuned_pf_train - tuned_pf_test) / tuned_pf_test,  // ← Overfitting indicator
        }
    
    return results
```

### Output
```json
{
  "symbol": "XAUUSD",
  "phase3_vectorbt_validation": {
    "Asian": {
      "indicator": "osma",
      "baseline_pf_test": 9.8,  // Baseline on test data
      "tuned_pf_test": 9.95,    // Tuned on test data
      "improvement_test": 0.0153,  // 1.53% improvement (REAL, on unseen data)
      "validation_criteria": {
        "pf_improvement": true,
        "improvement_magnitude": true,
        "no_overfitting": true,
        "minimum_threshold": true
      },
      "accepted": true,  // ✅ PASS - All criteria met
      "train_vs_test_gap": 0.027,  // Only 2.7% gap = good generalization
      "baseline_params": {"fast": 12, "slow": 26, "signal": 9},
      "tuned_params": {"fast": 15, "slow": 32, "signal": 11}
    },
    "London": {
      "indicator": "bulls_bears",
      "baseline_pf_test": 7.2,
      "tuned_pf_test": 6.8,  // ← WORSE on test data
      "improvement_test": -0.0556,
      "validation_criteria": {
        "pf_improvement": false,  // ✗ FAIL
        "improvement_magnitude": false,
        "no_overfitting": false,
        "minimum_threshold": true
      },
      "accepted": false,  // ✗ REJECT - Overfitted during Optuna
      "rejection_reason": "PF declined 5.6% on test data; overfitting detected",
      "tuned_params": {"..."}
    }
  }
}
```

**⭐ KEY INSIGHT**: London's tuned params looked great in training (7.92 PF) but failed on test data (6.8 PF). This is **overfitting** - they memorized the training data rather than learning generalizable patterns. Validation catches this before it hits live trading.

---

## Phase 4: Deployment (Detailed)

### Input
- Validation results from Phase 3
- Accepted tuned params

### Process

```python
def phase4_deployment(symbol, validation_results):
    """
    Deploy ACCEPTED params to live trading.
    Keep baseline params for REJECTED.
    """
    
    deployment_summary = {}
    
    for session, validation_result in validation_results.items():
        indicator = validation_result["indicator"]
        
        if validation_result["accepted"]:
            # DEPLOY tuned params
            deployed_params = validation_result["tuned_params"]
            deployed_baseline = validation_result["baseline_params"]
            deployed_pf = validation_result["tuned_pf_test"]
            
            # Save to file
            deploy_path = f"data/qmmp/{symbol}/deployed/{session}_{indicator}_deployed.json"
            save_json({
                "symbol": symbol,
                "session": session,
                "indicator": indicator,
                "deployed_params": deployed_params,
                "baseline_params": deployed_baseline,
                "deployed_pf": deployed_pf,
                "improvement": validation_result["improvement_test"],
                "deployed_at": datetime.now(timezone.utc).isoformat(),
            }, deploy_path)
            
            # Update live ParameterOptimizer
            param_optimizer.tuned[symbol][session] = deployed_params
            
            # Log to learning log
            learning_log.record(
                kind="DEPLOYED",
                symbol=symbol,
                session=session,
                indicator=indicator,
                improvement=validation_result["improvement_test"],
                message=f"Deployed tuned {indicator} ({validation_result['improvement_test']*100:.1f}% improvement)"
            )
            
            deployment_summary[session] = {
                "action": "DEPLOYED",
                "indicator": indicator,
                "improvement": validation_result["improvement_test"],
                "deployed_pf": deployed_pf,
            }
        else:
            # REJECT - keep baseline
            deployment_summary[session] = {
                "action": "REJECTED",
                "indicator": indicator,
                "reason": validation_result["rejection_reason"],
            }
            
            learning_log.record(
                kind="REJECTED",
                symbol=symbol,
                session=session,
                indicator=indicator,
                reason=validation_result["rejection_reason"],
                message=f"Rejected tuned {indicator}: {validation_result['rejection_reason']}"
            )
    
    return deployment_summary
```

### Output
```json
{
  "symbol": "XAUUSD",
  "phase4_deployment": {
    "Asian": {
      "action": "DEPLOYED",
      "indicator": "osma",
      "improvement": 0.0153,
      "deployed_pf": 9.95
    },
    "London": {
      "action": "REJECTED",
      "indicator": "bulls_bears",
      "reason": "PF declined 5.6% on test data; overfitting detected"
    },
    "NewYork": {
      "action": "DEPLOYED",
      "indicator": "confluence",
      "improvement": 0.0089,
      "deployed_pf": 6.58
    }
  }
}
```

---

## Phase 6: Reporting & Monitoring

### Nightly Report Structure

```json
{
  "nightly_run": {
    "started_at": "2026-08-24T22:00:00Z",
    "completed_at": "2026-08-24T22:43:12Z",
    "symbols": ["XAUUSD", "BTCUSD", "AUDCAD"],
    
    "phase1_discovery": {
      "total_symbol_session_timeframe_combos": 45,  // 3 symbols × 3 sessions × 5 timeframes
      "indicators_tested": 5,
      "best_indicators_found": 9,
      "details": {...}
    },
    
    "phase2_optuna_tuning": {
      "studies_run": 9,
      "total_trials": 900,  // 9 studies × 100 trials each
      "total_time_ms": 45000,  // 900 trials × 0.05ms per trial = 45ms (plus overhead)
      "details": {...}
    },
    
    "phase3_vectorbt_validation": {
      "tuned_params_tested": 9,
      "accepted": 6,
      "rejected": 3,  // Overfitting detected
      "acceptance_rate": 0.667,
      "avg_improvement": 0.0132,  // 1.32% average
      "details": {...}
    },
    
    "phase4_deployment": {
      "deployed": 6,
      "rejected": 3,
      "expected_improvement": 0.0132,
      "details": {...}
    },
    
    "summary": {
      "status": "SUCCESS",
      "symbols_processed": 3,
      "params_improved": 6,
      "params_rejected": 3,
      "estimated_edge_improvement": "1.32%",
      "next_run": "2026-08-25T22:00:00Z"
    },
    
    "notifications": {
      "email_to": "user@example.com",
      "subject": "[QMMP] Nightly Optimization: 6/9 params deployed (+1.32% edge)",
      "dashboard_update": true,
      "learning_log_audit": "9 entries logged"
    }
  }
}
```

---

## Nightly Orchestrator (10pm GMT Mon-Fri)

```python
class NightlyOptimizationOrchestrator:
    """Runs complete feedback loop every night at 10pm GMT (Mon-Fri during market closure)."""
    
    def __init__(self, symbols=None, sessions=None, timeframes=None):
        self.symbols = symbols or ["XAUUSD", "BTCUSD"]
        self.sessions = sessions or ["Asian", "London", "NewYork"]
        self.timeframes = timeframes or ["M1", "M5", "M15", "H1", "H4"]
    
    def run(self):
        """Execute complete pipeline."""
        logger.info("="*80)
        logger.info("NIGHTLY OPTIMIZATION PIPELINE STARTING")
        logger.info("="*80)
        
        report = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "symbols": self.symbols,
            "phase_results": {},
        }
        
        try:
            # Phase 1: Vectorbt Discovery
            logger.info("[1/6] Phase 1: Vectorbt Discovery")
            phase1_results = self.phase1_discovery()
            report["phase_results"]["discovery"] = phase1_results
            logger.info(f"✓ Phase 1 complete: {len(phase1_results)} symbol/session combos tested")
            
            # Phase 2: Optuna Tuning
            logger.info("[2/6] Phase 2: Optuna Tuning")
            phase2_results = self.phase2_optuna_tuning(phase1_results)
            report["phase_results"]["optuna"] = phase2_results
            logger.info(f"✓ Phase 2 complete: {len(phase2_results)} indicators tuned")
            
            # Phase 3: Vectorbt Validation
            logger.info("[3/6] Phase 3: Vectorbt Validation")
            phase3_results = self.phase3_validation(phase2_results)
            report["phase_results"]["validation"] = phase3_results
            accepted = sum(1 for s in phase3_results.values() if s.get("accepted"))
            logger.info(f"✓ Phase 3 complete: {accepted}/{len(phase3_results)} params accepted")
            
            # Phase 4: Deployment
            logger.info("[4/6] Phase 4: Deployment")
            phase4_results = self.phase4_deployment(phase3_results)
            report["phase_results"]["deployment"] = phase4_results
            logger.info(f"✓ Phase 4 complete: {phase4_results['deployed']} deployed, {phase4_results['rejected']} rejected")
            
            # Phase 5: (Skipped in nightly - continuous during live trading)
            logger.info("[5/6] Phase 5: Live Feedback (Continuous)")
            logger.info("→ Running continuously during live trading (not part of nightly)")
            
            # Phase 6: Reporting
            logger.info("[6/6] Phase 6: Reporting")
            self.phase6_reporting(report)
            logger.info(f"✓ Phase 6 complete: Report generated and notifications sent")
            
            report["completed_at"] = datetime.now(timezone.utc).isoformat()
            report["status"] = "SUCCESS"
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            report["status"] = "FAILED"
            report["error"] = str(e)
            self.send_error_notification(report)
        
        # Save report
        self.save_report(report)
        
        logger.info("="*80)
        logger.info("NIGHTLY OPTIMIZATION PIPELINE COMPLETE")
        logger.info("="*80)
        
        return report
    
    def schedule_nightly(self):
        """Schedule pipeline to run at 10pm GMT every Mon-Fri."""
        from apscheduler.schedulers.background import BackgroundScheduler
        
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            self.run,
            'cron',
            day_of_week='mon-fri',
            hour=22,  # 10pm GMT
            minute=0,
            second=0
        )
        scheduler.start()
        logger.info("Nightly optimizer scheduled for 10pm GMT Mon-Fri")
```

---

## Expected Performance

| Phase | Time (sequential) | Time (parallel) |
|-------|------------------|-----------------|
| Phase 1: Discovery (3 symbols × 3 sessions × 5 TF) | 15-30min | 3-6min |
| Phase 2: Optuna (900 trials @ 0.05ms + overhead) | 5-10min | 1-2min |
| Phase 3: Validation (6-9 param sets) | 2-3min | 1-2min |
| Phase 4: Deployment | 1-2min | 1-2min |
| Phase 6: Reporting | 1-2min | 1-2min |
| **TOTAL** | **25-50 minutes** | **7-15 minutes** |

With parallelization (8-core CPU), entire nightly pipeline completes in **7-15 minutes** - plenty of time before market open.

---

## Next Steps

1. Build Phase 1: Vectorbt discovery across all symbols/sessions/timeframes
2. Build Phase 2: Optuna tuning orchestrator
3. Build Phase 3: Walk-forward validation with acceptance gates
4. Build Phase 4: Deployment orchestrator
5. Build Phase 6: Comprehensive reporting
6. Build scheduler: APScheduler for 10pm GMT Mon-Fri
7. Test end-to-end on XAUUSD for 1 week
8. Extend to BTCUSD and other symbols
