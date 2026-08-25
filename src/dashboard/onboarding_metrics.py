"""
Real-time Onboarding Metrics API

Reads intermediate files created during vectorbt onboarding pipeline
and serves metrics to the dashboard for live progress monitoring.

Phases tracked:
1. Phase 1: Vectorbt discovery - indicators tested, best baseline found
2. Phase 2: Optuna tuning - parameter optimization in progress
3. Phase 3: Validation - walk-forward testing, overfitting detection
4. Phase 4: Deployment - floor discovery, EA generation
"""

import json
import os
from pathlib import Path
from datetime import datetime
from flask import Blueprint, jsonify
import logging

_log = logging.getLogger("onboarding_metrics")

bp = Blueprint("onboarding_metrics", __name__, url_prefix="/api/onboarding")

PROJECT_ROOT = Path(__file__).parent.parent.parent
QMMP_DIR = PROJECT_ROOT / "data" / "qmmp"


def _read_json_safe(filepath):
    """Safely read JSON file if it exists."""
    try:
        if Path(filepath).exists():
            with open(filepath) as f:
                return json.load(f)
    except Exception as e:
        _log.warning(f"Could not read {filepath}: {e}")
    return None


def _get_phase1_metrics(symbol: str):
    """Get Phase 1 (Vectorbt Discovery) metrics."""
    symbol_dir = QMMP_DIR / symbol
    discovery_file = symbol_dir / "phase1_vectorbt_discovery.json"
    
    if not discovery_file.exists():
        return {"status": "pending", "message": "Waiting for discovery to start..."}
    
    discovery_data = _read_json_safe(discovery_file)
    if not discovery_data:
        return {"status": "loading", "message": "Reading discovery data..."}
    
    sessions_data = discovery_data.get("sessions", {})
    
    metrics = {
        "status": "complete",
        "timestamp": discovery_data.get("timestamp"),
        "sessions_tested": len(sessions_data),
        "timeframes_tested": list(discovery_data.get("timeframes", [])),
        "best_per_session": {}
    }
    
    # Extract best indicator per session
    for session, timeframes in sessions_data.items():
        best = None
        best_pf = 0
        for tf_data in timeframes.values() if isinstance(timeframes, dict) else []:
            if isinstance(tf_data, dict) and tf_data.get("pf", 0) > best_pf:
                best = tf_data
                best_pf = tf_data.get("pf", 0)
        
        if best:
            metrics["best_per_session"][session] = {
                "indicator": best.get("primary_ind"),
                "filter": best.get("secondary_ind"),
                "pf": round(best.get("pf", 0), 2),
                "wr": round(best.get("wr", 0), 4),
                "trades": best.get("trades", 0),
                "timeframe": best.get("timeframe")
            }
    
    return metrics


def _get_phase2_metrics(symbol: str):
    """Get Phase 2 (Optuna Tuning) metrics."""
    symbol_dir = QMMP_DIR / symbol
    optuna_dir = symbol_dir / "phase2_optuna_tuning"
    
    if not optuna_dir.exists():
        return {"status": "pending", "message": "Waiting for Optuna tuning to start..."}
    
    # Try to read trial results if available
    trials_file = optuna_dir / "trials.json"
    trials_data = _read_json_safe(trials_file) or {}
    
    completed = len([t for t in trials_data.get("trials", []) if t.get("state") == "COMPLETE"])
    total = len(trials_data.get("trials", []))
    
    best_trial = trials_data.get("best_trial")
    
    metrics = {
        "status": "in_progress" if total > 0 else "pending",
        "trials_completed": completed,
        "trials_total": total,
        "progress_pct": int((completed / total * 100) if total > 0 else 0),
    }
    
    if best_trial:
        metrics["best_trial"] = {
            "trial_id": best_trial.get("number"),
            "pf": round(best_trial.get("pf", 0), 2),
            "improvement_pct": round(best_trial.get("improvement_pct", 0), 2),
            "params": best_trial.get("params", {})
        }
    
    return metrics


def _get_phase3_metrics(symbol: str):
    """Get Phase 3 (Validation) metrics."""
    symbol_dir = QMMP_DIR / symbol
    validation_file = symbol_dir / f"phase3_validation_{symbol}.json"
    
    if not validation_file.exists():
        return {"status": "pending", "message": "Waiting for validation phase..."}
    
    validation_data = _read_json_safe(validation_file)
    if not validation_data:
        return {"status": "loading", "message": "Reading validation data..."}
    
    validated_strategies = validation_data.get("validated_strategies", {})
    
    metrics = {
        "status": "complete",
        "timestamp": validation_data.get("timestamp"),
        "sessions_validated": len(validated_strategies),
        "sessions": {}
    }
    
    for session, strategy in validated_strategies.items():
        metrics["sessions"][session] = {
            "primary_ind": strategy.get("primary_ind"),
            "secondary_ind": strategy.get("secondary_ind"),
            "test_pf": round(strategy.get("pf", 0), 2),
            "test_wr": round(strategy.get("wr", 0), 4),
            "test_trades": strategy.get("trades", 0),
            "sharpe": round(strategy.get("sharpe", 0), 2),
            "timeframe": strategy.get("timeframe")
        }
    
    return metrics


def _get_phase4_metrics(symbol: str):
    """Get Phase 4 (Deployment) metrics."""
    symbol_dir = QMMP_DIR / symbol
    results_file = symbol_dir / f"{symbol}_vectorbt_results.json"
    ea_file = symbol_dir / f"GoldShark_{symbol}_vectorbt.mq5"
    
    metrics = {
        "status": "pending",
        "floors_discovered": False,
        "ea_generated": ea_file.exists()
    }
    
    if results_file.exists():
        results = _read_json_safe(results_file)
        if results and "floors" in results:
            metrics["status"] = "complete"
            metrics["floors_discovered"] = True
            metrics["floors"] = results["floors"]
    
    return metrics


@bp.route("/<symbol>/progress", methods=["GET"])
def get_onboarding_progress(symbol: str):
    """Get real-time onboarding progress for a symbol.
    
    Returns metrics from all 4 phases as they complete.
    """
    try:
        symbol = symbol.upper()
        
        phases = {
            "phase1_discovery": _get_phase1_metrics(symbol),
            "phase2_tuning": _get_phase2_metrics(symbol),
            "phase3_validation": _get_phase3_metrics(symbol),
            "phase4_deployment": _get_phase4_metrics(symbol)
        }
        
        # Determine overall progress
        statuses = [p.get("status", "pending") for p in phases.values()]
        if "in_progress" in statuses:
            overall_status = "in_progress"
            progress_pct = phases["phase2_tuning"].get("progress_pct", 0)
        elif all(s in ("complete", "pending") for s in statuses):
            overall_status = "complete" if any(s == "complete" for s in statuses) else "pending"
            progress_pct = 100 if overall_status == "complete" else 0
        else:
            overall_status = "pending"
            progress_pct = 0
        
        return jsonify({
            "status": "ok",
            "symbol": symbol,
            "overall_status": overall_status,
            "progress_pct": progress_pct,
            "timestamp": datetime.now().isoformat(),
            "phases": phases
        })
    
    except Exception as e:
        _log.error(f"Error getting onboarding progress: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/<symbol>/summary", methods=["GET"])
def get_onboarding_summary(symbol: str):
    """Get final onboarding summary with all discovered metrics."""
    try:
        symbol = symbol.upper()
        symbol_dir = QMMP_DIR / symbol
        results_file = symbol_dir / f"{symbol}_vectorbt_results.json"
        
        if not results_file.exists():
            return jsonify({"error": f"No onboarding results for {symbol}"}), 404
        
        results = _read_json_safe(results_file)
        if not results:
            return jsonify({"error": "Could not read results"}), 500
        
        # Extract key metrics
        validated = results.get("validated_strategies", {})
        floors = results.get("floors", {})
        
        summary = {
            "status": "ok",
            "symbol": symbol,
            "completed_at": results.get("timestamp"),
            "data_range": results.get("date_range"),
            "sessions_optimized": len(validated),
            "sessions": {}
        }
        
        for session, strategy in validated.items():
            floors_data = floors.get(session, {})
            summary["sessions"][session] = {
                "best_indicator": strategy.get("primary_ind"),
                "filter": strategy.get("secondary_ind"),
                "test_pf": round(strategy.get("pf", 0), 2),
                "test_wr": round(strategy.get("wr", 0), 4),
                "test_trades": strategy.get("trades", 0),
                "sharpe_ratio": round(strategy.get("sharpe", 0), 2),
                "timeframe": strategy.get("timeframe"),
                "floors": floors_data
            }
        
        return jsonify(summary)
    
    except Exception as e:
        _log.error(f"Error getting onboarding summary: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def register_routes(app):
    """Register onboarding metrics routes with Flask app."""
    app.register_blueprint(bp)
    _log.info("Registered Onboarding Metrics API routes")
