"""
Symbol Onboarding API

Provides endpoints for managing symbol data and running vectorbt-based onboarding pipeline.
"""

import os
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import jsonify, request

from src import config
from src.utils.logger import get_logger

logger = get_logger("symbol_api")

# In-memory task tracking
_tasks = {}
_tasks_lock = threading.Lock()

DATA_DIR = config.DATA_DIR
QMMP_DIR = os.path.join(DATA_DIR, "qmmp")


def get_symbol_status(symbol: str) -> dict:
    """Get current status of a symbol with session-specific results."""
    symbol_dir = os.path.join(QMMP_DIR, symbol)
    
    status = {
        "symbol": symbol,
        "status": "ready",
        "progress": None,
        "results": None,
        "sessions": None,
        "error": None,
        "last_updated": None,
    }
    
    if not os.path.exists(symbol_dir):
        return status
    
    # Check if onboarding is in progress
    with _tasks_lock:
        for task in _tasks.values():
            if task["symbol"] == symbol and task["status"] in ["queued", "running"]:
                status["status"] = "onboarding"
                status["progress"] = task["progress"]
                return status
    
    # Check if vectorbt results exist (preferred over onboarding_results.json)
    vectorbt_results_file = os.path.join(symbol_dir, f"{symbol}_vectorbt_results.json")
    if os.path.exists(vectorbt_results_file):
        try:
            with open(vectorbt_results_file) as f:
                vbt_data = json.load(f)
                status["status"] = "onboarded"
                
                # Extract session-specific data
                sessions = {}
                if "validated_strategies" in vbt_data:
                    for session_name, session_data in vbt_data["validated_strategies"].items():
                        sessions[session_name] = {
                            "session": session_name,
                            "best_strategy": session_data.get("primary_ind", "Unknown"),
                            "secondary_filter": session_data.get("secondary_ind", "none"),
                            "profit_factor": session_data.get("pf", 0.0),
                            "win_rate": session_data.get("wr", 0.0),
                            "sharpe_ratio": session_data.get("sharpe", 0.0),
                            "total_trades": session_data.get("trades", 0),
                            "sl_multiplier": session_data.get("sl_mult", 0.0),
                            "tp_ratio": session_data.get("tp_ratio", 0.0),
                        }
                
                # Also extract floors per session
                if "floors" in vbt_data:
                    for session_name, floor_data in vbt_data["floors"].items():
                        if session_name in sessions:
                            sessions[session_name]["floor_config"] = floor_data
                
                status["sessions"] = sessions
                
                # Overall results (aggregate from best session)
                if sessions:
                    best_session = max(sessions.values(), key=lambda x: x["profit_factor"])
                    status["results"] = {
                        "best_strategy": best_session["best_strategy"],
                        "profit_factor": best_session["profit_factor"],
                        "win_rate": best_session["win_rate"],
                        "sharpe_ratio": best_session["sharpe_ratio"],
                        "total_trades": best_session["total_trades"],
                        "best_session": best_session["session"],
                        "validated": True,
                    }
                
                # Get last updated time
                mtime = os.path.getmtime(vectorbt_results_file)
                status["last_updated"] = datetime.fromtimestamp(mtime).isoformat()
        except Exception as e:
            logger.warning(f"Failed to load vectorbt results for {symbol}: {e}")
            status["error"] = str(e)
            status["status"] = "error"
    
    # Fallback to onboarding_results.json if no vectorbt results
    elif not status["sessions"]:
        results_file = os.path.join(symbol_dir, "onboarding_results.json")
        if os.path.exists(results_file):
            try:
                with open(results_file) as f:
                    results = json.load(f)
                    status["status"] = "onboarded"
                    status["results"] = {
                        "best_strategy": results.get("best_strategy", "Unknown"),
                        "profit_factor": results.get("profit_factor", 0.0),
                        "win_rate": results.get("win_rate", 0.0),
                        "sharpe_ratio": results.get("sharpe_ratio", 0.0),
                        "total_trades": results.get("total_trades", 0),
                        "validated": results.get("validated", False),
                    }
                    # Get last updated time
                    mtime = os.path.getmtime(results_file)
                    status["last_updated"] = datetime.fromtimestamp(mtime).isoformat()
            except Exception as e:
                logger.warning(f"Failed to load results for {symbol}: {e}")
                status["error"] = str(e)
                status["status"] = "error"
    
    return status


def _run_onboarding(task_id: str, symbol: str):
    """Run vectorbt onboarding in background thread."""
    try:
        with _tasks_lock:
            _tasks[task_id]["status"] = "running"
            _tasks[task_id]["message"] = f"Initializing onboarding for {symbol}..."
            _tasks[task_id]["progress"] = 5
        
        # Import here to avoid circular dependencies
        from scripts.qmmp.vectorbt_onboard import VectorbtOnboarder
        
        # Create onboarder
        symbol_dir = os.path.join(QMMP_DIR, symbol)
        onboarder = VectorbtOnboarder(symbol=symbol, data_dir=symbol_dir)
        
        # Create progress tracking
        progress_stages = [
            ("Loading", 10),
            ("Data prep", 20),
            ("Session filtering", 35),
            ("Strategy testing", 70),
            ("Walk-forward validation", 85),
            ("Floor discovery", 92),
            ("EA generation", 98),
        ]
        current_stage_idx = 0
        
        # Run full onboarding
        logger.info(f"Task {task_id}: Starting {symbol} onboarding")
        
        with _tasks_lock:
            _tasks[task_id]["message"] = "Loading market data..."
            _tasks[task_id]["progress"] = 10
        
        # Run the onboarding pipeline
        success = onboarder.run_full_onboarding(min_pf=1.2)
        
        if not success:
            raise Exception("Onboarding pipeline failed")
        
        # Extract results
        results = {
            "symbol": symbol,
            "best_strategy": getattr(onboarder, 'best_strategy_name', 'Unknown'),
            "profit_factor": getattr(onboarder, 'best_pf', 0.0),
            "win_rate": getattr(onboarder, 'best_wr', 0.0),
            "sharpe_ratio": getattr(onboarder, 'best_sharpe', 0.0),
            "total_trades": getattr(onboarder, 'best_trades', 0),
            "validated": True,
            "completed_at": datetime.utcnow().isoformat(),
        }
        
        # Save results
        os.makedirs(symbol_dir, exist_ok=True)
        results_file = os.path.join(symbol_dir, "onboarding_results.json")
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        with _tasks_lock:
            _tasks[task_id]["status"] = "completed"
            _tasks[task_id]["progress"] = 100
            _tasks[task_id]["message"] = f"✓ Onboarding completed for {symbol}"
            _tasks[task_id]["completed_at"] = datetime.utcnow().isoformat()
        
        logger.info(f"Task {task_id}: Completed successfully - PF: {results['profit_factor']:.2f}")
    
    except Exception as e:
        logger.error(f"Task {task_id}: Failed with error: {e}", exc_info=True)
        with _tasks_lock:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["progress"] = 0
            _tasks[task_id]["message"] = f"Error: {str(e)}"
            _tasks[task_id]["completed_at"] = datetime.utcnow().isoformat()


def register_symbol_routes(app):
    """Register symbol management routes."""
    
    @app.route("/api/symbols", methods=["GET"])
    def list_symbols():
        """List all available symbols."""
        try:
            symbols = []
            if os.path.exists(QMMP_DIR):
                for entry in os.listdir(QMMP_DIR):
                    path = os.path.join(QMMP_DIR, entry)
                    if os.path.isdir(path):
                        symbols.append(get_symbol_status(entry))
            
            return jsonify(symbols)
        except Exception as e:
            logger.error(f"Failed to list symbols: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/symbols/<symbol>", methods=["GET"])
    def get_symbol(symbol):
        """Get status of a specific symbol."""
        try:
            status = get_symbol_status(symbol)
            return jsonify(status)
        except Exception as e:
            logger.error(f"Failed to get symbol {symbol}: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/symbols/<symbol>/onboard", methods=["POST"])
    def onboard_symbol(symbol):
        """Start onboarding process for a symbol."""
        try:
            # Create symbol directory
            symbol_dir = os.path.join(QMMP_DIR, symbol.upper())
            os.makedirs(symbol_dir, exist_ok=True)
            
            # Create and start task
            task_id = str(uuid.uuid4())
            
            with _tasks_lock:
                _tasks[task_id] = {
                    "task_id": task_id,
                    "symbol": symbol.upper(),
                    "status": "queued",
                    "progress": 0,
                    "message": f"Queued for onboarding: {symbol.upper()}",
                    "started_at": datetime.utcnow().isoformat(),
                    "completed_at": None,
                }
            
            # Start background thread
            thread = threading.Thread(
                target=_run_onboarding,
                args=(task_id, symbol.upper()),
                daemon=True
            )
            thread.start()
            
            logger.info(f"Started onboarding task {task_id} for {symbol}")
            
            return jsonify({
                "task_id": task_id,
                "symbol": symbol.upper(),
                "status": "queued",
                "message": f"Onboarding started for {symbol.upper()}"
            }), 202
        
        except Exception as e:
            logger.error(f"Failed to start onboarding for {symbol}: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/symbols/<symbol>/refresh", methods=["POST"])
    def refresh_symbol(symbol):
        """Re-run onboarding for an existing symbol."""
        try:
            # Same as onboard but will overwrite existing results
            symbol_dir = os.path.join(QMMP_DIR, symbol.upper())
            os.makedirs(symbol_dir, exist_ok=True)
            
            task_id = str(uuid.uuid4())
            
            with _tasks_lock:
                _tasks[task_id] = {
                    "task_id": task_id,
                    "symbol": symbol.upper(),
                    "status": "queued",
                    "progress": 0,
                    "message": f"Refreshing: {symbol.upper()}",
                    "started_at": datetime.utcnow().isoformat(),
                    "completed_at": None,
                }
            
            thread = threading.Thread(
                target=_run_onboarding,
                args=(task_id, symbol.upper()),
                daemon=True
            )
            thread.start()
            
            logger.info(f"Started refresh task {task_id} for {symbol}")
            
            return jsonify({
                "task_id": task_id,
                "symbol": symbol.upper(),
                "status": "queued",
                "message": f"Refresh started for {symbol.upper()}"
            }), 202
        
        except Exception as e:
            logger.error(f"Failed to refresh {symbol}: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/symbols/<symbol>", methods=["DELETE"])
    def remove_symbol(symbol):
        """Remove a symbol and its data."""
        try:
            symbol_dir = os.path.join(QMMP_DIR, symbol.upper())
            
            if os.path.exists(symbol_dir):
                import shutil
                shutil.rmtree(symbol_dir)
                logger.info(f"Removed symbol {symbol}")
            
            return jsonify({
                "symbol": symbol.upper(),
                "message": f"Symbol {symbol.upper()} removed"
            })
        
        except Exception as e:
            logger.error(f"Failed to remove {symbol}: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/tasks", methods=["GET"])
    def list_tasks():
        """List all onboarding tasks."""
        try:
            with _tasks_lock:
                tasks = list(_tasks.values())
            
            # Sort by started_at descending (newest first)
            tasks.sort(key=lambda t: t["started_at"], reverse=True)
            
            return jsonify(tasks)
        except Exception as e:
            logger.error(f"Failed to list tasks: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/api/tasks/<task_id>", methods=["GET"])
    def get_task(task_id):
        """Get status of a specific task."""
        try:
            with _tasks_lock:
                task = _tasks.get(task_id)
            
            if not task:
                return jsonify({"error": "Task not found"}), 404
            
            return jsonify(task)
        except Exception as e:
            logger.error(f"Failed to get task {task_id}: {e}")
            return jsonify({"error": str(e)}), 500
    
    logger.info("Symbol management routes registered")
