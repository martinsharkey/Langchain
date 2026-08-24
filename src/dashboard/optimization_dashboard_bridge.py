"""
Optimization Dashboard Integration Bridge

Connects the dashboard UI controls to the live ParameterOptimizer.

When user toggles a session enable/disable:
1. Dashboard calls POST /api/v2/optimization/control/{symbol}/{session}
2. Bridge applies the change to ParameterOptimizer.tuned
3. Live trading immediately uses updated params
4. Change is persisted to tuned_params.json

This ensures dashboard UI changes directly affect live trading behavior.
"""

import json
import os
from typing import Dict, Optional
from pathlib import Path

from src import config
from src.utils.logger import get_logger
from src.dashboard.optimization_results_component import SessionOptimizationDashboard
from src.learning.param_optimizer import ParameterOptimizer

logger = get_logger("optimization_dashboard_bridge")

TUNED_PATH = os.path.join(config.DATA_DIR, "tuned_params.json")


class OptimizationDashboardBridge:
    """Bridge between dashboard UI and live parameter optimizer"""
    
    def __init__(self):
        self.param_optimizer = ParameterOptimizer()
    
    def apply_session_toggle(self, symbol: str, session: str, enabled: bool) -> Dict:
        """
        Apply enable/disable toggle from dashboard to live trading.
        
        Args:
            symbol: Trading symbol (XAUUSD, BTCUSD, etc.)
            session: Trading session (Asian, London, NewYork)
            enabled: True to enable, False to disable
        
        Returns:
            Dict with status, applied params, and confirmation
        """
        try:
            # Load current optimization results
            dashboard = SessionOptimizationDashboard(symbol=symbol)
            dashboard.load_from_files()
            
            if session not in dashboard.results:
                return {
                    "error": f"Session {session} not found",
                    "status": "error",
                    "applied": False
                }
            
            result = dashboard.results[session]
            
            # Validate that session has finalized optimization
            if result.status.value not in ["accepted", "rejected"]:
                return {
                    "error": f"Cannot modify: session status is {result.status.value}",
                    "status": "error",
                    "applied": False
                }
            
            # Get params to apply
            if enabled and result.status.value == "accepted" and result.validation:
                # Use tuned params
                params_to_apply = result.optuna.tuned_params if result.optuna else None
                param_source = "tuned"
            else:
                # Use baseline params
                params_to_apply = result.optuna.baseline_params if result.optuna else None
                param_source = "baseline"
            
            if not params_to_apply:
                return {
                    "error": "No parameters available for this session",
                    "status": "error",
                    "applied": False
                }
            
            # Create session key for tracking
            session_key = f"{symbol}__{session}"
            
            # Apply to ParameterOptimizer
            self.param_optimizer.apply_session_params(session_key, params_to_apply)
            
            # Persist to tuned_params.json
            self._persist_session_state(symbol, session, enabled, params_to_apply, param_source)
            
            logger.info(f"✓ Applied {param_source} params for {symbol}/{session} (enabled={enabled})")
            
            return {
                "symbol": symbol,
                "session": session,
                "enabled": enabled,
                "status": "applied",
                "applied": True,
                "param_source": param_source,
                "params": params_to_apply,
                "message": f"Session {session} now using {param_source} parameters for live trading"
            }
        
        except Exception as e:
            logger.error(f"Failed to apply session toggle: {e}", exc_info=True)
            return {
                "error": str(e),
                "status": "error",
                "applied": False
            }
    
    def _persist_session_state(self, symbol: str, session: str, enabled: bool, 
                              params: Dict, source: str) -> None:
        """
        Persist session state to tuned_params.json
        
        Tracks which sessions are enabled and what params are active.
        """
        try:
            # Load existing tuned params
            if os.path.exists(TUNED_PATH):
                with open(TUNED_PATH) as f:
                    data = json.load(f)
            else:
                data = {}
            
            # Ensure symbol entry exists
            if symbol not in data:
                data[symbol] = {}
            
            # Ensure sessions dict exists
            if "sessions" not in data[symbol]:
                data[symbol]["sessions"] = {}
            
            # Update session state
            data[symbol]["sessions"][session] = {
                "enabled": enabled,
                "params": params,
                "source": source,
                "updated_at": str(__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())
            }
            
            # Save back
            os.makedirs(os.path.dirname(TUNED_PATH), exist_ok=True)
            with open(TUNED_PATH, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Persisted session state: {symbol}/{session} (enabled={enabled}, source={source})")
        
        except Exception as e:
            logger.error(f"Failed to persist session state: {e}")
            # Don't fail the whole operation if persistence fails
            pass
    
    def get_session_state(self, symbol: str, session: str) -> Optional[Dict]:
        """Get current state of a session from tuned_params.json"""
        try:
            if not os.path.exists(TUNED_PATH):
                return None
            
            with open(TUNED_PATH) as f:
                data = json.load(f)
            
            if symbol not in data:
                return None
            
            if "sessions" not in data[symbol]:
                return None
            
            return data[symbol]["sessions"].get(session)
        
        except Exception as e:
            logger.error(f"Failed to get session state: {e}")
            return None
    
    def restore_session_states(self, symbol: str) -> Dict[str, bool]:
        """
        Restore all session states from tuned_params.json when bot starts.
        
        Called on initialization to ensure live trading resumes with correct params.
        
        Returns: Dict[session_name] -> enabled
        """
        try:
            restored = {}
            
            if not os.path.exists(TUNED_PATH):
                logger.debug("No tuned_params.json found, using defaults")
                return restored
            
            with open(TUNED_PATH) as f:
                data = json.load(f)
            
            if symbol not in data or "sessions" not in data[symbol]:
                logger.debug(f"No session states for {symbol}")
                return restored
            
            for session, state in data[symbol]["sessions"].items():
                if state.get("enabled"):
                    params = state.get("params")
                    if params:
                        session_key = f"{symbol}__{session}"
                        self.param_optimizer.apply_session_params(session_key, params)
                        restored[session] = True
                        logger.info(f"✓ Restored {session} params for {symbol}")
            
            return restored
        
        except Exception as e:
            logger.error(f"Failed to restore session states: {e}")
            return {}


class ParameterOptimizerExtension:
    """Extension methods for ParameterOptimizer to support dashboard integration"""
    
    @staticmethod
    def apply_session_params(self, session_key: str, params: Dict) -> None:
        """
        Apply session-specific parameters to the optimizer.
        
        Args:
            session_key: "{SYMBOL}__{SESSION}" (e.g., "XAUUSD__Asian")
            params: Parameter dict from optimization results
        """
        try:
            # Ensure tuned dict exists
            if not hasattr(self, 'tuned'):
                self.tuned = {}
            
            # Store params
            self.tuned[session_key] = params
            
            logger.debug(f"Applied params for {session_key}: {list(params.keys())}")
        
        except Exception as e:
            logger.error(f"Failed to apply session params: {e}")
