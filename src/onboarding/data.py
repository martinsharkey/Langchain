"""MT5 data loading for onboarding (OHLCV + optional ticks).

Wraps ``src.mt5.data`` and normalises output into a tz-aware UTC DataFrame with
columns [open, high, low, close, volume].
"""

from __future__ import annotations

import logging
from datetime import datetime
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


def load_ohlcv_range(symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Load OHLCV bars for a symbol/timeframe within a UTC date range.

    Uses MT5's ``copy_rates_range`` to pull only the bars within the window,
    avoiding the need to load millions of bars then filter.
    """
    import MetaTrader5 as mt5

    from src.mt5.connector import get_connector

    connector = get_connector()
    if not connector.ensure_connected():
        raise ConnectionError("MT5 not connected. Cannot fetch rates.")

    tf = _get_timeframe_value(timeframe)
    rates = mt5.copy_rates_range(symbol, tf, start, end)
    if rates is None or len(rates) == 0:
        raise ConnectionError(f"No OHLCV data for {symbol} {timeframe} in range {start}–{end}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time")
    df = df.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close", "tick_volume": "volume"})
    if "volume" not in df.columns:
        df["volume"] = 0.0
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            df[col] = 0.0
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def _get_timeframe_value(timeframe: str):
    """Convert a timeframe string to the MT5 constant."""
    import MetaTrader5 as mt5

    mapping = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    if timeframe not in mapping:
        raise ValueError(f"Unknown timeframe: {timeframe}")
    return mapping[timeframe]


def get_mt5_symbols() -> list:
    """Get all tradeable MT5 symbols, sorted alphabetically.

    Returns a list of dicts: [{name, description, tradeable, path}, ...].
    """
    import MetaTrader5 as mt5

    from src.mt5.connector import get_connector

    connector = get_connector()
    if not connector.ensure_connected():
        raise ConnectionError("MT5 not connected.")

    symbols = mt5.symbols_get()
    if symbols is None:
        return []

    result = []
    for s in symbols:
        result.append({
            "name": s.name,
            "description": s.description,
            "tradeable:": s.tradable,
            "path": s.path,
            "currency_base": s.currency_base,
            "currency_profit": s.currency_profit,
            "digits": s.digits,
        })
    result.sort(key=lambda x: x["name"])
    return result


def load_ticks(symbol: str, from_epoch: float, to_epoch: float) -> Optional[dict]:
    """Load bid/ask ticks for a window. Returns None if unavailable."""
    return get_ticks(symbol, from_epoch, to_epoch, lock=True)


__all__ = ["load_ohlcv", "load_ticks"]
