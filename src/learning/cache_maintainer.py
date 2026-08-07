"""
Rolling Dukascopy cache maintainer.

Keeps the last N days of Dukascopy ticks warm for each active symbol so a backtest ALWAYS
has >=2000 bars — the data process behind 'prove every change with backtest+forward'. Runs
in a background thread (patient, gentle), refreshing the trailing window periodically.
Without this, caching is on-demand and a validation can silently no-op on a thin cache.
"""
from __future__ import annotations
import threading, time
from datetime import datetime, timezone, timedelta

from src.utils.logger import get_logger

logger = get_logger("cache_maintainer")


class RollingCacheMaintainer:
    def __init__(self, symbols, days: int = 10, refresh_hours: float = 6.0, workers: int = 3):
        self.symbols = [s.upper().split("-")[0] for s in symbols]
        self.days = days
        self.refresh_secs = refresh_hours * 3600
        self.workers = workers
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="cache-maintainer", daemon=True)
        self._thread.start()
        logger.warning(f"[CACHE] rolling maintainer started: last {self.days}d for {self.symbols} "
                       f"(refresh every {self.refresh_secs/3600:.0f}h)")

    def _run(self):
        from src.data_sources.dukascopy import fetch_ticks
        while not self._stop.is_set():
            for sym in self.symbols:
                if self._stop.is_set():
                    break
                try:
                    end = datetime.now(timezone.utc)
                    start = end - timedelta(days=self.days)
                    n = fetch_ticks(sym, start, end, use_cache=True, workers=self.workers)
                    logger.info(f"[CACHE] {sym}: warmed last {self.days}d -> {len(n)} ticks")
                except Exception as e:
                    logger.debug(f"[CACHE] {sym} warm skip: {e}")
            # sleep in small steps so stop is responsive
            slept = 0
            while slept < self.refresh_secs and not self._stop.is_set():
                time.sleep(5); slept += 5

    def stop(self):
        self._stop.set()
