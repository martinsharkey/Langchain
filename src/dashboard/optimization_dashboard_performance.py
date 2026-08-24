"""
Optimization Dashboard - Performance Optimization Module

Provides caching, query optimization, and performance monitoring
to ensure dashboard responsiveness at scale.
"""

import json
import os
import time
from typing import Dict, Optional, Any
from functools import lru_cache, wraps
from datetime import datetime, timedelta
import threading

from src.utils.logger import get_logger

logger = get_logger("optimization_dashboard_perf")


class CachedOptimizationDashboard:
    """
    Caching wrapper for SessionOptimizationDashboard to reduce disk I/O
    and improve query performance.
    """
    
    def __init__(self, symbol: str, cache_ttl_seconds: int = 30):
        """
        Args:
            symbol: Trading symbol
            cache_ttl_seconds: Cache time-to-live in seconds (default 30s)
        """
        self.symbol = symbol
        self.cache_ttl = cache_ttl_seconds
        self._cache = {}
        self._cache_times = {}
        self._lock = threading.RLock()
    
    def get_results(self, force_refresh: bool = False) -> Dict:
        """
        Get optimization results with caching.
        
        Args:
            force_refresh: Bypass cache and reload from disk
        
        Returns:
            Cached or fresh optimization results
        """
        cache_key = f"results_{self.symbol}"
        
        if not force_refresh and self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        # Load from disk (uncached operation)
        start_time = time.time()
        from src.dashboard.optimization_results_component import SessionOptimizationDashboard
        
        try:
            dashboard = SessionOptimizationDashboard(symbol=self.symbol)
            dashboard.load_from_files()
            
            # Convert results to dict for serialization
            results = {
                session: self._result_to_dict(result)
                for session, result in dashboard.results.items()
            }
            
            elapsed = time.time() - start_time
            logger.debug(f"Loaded {len(results)} sessions for {self.symbol} in {elapsed:.3f}s")
            
            # Update cache
            with self._lock:
                self._cache[cache_key] = results
                self._cache_times[cache_key] = datetime.now()
            
            return results
        
        except Exception as e:
            logger.error(f"Failed to load results for {self.symbol}: {e}")
            # Return cached data even if stale, rather than failing
            if cache_key in self._cache:
                logger.warning(f"Returning stale cache for {self.symbol}")
                return self._cache[cache_key]
            return {}
    
    def get_session(self, session: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        Get specific session result with caching.
        
        Args:
            session: Session name
            force_refresh: Bypass cache
        
        Returns:
            Session result dict or None if not found
        """
        results = self.get_results(force_refresh=force_refresh)
        return results.get(session)
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid"""
        if cache_key not in self._cache_times:
            return False
        
        age = datetime.now() - self._cache_times[cache_key]
        return age.total_seconds() < self.cache_ttl
    
    def invalidate_cache(self):
        """Force cache invalidation (call after toggle operations)"""
        with self._lock:
            self._cache.clear()
            self._cache_times.clear()
    
    @staticmethod
    def _result_to_dict(result) -> Dict:
        """Convert SessionOptimizationResult to dict for serialization"""
        return {
            "status": result.status.value if hasattr(result.status, 'value') else str(result.status),
            "symbol": result.symbol,
            "session": result.session,
            "enabled": result.is_enabled() if hasattr(result, 'is_enabled') else True,
            "discovery": {
                "indicator_name": result.discovery.indicator_name,
                "timeframe": result.discovery.timeframe,
                "baseline_profit_factor": result.discovery.baseline_profit_factor,
                "baseline_trades": result.discovery.baseline_trades
            } if result.discovery else None,
            "optuna": {
                "num_trials": result.optuna.num_trials,
                "baseline_profit_factor": result.optuna.baseline_profit_factor,
                "tuned_profit_factor": result.optuna.tuned_profit_factor,
                "improvement_pct": result.optuna.improvement_pct
            } if result.optuna else None,
            "validation": {
                "test_profit_factor": result.validation.test_profit_factor,
                "train_test_gap_pct": result.validation.train_test_gap_pct,
                "is_acceptable": result.validation.is_acceptable
            } if result.validation else None,
            "created_at": result.created_at.isoformat() if result.created_at else None,
            "updated_at": result.updated_at.isoformat() if result.updated_at else None
        }


class PerformanceMetrics:
    """Track performance metrics for monitoring and optimization"""
    
    def __init__(self):
        self.api_calls = {}
        self.cache_hits = 0
        self.cache_misses = 0
        self.toggle_operations = 0
        self.errors = 0
        self._lock = threading.RLock()
    
    def record_api_call(self, endpoint: str, elapsed_ms: float):
        """Record API call latency"""
        with self._lock:
            if endpoint not in self.api_calls:
                self.api_calls[endpoint] = []
            
            self.api_calls[endpoint].append(elapsed_ms)
            
            # Keep only recent calls (last 1000)
            if len(self.api_calls[endpoint]) > 1000:
                self.api_calls[endpoint] = self.api_calls[endpoint][-1000:]
    
    def record_cache_hit(self):
        """Record cache hit"""
        with self._lock:
            self.cache_hits += 1
    
    def record_cache_miss(self):
        """Record cache miss"""
        with self._lock:
            self.cache_misses += 1
    
    def record_toggle(self):
        """Record toggle operation"""
        with self._lock:
            self.toggle_operations += 1
    
    def record_error(self):
        """Record error"""
        with self._lock:
            self.errors += 1
    
    def get_stats(self) -> Dict:
        """Get current performance statistics"""
        with self._lock:
            total_calls = self.cache_hits + self.cache_misses
            cache_hit_rate = (
                (self.cache_hits / total_calls * 100) if total_calls > 0 else 0
            )
            
            api_latencies = {}
            for endpoint, times in self.api_calls.items():
                if times:
                    api_latencies[endpoint] = {
                        "min_ms": min(times),
                        "max_ms": max(times),
                        "avg_ms": sum(times) / len(times),
                        "p95_ms": sorted(times)[int(len(times) * 0.95)] if len(times) > 1 else times[0],
                        "calls": len(times)
                    }
            
            return {
                "cache_hit_rate_pct": cache_hit_rate,
                "total_cache_hits": self.cache_hits,
                "total_cache_misses": self.cache_misses,
                "toggle_operations": self.toggle_operations,
                "total_errors": self.errors,
                "api_latencies_ms": api_latencies,
                "timestamp": datetime.now().isoformat()
            }


# Global performance metrics instance
_metrics = PerformanceMetrics()


def track_performance(endpoint_name: str):
    """Decorator to track API performance"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.time() - start_time) * 1000
                _metrics.record_api_call(endpoint_name, elapsed_ms)
                
                if elapsed_ms > 500:
                    logger.warning(
                        f"Slow API call: {endpoint_name} took {elapsed_ms:.1f}ms"
                    )
                
                return result
            except Exception as e:
                _metrics.record_error()
                raise
        
        return wrapper
    return decorator


def get_performance_report() -> Dict:
    """Get current performance report"""
    return _metrics.get_stats()


# Example: Cached dashboard factory
_cached_dashboards = {}


def get_cached_dashboard(symbol: str, cache_ttl_seconds: int = 30) -> CachedOptimizationDashboard:
    """
    Get or create cached dashboard instance for a symbol.
    
    Args:
        symbol: Trading symbol
        cache_ttl_seconds: Cache time-to-live
    
    Returns:
        CachedOptimizationDashboard instance
    """
    if symbol not in _cached_dashboards:
        _cached_dashboards[symbol] = CachedOptimizationDashboard(
            symbol, 
            cache_ttl_seconds=cache_ttl_seconds
        )
    
    return _cached_dashboards[symbol]


def invalidate_symbol_cache(symbol: str):
    """Invalidate cache for a symbol (call after toggle)"""
    if symbol in _cached_dashboards:
        _cached_dashboards[symbol].invalidate_cache()


class QueryOptimizer:
    """
    Optimizes common query patterns for dashboard access.
    """
    
    @staticmethod
    @lru_cache(maxsize=128)
    def get_symbol_list_from_config(config_path: str) -> list:
        """
        Get list of symbols from config with caching.
        
        Args:
            config_path: Path to strategy config
        
        Returns:
            List of symbols
        """
        try:
            if not os.path.exists(config_path):
                return []
            
            with open(config_path) as f:
                config = json.load(f)
            
            return list(config.get("symbols", {}).keys())
        except Exception as e:
            logger.error(f"Failed to load symbols from {config_path}: {e}")
            return []
    
    @staticmethod
    def filter_results_by_status(results: Dict, status: str) -> Dict:
        """
        Filter optimization results by status with minimal overhead.
        
        Args:
            results: All optimization results
            status: Status filter (accepted, rejected, pending)
        
        Returns:
            Filtered results
        """
        if not status:
            return results
        
        return {
            session: result
            for session, result in results.items()
            if result.get("status") == status
        }
    
    @staticmethod
    def get_top_sessions_by_improvement(results: Dict, top_n: int = 5) -> list:
        """
        Get top sessions by improvement percentage.
        
        Args:
            results: All optimization results
            top_n: Number of top sessions to return
        
        Returns:
            List of (session, improvement_pct) tuples, sorted descending
        """
        improvements = []
        for session, result in results.items():
            optuna = result.get("optuna", {})
            improvement = optuna.get("improvement_pct", 0)
            improvements.append((session, improvement))
        
        return sorted(improvements, key=lambda x: x[1], reverse=True)[:top_n]


# Integration with Flask routes
def with_performance_tracking(endpoint_name: str):
    """Decorator for Flask routes to track performance"""
    def decorator(func):
        @wraps(func)
        @track_performance(endpoint_name)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator
