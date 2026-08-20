"""Automatic data refresh — keeps broker parquet data fresh without human intervention.

Design:
    - Lazy refresh: triggered when backtester/onboarding needs data
    - Non-blocking: returns stale data immediately, refreshes in background
    - Thread-safe: single refresh per symbol/TF at a time
    - Graceful: if MT5 is unreachable, continues with stale data + warning
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# How many days before data is considered stale
_STALE_DAYS = 1
# Minimum interval between refresh attempts for the same symbol (seconds)
_REFRESH_COOLDOWN = 3600


class DataRefreshManager:
    """Manages automatic freshness checks and background refreshes for broker data.

    Usage:
        refresh_mgr = DataRefreshManager(broker="vt_markets")
        # Returns immediately; triggers background refresh if data is stale
        refresh_mgr.ensure_fresh("XAUUSD", "M15")
        # Data is now fresh (or being refreshed)
        bars = dm.get_rates("XAUUSD", "M15")
    """

    def __init__(self, broker: str, base_path: Optional[Path] = None, data_manager=None):
        self.broker = broker
        self.base_path = base_path or Path("data/broker_data") / broker
        self.dm = data_manager
        self._refreshing: set[str] = set()
        self._lock = threading.Lock()
        self._last_refresh_attempt: dict[str, float] = {}

    def ensure_fresh(self, symbol: str, timeframe: str) -> bool:
        """Ensure data for symbol/timeframe is fresh. Non-blocking.

        Returns True if data is fresh (or refresh is in progress), False if
        data is stale and refresh couldn't be triggered.
        """
        path = self.base_path / symbol.upper() / f"{timeframe}.parquet"
        if not path.exists():
            logger.warning(f"[REFRESH] {symbol} {timeframe}: no local data, cannot refresh without MT5")
            return False

        mtime = path.stat().st_mtime
        age_days = (time.time() - mtime) / 86400

        if age_days < _STALE_DAYS:
            return True

        key = f"{symbol}:{timeframe}"
        now = time.time()

        with self._lock:
            if key in self._refreshing:
                return True

            if key in self._last_refresh_attempt:
                if now - self._last_refresh_attempt[key] < _REFRESH_COOLDOWN:
                    logger.info(f"[REFRESH] {symbol} {timeframe}: cooldown active, using stale data ({age_days:.1f}d old)")
                    return True

            self._refreshing.add(key)
            self._last_refresh_attempt[key] = now

        logger.warning(f"[REFRESH] {symbol} {timeframe}: data is {age_days:.1f}d old, refreshing in background")
        thread = threading.Thread(
            target=self._refresh_symbol,
            args=(symbol, timeframe, key),
            daemon=True,
            name=f"refresh-{symbol}-{timeframe}",
        )
        thread.start()
        return True

    def refresh_symbol(self, symbol: str, timeframe: str) -> bool:
        """Synchronous refresh for a specific symbol/timeframe. Blocks until complete."""
        key = f"{symbol}:{timeframe}"
        with self._lock:
            if key in self._refreshing:
                return False
            self._refreshing.add(key)
        try:
            self._refresh_symbol(symbol, timeframe, key)
            return True
        finally:
            with self._lock:
                self._refreshing.discard(key)

    def _refresh_symbol(self, symbol: str, timeframe: str, key: str):
        """Actual refresh logic. Runs in background thread."""
        try:
            from scripts.data_acquisition.pull_mt5_history import (
                connect_mt5,
                pull_bars,
                store_parquet,
            )
            from datetime import timezone as tz

            mt5, account = connect_mt5()
            if mt5 is None:
                logger.error(f"[REFRESH] {symbol} {timeframe}: MT5 not available")
                return

            start = datetime(2000, 1, 1, tzinfo=tz.utc)
            end = datetime.now(tz.utc)
            df = pull_bars(mt5, symbol, timeframe, start, end)
            mt5.shutdown()

            if df is None or df.empty:
                logger.warning(f"[REFRESH] {symbol} {timeframe}: pull returned no data")
                return

            path = self.base_path / symbol.upper() / f"{timeframe}.parquet"
            store_parquet(df, path, force=False)
            logger.info(f"[REFRESH] {symbol} {timeframe}: refreshed {len(df)} bars")

            # Invalidate DataManager cache if available
            if self.dm is not None:
                cache_key = f"{self.broker}:{symbol}:{timeframe}"
                self.dm._bar_cache.pop(cache_key, None)

        except Exception as e:
            logger.warning(f"[REFRESH] {symbol} {timeframe}: failed — {e}")
        finally:
            with self._lock:
                self._refreshing.discard(key)

    def refresh_all(self, symbols: list[str], timeframes: list[str]) -> dict[str, bool]:
        """Trigger refresh for all symbol/timeframe combinations. Non-blocking."""
        results = {}
        for sym in symbols:
            for tf in timeframes:
                results[f"{sym}:{tf}"] = self.ensure_fresh(sym, tf)
        return results
