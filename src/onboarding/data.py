"""MT5 data loading for onboarding (OHLCV + optional ticks).

Wraps ``src.mt5.data`` and normalises output into a tz-aware UTC DataFrame with
columns [open, high, low, close, volume].
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from src.mt5.data import get_rates, get_ticks

logger = logging.getLogger(__name__)


def load_ohlcv(symbol: str, timeframe: str, count: int = 5000) -> pd.DataFrame:
    """Load OHLCV bars for a symbol/timeframe as a UTC-indexed DataFrame."""
    rates = get_rates(symbol=symbol, timeframe=timeframe, count=count, lock=True)
    if not rates:
        raise ConnectionError(f"No OHLCV data for {symbol} {timeframe}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            df[col] = 0.0
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def load_ticks(symbol: str, from_epoch: float, to_epoch: float) -> Optional[dict]:
    """Load bid/ask ticks for a window. Returns None if unavailable."""
    return get_ticks(symbol, from_epoch, to_epoch, lock=True)


__all__ = ["load_ohlcv", "load_ticks"]
