"""
Technical indicators for XAUUSD trading strategies.
Provides common indicators used in gold trading.
"""

import numpy as np
import pandas as pd
from typing import Optional


def ohlcv_to_dataframe(data: list[dict]) -> pd.DataFrame:
    """
    Convert OHLCV data list to a pandas DataFrame.
    
    Args:
        data: List of candle dicts with o, h, l, c, v keys.
    
    Returns:
        DataFrame with OHLCV columns.
    """
    df = pd.DataFrame(data)
    df.columns = [c.lower() for c in df.columns]
    
    # Ensure required columns exist
    required = ["open", "high", "low", "close", "volume"]
    for col in required:
        if col not in df.columns:
            # Try alternative names
            alt_map = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
            if col in alt_map and alt_map[col] in df.columns:
                df[col] = df[alt_map[col]]
    
    return df


def sma(data: pd.Series, period: int = 20) -> pd.Series:
    """Simple Moving Average."""
    return data.rolling(window=period).mean()


def ema(data: pd.Series, period: int = 20) -> pd.Series:
    """Exponential Moving Average."""
    return data.ewm(span=period, adjust=False).mean()


def rsi(data: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index.
    
    Args:
        data: Price series (typically close).
        period: RSI period (default: 14).
    
    Returns:
        RSI values (0-100).
    """
    delta = data.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    # Use Wilder's smoothing method
    for i in range(period, len(avg_gain)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def macd(
    data: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    MACD (Moving Average Convergence Divergence).
    
    Args:
        data: Price series.
        fast: Fast EMA period.
        slow: Slow EMA period.
        signal: Signal line period.
    
    Returns:
        Tuple of (MACD line, Signal line, Histogram).
    """
    ema_fast = ema(data, fast)
    ema_slow = ema(data, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram


def bollinger_bands(
    data: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bollinger Bands.
    
    Args:
        data: Price series.
        period: Moving average period.
        std_dev: Number of standard deviations.
    
    Returns:
        Tuple of (Upper band, Middle band, Lower band).
    """
    middle = sma(data, period)
    std = data.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    
    return upper, middle, lower


def atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range.
    
    Args:
        data: DataFrame with high, low, close columns.
        period: ATR period.
    
    Returns:
        ATR values.
    """
    high = data["high"]
    low = data["low"]
    close = data["close"]
    
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    return atr


def stochastic(
    data: pd.DataFrame,
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """
    Stochastic Oscillator.
    
    Args:
        data: DataFrame with high, low, close columns.
        k_period: %K period.
        d_period: %D period (smoothing).
    
    Returns:
        Tuple of (%K, %D).
    """
    low_min = data["low"].rolling(window=k_period).min()
    high_max = data["high"].rolling(window=k_period).max()
    
    k = 100 * ((data["close"] - low_min) / (high_max - low_min))
    d = k.rolling(window=d_period).mean()
    
    return k, d


def support_resistance_levels(
    data: pd.DataFrame,
    lookback: int = 50,
    threshold: float = 0.005,
) -> tuple[list[float], list[float]]:
    """
    Identify key support and resistance levels.
    
    Args:
        data: DataFrame with high, low columns.
        lookback: Number of candles to look back.
        threshold: Price proximity threshold (0.5% default).
    
    Returns:
        Tuple of (support levels, resistance levels).
    """
    highs = data["high"].tail(lookback)
    lows = data["low"].tail(lookback)
    
    # Find local maxima (resistance)
    resistance = []
    for i in range(2, len(highs) - 2):
        if (highs.iloc[i] > highs.iloc[i-1] and 
            highs.iloc[i] > highs.iloc[i-2] and
            highs.iloc[i] > highs.iloc[i+1] and 
            highs.iloc[i] > highs.iloc[i+2]):
            resistance.append(highs.iloc[i])
    
    # Find local minima (support)
    support = []
    for i in range(2, len(lows) - 2):
        if (lows.iloc[i] < lows.iloc[i-1] and 
            lows.iloc[i] < lows.iloc[i-2] and
            lows.iloc[i] < lows.iloc[i+1] and 
            lows.iloc[i] < lows.iloc[i+2]):
            support.append(lows.iloc[i])
    
    # Cluster nearby levels
    def cluster_levels(levels: list[float]) -> list[float]:
        if not levels:
            return []
        levels = sorted(levels)
        clustered = [levels[0]]
        for level in levels[1:]:
            if abs(level - clustered[-1]) / clustered[-1] > threshold:
                clustered.append(level)
        return clustered
    
    return cluster_levels(support), cluster_levels(resistance)
