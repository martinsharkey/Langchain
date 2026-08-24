"""
Flask Routes for Session Optimization Dashboard

Integrates with existing dashboard API v2 Flask blueprint.
Endpoints:
  GET /api/v2/optimization/results/{symbol}
  GET /api/v2/optimization/results/{symbol}/{session}
  POST /api/v2/optimization/control/{symbol}/{session}
  GET /api/v2/optimization/summary/{symbol}
"""

from flask import Blueprint, jsonify, request
from src.dashboard.optimization_results_component import SessionOptimizationDashboard
from src.dashboard.optimization_dashboard_bridge import OptimizationDashboardBridge
from src.dashboard.optimization_dashboard_performance import (
    get_cached_dashboard,
    invalidate_symbol_cache,
    with_performance_tracking,
    get_performance_report,
    QueryOptimizer
)
from src.utils.logger import get_logger
import logging

_log = get_logger("optimization_routes_v2")
_bridge = OptimizationDashboardBridge()

# Create blueprint (will be registered in main Flask app)
bp = Blueprint("optimization_v2", __name__, url_prefix="/api/v2/optimization")


@bp.route("/results/<symbol>", methods=["GET"])
@with_performance_tracking("GET /results/{symbol}")
def get_optimization_results(symbol):
    """
    Get optimization results for all sessions of a symbol.
    
    Uses caching to minimize disk I/O and improve response time.
    
    Returns per-session:
    - Vectorbt discovery results (baseline indicator, PF)
    - Optuna tuning results (improvement on training data)
    - Validation results (test data, overfitting check)
    - Recommendation (Accept/Reject)
    - Enable/Disable status
    """
    try:
        # Use cached dashboard for performance
        cached_dashboard = get_cached_dashboard(symbol)
        results = cached_dashboard.get_results()
        
        if not results:
            return jsonify({
                "symbol": symbol,
                "sessions": {},
                "summary": {
                    "total": 0,
                    "accepted": 0,
                    "rejected": 0,
                    "pending": 0,
                    "enabled": 0
                }
            }), 200
        
        # Calculate summary
        summary = {
            "total": len(results),
            "accepted": sum(1 for r in results.values() if r.get("status") == "accepted"),
            "rejected": sum(1 for r in results.values() if r.get("status") == "rejected"),
            "pending": sum(1 for r in results.values() if r.get("status") == "pending"),
            "enabled": sum(1 for r in results.values() if r.get("enabled", True))
        }
        
        return jsonify({
            "symbol": symbol,
            "sessions": results,
            "summary": summary
        }), 200
    
    except Exception as e:
        _log.error(f"Failed to get results for {symbol}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    
    except Exception as e:
        _log.error(f"Failed to get optimization results: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/results/<symbol>/<session>", methods=["GET"])
def get_session_optimization_result(symbol, session):
    """
    Get detailed optimization results for one session.
    
    Includes:
    - Vectorbt discovery (indicator, timeframe, PF, win rate, trades)
    - Optuna tuning (baseline → tuned PF, improvement %)
    - Validation (test data results, overfitting detection)
    - Recommendation (with reasoning)
    - Enable/Disable toggle
    """
    try:
        dashboard = SessionOptimizationDashboard(symbol=symbol)
        dashboard.load_from_files()
        
        if session not in dashboard.results:
            return jsonify({
                "error": f"Session {session} not found for symbol {symbol}"
            }), 404
        
        return jsonify(dashboard.get_ui_card_data(session)), 200
    
    except Exception as e:
        _log.error(f"Failed to get session results: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/control/<symbol>/<session>", methods=["POST"])
@with_performance_tracking("POST /control/{symbol}/{session}")
def toggle_session_optimization(symbol, session):
    """
    Toggle enable/disable for a session's optimization.
    
    POST /api/v2/optimization/control/XAUUSD/Asian
    JSON body: {"enabled": true}  or  {"enabled": false}
    
    Can only toggle sessions that have accepted or rejected validation results.
    Applies changes directly to live parameter optimizer.
    """
    try:
        data = request.get_json() or {}
        enabled = data.get("enabled")
        
        if enabled is None:
            return jsonify({"error": "Missing 'enabled' field in request body"}), 400
        
        # Use bridge to apply changes to live optimizer
        result = _bridge.apply_session_toggle(symbol, session, enabled)
        
        # Invalidate cache so next request gets fresh data
        invalidate_symbol_cache(symbol)
        
        if result.get("applied"):
            return jsonify(result), 200
        else:
            error_code = 404 if "not found" in result.get("error", "").lower() else 400
            return jsonify(result), error_code
    
    except Exception as e:
        _log.error(f"Failed to toggle session: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/summary/<symbol>", methods=["GET"])
def get_optimization_summary(symbol):
    """
    Get summary of optimization results for a symbol.
    
    Returns:
    - Total sessions
    - Accepted count
    - Rejected count
    - Pending count
    - Enabled count
    - Per-session status
    """
    try:
        dashboard = SessionOptimizationDashboard(symbol=symbol)
        dashboard.load_from_files()
        
        return jsonify({
            "symbol": symbol,
            "summary": {
                "total_sessions": len(dashboard.sessions),
                "accepted": sum(1 for r in dashboard.results.values() 
                              if r.status.value == "accepted"),
                "rejected": sum(1 for r in dashboard.results.values() 
                              if r.status.value == "rejected"),
                "pending": sum(1 for r in dashboard.results.values() 
                             if r.status.value == "pending"),
                "enabled": sum(1 for r in dashboard.results.values() 
                             if r.is_enabled()),
            },
            "sessions": {
                session: {
                    "status": result.status.value,
                    "enabled": result.is_enabled(),
                    "recommendation": result.get_recommendation()["action"]
                }
                for session, result in dashboard.results.items()
            }
        }), 200
    
    except Exception as e:
        _log.error(f"Failed to get optimization summary: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/performance", methods=["GET"])
def get_performance_stats():
    """
    Get dashboard performance statistics.
    
    Returns:
    - Cache hit rate
    - API latency percentiles
    - Error count
    - Toggle operation count
    """
    try:
        stats = get_performance_report()
        return jsonify(stats), 200
    except Exception as e:
        _log.error(f"Failed to get performance stats: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/cache/<symbol>/invalidate", methods=["POST"])
def invalidate_cache(symbol):
    """
    Manually invalidate cache for a symbol.
    
    Called after toggle operations to ensure fresh data on next request.
    """
    try:
        invalidate_symbol_cache(symbol)
        return jsonify({
            "message": f"Cache invalidated for {symbol}",
            "symbol": symbol
        }), 200
    except Exception as e:
        _log.error(f"Failed to invalidate cache: {e}")
        return jsonify({"error": str(e)}), 500
