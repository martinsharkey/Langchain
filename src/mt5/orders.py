"""
Order management for MetaTrader 5.
Provides order placement, modification, and closing functionality.

On macOS, orders are executed via the silicon-metatrader5 Docker bridge (RPyC to container).
On Windows, orders are executed directly via the MetaTrader5 package.
Falls back to simulated order execution when neither is available.
"""

from typing import Optional
from enum import Enum
from datetime import datetime

from src.mt5.connector import get_connector, MT5_AVAILABLE, mt5, mt5_error_handler, SILICON_MT5_AVAILABLE, mt5_lock
from src.mt5.account import get_positions
from src.utils.logger import get_logger

logger = get_logger("mt5.orders")


class OrderType(Enum):
    """Order types supported by MT5."""
    BUY = 0
    SELL = 1
    BUY_LIMIT = 2
    SELL_LIMIT = 3
    BUY_STOP = 4
    SELL_STOP = 5


class OrderFilling(Enum):
    """Order filling modes."""
    FOK = 0  # Fill or Kill
    IOC = 1  # Immediate or Cancel
    RETURN = 2  # Return remaining


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
def place_order(
    symbol: str = "XAUUSD",
    order_type: str = "buy",
    volume: float = 0.01,
    price: Optional[float] = None,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
    comment: str = "LangChain Agent",
    magic: int = 123456,
) -> dict:
    """
    Place a market or pending order on live MT5.
    
    REQUIRED: Must place real orders on live account.
    Does NOT simulate orders.
    
    Args:
        symbol: Trading symbol (default: XAUUSD).
        order_type: "buy" or "sell".
        volume: Lot size (default: 0.01).
        price: Optional specific price. If None, uses market price.
        sl: Stop loss price.
        tp: Take profit price.
        comment: Order comment.
        magic: Magic number for order identification.
    
    Returns:
        Dict with order result details
        
    Raises:
        ConnectionError: If MT5 not connected or order fails
    """
    connector = get_connector()
    
    if not connector.is_connected():
        raise ConnectionError("MT5 not connected. Cannot place order.")
    
    # Try silicon-metatrader5 Docker bridge first (macOS)
    silicon_mt5 = _get_silicon_mt5()
    if silicon_mt5:
        try:
            result = _place_order_via_silicon(
                silicon_mt5, symbol, order_type, volume,
                price, sl, tp, comment, magic
            )
            if result.get("success"):
                return result
            else:
                raise ConnectionError(f"Order failed via Docker bridge: {result}")
        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"Docker bridge place_order failed: {e}")
    
    # Try native MT5 (Windows)
    if not MT5_AVAILABLE:
        raise ConnectionError("MT5 package not available")
    
    if not connector.is_connected():
        raise ConnectionError("MT5 not connected. Cannot place order.")
    
    return _place_order_native(symbol, order_type, volume, price, sl, tp, comment, magic)


def _place_order_via_silicon(
    silicon_mt5,
    symbol: str,
    order_type: str,
    volume: float,
    price: Optional[float],
    sl: Optional[float],
    tp: Optional[float],
    comment: str,
    magic: int,
) -> dict:
    """Place an order via the silicon-metatrader5 Docker bridge."""
    # Determine order type
    if order_type.lower() == "buy":
        mt5_type = silicon_mt5.ORDER_TYPE_BUY
    elif order_type.lower() == "sell":
        mt5_type = silicon_mt5.ORDER_TYPE_SELL
    else:
        return {"success": False, "error": f"Invalid order type: {order_type}"}
    
    # Get current price if not specified
    if price is None:
        tick = silicon_mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"success": False, "error": f"Cannot get price for {symbol}"}
        price = tick.ask if mt5_type == silicon_mt5.ORDER_TYPE_BUY else tick.bid
    
    # Prepare order request
    request = {
        "action": silicon_mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": mt5_type,
        "price": float(price),
        "sl": float(sl) if sl else 0.0,
        "tp": float(tp) if tp else 0.0,
        "deviation": 20,
        "magic": magic,
        "comment": comment,
        "type_time": silicon_mt5.ORDER_TIME_GTC,
        "type_filling": silicon_mt5.ORDER_FILLING_IOC,
    }
    
    # Send order
    result = silicon_mt5.order_send(request)
    if result is None:
        return {"success": False, "error": "Order send returned None"}
    
    if result.retcode == silicon_mt5.TRADE_RETCODE_DONE:
        logger.info(
            f"Order placed via Docker bridge: {order_type.upper()} {volume} {symbol} "
            f"@ ${result.price:.2f} (order: {result.order})"
        )
        return {
            "success": True,
            "order_id": result.order,
            "deal_id": result.deal,
            "price": result.price,
            "volume": result.volume,
            "message": f"Order {result.order} executed via Docker bridge",
            "simulated": False,
        }
    else:
        logger.error(f"Order failed via Docker bridge: retcode={result.retcode}")
        return {
            "success": False,
            "error": f"Order failed: retcode={result.retcode}",
            "retcode": result.retcode,
            "comment": result.comment,
            "simulated": False,
        }


def _place_order_native(
    symbol: str,
    order_type: str,
    volume: float,
    price: Optional[float],
    sl: Optional[float],
    tp: Optional[float],
    comment: str,
    magic: int,
) -> dict:
    """Place an order via native MetaTrader5 package (Windows)."""
    with mt5_lock():
        # Determine order type
        if order_type.lower() == "buy":
            mt5_type = mt5.ORDER_TYPE_BUY
        elif order_type.lower() == "sell":
            mt5_type = mt5.ORDER_TYPE_SELL
        else:
            return {"success": False, "error": f"Invalid order type: {order_type}"}
        
        # Get current price if not specified
        if price is None:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return {"success": False, "error": f"Cannot get price for {symbol}"}
            price = tick.ask if mt5_type == mt5.ORDER_TYPE_BUY else tick.bid
        
        # Prepare order request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": mt5_type,
            "price": float(price),
            "sl": float(sl) if sl else 0.0,
            "tp": float(tp) if tp else 0.0,
            "deviation": 20,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        # Send order
        result = mt5.order_send(request)
        if result is None:
            return {"success": False, "error": "Order send returned None"}
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(
                f"Order placed: {order_type.upper()} {volume} {symbol} "
                f"@ ${result.price:.2f} (order: {result.order})"
            )
            return {
                "success": True,
                "order_id": result.order,
                "deal_id": result.deal,
                "price": result.price,
                "volume": result.volume,
                "message": f"Order {result.order} executed",
                "simulated": False,
            }
        else:
            logger.error(f"Order failed: retcode={result.retcode}")
            return {
                "success": False,
                "error": f"Order failed: retcode={result.retcode}",
                "retcode": result.retcode,
                "comment": result.comment,
                "simulated": False,
            }


@mt5_error_handler
def close_order(
    ticket: int,
    symbol: str = "",
    volume: float = 0.0,
) -> dict:
    """
    Close an open order by ticket number on live MT5.
    
    REQUIRED: Must close real orders on live account.
    Does NOT simulate closures.
    
    Args:
        ticket: Order ticket number to close.
        symbol: Symbol of the order (optional, for bridge).
        volume: Volume to close (0 = full volume).
    
    Returns:
        Dict with close result details
        
    Raises:
        ConnectionError: If MT5 not connected or close fails
    """
    connector = get_connector()
    
    if not connector.is_connected():
        raise ConnectionError("MT5 not connected. Cannot close order.")
    
    # Try silicon-metatrader5 Docker bridge first (macOS)
    silicon_mt5 = _get_silicon_mt5()
    if silicon_mt5:
        try:
            result = _close_order_via_silicon(
                silicon_mt5, ticket, symbol, volume
            )
            if result.get("success"):
                return result
            else:
                raise ConnectionError(f"Order close failed via Docker bridge: {result}")
        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"Docker bridge close_order failed: {e}")
    
    # Try native MT5 (Windows)
    if not MT5_AVAILABLE:
        raise ConnectionError("MT5 package not available")
    
    if not connector.is_connected():
        raise ConnectionError("MT5 not connected. Cannot close order.")
    
    return _close_order_native(ticket, volume)


def _close_order_via_silicon(
    silicon_mt5,
    ticket: int,
    symbol: str = "",
    volume: float = 0.0,
) -> dict:
    """Close an order via the silicon-metatrader5 Docker bridge."""
    # Get position to determine type
    position = silicon_mt5.positions_get(ticket=ticket)
    if position is None or len(position) == 0:
        return {"success": False, "error": f"Position {ticket} not found"}
    
    position = position[0]
    position_type = position.type
    
    # Determine opposite order type for closing
    if position_type == silicon_mt5.ORDER_TYPE_BUY:
        order_type = silicon_mt5.ORDER_TYPE_SELL
        price = silicon_mt5.symbol_info_tick(position.symbol).bid
    else:
        order_type = silicon_mt5.ORDER_TYPE_BUY
        price = silicon_mt5.symbol_info_tick(position.symbol).ask
    
    close_volume = volume if volume > 0 else float(position.volume)
    
    request = {
        "action": silicon_mt5.TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "volume": close_volume,
        "type": order_type,
        "position": ticket,
        "price": float(price),
        "deviation": 20,
        "magic": position.magic,
        "comment": "Close by bot",
        "type_time": silicon_mt5.ORDER_TIME_GTC,
        "type_filling": silicon_mt5.ORDER_FILLING_IOC,
    }
    
    result = silicon_mt5.order_send(request)
    if result is None:
        return {"success": False, "error": "Order send returned None"}
    
    if result.retcode == silicon_mt5.TRADE_RETCODE_DONE:
        logger.info(f"Position {ticket} closed via Docker bridge (deal: {result.deal})")
        return {
            "success": True,
            "order_id": result.order,
            "deal_id": result.deal,
            "price": result.price,
            "message": f"Position {ticket} closed via Docker bridge",
            "simulated": False,
        }
    else:
        return {
            "success": False,
            "error": f"Close failed: retcode={result.retcode}",
            "simulated": False,
        }


def _close_order_native(
    ticket: int,
    volume: float = 0.0,
) -> dict:
    """Close an order via native MetaTrader5 package (Windows)."""
    with mt5_lock():
        # Get position to determine type
        position = mt5.positions_get(ticket=ticket)
        if position is None or len(position) == 0:
            return {"success": False, "error": f"Position {ticket} not found"}
        
        position = position[0]
        position_type = position.type
        
        # Determine opposite order type for closing
        if position_type == mt5.ORDER_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(position.symbol).bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(position.symbol).ask
        
        close_volume = volume if volume > 0 else float(position.volume)
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": close_volume,
            "type": order_type,
            "position": ticket,
            "price": float(price),
            "deviation": 20,
            "magic": position.magic,
            "comment": "Close by bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result is None:
            return {"success": False, "error": "Order send returned None"}
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Position {ticket} closed (deal: {result.deal})")
            return {
                "success": True,
                "order_id": result.order,
                "deal_id": result.deal,
                "price": result.price,
                "message": f"Position {ticket} closed",
                "simulated": False,
        }
    else:
        return {
            "success": False,
            "error": f"Close failed: retcode={result.retcode}",
            "simulated": False,
        }

