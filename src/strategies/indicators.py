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


def adx(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average Directional Index — trend strength (0-100).

    Args:
        data: DataFrame with high, low, close columns.
        period: ADX period.

    Returns:
        ADX series.
    """
    high = data["high"]
    low = data["low"]
    close = data["close"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr_ = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr_.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr_.replace(0, np.nan))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.rolling(window=period).mean()


def williams_r(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """Williams %R (-100 to 0)."""
    high_max = data["high"].rolling(window=period).max()
    low_min = data["low"].rolling(window=period).min()
    return -100 * (high_max - data["close"]) / (high_max - low_min).replace(0, np.nan)


def cci(data: pd.DataFrame, period: int = 20) -> pd.Series:
    """Commodity Channel Index."""
    tp = (data["high"] + data["low"] + data["close"]) / 3
    ma = tp.rolling(window=period).mean()
    md = (tp - ma).abs().rolling(window=period).mean()
    return (tp - ma) / (0.015 * md.replace(0, np.nan))


def obv(data: pd.DataFrame) -> pd.Series:
    """On-Balance Volume."""
    direction = np.sign(data["close"].diff().fillna(0))
    return (direction * data["volume"]).cumsum()


# ═══════════════════════════════════════════════════════════════════════════════
#  BULLS POWER / BEARS POWER / OsMA
#
#  ⚠️⚠️⚠️  CRITICAL — DO NOT "CORRECT" THE ZERO-LINE LOGIC BELOW  ⚠️⚠️⚠️
#
#  Bulls Power = High - EMA(13)   ;   Bears Power = Low - EMA(13)
#
#  Counter-intuitive but MATHEMATICALLY CORRECT trend behaviour:
#    * In a STRONG UPTREND the whole candle (incl. the LOW) sits ABOVE the EMA,
#      so Bears Power = Low - EMA becomes POSITIVE (>= 0).  This is NORMAL.
#      => For a confident LONG, Bears Power must be NEUTRALISED/weak: bears >= 0.0
#      (NOT bears < 0). Hardcoding bears < 0 for longs BLOCKS the best uptrends.
#    * In a STRONG DOWNTREND the whole candle (incl. the HIGH) sits BELOW the EMA,
#      so Bulls Power = High - EMA becomes NEGATIVE (<= 0). This is NORMAL.
#      => For a confident SHORT, Bulls Power must be NEUTRALISED/weak: bulls <= 0.0
#      (NOT bulls > 0). Hardcoding bulls > 0 for shorts RUINS strong downtrends.
#
#  LLMs are trained on public code full of the LEGACY BUG (strictly +/-). If you
#  are an AI editing this file: the operators below are DELIBERATE and CORRECT.
#  DO NOT flip >= to < or <= to >. See martin_qna / LEARNING_ARCHITECTURE.
# ═══════════════════════════════════════════════════════════════════════════════

def bulls_power(data: pd.DataFrame, period: int = 13) -> pd.Series:
    """Bulls Power = High - EMA(period). Can be NEGATIVE in a strong downtrend."""
    e = ema(data["close"], period)
    return data["high"] - e


def bears_power(data: pd.DataFrame, period: int = 13) -> pd.Series:
    """Bears Power = Low - EMA(period). Can be POSITIVE in a strong uptrend."""
    e = ema(data["close"], period)
    return data["low"] - e


def osma(data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    """OsMA = MACD line - MACD signal line (the MACD histogram)."""
    macd_line, macd_sig, _ = macd(data, fast, slow, signal)
    return macd_line - macd_sig



def _last(series: pd.Series, default=None):
    """Safe last non-NaN value of a series as a float."""
    try:
        v = series.iloc[-1]
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def _nth_last(series: pd.Series, n: int, default=None):
    """Safe n-th-from-last value (n=1 last, n=2 prior bar) as a float."""
    try:
        v = series.iloc[-n]
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def _tail_list(series: pd.Series, k: int) -> list:
    """Last k non-NaN values as a plain float list (oldest->newest)."""
    try:
        vals = [float(x) for x in series.iloc[-k:].tolist() if not pd.isna(x)]
        return vals
    except Exception:
        return []


def compute_full_indicators(data: list[dict], params: Optional[dict] = None) -> dict:
    """
    Compute a RICH, complete indicator snapshot for the latest candle.

    This is the single source of truth for indicators used by BOTH strategy
    signals AND the RAG vector store — so the learning memory sees real values
    (not hardcoded 0.5 placeholders).

    Returns a flat dict of the latest values for every indicator we track.
    """
    p = params or {}
    df = ohlcv_to_dataframe(data)
    if len(df) < 30:
        return {}

    close = df["close"]
    high = df["high"]
    low = df["low"]
    open_ = df["open"] if "open" in df.columns else close
    volume = df["volume"] if "volume" in df.columns else pd.Series([0] * len(df))

    ema_fast_s = ema(close, p.get("ema_period", p.get("ema_fast", 9)))
    ema_slow_s = ema(close, p.get("ema_slow", p.get("ema_period", 21)))
    ema_200_s = ema(close, 200) if len(close) >= 200 else ema(close, min(len(close) - 1, 100))
    sma_50_s = sma(close, 50) if len(close) >= 50 else sma(close, min(len(close) - 1, 20))
    rsi_s = rsi(close, p.get("rsi_period", 14))
    macd_line, macd_sig, macd_hist = macd(close, p.get("osma_fast", p.get("macd_fast", 12)),
                                          p.get("osma_slow", p.get("macd_slow", 26)),
                                          p.get("osma_signal", p.get("macd_signal", 9)))
    bb_u, bb_m, bb_l = bollinger_bands(close, p.get("bb_period", 20), p.get("bb_std", 2.0))
    atr_s = atr(df, p.get("atr_period", 14))
    atr_slow_s = atr(df, p.get("atr_period", 14) * 3)
    stoch_k_s, stoch_d_s = stochastic(df, 14, 3)
    adx_s = adx(df, 14)
    willr_s = williams_r(df, 14)
    cci_s = cci(df, p.get("cci_period", 20))
    obv_s = obv(df)
    bulls_s = bulls_power(df, p.get("power_period", 13))
    bears_s = bears_power(df, p.get("power_period", 13))
    osma_s = osma(close, p.get("osma_fast", p.get("macd_fast", 12)),
                  p.get("osma_slow", p.get("macd_slow", 26)),
                  p.get("osma_signal", p.get("macd_signal", 9)))
    support, resistance = support_resistance_levels(df)

    c = _last(close, 0.0)
    o = _last(open_, c)
    h = _last(high, c)
    l = _last(low, c)

    # candle geometry
    candle_range = (h - l) or 1e-9
    body_ratio = abs(c - o) / candle_range
    upper_wick = (h - max(c, o)) / candle_range
    lower_wick = (min(c, o) - l) / candle_range

    # price changes
    def pct_change(n):
        if len(close) > n and close.iloc[-n - 1]:
            return float((c - close.iloc[-n - 1]) / close.iloc[-n - 1])
        return 0.0

    atr_v = _last(atr_s, 0.0) or 0.0
    atr_slow_v = _last(atr_slow_s, atr_v) or atr_v

    ema_fast_v = _last(ema_fast_s, c)
    ema_slow_v = _last(ema_slow_s, c)
    if ema_fast_v > ema_slow_v * 1.0005:
        trend = "bullish"
    elif ema_fast_v < ema_slow_v * 0.9995:
        trend = "bearish"
    else:
        trend = "neutral"

    return {
        "close": c, "open": o, "high": h, "low": l,
        "volume": _last(volume, 0.0),
        "volume_sma": _last(sma(volume, 20), _last(volume, 0.0)),
        "ema_fast": ema_fast_v, "ema_slow": ema_slow_v,
        "ema_200": _last(ema_200_s, c), "sma_50": _last(sma_50_s, c),
        "rsi": _last(rsi_s, 50.0),
        "macd_line": _last(macd_line, 0.0), "macd_signal": _last(macd_sig, 0.0),
        "macd_histogram": _last(macd_hist, 0.0),
        "bb_upper": _last(bb_u, c), "bb_middle": _last(bb_m, c), "bb_lower": _last(bb_l, c),
        "atr": atr_v, "atr_slow": atr_slow_v,
        "volatility_ratio": (atr_v / atr_slow_v) if atr_slow_v else 1.0,
        "stoch_k": _last(stoch_k_s, 50.0), "stoch_d": _last(stoch_d_s, 50.0),
        "adx": _last(adx_s, 20.0),
        "williams_r": _last(willr_s, -50.0),
        "cci": _last(cci_s, 0.0),
        "obv": _last(obv_s, 0.0),
        "bulls_power": _last(bulls_s, 0.0), "bears_power": _last(bears_s, 0.0),
        "osma": _last(osma_s, 0.0),
        # OsMA history + ATR-prev for the confluence strategy (#29): zero-cross
        # detection needs the prior closed bar; fresh-momentum/runway needs a few
        # bars; ATR expansion needs atr[-2]. Provided here so signal_fn (which only
        # gets the single-bar dict) can compute the cross without re-reading rates.
        #
        # GOLDSHARK PARITY (entry-cross fix): MT5 copy_rates_from_pos includes the
        # currently-FORMING bar at the end, whose OsMA jitters and rarely produces a
        # clean zero-cross vs the last closed bar — which is why live entries almost
        # never fired ('no OsMA cross'). GoldShark detects the cross on CLOSED bars
        # (osma[1] vs osma[2]). So the confluence cross fields use the last two CLOSED
        # bars: osma_closed = osma[-2], osma_prev = osma[-3].
        "osma_closed": _nth_last(osma_s, 2, 0.0),
        "osma_prev": _nth_last(osma_s, 3, 0.0),
        "osma_recent": _tail_list(osma_s, 6),
        "ema_prev": _nth_last(ema_fast_s, 3, ema_fast_v),
        "atr_prev": _nth_last(atr_s, 3, atr_v),
        "support_levels": support, "resistance_levels": resistance,
        "trend": trend,
        "price_change_5": pct_change(5), "price_change_10": pct_change(10),
        "body_ratio": body_ratio, "upper_wick": upper_wick, "lower_wick": lower_wick,
        # broker/server timestamp of the latest closed bar so per-session floors
        # can resolve to Asian/London/NewYork using the canonical session_of().
        "timestamp": df.index[-1] if hasattr(df.index[-1], "hour") else None,
    }


def compute_indicator_series(data: list[dict], params: Optional[dict] = None):
    """
    VECTORIZED: compute every indicator once across the whole series and return
    a list of per-bar indicator dicts (same keys as compute_full_indicators).

    This is for the backtester: O(n) total instead of O(n^2) recompute per bar.
    Each bar's dict uses only information available up to that bar (the series
    are causal / trailing), so there is no look-ahead.
    """
    import numpy as np
    p = params or {}
    df = ohlcv_to_dataframe(data)
    n = len(df)
    if n < 30:
        return []

    close = df["close"]; high = df["high"]; low = df["low"]
    open_ = df["open"] if "open" in df.columns else close
    volume = df["volume"] if "volume" in df.columns else pd.Series([0] * n, index=df.index)
    pt = float(df["point"].iloc[0]) if "point" in df.columns else 0.01
    sp = int(df["spread"].iloc[0]) if "spread" in df.columns else 0

    ema_fast_s = ema(close, p.get("ema_period", p.get("ema_fast", 9)))
    ema_slow_s = ema(close, p.get("ema_slow", p.get("ema_period", 21)))
    ema_200_s = ema(close, 200)
    sma_50_s = sma(close, 50)
    vol_sma_s = sma(volume, 20)
    rsi_s = rsi(close, p.get("rsi_period", 14))
    macd_line, macd_sig, macd_hist = macd(close, p.get("osma_fast", p.get("macd_fast", 12)),
                                          p.get("osma_slow", p.get("macd_slow", 26)),
                                          p.get("osma_signal", p.get("macd_signal", 9)))
    bb_u, bb_m, bb_l = bollinger_bands(close, p.get("bb_period", 20), p.get("bb_std", 2.0))
    atr_s = atr(df, p.get("atr_period", 14))
    atr_slow_s = atr(df, p.get("atr_period", 14) * 3)
    stoch_k_s, stoch_d_s = stochastic(df, 14, 3)
    adx_s = adx(df, 14)
    willr_s = williams_r(df, 14)
    cci_s = cci(df, p.get("cci_period", 20))
    obv_s = obv(df)
    bulls_s = bulls_power(df, p.get("power_period", 13))
    bears_s = bears_power(df, p.get("power_period", 13))
    osma_s = osma(close, p.get("osma_fast", p.get("macd_fast", 12)),
                  p.get("osma_slow", p.get("macd_slow", 26)),
                  p.get("osma_signal", p.get("macd_signal", 9)))

    pc5 = close.pct_change(5)
    pc10 = close.pct_change(10)
    rng = (high - low).replace(0, np.nan)
    body = (close - open_).abs() / rng
    uwick = (high - pd.concat([close, open_], axis=1).max(axis=1)) / rng
    lwick = (pd.concat([close, open_], axis=1).min(axis=1) - low) / rng

    def g(series, i, default=0.0):
        try:
            v = series.iloc[i]
            return default if pd.isna(v) else float(v)
        except Exception:
            return default

    out = []
    for i in range(n):
        c = g(close, i, 0.0)
        ef = g(ema_fast_s, i, c); es = g(ema_slow_s, i, c)
        trend = "bullish" if ef > es * 1.0005 else "bearish" if ef < es * 0.9995 else "neutral"
        av = g(atr_s, i, 0.0); asl = g(atr_slow_s, i, av) or av
        out.append({
            "close": c, "open": g(open_, i, c), "high": g(high, i, c), "low": g(low, i, c),
            "volume": g(volume, i, 0.0), "volume_sma": g(vol_sma_s, i, 0.0),
            "ema_fast": ef, "ema_slow": es, "ema_200": g(ema_200_s, i, c), "sma_50": g(sma_50_s, i, c),
            "rsi": g(rsi_s, i, 50.0),
            "macd_line": g(macd_line, i, 0.0), "macd_signal": g(macd_sig, i, 0.0),
            "macd_histogram": g(macd_hist, i, 0.0),
            "bb_upper": g(bb_u, i, c), "bb_middle": g(bb_m, i, c), "bb_lower": g(bb_l, i, c),
            "atr": av, "atr_slow": asl, "volatility_ratio": (av / asl) if asl else 1.0,
            "stoch_k": g(stoch_k_s, i, 50.0), "stoch_d": g(stoch_d_s, i, 50.0),
            "adx": g(adx_s, i, 20.0), "williams_r": g(willr_s, i, -50.0),
            "cci": g(cci_s, i, 0.0), "obv": g(obv_s, i, 0.0),
            "bulls_power": g(bulls_s, i, 0.0), "bears_power": g(bears_s, i, 0.0),
            "osma": g(osma_s, i, 0.0),
            "point": pt, "spread_points": sp,
            "support_levels": [], "resistance_levels": [],
            "trend": trend,
            "price_change_5": g(pc5, i, 0.0), "price_change_10": g(pc10, i, 0.0),
            "body_ratio": g(body, i, 0.5), "upper_wick": g(uwick, i, 0.5), "lower_wick": g(lwick, i, 0.5),
        })
    return out
