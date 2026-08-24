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
from src.utils.logger import get_logger
import logging

_log = get_logger("optimization_routes_v2")

# Create blueprint (will be registered in main Flask app)
bp = Blueprint("optimization_v2", __name__, url_prefix="/api/v2/optimization")


@bp.route("/results/<symbol>", methods=["GET"])
def get_optimization_results(symbol):
    """
    Get optimization results for all sessions of a symbol.
    
    Returns per-session:
    - Vectorbt discovery results (baseline indicator, PF)
    - Optuna tuning results (improvement on training data)
    - Validation results (test data, overfitting check)
    - Recommendation (Accept/Reject)
    - Enable/Disable status
    """
    try:
        dashboard = SessionOptimizationDashboard(symbol=symbol)
        dashboard.load_from_files()
        
        return jsonify({
            "symbol": symbol,
            "timestamp": list(dashboard.results.values())[0].timestamp if dashboard.results else None,
            "sessions": dashboard.get_all_cards(),
            "summary": {
                "total": len(dashboard.sessions),
                "accepted": sum(1 for r in dashboard.results.values() 
                              if r.status.value == "accepted"),
                "rejected": sum(1 for r in dashboard.results.values() 
                              if r.status.value == "rejected"),
                "pending": sum(1 for r in dashboard.results.values() 
                             if r.status.value == "pending"),
                "enabled": sum(1 for r in dashboard.results.values() 
                             if r.is_enabled()),
            }
        }), 200
    
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
def toggle_session_optimization(symbol, session):
    """
    Toggle enable/disable for a session's optimization.
    
    POST /api/v2/optimization/control/XAUUSD/Asian
    JSON body: {"enabled": true}  or  {"enabled": false}
    
    Can only toggle sessions that have accepted or rejected validation results.
    """
    try:
        data = request.get_json() or {}
        enabled = data.get("enabled")
        
        if enabled is None:
            return jsonify({"error": "Missing 'enabled' field in request body"}), 400
        
        dashboard = SessionOptimizationDashboard(symbol=symbol)
        dashboard.load_from_files()
        
        if session not in dashboard.results:
            return jsonify({"error": f"Session {session} not found"}), 404
        
        result = dashboard.results[session]
        
        # Can only toggle if optimization is complete
        if result.status.value not in ["accepted", "rejected"]:
            return jsonify({
                "error": f"Cannot toggle: optimization status is {result.status.value}"
            }), 400
        
        # Save override
        result.override_enabled = enabled
        
        return jsonify({
            "symbol": symbol,
            "session": session,
            "enabled": result.is_enabled(),
            "status": result.status.value,
            "message": f"Session {session} {'enabled' if enabled else 'disabled'} for live trading"
        }), 200
    
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
