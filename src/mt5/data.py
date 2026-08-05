"""
Market data operations for MetaTrader 5.
Provides OHLCV data, tick data, and symbol information.

On macOS, data is fetched via the silicon-metatrader5 Docker bridge (RPyC to container).
On Windows, data is fetched directly via the MetaTrader5 package.
Falls back to simulated data when neither is available.
"""

from typing import Optional
from datetime import datetime, timedelta

from src.mt5.connector import get_connector, MT5_AVAILABLE, mt5, mt5_error_handler, SILICON_MT5_AVAILABLE
from src.utils.logger import get_logger

logger = get_logger("mt5.data")

# MT5 Timeframe mapping (fallback values for simulation mode)
TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1 if MT5_AVAILABLE else 1,
    "M5": mt5.TIMEFRAME_M5 if MT5_AVAILABLE else 5,
    "M15": mt5.TIMEFRAME_M15 if MT5_AVAILABLE else 15,
    "M30": mt5.TIMEFRAME_M30 if MT5_AVAILABLE else 30,
    "H1": mt5.TIMEFRAME_H1 if MT5_AVAILABLE else 60,
    "H4": mt5.TIMEFRAME_H4 if MT5_AVAILABLE else 240,
    "D1": mt5.TIMEFRAME_D1 if MT5_AVAILABLE else 1440,
    "W1": mt5.TIMEFRAME_W1 if MT5_AVAILABLE else 10080,
    "MN1": mt5.TIMEFRAME_MN1 if MT5_AVAILABLE else 43200,
}


def _get_silicon_mt5():
    """Get the silicon-metatrader5 client from the connector if available."""
    try:
        connector = get_connector()
        if connector.bridge_available:
            return connector.get_silicon_mt5()
    except Exception:
        pass
    return None


def _get_timeframe_value(timeframe: str):
    """Get the numeric timeframe value for silicon-metatrader5."""
    # silicon-metatrader5 uses the same MT5 timeframe constants
    if SILICON_MT5_AVAILABLE:
        from siliconmetatrader5 import MetaTrader5 as SM5
        tf_map = {
            "M1": SM5.TIMEFRAME_M1,
            "M5": SM5.TIMEFRAME_M5,
            "M15": SM5.TIMEFRAME_M15,
            "M30": SM5.TIMEFRAME_M30,
            "H1": SM5.TIMEFRAME_H1,
            "H4": SM5.TIMEFRAME_H4,
            "D1": SM5.TIMEFRAME_D1,
            "W1": SM5.TIMEFRAME_W1,
            "MN1": SM5.TIMEFRAME_MN1,
        }
        return tf_map.get(timeframe, SM5.TIMEFRAME_H1)
    return TIMEFRAMES.get(timeframe, 60)


@mt5_error_handler
def get_rates(
    symbol: str = "XAUUSD",
    timeframe: str = "H1",
    count: int = 100,
) -> list[dict]:
    """
    Get OHLCV (Open, High, Low, Close, Volume) rate data.
    
    REQUIRED: Must get live data from MT5.
    Does NOT fall back to simulated data.
    
    Args:
        symbol: Trading symbol (default: XAUUSD).
        timeframe: Timeframe string (M1, M5, M15, M30, H1, H4, D1, W1, MN1).
        count: Number of candles to fetch.
    
    Returns:
        List of candle dictionaries with o, h, l, c, v, time fields.
        
    Raises:
        ConnectionError: If MT5 not connected or no data available
    """
    connector = get_connector()
    
    if not connector.is_connected():
        raise ConnectionError("MT5 not connected. Cannot fetch rates.")
    
    # Try silicon-metatrader5 Docker bridge first (macOS)
    silicon_mt5 = _get_silicon_mt5()
    if silicon_mt5:
        try:
            tf = _get_timeframe_value(timeframe)
            rates = silicon_mt5.copy_rates_from_pos(symbol, tf, 0, count)
            
            if rates is not None and len(rates) > 0:
                logger.info(
                    f"Fetched {len(rates)} {symbol} {timeframe} candles "
                    f"via Docker bridge"
                )
                return [
                    {
                        "time": str(datetime.fromtimestamp(r["time"])),
                        "timestamp": r["time"],
                        "open": r["open"],
                        "high": r["high"],
                        "low": r["low"],
                        "close": r["close"],
                        "volume": r.get("tick_volume", r.get("volume", 0)),
                        "spread": r.get("spread", 0),
                        "real_time": r.get("real_time", 0),
                    }
                    for r in rates
                ]
            else:
                raise ConnectionError(
                    f"No data for {symbol} {timeframe}. "
                    f"Check MT5 terminal and market data availability."
                )
        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"Docker bridge get_rates failed: {e}")
    
    # Try native MT5 (Windows)
    if not MT5_AVAILABLE:
        raise ConnectionError("MT5 package not available")
    
    tf = TIMEFRAMES.get(timeframe, mt5.TIMEFRAME_H1)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    
    if rates is None or len(rates) == 0:
        raise ConnectionError(
            f"No data for {symbol} {timeframe}. "
            f"Check MT5 terminal and market data availability."
        )
    
    result = []
    for rate in rates:
        result.append({
            "time": str(datetime.fromtimestamp(int(rate["time"]))),
            "timestamp": int(rate["time"]),
            "open": float(rate["open"]),
            "high": float(rate["high"]),
            "low": float(rate["low"]),
            "close": float(rate["close"]),
            "volume": int(rate["tick_volume"]),
            "spread": int(rate["spread"]) if "spread" in rates.dtype.names else 0,
        })
    
    return result


def get_ticks(symbol: str, from_epoch: float, to_epoch: float, max_ticks: int = 5_000_000):
    """Real bid/ask TICKS for [from_epoch, to_epoch]. Returns a dict of parallel arrays
    {'time': [...], 'bid': [...], 'ask': [...]} (lists of float), or None if unavailable.
    Used by the backtester for tick-accurate SL/TP fills (MT5 'real ticks' model). Never
    raises — returns None so the caller can fall back to bar-based fills."""
    if not MT5_AVAILABLE:
        return None
    try:
        import datetime as _dt
        t = mt5.copy_ticks_from(symbol, _dt.datetime.utcfromtimestamp(float(from_epoch)),
                                int(max_ticks), mt5.COPY_TICKS_ALL)
        if t is None or len(t) == 0:
            return None
        tt = t["time"].astype("int64")
        # clip to the requested window
        mask = (tt >= int(from_epoch)) & (tt <= int(to_epoch))
        return {"time": tt[mask].tolist(),
                "bid": t["bid"][mask].astype("float64").tolist(),
                "ask": t["ask"][mask].astype("float64").tolist()}
    except Exception as e:
        logger.debug(f"get_ticks failed {symbol}: {e}")
        return None


@mt5_error_handler
def get_last_price(symbol: str = "XAUUSD") -> Optional[dict]:
    """
    Get the latest price tick for a symbol.
    
    REQUIRED: Must get live data from MT5.
    Does NOT fall back to simulated data.
    
    Args:
        symbol: Trading symbol (default: XAUUSD).
    
    Returns:
        Dict with bid, ask, spread, and time
        
    Raises:
        ConnectionError: If MT5 not connected or no tick available
    """
    connector = get_connector()
    
    if not connector.is_connected():
        raise ConnectionError("MT5 not connected. Cannot fetch price.")
    
    # Try silicon-metatrader5 Docker bridge first (macOS)
    silicon_mt5 = _get_silicon_mt5()
    if silicon_mt5:
        try:
            tick = silicon_mt5.symbol_info_tick(symbol)
            if tick is not None:
                return {
                    "symbol": symbol,
                    "bid": tick.bid,
                    "ask": tick.ask,
                    "spread": tick.spread,
                    "time": str(datetime.fromtimestamp(tick.time)),
                    "last": tick.last,
                    "volume": tick.volume,
                    "real_time": True,
                }
            else:
                raise ConnectionError(
                    f"No tick data for {symbol}. "
                    f"Check MT5 terminal and market availability."
                )
        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"Docker bridge get_last_price failed: {e}")
    
    # Try native MT5 (Windows)
    if not MT5_AVAILABLE:
        raise ConnectionError("MT5 package not available")
    
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise ConnectionError(
            f"No tick data for {symbol}. "
            f"Check MT5 terminal and market availability."
        )
    
    return {
        "symbol": symbol,
        "bid": tick.bid,
        "ask": tick.ask,
        "spread": round(tick.ask - tick.bid, 8),
        "time": str(datetime.fromtimestamp(tick.time)),
        "last": getattr(tick, "last", 0.0),
        "volume": getattr(tick, "volume", 0),
    }


@mt5_error_handler
def get_symbol_info(symbol: str = "XAUUSD") -> Optional[dict]:
    """
    Get symbol information and specifications.
    
    REQUIRED: Must get live data from MT5.
    Does NOT fall back to simulated data.
    
    Args:
        symbol: Trading symbol (default: XAUUSD).
    
    Returns:
        Dict with symbol specifications
        
    Raises:
        ConnectionError: If MT5 not connected or symbol not available
    """
    connector = get_connector()
    
    if not connector.is_connected():
        raise ConnectionError("MT5 not connected. Cannot fetch symbol info.")
    
    # Try silicon-metatrader5 Docker bridge first (macOS)
    silicon_mt5 = _get_silicon_mt5()
    if silicon_mt5:
        try:
            info = silicon_mt5.symbol_info(symbol)
            if info is not None:
                return {
                    "symbol": info.name,
                    "digits": info.digits,
                    "point": info.point,
                    "spread": info.spread,
                    "trade_mode": info.trade_mode,
                    "contract_size": info.contract_size,
                    "tick_size": info.tick_size,
                    "tick_value": info.tick_value,
                    "min_volume": info.volume_min,
                    "max_volume": info.volume_max,
                    "volume_step": info.volume_step,
                    "description": info.description,
                    "simulated": False,
                }
            else:
                raise ConnectionError(f"Symbol {symbol} not found in MT5")
        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"Docker bridge get_symbol_info failed: {e}")
    
    # Try native MT5 (Windows)
    if not MT5_AVAILABLE:
        raise ConnectionError("MT5 package not available")
    
    info = mt5.symbol_info(symbol)
    if info is None:
        raise ConnectionError(f"Symbol {symbol} not found in MT5")
    
    return {
        "symbol": info.name,
        "digits": info.digits,
        "point": info.point,
        "spread": info.spread,
        "trade_mode": info.trade_mode,
        "contract_size": info.contract_size,
        "tick_size": info.tick_size,
        "tick_value": info.tick_value,
        "min_volume": info.volume_min,
        "max_volume": info.volume_max,
        "volume_step": info.volume_step,
        "description": info.description,
        "simulated": False,
    }

