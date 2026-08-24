"""
API Endpoint for Session Optimization Dashboard

GET /api/v2/optimization/results/{symbol}
  Returns optimization results for all sessions
  
GET /api/v2/optimization/results/{symbol}/{session}
  Returns optimization results for one session

POST /api/v2/optimization/control/{symbol}/{session}
  Toggle enable/disable for a session
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, List
import json

from src.dashboard.optimization_results_component import (
    SessionOptimizationDashboard,
    OptimizationStatus
)

router = APIRouter(prefix="/api/v2/optimization", tags=["optimization"])


@router.get("/results/{symbol}")
async def get_optimization_results(symbol: str):
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
        
        return {
            "symbol": symbol,
            "timestamp": dashboard.results[list(dashboard.results.keys())[0]].timestamp if dashboard.results else None,
            "sessions": dashboard.get_all_cards(),
            "summary": {
                "total": len(dashboard.sessions),
                "accepted": sum(1 for r in dashboard.results.values() 
                              if r.status == OptimizationStatus.ACCEPTED),
                "rejected": sum(1 for r in dashboard.results.values() 
                              if r.status == OptimizationStatus.REJECTED),
                "pending": sum(1 for r in dashboard.results.values() 
                             if r.status == OptimizationStatus.PENDING),
                "enabled": sum(1 for r in dashboard.results.values() 
                             if r.is_enabled()),
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results/{symbol}/{session}")
async def get_session_optimization_result(symbol: str, session: str):
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
            raise HTTPException(
                status_code=404,
                detail=f"Session {session} not found for symbol {symbol}"
            )
        
        return dashboard.get_ui_card_data(session)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/control/{symbol}/{session}")
async def toggle_session_optimization(
    symbol: str,
    session: str,
    enabled: bool = Query(..., description="Enable or disable for live trading")
):
    """
    Toggle enable/disable for a session's optimization.
    
    POST /api/v2/optimization/control/XAUUSD/Asian?enabled=true
    POST /api/v2/optimization/control/XAUUSD/Asian?enabled=false
    
    Can only toggle sessions that have accepted or rejected validation results.
    """
    try:
        dashboard = SessionOptimizationDashboard(symbol=symbol)
        dashboard.load_from_files()
        
        if session not in dashboard.results:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session} not found"
            )
        
        result = dashboard.results[session]
        
        # Can only toggle if optimization is complete
        if result.status not in [OptimizationStatus.ACCEPTED, OptimizationStatus.REJECTED]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot toggle: optimization status is {result.status.value}"
            )
        
        # Save override
        result.override_enabled = enabled
        
        return {
            "symbol": symbol,
            "session": session,
            "enabled": result.is_enabled(),
            "status": result.status.value,
            "message": f"Session {session} {'enabled' if enabled else 'disabled'} for live trading"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary/{symbol}")
async def get_optimization_summary(symbol: str):
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
        
        return {
            "symbol": symbol,
            "summary": {
                "total_sessions": len(dashboard.sessions),
                "accepted": sum(1 for r in dashboard.results.values() 
                              if r.status == OptimizationStatus.ACCEPTED),
                "rejected": sum(1 for r in dashboard.results.values() 
                              if r.status == OptimizationStatus.REJECTED),
                "pending": sum(1 for r in dashboard.results.values() 
                             if r.status == OptimizationStatus.PENDING),
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
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
