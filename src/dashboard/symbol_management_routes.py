"""
Symbol Management API Routes for Dashboard.

Endpoints:
  POST   /api/symbols                   - Add a symbol for onboarding
  GET    /api/symbols                   - List all available symbols
  DELETE /api/symbols/{symbol}          - Remove a symbol
  GET    /api/symbols/{symbol}/status   - Get onboarding status for symbol
  POST   /api/symbols/{symbol}/onboard  - Start onboarding for symbol
  GET    /api/onboarding/tasks          - List active onboarding tasks
"""

from flask import Blueprint, jsonify, request
import logging
import json
import os
from pathlib import Path
from datetime import datetime
import subprocess
import threading

_log = logging.getLogger("symbol_management_routes")

bp = Blueprint("symbol_management", __name__, url_prefix="/api")

# Store active onboarding tasks
_onboarding_tasks = {}
_tasks_lock = threading.Lock()

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent


def _get_symbol_data_dir(symbol: str) -> Path:
    """Get data directory for symbol."""
    return PROJECT_ROOT / "data" / "qmmp" / symbol


def _get_onboarding_status(symbol: str) -> dict:
    """Get current onboarding status for symbol."""
    symbol_dir = _get_symbol_data_dir(symbol)
    
    if not symbol_dir.exists():
        return {
            "symbol": symbol,
            "status": "not_started",
            "phase1_complete": False,
            "phase2_complete": False,
            "phase3_complete": False,
            "sessions": []
        }
    
    # Check which phases are complete
    phase1_file = symbol_dir / "phase1_vectorbt_discovery.json"
    phase2_dir = symbol_dir / "phase2_optuna_tuning"
    phase3_file = symbol_dir / f"phase3_validation_{symbol}.json"
    
    phase1_complete = phase1_file.exists()
    phase2_complete = phase2_dir.exists() and (phase2_dir / "completed.txt").exists()
    phase3_complete = phase3_file.exists()
    
    # Load sessions if available
    sessions = []
    if phase1_complete:
        try:
            with open(phase1_file) as f:
                discovery = json.load(f)
                sessions = list(discovery.get("sessions", {}).keys())
        except:
            pass
    
    # Determine overall status
    if phase3_complete:
        status = "validated"
    elif phase2_complete:
        status = "tuned"
    elif phase1_complete:
        status = "discovered"
    else:
        status = "not_started"
    
    return {
        "symbol": symbol,
        "status": status,
        "phase1_complete": phase1_complete,
        "phase2_complete": phase2_complete,
        "phase3_complete": phase3_complete,
        "sessions": sessions,
        "last_updated": datetime.now().isoformat()
    }


@bp.route("/symbols", methods=["POST"])
def add_symbol():
    """Add a symbol for onboarding.
    
    Request body: {
      "symbol": "XAUUSD"
    }
    
    Returns: {
      "status": "ok",
      "symbol": "XAUUSD",
      "message": "Symbol added successfully"
    }
    """
    try:
        data = request.get_json() or {}
        symbol = data.get("symbol", "").upper().strip()
        
        if not symbol:
            return jsonify({"error": "Symbol is required"}), 400
        
        if len(symbol) < 2 or len(symbol) > 20:
            return jsonify({"error": "Symbol must be 2-20 characters"}), 400
        
        # Create symbol directory
        symbol_dir = _get_symbol_data_dir(symbol)
        symbol_dir.mkdir(parents=True, exist_ok=True)
        
        # Create metadata file
        metadata = {
            "symbol": symbol,
            "added_at": datetime.now().isoformat(),
            "status": "pending_onboarding"
        }
        
        metadata_file = symbol_dir / "metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        _log.info(f"Added symbol {symbol} for onboarding")
        
        return jsonify({
            "status": "ok",
            "symbol": symbol,
            "message": f"Symbol {symbol} added successfully"
        }), 201
    
    except Exception as e:
        _log.error(f"Error adding symbol: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/symbols", methods=["GET"])
def list_symbols():
    """List all available symbols and their onboarding status.
    
    Returns: {
      "status": "ok",
      "symbols": [
        {
          "symbol": "XAUUSD",
          "status": "discovered",
          "phase1_complete": true,
          "phase2_complete": false,
          "phase3_complete": false
        },
        ...
      ]
    }
    """
    try:
        data_dir = PROJECT_ROOT / "data" / "qmmp"
        
        if not data_dir.exists():
            return jsonify({"status": "ok", "symbols": []})
        
        symbols = []
        for symbol_dir in data_dir.iterdir():
            if symbol_dir.is_dir():
                symbol = symbol_dir.name
                status = _get_onboarding_status(symbol)
                symbols.append(status)
        
        # Sort by status
        status_order = {"validated": 0, "tuned": 1, "discovered": 2, "not_started": 3}
        symbols.sort(key=lambda s: status_order.get(s["status"], 4))
        
        return jsonify({
            "status": "ok",
            "symbols": symbols,
            "total": len(symbols)
        })
    
    except Exception as e:
        _log.error(f"Error listing symbols: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/symbols/<symbol>", methods=["DELETE"])
def delete_symbol(symbol: str):
    """Remove a symbol (and its onboarding data).
    
    Returns: {
      "status": "ok",
      "message": "Symbol XAUUSD deleted"
    }
    """
    try:
        symbol = symbol.upper()
        symbol_dir = _get_symbol_data_dir(symbol)
        
        if not symbol_dir.exists():
            return jsonify({"error": f"Symbol {symbol} not found"}), 404
        
        # Check if onboarding is in progress
        with _tasks_lock:
            if symbol in _onboarding_tasks:
                task = _onboarding_tasks[symbol]
                if task["status"] == "running":
                    return jsonify({"error": f"Cannot delete {symbol}: onboarding in progress"}), 409
        
        # Delete directory (in background to avoid blocking)
        import shutil
        try:
            shutil.rmtree(symbol_dir)
            _log.info(f"Deleted symbol {symbol}")
        except Exception as e:
            _log.warning(f"Could not immediately delete {symbol_dir}: {e}")
        
        return jsonify({
            "status": "ok",
            "message": f"Symbol {symbol} deleted"
        })
    
    except Exception as e:
        _log.error(f"Error deleting symbol: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/symbols/<symbol>/status", methods=["GET"])
def get_symbol_status(symbol: str):
    """Get detailed onboarding status for a symbol.
    
    Returns: {
      "symbol": "XAUUSD",
      "status": "discovered",
      "phase1": {
        "complete": true,
        "best_indicators": [...],
        "discovered_at": "2026-08-24T..."
      },
      "phase2": {
        "complete": false,
        "status": "pending"
      },
      "phase3": {
        "complete": false,
        "status": "pending"
      },
      "sessions": ["asian", "london", ...]
    }
    """
    try:
        symbol = symbol.upper()
        status = _get_onboarding_status(symbol)
        symbol_dir = _get_symbol_data_dir(symbol)
        
        # Add phase details if available
        phase1_file = symbol_dir / "phase1_vectorbt_discovery.json"
        if phase1_file.exists():
            with open(phase1_file) as f:
                phase1_data = json.load(f)
                status["phase1"] = {
                    "complete": True,
                    "discovered_at": phase1_data.get("timestamp"),
                    "sessions_analyzed": len(phase1_data.get("sessions", {}))
                }
        
        # Check phase 2
        phase2_dir = symbol_dir / "phase2_optuna_tuning"
        if phase2_dir.exists():
            status["phase2"] = {
                "complete": (phase2_dir / "completed.txt").exists(),
                "status": "tuning"
            }
        
        # Check phase 3
        phase3_file = symbol_dir / f"phase3_validation_{symbol}.json"
        if phase3_file.exists():
            with open(phase3_file) as f:
                phase3_data = json.load(f)
                status["phase3"] = {
                    "complete": True,
                    "validated_at": phase3_data.get("timestamp"),
                    "sessions_validated": len(phase3_data.get("sessions", {}))
                }
        
        return jsonify({"status": "ok", "data": status})
    
    except Exception as e:
        _log.error(f"Error getting symbol status: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/onboarding/tasks", methods=["GET"])
def list_onboarding_tasks():
    """Get list of all onboarding tasks (running and completed).
    
    Returns: {
      "status": "ok",
      "tasks": [
        {
          "task_id": "xauusd_onboard_20260824_120000",
          "symbol": "XAUUSD",
          "status": "running",
          "started_at": "2026-08-24T12:00:00",
          "progress_pct": 45
        },
        ...
      ],
      "running_count": 1,
      "completed_count": 3
    }
    """
    try:
        with _tasks_lock:
            tasks = list(_onboarding_tasks.values())
        
        # Calculate progress for running tasks
        for task in tasks:
            if task["status"] == "running":
                # Check if symbol dir exists and has phase files
                symbol_dir = _get_symbol_data_dir(task["symbol"])
                
                phase1_complete = (symbol_dir / "phase1_vectorbt_discovery.json").exists()
                phase2_complete = (symbol_dir / "phase2_optuna_tuning" / "completed.txt").exists()
                phase3_complete = (symbol_dir / f"phase3_validation_{task['symbol']}.json").exists()
                
                if phase3_complete:
                    task["progress_pct"] = 100
                    task["current_phase"] = "validation"
                elif phase2_complete:
                    task["progress_pct"] = 70
                    task["current_phase"] = "tuning"
                elif phase1_complete:
                    task["progress_pct"] = 40
                    task["current_phase"] = "discovery"
                else:
                    task["progress_pct"] = 10
                    task["current_phase"] = "initializing"
        
        running = [t for t in tasks if t["status"] == "running"]
        completed = [t for t in tasks if t["status"] in ("completed", "failed", "timeout")]
        
        return jsonify({
            "status": "ok",
            "tasks": tasks,
            "running_count": len(running),
            "completed_count": len(completed),
            "total": len(tasks)
        })
    
    except Exception as e:
        _log.error(f"Error listing tasks: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/onboarding/tasks/<task_id>", methods=["GET"])
def get_task_status(task_id: str):
    """Get detailed status of a specific onboarding task.
    
    Returns: {
      "task_id": "xauusd_onboard_20260824_120000",
      "symbol": "XAUUSD",
      "status": "running",
      "progress_pct": 45,
      "current_phase": "discovery",
      "started_at": "2026-08-24T12:00:00",
      "estimated_completion": "2026-08-24T13:00:00"
    }
    """
    try:
        with _tasks_lock:
            task = None
            for t in _onboarding_tasks.values():
                if t["task_id"] == task_id:
                    task = t
                    break
        
        if not task:
            return jsonify({"error": f"Task {task_id} not found"}), 404
        
        return jsonify({"status": "ok", "data": task})
    
    except Exception as e:
        _log.error(f"Error getting task status: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/symbols/live", methods=["GET"])
def list_live_symbols():
    """Get all tradeable MT5 symbols, sorted alphabetical (live from broker)."""
    try:
        from src.onboarding.data import get_mt5_symbols

        symbols = get_mt5_symbols()
        return jsonify({"status": "ok", "symbols": symbols}), 200
    except Exception as e:
        _log.error(f"Error listing MT5 symbols: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/symbols/<symbol>/onboard", methods=["POST"])
def start_onboarding(symbol: str):
    """Start onboarding process for a symbol with full wizard config.

    Request body: {
      "sessions": ["asian", "london"],
      "timeframes": ["M1", "M5", "M15", "H1"],
      "start_date": "2024-08-26",
      "end_date": "2026-08-26",
      "top_n": 10
    }

    Returns: {
      "status": "ok",
      "task_id": "btcusd_onboard_20260826_235500",
      "symbol": "BTCUSD",
      "estimated_seconds": 1234.5,
      "message": "Onboarding started"
    }
    """
    try:
        symbol = symbol.upper()
        data = request.get_json() or {}

        sessions = data.get("sessions") or []
        timeframes = data.get("timeframes") or []
        start_date_str = data.get("start_date")
        end_date_str = data.get("end_date")
        top_n = data.get("top_n", 10)

        if not sessions or not timeframes:
            return jsonify({"error": "sessions and timeframes are required"}), 400

        # Parse dates (UTC).
        from datetime import datetime, timezone
        if start_date_str:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            start_date = datetime(2024, 8, 26, tzinfo=timezone.utc)
        if end_date_str:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=timezone.utc)
        else:
            end_date = datetime.now(timezone.utc)

        # Check if already onboarding.
        with _tasks_lock:
            if symbol in _onboarding_tasks:
                task = _onboarding_tasks[symbol]
                if task["status"] == "running":
                    return jsonify({
                        "error": f"Onboarding already running for {symbol}",
                        "task_id": task["task_id"]
                    }), 409

        task_id = f"{symbol.lower()}_onboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        task_info = {
            "task_id": task_id,
            "symbol": symbol,
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "config": {
                "sessions": sessions,
                "timeframes": timeframes,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "process": None,
        }

        def run_onboarding():
            try:
                from src.onboarding.orchestrator import OnboardingOrchestrator

                orch = OnboardingOrchestrator(
                    symbol=symbol,
                    sessions=sessions,
                    timeframes=timeframes,
                    start_date=start_date,
                    end_date=end_date,
                    top_n=top_n,
                )
                orch.run()
                task_info["status"] = "completed"
                task_info["completed_at"] = datetime.now().isoformat()
                _log.info(f"Onboarding {symbol} completed")
            except Exception as e:
                task_info["status"] = "failed"
                task_info["error"] = str(e)
                task_info["completed_at"] = datetime.now().isoformat()
                _log.error(f"Onboarding error for {symbol}: {e}", exc_info=True)

        with _tasks_lock:
            _onboarding_tasks[symbol] = task_info

        from src.onboarding.orchestrator import OnboardingOrchestrator
        orch = OnboardingOrchestrator(
            symbol=symbol, sessions=sessions, timeframes=timeframes,
            start_date=start_date, end_date=end_date, top_n=top_n,
        )
        estimated = orch.estimate_runtime_seconds()

        thread = threading.Thread(target=run_onboarding, daemon=True, name=f"onboard_{symbol}")
        thread.start()
        task_info["process"] = thread.ident

        _log.info(f"Started onboarding for {symbol} (est. {estimated:.0f}s)")

        return jsonify({
            "status": "ok",
            "task_id": task_id,
            "symbol": symbol,
            "estimated_seconds": round(estimated, 1),
            "message": f"Onboarding started for {symbol}",
        }), 201

    except Exception as e:
        _log.error(f"Error starting onboarding: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/onboarding/<symbol>/progress", methods=["GET"])
def get_onboarding_progress(symbol: str):
    """Get real-time progress markers for a symbol's onboarding."""
    try:
        symbol = symbol.upper()
        output_dir = PROJECT_ROOT / "tests" / "onboarding" / symbol
        from src.onboarding.orchestrator import read_progress

        markers = read_progress(output_dir)
        return jsonify({"status": "ok", "symbol": symbol, "progress": markers}), 200
    except Exception as e:
        _log.error(f"Error reading progress for {symbol}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/onboarding/<symbol>/results", methods=["GET"])
def get_onboarding_results(symbol: str):
    """Get live results rows for a symbol's onboarding."""
    try:
        symbol = symbol.upper()
        output_dir = PROJECT_ROOT / "tests" / "onboarding" / symbol
        from src.onboarding.orchestrator import read_live_results

        results = read_live_results(output_dir)
        return jsonify({"status": "ok", "symbol": symbol, "results": results}), 200
    except Exception as e:
        _log.error(f"Error reading results for {symbol}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/onboarding/<symbol>/download", methods=["GET"])
def download_onboarding(symbol: str):
    """Download the raw onboarding JSON file."""
    try:
        from flask import send_file

        symbol = symbol.upper()
        output_dir = PROJECT_ROOT / "tests" / "onboarding" / symbol
        # Find the most recent raw JSON file.
        files = sorted(output_dir.glob(f"{symbol}_onboarding_*.json"), reverse=True)
        if not files:
            return jsonify({"error": f"No onboarding results for {symbol}"}), 404
        return send_file(files[0], as_attachment=True, download_name=files[0].name)
    except Exception as e:
        _log.error(f"Error downloading for {symbol}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def register_routes(app):
    """Register symbol management routes with Flask app."""
    app.register_blueprint(bp)
    _log.info("Registered Symbol Management routes")
