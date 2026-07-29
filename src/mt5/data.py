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
    
    Priority:
    1. silicon-metatrader5 Docker bridge (macOS with Docker + Wine)
    2. Native MetaTrader5 package (Windows)
    3. Simulated data (fallback)
    
    Args:
        symbol: Trading symbol (default: XAUUSD).
        timeframe: Timeframe string (M1, M5, M15, M30, H1, H4, D1, W1, MN1).
        count: Number of candles to fetch.
    
    Returns:
        List of candle dictionaries with o, h, l, c, v, time fields.
    """
    connector = get_connector()
    
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
                logger.warning(
                    f"No data for {symbol} {timeframe} via Docker bridge "
                    f"(MT5 may not have account logged in)"
                )
        except Exception as e:
            logger.warning(f"Docker bridge get_rates failed: {e}")
    
    # Fall back to simulation if in simulation mode
    if connector.in_simulation_mode:
        return _generate_simulated_rates(count)
    
    # Try native MT5 (Windows)
    if not connector.is_connected():
        logger.warning("Not connected to MT5, using simulated data")
        return _generate_simulated_rates(count)
    
    tf = TIMEFRAMES.get(timeframe, mt5.TIMEFRAME_H1)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    
    if rates is None or len(rates) == 0:
        logger.warning(f"No data for {symbol} {timeframe}, using simulation")
        return _generate_simulated_rates(count)
    
    result = []
    for rate in rates:
        result.append({
            "time": str(datetime.fromtimestamp(rate.time)),
            "timestamp": rate.time,
            "open": rate.open,
            "high": rate.high,
            "low": rate.low,
            "close": rate.close,
            "volume": rate.tick_volume,
            "spread": rate.spread,
        })
    
    return result


@mt5_error_handler
def get_last_price(symbol: str = "XAUUSD") -> Optional[dict]:
    """
    Get the latest price tick for a symbol.
    
    Priority:
    1. silicon-metatrader5 Docker bridge (macOS with Docker + Wine)
    2. Native MetaTrader5 package (Windows)
    3. Simulated tick (fallback)
    
    Args:
        symbol: Trading symbol (default: XAUUSD).
    
    Returns:
        Dict with bid, ask, spread, and time, or None if unavailable.
    """
    connector = get_connector()
    
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
        except Exception as e:
            logger.warning(f"Docker bridge get_last_price failed: {e}")
    
    # Fall back to simulation if in simulation mode
    if connector.in_simulation_mode:
        return _generate_simulated_tick()
    
    # Try native MT5 (Windows)
    if not connector.is_connected():
        return _generate_simulated_tick()
    
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return _generate_simulated_tick()
    
    return {
        "symbol": symbol,
        "bid": tick.bid,
        "ask": tick.ask,
        "spread": tick.spread,
        "time": str(datetime.fromtimestamp(tick.time)),
        "last": tick.last,
        "volume": tick.volume,
    }


@mt5_error_handler
def get_symbol_info(symbol: str = "XAUUSD") -> Optional[dict]:
    """
    Get symbol information and specifications.
    
    Priority:
    1. silicon-metatrader5 Docker bridge (macOS with Docker + Wine)
    2. Native MetaTrader5 package (Windows)
    3. Simulated data (fallback)
    
    Args:
        symbol: Trading symbol (default: XAUUSD).
    
    Returns:
        Dict with symbol specifications, or None if unavailable.
    """
    connector = get_connector()
    
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
        except Exception as e:
            logger.warning(f"Docker bridge get_symbol_info failed: {e}")
    
    # Fall back to simulation
    if connector.in_simulation_mode:
        return {
            "symbol": symbol,
            "digits": 2,
            "point": 0.01,
            "spread": 25,
            "trade_mode": "real",
            "contract_size": 100.0,
            "tick_size": 0.01,
            "tick_value": 1.0,
            "min_volume": 0.01,
            "max_volume": 100.0,
            "volume_step": 0.01,
            "description": "Gold vs US Dollar (simulated)",
            "simulated": True,
        }
    
    if not connector.is_connected():
        return None
    
    info = mt5.symbol_info(symbol)
    if info is None:
        return None
    
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


# ─── Simulated Data Generator ───────────────────────────────
# Used when MT5 is not available (macOS without Docker bridge)

# Current XAUUSD price (approximate, updated periodically)
CURRENT_GOLD_PRICE = 4038.0  # As of July 2026


def _generate_simulated_rates(count: int = 100) -> list[dict]:
    """Generate simulated OHLCV data for testing."""
    import random
    import math
    
    base_price = CURRENT_GOLD_PRICE
    rates = []
    
    for i in range(count):
        # Random walk with realistic gold volatility (~0.5% daily)
        change = random.gauss(0, base_price * 0.002)
        open_price = base_price + change
        high = open_price + abs(random.gauss(0, base_price * 0.003))
        low = open_price - abs(random.gauss(0, base_price * 0.003))
        close = random.uniform(low, high)
        volume = random.randint(100, 10000)
        
        timestamp = int((datetime.now() - timedelta(hours=count - i)).timestamp())
        
        rates.append({
            "time": str(datetime.fromtimestamp(timestamp)),
            "timestamp": timestamp,
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": volume,
            "spread": random.randint(20, 40),
        })
        
        base_price = close
    
    return rates


def _generate_simulated_tick() -> dict:
    """Generate a simulated price tick."""
    import random
    base_price = CURRENT_GOLD_PRICE
    spread = random.uniform(0.2, 0.5)
    
    return {
        "symbol": "XAUUSD",
        "bid": round(base_price + random.gauss(0, base_price * 0.0005), 2),
        "ask": round(base_price + spread + random.gauss(0, base_price * 0.0005), 2),
        "spread": round(spread * 100, 0),
        "time": str(datetime.now()),
        "last": round(base_price + random.gauss(0, base_price * 0.0005), 2),
        "volume": random.randint(100, 5000),
    }
