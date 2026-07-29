"""
Account operations for MetaTrader 5.
Provides account information, positions, and trade history.

On macOS, data is fetched via the silicon-metatrader5 Docker bridge (RPyC to container).
On Windows, data is fetched directly via the MetaTrader5 package.
"""

from typing import Optional

from src.mt5.connector import get_connector, MT5_AVAILABLE, mt5, mt5_error_handler, SILICON_MT5_AVAILABLE
from src.utils.logger import get_logger

logger = get_logger("mt5.account")


def _get_silicon_mt5():
    """Get the silicon-metatrader5 client from the connector if available."""
    try:
        connector = get_connector()
        if connector.bridge_available:
            return connector.get_silicon_mt5()
    except Exception:
        pass
    return None


@mt5_error_handler
def get_account_info() -> dict:
    """
    Get current account information.
    
    Returns:
        Dict with balance, equity, margin, free_margin, leverage, currency.
    """
    connector = get_connector()
    info = connector.get_account_info()
    if info:
        return info
    return {"error": "Not connected to MT5"}


@mt5_error_handler
def get_positions(symbol: Optional[str] = None) -> list[dict]:
    """
    Get open positions.
    
    Priority:
    1. silicon-metatrader5 Docker bridge (macOS with Docker + Wine)
    2. Native MetaTrader5 package (Windows)
    
    Args:
        symbol: Optional symbol filter (e.g., "XAUUSD").
    
    Returns:
        List of position dictionaries.
    """
    connector = get_connector()
    
    if connector.in_simulation_mode:
        return []  # No simulated positions
    
    # Try silicon-metatrader5 Docker bridge first (macOS)
    silicon_mt5 = _get_silicon_mt5()
    if silicon_mt5:
        try:
            if symbol:
                positions = silicon_mt5.positions_get(symbol=symbol)
            else:
                positions = silicon_mt5.positions_get()
            
            if positions is None:
                return []
            
            return _format_positions(positions)
        except Exception as e:
            logger.warning(f"Docker bridge get_positions failed: {e}")
    
    if not connector.is_connected():
        return [{"error": "Not connected to MT5"}]
    
    # Try native MT5 (Windows)
    if symbol:
        positions = mt5.positions_get(symbol=symbol)
    else:
        positions = mt5.positions_get()
    
    if positions is None:
        return []
    
    return _format_positions(positions)


def _format_positions(positions) -> list[dict]:
    """Format MT5 positions into standard dict format."""
    result = []
    for pos in positions:
        result.append({
            "ticket": pos.ticket,
            "symbol": pos.symbol,
            "type": "buy" if pos.type == 0 else "sell",
            "volume": pos.volume,
            "price_open": pos.price_open,
            "price_current": pos.price_current,
            "sl": pos.sl,
            "tp": pos.tp,
            "profit": pos.profit,
            "swap": pos.swap,
            "comment": pos.comment,
            "time": str(pos.time),
        })
    return result


@mt5_error_handler
def get_position_count(symbol: Optional[str] = None) -> int:
    """Get the number of open positions."""
    return len(get_positions(symbol))


@mt5_error_handler
def get_total_profit() -> float:
    """Get total profit from all open positions."""
    positions = get_positions()
    total = sum(p.get("profit", 0) for p in positions if "error" not in p)
    return total


@mt5_error_handler
def get_history(deals: int = 100) -> list[dict]:
    """
    Get recent trade history.
    
    Priority:
    1. silicon-metatrader5 Docker bridge (macOS with Docker + Wine)
    2. Native MetaTrader5 package (Windows)
    
    Args:
        deals: Number of recent deals to fetch.
    
    Returns:
        List of deal dictionaries.
    """
    connector = get_connector()
    
    if connector.in_simulation_mode:
        return []  # No simulated history
    
    # Try silicon-metatrader5 Docker bridge first (macOS)
    silicon_mt5 = _get_silicon_mt5()
    if silicon_mt5:
        try:
            import datetime
            from pytz import timezone
            
            to_time = datetime.datetime.now(timezone("UTC"))
            from_time = to_time - datetime.timedelta(days=7)
            
            history = silicon_mt5.history_deals_get(from_time, to_time)
            if history is None:
                return []
            
            result = []
            for deal in history[-deals:]:
                result.append({
                    "ticket": deal.ticket,
                    "symbol": deal.symbol,
                    "type": "buy" if deal.type == 0 else "sell",
                    "volume": deal.volume,
                    "price": deal.price,
                    "profit": deal.profit,
                    "commission": deal.commission,
                    "swap": deal.swap,
                    "comment": deal.comment,
                    "time": str(deal.time),
                })
            return result
        except Exception as e:
            logger.warning(f"Docker bridge get_history failed: {e}")
    
    if not connector.is_connected():
        return [{"error": "Not connected to MT5"}]
    
    # Try native MT5 (Windows)
    import datetime
    from pytz import timezone
    
    to_time = datetime.datetime.now(timezone("UTC"))
    from_time = to_time - datetime.timedelta(days=7)
    
    history = mt5.history_deals_get(from_time, to_time)
    if history is None:
        return []
    
    result = []
    for deal in history[-deals:]:
        result.append({
            "ticket": deal.ticket,
            "symbol": deal.symbol,
            "type": "buy" if deal.type == 0 else "sell",
            "volume": deal.volume,
            "price": deal.price,
            "profit": deal.profit,
            "commission": deal.commission,
            "swap": deal.swap,
            "comment": deal.comment,
            "time": str(deal.time),
        })
    
    return result
