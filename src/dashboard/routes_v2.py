"""
Dashboard API v2 Flask Routes (Simplified Fallback Version).

Expose analytics API endpoints for the new dashboard frontend.
When the full API isn't available, return empty/placeholder data.

Routes:
  GET /api/v2/strategies              - List all strategies with metrics
  GET /api/v2/strategies/{name}       - Detailed strategy view
  GET /api/v2/backtest/results        - Backtest results
  GET /api/v2/vectorbt/discovery      - Edge discovery status
  GET /api/v2/summary                 - Dashboard summary statistics
"""

from flask import Blueprint, jsonify, request
import logging

_log = logging.getLogger("dashboard_routes_v2")

bp = Blueprint("dashboard_v2", __name__, url_prefix="/api/v2")


@bp.route("/strategies", methods=["GET"])
def list_strategies():
    """List all strategies with backtest + live metrics."""
    try:
        # Try to load real API if available
        from src.dashboard.api_v2 import get_api
        try:
            api = get_api()
            symbol = request.args.get("symbol")
            strategies = api.list_strategies(symbol)
            
            # Convert to JSON-serializable format
            data = []
            for s in strategies:
                strat_dict = {
                    "symbol": s.symbol,
                    "name": s.name,
                    "rank": s.rank,
                    "enabled": s.enabled,
                    "validated": s.validated,
                    "vectorbt_pf": s.vectorbt_pf,
                }
                if s.backtest:
                    strat_dict["backtest"] = {
                        "pf": s.backtest.metrics.profit_factor,
                        "wr": s.backtest.metrics.win_rate,
                        "sharpe": s.backtest.metrics.sharpe_ratio,
                        "trades": s.backtest.metrics.total_trades,
                    }
                if s.live:
                    strat_dict["live"] = {
                        "trades": s.live.total_trades,
                        "wr": s.live.win_rate,
                        "pf": s.live.profit_factor,
                        "pnl": s.live.total_pnl,
                    }
                data.append(strat_dict)
            
            summary = api.get_summary_stats()
            
            return jsonify({
                "status": "ok",
                "data": data,
                "summary": summary
            })
        except Exception as e:
            _log.warning(f"Dashboard API error: {e}, returning empty strategies")
    except:
        pass
    
    # Fallback: return empty data
    return jsonify({
        "status": "ok",
        "data": [],
        "summary": {
            "total": 0,
            "validated": 0,
            "avg_pf": 0.0
        }
    })


@bp.route("/strategies/<strategy_name>", methods=["GET"])
def get_strategy(strategy_name: str):
    """Get detailed metrics for a specific strategy."""
    return jsonify({
        "status": "ok",
        "strategy": {
            "name": strategy_name,
            "symbol": "N/A",
            "validated": False
        },
        "rank_by_pf": 0
    })


@bp.route("/backtest/results", methods=["GET"])
def get_backtest_results():
    """Get backtest results for all strategies."""
    return jsonify({
        "status": "ok",
        "data": []
    })


@bp.route("/vectorbt/discovery", methods=["GET"])
def get_vectorbt_discovery():
    """Get vectorbt edge discovery status."""
    return jsonify({
        "status": "ok",
        "data": {
            "swept_at": None,
            "min_pf_threshold": 1.2,
            "timeframe": "M1",
            "symbols": {}
        }
    })


@bp.route("/summary", methods=["GET"])
def get_dashboard_summary():
    """Get dashboard summary statistics."""
    return jsonify({
        "status": "ok",
        "data": {
            "total_strategies": 0,
            "validated_strategies": 0,
            "avg_profit_factor": 0.0,
            "best_strategy": None,
            "worst_strategy": None
        }
    })


def register_routes(app):
    """Register all dashboard v2 routes with Flask app."""
    app.register_blueprint(bp)
    _log.info("Registered Dashboard API v2 routes (fallback mode)")
