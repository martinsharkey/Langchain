"""Broker-agnostic data manager — reads historical market data from local parquet.

Architecture:
    data/broker_data/<broker>/<symbol>/<TF>.parquet   — OHLCV bars
    data/broker_data/<broker>/<symbol>/ticks.parquet   — bid/ask ticks (optional)

The DataManager replaces direct MT5 calls in backtesting, onboarding, and research.
All data is pre-acquired by pull_mt5_history.py and stored locally.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Default point value when not stored in parquet
_DEFAULT_POINT = 0.01
# Default spread when not stored in parquet
_DEFAULT_SPREAD = 0


@dataclass
class DataSourceConfig:
    """Configuration for a broker data source."""
    broker: str
    base_path: Path = None  # defaults to data/broker_data/<broker>

    def __post_init__(self):
        if self.base_path is None:
            self.base_path = Path("data/broker_data") / self.broker


class DataManager:
    """Reads OHLCV bars and tick data from local parquet files.

    Usage:
        dm = DataManager(DataSourceConfig(broker="vt_markets"))
        bars = dm.get_rates("XAUUSD", "M15", bars=12000)
        ticks = dm.get_ticks("XAUUSD", start_ts, end_ts)
    """

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self._bar_cache: dict[str, pd.DataFrame] = {}
        self._tick_cache: Optional[pd.DataFrame] = None

    # ── bar data ─────────────────────────────────────────────────────

    def get_rates(self, symbol: str, timeframe: str, count: int = 12000) -> list[dict]:
        """Return the most recent `count` bars for `symbol`@`timeframe`.

        Matches the signature of src.mt5.data.get_rates so it can be injected
        directly into Backtester, FloorDiscovery, etc.

        Returns list[dict] with keys: time(str), timestamp(int), open, high,
        low, close, volume(int), spread(int), point(float).
        """
        df = self._load_bars(symbol, timeframe)
        if df is None or df.empty:
            logger.warning(f"[DataManager] no bar data for {symbol} {timeframe} "
                           f"(broker={self.config.broker})")
            return []

        # Take the most recent N bars
        df = df.tail(count).copy()

        # Ensure required columns exist
        if "timestamp" not in df.columns:
            if "time" in df.columns:
                df["timestamp"] = self._to_epoch(df["time"])
            else:
                logger.error(f"[DataManager] no 'time' column in {symbol} {timeframe}")
                return []

        if "spread" not in df.columns:
            df["spread"] = _DEFAULT_SPREAD
        if "point" not in df.columns:
            df["point"] = _DEFAULT_POINT

        # Convert to list of dicts matching MT5 get_rates format
        result = []
        for _, row in df.iterrows():
            result.append({
                "time": str(row.get("time", "")),
                "timestamp": int(row["timestamp"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row.get("volume", 0)),
                "spread": int(row.get("spread", 0)),
                "point": float(row.get("point", _DEFAULT_POINT)),
            })
        return result

    def bar_count(self, symbol: str, timeframe: str) -> int:
        """Return the number of bars available for a symbol/timeframe."""
        df = self._load_bars(symbol, timeframe)
        return len(df) if df is not None else 0

    def available_timeframes(self, symbol: str) -> list[str]:
        """List timeframes that have parquet data for a symbol."""
        sym_dir = self.config.base_path / symbol.upper()
        if not sym_dir.exists():
            return []
        tfs = []
        for f in sym_dir.iterdir():
            if f.suffix == ".parquet" and f.name != "ticks.parquet":
                tfs.append(f.stem)
        return sorted(tfs)

    def available_symbols(self) -> list[str]:
        """List symbols that have any parquet data."""
        if not self.config.base_path.exists():
            return []
        return sorted([d.name for d in self.config.base_path.iterdir() if d.is_dir()])

    # ── tick data ────────────────────────────────────────────────────

    def get_ticks(self, symbol: str, from_epoch: float, to_epoch: float) -> dict:
        """Return tick data for [from_epoch, to_epoch].

        Matches the signature of src.mt5.data.get_ticks.
        Returns {"time": [...], "bid": [...], "ask": [...]} or None.
        """
        df = self._load_ticks(symbol)
        if df is None or df.empty:
            return None

        # Filter by time range
        mask = (df["timestamp"] >= from_epoch) & (df["timestamp"] <= to_epoch)
        df = df.loc[mask].sort_values("timestamp")

        if df.empty:
            return None

        return {
            "time": df["timestamp"].tolist(),
            "bid": df["bid"].tolist(),
            "ask": df["ask"].tolist(),
        }

    def tick_count(self, symbol: str) -> int:
        """Return the number of ticks stored for a symbol."""
        df = self._load_ticks(symbol)
        return len(df) if df is not None else 0

    # ── internal ─────────────────────────────────────────────────────

    def _bar_path(self, symbol: str, timeframe: str) -> Path:
        return self.config.base_path / symbol.upper() / f"{timeframe}.parquet"

    def _tick_path(self, symbol: str) -> Path:
        return self.config.base_path / symbol.upper() / "ticks.parquet"

    def _load_bars(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        key = f"{self.config.broker}:{symbol}:{timeframe}"
        if key in self._bar_cache:
            return self._bar_cache[key]

        path = self._bar_path(symbol, timeframe)
        if not path.exists():
            return None

        try:
            df = pd.read_parquet(path)
            self._bar_cache[key] = df
            return df
        except Exception as e:
            logger.error(f"[DataManager] failed to read {path}: {e}")
            return None

    def _load_ticks(self, symbol: str) -> Optional[pd.DataFrame]:
        if self._tick_cache is not None:
            return self._tick_cache

        path = self._tick_path(symbol)
        if not path.exists():
            return None

        try:
            self._tick_cache = pd.read_parquet(path)
            return self._tick_cache
        except Exception as e:
            logger.error(f"[DataManager] failed to read ticks {path}: {e}")
            return None

    @staticmethod
    def _to_epoch(times) -> pd.Series:
        """Convert datetime/time columns to epoch seconds (int)."""
        if pd.api.types.is_datetime64_any_dtype(times):
            return times.astype("int64") // 10**9
        if isinstance(times.iloc[0], str):
            # Try parsing ISO strings
            try:
                return pd.to_datetime(times, utc=True).astype("int64") // 10**9
            except Exception:
                pass
        if hasattr(times.iloc[0], "timestamp"):
            return times.apply(lambda t: int(t.timestamp()))
        # Fallback: assume already numeric
        return pd.to_numeric(times, errors="coerce")
