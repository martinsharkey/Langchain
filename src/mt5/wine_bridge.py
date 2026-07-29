"""
Wine Bridge — MetaTrader 5 Bridge Service for macOS.

This script runs under Wine (Windows Python) and provides a TCP socket interface
for the macOS Python bot to communicate with the MetaTrader5 Windows-native package.

Architecture:
  macOS Python (bot)  ←→  TCP socket (localhost:4590)  ←→  Wine Python (this script)
                                                                      ↕
                                                              MetaTrader5 package
                                                                      ↕
                                                              MT5 Terminal (Wine)

Usage (start bridge):
  WINEPREFIX=~/Library/Application Support/net.metaquotes.wine.metatrader5 \\
  /Applications/MetaTrader\\ 5.app/Contents/SharedSupport/wine/bin/wine \\
  python.exe src/mt5/wine_bridge.py

Protocol:
  JSON messages over TCP, terminated by newline.
  Request:  {"id": 1, "method": "get_rates", "params": {"symbol": "XAUUSD", "timeframe": "H1", "count": 100}}
  Response: {"id": 1, "result": {...}, "error": null}
"""

import json
import socket
import struct
import sys
import os
import traceback
from typing import Optional

# Add the project root to path so we can import config
# __file__ is at .../src/mt5/wine_bridge.py, so we go up 3 levels to project root
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

HOST = "127.0.0.1"
PORT = 4590

# ─── MT5 Connection ─────────────────────────────────────────

mt5 = None
_connected = False


def ensure_mt5_initialized() -> bool:
    """Initialize MT5 connection if not already connected."""
    global _connected, mt5

    if _connected:
        return True

    try:
        import MetaTrader5 as mt5_mod
        mt5 = mt5_mod
    except ImportError:
        return False

    # Try to initialize with demo account credentials from config
    try:
        from src.config import MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER
        login = MT5_ACCOUNT if MT5_ACCOUNT > 0 else None
        password = MT5_PASSWORD if MT5_PASSWORD else None
        server = MT5_SERVER if MT5_SERVER else None
    except (ImportError, Exception):
        login = None
        password = None
        server = None

    # Initialize MT5
    initialized = mt5.initialize(
        login=login,
        password=password,
        server=server,
    )

    if initialized:
        _connected = True
        return True

    return False


# ─── API Methods ─────────────────────────────────────────────


def handle_get_rates(params: dict) -> dict:
    """Get OHLCV rate data."""
    symbol = params.get("symbol", "XAUUSD")
    timeframe_str = params.get("timeframe", "H1")
    count = params.get("count", 100)

    TIMEFRAMES = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
        "W1": mt5.TIMEFRAME_W1,
        "MN1": mt5.TIMEFRAME_MN1,
    }

    tf = TIMEFRAMES.get(timeframe_str, mt5.TIMEFRAME_H1)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)

    if rates is None or len(rates) == 0:
        return {"error": f"No data for {symbol} {timeframe_str}", "rates": []}

    result = []
    for rate in rates:
        result.append({
            "time": rate.time,
            "open": float(rate.open),
            "high": float(rate.high),
            "low": float(rate.low),
            "close": float(rate.close),
            "volume": int(rate.tick_volume),
            "spread": int(rate.spread),
            "real_volume": int(rate.real_volume),
        })

    return {"rates": result, "count": len(result)}


def handle_get_last_price(params: dict) -> dict:
    """Get the latest price tick."""
    symbol = params.get("symbol", "XAUUSD")

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"error": f"No tick data for {symbol}"}

    return {
        "symbol": symbol,
        "bid": float(tick.bid),
        "ask": float(tick.ask),
        "spread": int(tick.spread),
        "last": float(tick.last),
        "volume": int(tick.volume),
        "time": tick.time,
        "flags": tick.flags,
    }


def handle_get_account_info(params: dict) -> dict:
    """Get account information."""
    info = mt5.account_info()
    if info is None:
        return {"error": "No account info available"}

    return {
        "login": info.login,
        "balance": float(info.balance),
        "equity": float(info.equity),
        "margin": float(info.margin),
        "margin_free": float(info.margin_free),
        "margin_level": float(info.margin_level),
        "leverage": int(info.leverage),
        "currency": info.currency,
        "name": info.name,
        "server": info.server,
        "company": info.company,
        "trade_allowed": info.trade_allowed,
    }


def handle_get_symbol_info(params: dict) -> dict:
    """Get symbol information."""
    symbol = params.get("symbol", "XAUUSD")

    info = mt5.symbol_info(symbol)
    if info is None:
        return {"error": f"No symbol info for {symbol}"}

    return {
        "symbol": info.name,
        "digits": info.digits,
        "point": float(info.point),
        "spread": info.spread,
        "spread_float": info.spread_float,
        "trade_mode": info.trade_mode,
        "trade_excecution": info.trade_excecution,
        "trade_stops_level": info.trade_stops_level,
        "trade_freeze_level": info.trade_freeze_level,
        "swap_long": info.swap_long,
        "swap_short": info.swap_short,
        "swap_mode": info.swap_mode,
        "margin_initial": info.margin_initial,
        "margin_maintenance": info.margin_maintenance,
        "contract_size": info.contract_size,
        "tick_size": float(info.tick_size),
        "tick_value": float(info.tick_value),
        "min_volume": float(info.volume_min),
        "max_volume": float(info.volume_max),
        "volume_step": float(info.volume_step),
        "description": info.description,
        "path": info.path,
        "currency_base": info.currency_base,
        "currency_profit": info.currency_profit,
        "currency_margin": info.currency_margin,
        "start_time": info.start_time,
        "expiration_time": info.expiration_time,
        "time": info.time,
    }


def handle_place_order(params: dict) -> dict:
    """Place a trade order."""
    from datetime import datetime

    symbol = params.get("symbol", "XAUUSD")
    order_type = params.get("type", "buy")  # "buy" or "sell"
    volume = params.get("volume", 0.01)
    price = params.get("price", 0.0)
    sl = params.get("sl", 0.0)
    tp = params.get("tp", 0.0)
    comment = params.get("comment", "Trading Bot")
    magic = params.get("magic", 123456)

    # Determine order type
    if order_type.lower() == "buy":
        mt5_type = mt5.ORDER_TYPE_BUY
    elif order_type.lower() == "sell":
        mt5_type = mt5.ORDER_TYPE_SELL
    else:
        return {"error": f"Invalid order type: {order_type}"}

    # Get current price if not specified
    if price == 0.0:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"error": f"Cannot get price for {symbol}"}
        price = tick.ask if mt5_type == mt5.ORDER_TYPE_BUY else tick.bid

    # Prepare order request
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": mt5_type,
        "price": float(price),
        "sl": float(sl) if sl > 0 else 0.0,
        "tp": float(tp) if tp > 0 else 0.0,
        "deviation": 20,
        "magic": magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    # Send order
    result = mt5.order_send(request)
    if result is None:
        return {"error": "Order send returned None"}

    return {
        "retcode": result.retcode,
        "deal": result.deal,
        "order": result.order,
        "volume": float(result.volume),
        "price": float(result.price),
        "bid": float(result.bid),
        "ask": float(result.ask),
        "comment": result.comment,
        "request_id": result.request_id,
        "retcode_external": result.retcode_external,
        "success": result.retcode == mt5.TRADE_RETCODE_DONE,
    }


def handle_get_positions(params: dict) -> dict:
    """Get open positions."""
    symbol = params.get("symbol", None)  # None = all symbols

    if symbol:
        positions = mt5.positions_get(symbol=symbol)
    else:
        positions = mt5.positions_get()

    if positions is None:
        return {"positions": [], "count": 0}

    result = []
    for pos in positions:
        result.append({
            "ticket": pos.ticket,
            "symbol": pos.symbol,
            "type": "buy" if pos.type == mt5.ORDER_TYPE_BUY else "sell",
            "volume": float(pos.volume),
            "price_open": float(pos.price_open),
            "sl": float(pos.sl),
            "tp": float(pos.tp),
            "price_current": float(pos.price_current),
            "profit": float(pos.profit),
            "swap": float(pos.swap),
            "commission": float(pos.commission),
            "magic": pos.magic,
            "comment": pos.comment,
            "time": pos.time,
        })

    return {"positions": result, "count": len(result)}


def handle_close_position(params: dict) -> dict:
    """Close a position by ticket."""
    ticket = params.get("ticket", 0)
    symbol = params.get("symbol", "")
    volume = params.get("volume", 0.0)

    if ticket == 0:
        return {"error": "No ticket specified"}

    # Get position to determine type
    position = mt5.positions_get(ticket=ticket)
    if position is None or len(position) == 0:
        return {"error": f"Position {ticket} not found"}

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
        return {"error": "Order send returned None"}

    return {
        "retcode": result.retcode,
        "deal": result.deal,
        "order": result.order,
        "volume": float(result.volume),
        "price": float(result.price),
        "success": result.retcode == mt5.TRADE_RETCODE_DONE,
    }


def handle_get_history(params: dict) -> dict:
    """Get historical deals."""
    from datetime import datetime

    days = params.get("days", 7)
    from_date = params.get("from", None)
    to_date = params.get("to", None)

    if from_date and to_date:
        dt_from = datetime.fromtimestamp(from_date)
        dt_to = datetime.fromtimestamp(to_date)
    else:
        from datetime import timedelta
        dt_to = datetime.now()
        dt_from = dt_to - timedelta(days=days)

    deals = mt5.history_deals_get(dt_from, dt_to)
    if deals is None:
        return {"deals": [], "count": 0}

    result = []
    for deal in deals:
        result.append({
            "ticket": deal.ticket,
            "order": deal.order,
            "symbol": deal.symbol,
            "type": deal.type,
            "volume": float(deal.volume),
            "price": float(deal.price),
            "commission": float(deal.commission),
            "swap": float(deal.swap),
            "profit": float(deal.profit),
            "magic": deal.magic,
            "comment": deal.comment,
            "time": deal.time,
        })

    return {"deals": result, "count": len(result)}


def handle_ping(params: dict) -> dict:
    """Health check."""
    return {
        "status": "ok",
        "mt5_connected": _connected,
        "mt5_version": mt5.__version__ if mt5 else None,
    }


# ─── Method Router ───────────────────────────────────────────

METHODS = {
    "get_rates": handle_get_rates,
    "get_last_price": handle_get_last_price,
    "get_account_info": handle_get_account_info,
    "get_symbol_info": handle_get_symbol_info,
    "place_order": handle_place_order,
    "get_positions": handle_get_positions,
    "close_position": handle_close_position,
    "get_history": handle_get_history,
    "ping": handle_ping,
}


# ─── TCP Server ──────────────────────────────────────────────


def handle_client(conn: socket.socket):
    """Handle a single client connection."""
    buffer = ""
    while True:
        try:
            data = conn.recv(65536)
            if not data:
                break

            buffer += data.decode("utf-8")

            # Process complete messages (newline-delimited JSON)
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                except json.JSONDecodeError as e:
                    response = {"id": None, "error": f"Invalid JSON: {str(e)}", "result": None}
                    conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
                    continue

                req_id = request.get("id", 0)
                method = request.get("method", "")
                params = request.get("params", {})

                if method not in METHODS:
                    response = {
                        "id": req_id,
                        "error": f"Unknown method: {method}",
                        "result": None,
                    }
                else:
                    try:
                        # Ensure MT5 is initialized for non-ping methods
                        if method != "ping" and not ensure_mt5_initialized():
                            response = {
                                "id": req_id,
                                "error": "MT5 not initialized",
                                "result": None,
                            }
                        else:
                            result = METHODS[method](params)
                            response = {
                                "id": req_id,
                                "result": result,
                                "error": result.get("error") if isinstance(result, dict) and "error" in result else None,
                            }
                    except Exception as e:
                        response = {
                            "id": req_id,
                            "error": f"{type(e).__name__}: {str(e)}",
                            "result": None,
                        }

                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

        except (socket.timeout, ConnectionResetError, BrokenPipeError):
            break
        except Exception as e:
            try:
                response = {"id": None, "error": f"Server error: {str(e)}", "result": None}
                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
            except Exception:
                break

    try:
        conn.close()
    except Exception:
        pass


def run_server():
    """Run the Wine bridge TCP server."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    server.settimeout(1.0)

    print(f"MT5 Wine Bridge listening on {HOST}:{PORT}", flush=True)

    # Try to initialize MT5 immediately
    if ensure_mt5_initialized():
        print("MT5 initialized successfully", flush=True)
        info = handle_get_account_info({})
        if "error" not in info:
            print(f"Account: {info.get('name', 'N/A')} ({info.get('server', 'N/A')})", flush=True)
            print(f"Balance: ${info.get('balance', 0):.2f}", flush=True)
    else:
        print("MT5 not available yet — will retry on each request", flush=True)

    try:
        while True:
            try:
                conn, addr = server.accept()
                print(f"Client connected: {addr}", flush=True)
                handle_client(conn)
                print(f"Client disconnected: {addr}", flush=True)
            except socket.timeout:
                continue
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
    finally:
        if _connected and mt5:
            mt5.shutdown()
        server.close()
        print("Bridge stopped", flush=True)


if __name__ == "__main__":
    run_server()
