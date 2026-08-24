"""
Dashboard API v2 Flask Routes.

Expose analytics API endpoints for the new dashboard frontend.
Routes:
  GET /api/v2/strategies              - List all strategies with metrics
  GET /api/v2/strategies/{name}       - Detailed strategy view
  GET /api/v2/backtest/results        - Backtest results
  GET /api/v2/vectorbt/discovery      - Edge discovery status
  GET /api/v2/summary                 - Dashboard summary statistics
"""

from flask import Blueprint, jsonify, request
from src.dashboard.api_v2 import get_api
import logging

_log = logging.getLogger("dashboard_routes_v2")

bp = Blueprint("dashboard_v2", __name__, url_prefix="/api/v2")


@bp.route("/strategies", methods=["GET"])
def list_strategies():
    """List all strategies with backtest + live metrics.
    
    Query params:
      ?symbol=XAUUSD   - Filter by symbol
      ?sort=pf         - Sort by profit_factor (default: symbol, rank)
    
    Returns: {
      "data": [Strategy, ...],
      "summary": {
        "total": int,
        "validated": int,
        "avg_pf": float
      }
    }
    """
    try:
        api = get_api()
        symbol = request.args.get("symbol")
        sort_by = request.args.get("sort", "default")
        
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
                "regime_edges": [
                    {"regime": e.regime, "multiplier": e.multiplier}
                    for e in s.regime_edges
                ]
            }
            
            # Add backtest metrics if available
            if s.backtest:
                strat_dict["backtest"] = {
                    "pf": s.backtest.metrics.profit_factor,
                    "wr": s.backtest.metrics.win_rate,
                    "sharpe": s.backtest.metrics.sharpe_ratio,
                    "trades": s.backtest.metrics.total_trades,
                    "validated_at": s.backtest.validated_at
                }
            
            # Add live metrics if available
            if s.live:
                strat_dict["live"] = {
                    "trades": s.live.total_trades,
                    "wr": s.live.win_rate,
                    "pf": s.live.profit_factor,
                    "pnl": s.live.total_pnl,
                    "avg_win": s.live.avg_win,
                    "avg_loss": s.live.avg_loss
                }
            
            # Add Optuna if available
            if s.optuna_study:
                strat_dict["optuna"] = {
                    "study": s.optuna_study,
                    "trials": s.optuna_trials,
                    "best_value": s.optuna_best_value,
                    "improvement_pct": s.optuna_improvement_pct,
                    "last_optimized": s.last_optimized
                }
            
            data.append(strat_dict)
        
        # Sort
        if sort_by == "pf":
            data.sort(key=lambda s: -(s.get("vectorbt_pf") or 0))
        elif sort_by == "live_pf":
            data.sort(key=lambda s: -(s.get("live", {}).get("pf") or 0))
        
        # Summary
        summary = api.get_summary_stats()
        
        return jsonify({
            "status": "ok",
            "data": data,
            "summary": summary
        })
    
    except Exception as e:
        _log.error(f"Error in list_strategies: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/strategies/<strategy_name>", methods=["GET"])
def get_strategy(strategy_name: str):
    """Get detailed metrics for a specific strategy.
    
    Returns: {
      "strategy": Strategy with full details,
      "comparison": {
        "rank_by_pf": int,
        "rank_by_live_wr": int
      }
    }
    """
    try:
        api = get_api()
        
        all_strategies = api.list_strategies()
        strat = next((s for s in all_strategies if s.name == strategy_name), None)
        
        if not strat:
            return jsonify({"error": "Strategy not found"}), 404
        
        # Convert to dict (same as list_strategies)
        strat_dict = {
            "symbol": strat.symbol,
            "name": strat.name,
            "rank": strat.rank,
            "enabled": strat.enabled,
            "validated": strat.validated,
            "vectorbt_pf": strat.vectorbt_pf,
            "regime_edges": [
                {"regime": e.regime, "multiplier": e.multiplier}
                for e in strat.regime_edges
            ]
        }
        
        if strat.backtest:
            strat_dict["backtest"] = {
                "pf": strat.backtest.metrics.profit_factor,
                "wr": strat.backtest.metrics.win_rate,
                "sharpe": strat.backtest.metrics.sharpe_ratio,
                "trades": strat.backtest.metrics.total_trades,
                "validated_at": strat.backtest.validated_at
            }
        
        if strat.live:
            strat_dict["live"] = {
                "trades": strat.live.total_trades,
                "wr": strat.live.win_rate,
                "pf": strat.live.profit_factor,
                "pnl": strat.live.total_pnl
            }
        
        # Rankings
        by_pf = sorted(all_strategies, key=lambda s: -(s.vectorbt_pf or 0))
        rank_by_pf = next((i+1 for i, s in enumerate(by_pf) if s.name == strategy_name), None)
        
        return jsonify({
            "status": "ok",
            "strategy": strat_dict,
            "rank_by_pf": rank_by_pf
        })
    
    except Exception as e:
        _log.error(f"Error in get_strategy: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/backtest/results", methods=["GET"])
def get_backtest_results():
    """Get backtest results for all strategies.
    
    Query params:
      ?symbol=XAUUSD           - Filter by symbol
      ?strategy=OsMA_Confluence - Filter by strategy
    
    Returns: {
      "data": [BacktestResult, ...]
    }
    """
    try:
        api = get_api()
        symbol = request.args.get("symbol")
        strategy = request.args.get("strategy")
        
        results = api.get_backtest_results(symbol, strategy)
        
        return jsonify({
            "status": "ok",
            "data": results
        })
    
    except Exception as e:
        _log.error(f"Error in get_backtest_results: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/vectorbt/discovery", methods=["GET"])
def get_vectorbt_discovery():
    """Get vectorbt edge discovery status.
    
    Returns: {
      "swept_at": ISO8601,
      "min_pf_threshold": float,
      "timeframe": string,
      "symbols": {
        "XAUUSD": { "validated": bool, "pockets": int },
        ...
      }
    }
    """
    try:
        api = get_api()
        discovery = api.get_vectorbt_discovery()
        
        return jsonify({
            "status": "ok",
            "data": discovery
        })
    
    except Exception as e:
        _log.error(f"Error in get_vectorbt_discovery: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/summary", methods=["GET"])
def get_dashboard_summary():
    """Get dashboard summary statistics.
    
    Returns: {
      "total_strategies": int,
      "validated_strategies": int,
      "avg_profit_factor": float,
      "best_strategy": {...},
      "worst_strategy": {...}
    }
    """
    try:
        api = get_api()
        summary = api.get_summary_stats()
        
        return jsonify({
            "status": "ok",
            "data": summary
        })
    
    except Exception as e:
        _log.error(f"Error in get_dashboard_summary: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def register_routes(app):
    """Register all dashboard v2 routes with Flask app."""
    app.register_blueprint(bp)
    _log.info("Registered Dashboard API v2 routes")
