"""
StrategyConfigManager: Load and manage per-symbol strategy configurations from JSON.

This module provides a configuration-driven interface to strategy selection,
replacing the hardcoded FOCUSED_EDGE in edge_weights.py. It reads from
data/strategy_config.json and supports hot-reload without bot restart.

Key responsibilities:
  1. Load strategy_config.json at startup
  2. Provide per-symbol ranked strategy lists
  3. Return strategy parameters for a given symbol and strategy
  4. Support hot-reload for runtime config updates
  5. Validate configuration integrity
"""

import os
import json
import logging
from typing import Optional, List, Dict, Tuple, Set
from dataclasses import dataclass, asdict
import threading
import time

_log = logging.getLogger("strategy_config_manager")


@dataclass
class StrategyParameters:
    """Strategy-specific parameter values."""
    pass  # Will be dynamically populated from config JSON


@dataclass
class StrategyEntry:
    """Single strategy in a per-symbol configuration."""
    rank: int
    strategy: str
    enabled: bool
    description: str
    parameters: Dict
    performance: Dict
    optuna_study: Optional[str]
    notes: str


class StrategyConfigManager:
    """Manages per-symbol strategy configuration loaded from JSON."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the config manager and load initial configuration.
        
        Args:
            config_path: Path to strategy_config.json. If None, uses default location.
        """
        self.config_path = config_path or self._default_config_path()
        self._config = {}
        self._lock = threading.RLock()
        self._last_load_time = 0
        self._load_config()
    
    @staticmethod
    def _default_config_path() -> str:
        """Get default path to strategy_config.json."""
        try:
            from src import config
            base = config.DATA_DIR
        except Exception:
            base = os.path.join(os.getcwd(), "data")
        return os.path.join(base, "strategy_config.json")
    
    def _load_config(self) -> bool:
        """Load configuration from JSON file.
        
        Returns:
            True if successfully loaded, False otherwise.
        """
        try:
            if not os.path.exists(self.config_path):
                _log.warning(f"strategy_config.json not found at {self.config_path}")
                return False
            
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                self._config = data
                self._last_load_time = time.time()
            
            _log.info(f"Loaded strategy config with {len(data.get('strategies', {}))} symbols")
            return True
        
        except json.JSONDecodeError as e:
            _log.error(f"Invalid JSON in strategy_config.json: {e}")
            return False
        except Exception as e:
            _log.error(f"Failed to load strategy_config.json: {e}")
            return False
    
    def reload(self) -> bool:
        """Reload configuration from disk (hot-reload support).
        
        Returns:
            True if successfully reloaded, False otherwise.
        """
        return self._load_config()
    
    def get_ranked_strategies(self, symbol: str) -> Optional[List[Tuple[str, Set[str]]]]:
        """Get ranked list of (strategy_name, allowed_regimes) for a symbol.
        
        This replaces focused_rules() from edge_weights.py and provides the same
        interface: a list of (strategy_name, set_of_allowed_regimes) tuples.
        
        Args:
            symbol: Symbol name (e.g., "XAUUSD", "BTCUSD")
        
        Returns:
            List of (strategy_name, allowed_regimes_set) sorted by rank, or None
            if symbol not found in config.
        """
        if not symbol:
            return None
        
        with self._lock:
            strategies_by_symbol = self._config.get("strategies", {})
        
        # Try exact match first, then prefix match
        su = symbol.upper()
        for key in strategies_by_symbol.keys():
            if su == key.upper() or su.startswith(key.upper()):
                entries = strategies_by_symbol[key]
                # Sort by rank and return only enabled strategies
                entries_sorted = sorted(
                    [e for e in entries if e.get("enabled", True)],
                    key=lambda x: x.get("rank", 999)
                )
                return [
                    (e["strategy"], set(e.get("parameters", {}).keys()) if "parameters" in e else set())
                    for e in entries_sorted
                ]
        
        return None
    
    def get_strategy_parameters(self, symbol: str, strategy: str) -> Optional[Dict]:
        """Get parameters for a specific strategy on a symbol.
        
        Args:
            symbol: Symbol name
            strategy: Strategy name
        
        Returns:
            Dictionary of parameters, or None if not found.
        """
        if not symbol or not strategy:
            return None
        
        with self._lock:
            strategies_by_symbol = self._config.get("strategies", {})
        
        su = symbol.upper()
        for key in strategies_by_symbol.keys():
            if su == key.upper() or su.startswith(key.upper()):
                entries = strategies_by_symbol[key]
                for entry in entries:
                    if entry.get("strategy") == strategy:
                        return entry.get("parameters", {})
        
        return None
    
    def get_strategy_info(self, symbol: str, strategy: str) -> Optional[Dict]:
        """Get full strategy entry including performance metrics and metadata.
        
        Args:
            symbol: Symbol name
            strategy: Strategy name
        
        Returns:
            Full strategy entry dict, or None if not found.
        """
        if not symbol or not strategy:
            return None
        
        with self._lock:
            strategies_by_symbol = self._config.get("strategies", {})
        
        su = symbol.upper()
        for key in strategies_by_symbol.keys():
            if su == key.upper() or su.startswith(key.upper()):
                entries = strategies_by_symbol[key]
                for entry in entries:
                    if entry.get("strategy") == strategy:
                        return entry
        
        return None
    
    def get_all_symbols(self) -> List[str]:
        """Get list of all configured symbols."""
        with self._lock:
            return list(self._config.get("strategies", {}).keys())
    
    def get_defaults(self) -> Dict:
        """Get default configuration settings."""
        with self._lock:
            return self._config.get("defaults", {})
    
    def is_fallback_on_hold_enabled(self) -> bool:
        """Check if fallback-on-hold is enabled in defaults."""
        defaults = self.get_defaults()
        return defaults.get("fallback_on_hold", True)
    
    def validate_config(self) -> Tuple[bool, List[str]]:
        """Validate configuration integrity.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        with self._lock:
            config = self._config
        
        if not config:
            errors.append("Configuration is empty")
            return False, errors
        
        version = config.get("version")
        if not version:
            errors.append("Missing 'version' field")
        
        strategies = config.get("strategies", {})
        if not strategies:
            errors.append("No strategies defined")
            return False, errors
        
        for symbol, entries in strategies.items():
            if not isinstance(entries, list):
                errors.append(f"Symbol '{symbol}' strategies is not a list")
                continue
            
            for i, entry in enumerate(entries):
                # Check required fields
                if "strategy" not in entry:
                    errors.append(f"  {symbol}[{i}]: missing 'strategy' field")
                if "rank" not in entry:
                    errors.append(f"  {symbol}[{i}]: missing 'rank' field")
                if "parameters" not in entry:
                    errors.append(f"  {symbol}[{i}]: missing 'parameters' field")
                
                # Check performance metrics
                perf = entry.get("performance", {})
                if "last_validated" in perf:
                    try:
                        # Simple check that it's a valid ISO timestamp-like string
                        if not isinstance(perf["last_validated"], str):
                            errors.append(f"  {symbol}[{i}]: performance.last_validated is not a string")
                    except:
                        pass
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    def get_config_summary(self) -> Dict:
        """Get a summary of the configuration (counts, versions, etc)."""
        with self._lock:
            config = self._config
        
        strategies = config.get("strategies", {})
        
        summary = {
            "version": config.get("version"),
            "num_symbols": len(strategies),
            "symbols": list(strategies.keys()),
            "total_strategy_entries": sum(len(v) for v in strategies.values()),
            "enabled_entries": sum(
                len([e for e in v if e.get("enabled", True)])
                for v in strategies.values()
            ),
            "last_loaded": self._last_load_time,
        }
        
        return summary


# Global singleton instance
_manager: Optional[StrategyConfigManager] = None


def initialize(config_path: Optional[str] = None) -> StrategyConfigManager:
    """Initialize the global StrategyConfigManager instance.
    
    Args:
        config_path: Optional path to strategy_config.json
    
    Returns:
        The initialized manager instance.
    """
    global _manager
    if _manager is None:
        _manager = StrategyConfigManager(config_path)
    return _manager


def get_manager() -> StrategyConfigManager:
    """Get the global StrategyConfigManager instance.
    
    Returns:
        The manager instance, or raises RuntimeError if not initialized.
    """
    global _manager
    if _manager is None:
        raise RuntimeError("StrategyConfigManager not initialized. Call initialize() first.")
    return _manager
