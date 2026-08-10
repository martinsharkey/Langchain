"""
Wine Bridge Client — communicates with the MT5 Wine bridge service.

The bridge runs as a Windows Python process under Wine, using the native
MetaTrader5 package to connect to the MT5 terminal. This client provides
a clean async/sync interface for the macOS Python bot to call MT5 functions.

Usage:
    from src.mt5.bridge_client import WineBridgeClient
    
    bridge = WineBridgeClient()
    if bridge.connect():
        rates = bridge.get_rates("XAUUSD", "H1", 100)
        price = bridge.get_last_price("XAUUSD")
        account = bridge.get_account_info()
        bridge.disconnect()
"""

import json
import socket
import time
import subprocess
import os
from typing import Optional, Any
from src.utils.logger import get_logger

logger = get_logger("mt5.bridge")

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 4590
BRIDGE_TIMEOUT = 10.0  # Connection timeout
REQUEST_TIMEOUT = 30.0  # Per-request timeout

# Wine bridge paths
WINE_BIN = "/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine"
WINEPREFIX = os.path.expanduser("~/Library/Application Support/net.metaquotes.wine.metatrader5")
WINE_PYTHON = os.path.join(WINEPREFIX, "drive_c", "Python312", "python.exe")
BRIDGE_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mt5", "wine_bridge.py")


class WineBridgeClient:
    """Client for communicating with the MT5 Wine bridge service."""

    def __init__(self):
        self._sock: Optional[socket.socket] = None
        self._buffer = ""
        self._request_id = 0
        self._bridge_process: Optional[subprocess.Popen] = None

    # ─── Connection Management ───────────────────────────────

    def connect(self, auto_start: bool = True, retries: int = 3) -> bool:
        """
        Connect to the Wine bridge service.
        
        Args:
            auto_start: If True, attempt to start the bridge if not running.
            retries: Number of connection retry attempts.
        
        Returns:
            True if connected successfully.
        """
        for attempt in range(1, retries + 1):
            try:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.settimeout(BRIDGE_TIMEOUT)
                self._sock.connect((BRIDGE_HOST, BRIDGE_PORT))
                logger.info(f"Connected to Wine bridge (attempt {attempt})")
                
                # Verify connection with ping
                result = self._send_request("ping", {})
                if result and result.get("status") == "ok":
                    mt5_ver = result.get("mt5_version", "unknown")
                    logger.info(f"Wine bridge verified — MT5 version: {mt5_ver}")
                    return True
                
                self._sock = None
                
            except (socket.timeout, ConnectionRefusedError, OSError) as e:
                logger.debug(f"Bridge connection failed (attempt {attempt}): {e}")
                self._sock = None
                
                if auto_start and attempt == 1:
                    self._start_bridge()
                
                if attempt < retries:
                    time.sleep(2)
        
        logger.warning("Could not connect to Wine bridge — will use simulation mode")
        return False

    def disconnect(self):
        """Disconnect from the bridge."""
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._buffer = ""

    @property
    def is_connected(self) -> bool:
        """Check if connected to the bridge."""
        if self._sock is None:
            return False
        try:
            self._sock.settimeout(1)
            result = self._send_request("ping", {})
            return result is not None and result.get("status") == "ok"
        except Exception:
            return False
        finally:
            try:
                self._sock.settimeout(REQUEST_TIMEOUT)
            except Exception:
                pass

    # ─── Bridge Lifecycle ────────────────────────────────────

    def _start_bridge(self) -> bool:
        """Start the Wine bridge process."""
        if not os.path.exists(WINE_BIN):
            logger.error(f"Wine binary not found: {WINE_BIN}")
            return False
        
        if not os.path.exists(WINE_PYTHON):
            logger.error(f"Windows Python not found: {WINE_PYTHON}")
            return False
        
        if not os.path.exists(BRIDGE_SCRIPT):
            logger.error(f"Bridge script not found: {BRIDGE_SCRIPT}")
            return False

        logger.info("Starting Wine bridge service...")
        
        try:
            env = os.environ.copy()
            env["WINEPREFIX"] = WINEPREFIX
            
            self._bridge_process = subprocess.Popen(
                [WINE_BIN, WINE_PYTHON, BRIDGE_SCRIPT],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            # Wait for bridge to start
            time.sleep(3)
            return True
            
        except Exception as e:
            logger.error(f"Failed to start Wine bridge: {e}")
            return False

    def stop_bridge(self):
        """Stop the bridge process."""
        if self._bridge_process:
            try:
                self._bridge_process.terminate()
                self._bridge_process.wait(timeout=5)
            except Exception:
                try:
                    self._bridge_process.kill()
                except Exception:
                    pass
            self._bridge_process = None

    # ─── Request/Response ────────────────────────────────────

    def _send_request(self, method: str, params: dict = None) -> Optional[Any]:
        """Send a JSON-RPC request and wait for response."""
        if self._sock is None:
            return None

        self._request_id += 1
        request = {
            "id": self._request_id,
            "method": method,
            "params": params or {},
        }

        try:
            # Send request
            payload = (json.dumps(request) + "\n").encode("utf-8")
            self._sock.sendall(payload)

            # Read response
            self._sock.settimeout(REQUEST_TIMEOUT)
            
            while "\n" not in self._buffer:
                data = self._sock.recv(65536)
                if not data:
                    self._sock = None
                    return None
                self._buffer += data.decode("utf-8")

            line, self._buffer = self._buffer.split("\n", 1)
            response = json.loads(line.strip())

            if response.get("error"):
                logger.error(f"Bridge error in {method}: {response['error']}")
                return None

            return response.get("result")

        except (socket.timeout, ConnectionResetError, BrokenPipeError, OSError) as e:
            logger.warning(f"Bridge connection lost: {e}")
            self._sock = None
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from bridge: {e}")
            return None

    # ─── MT5 API Methods ─────────────────────────────────────

    def get_rates(self, symbol: str = "XAUUSD", timeframe: str = "H1", count: int = 100) -> Optional[list]:
        """Get OHLCV rate data."""
        return self._send_request("get_rates", {
            "symbol": symbol,
            "timeframe": timeframe,
            "count": count,
        })

    def get_last_price(self, symbol: str = "XAUUSD") -> Optional[dict]:
        """Get the latest price tick."""
        return self._send_request("get_last_price", {
            "symbol": symbol,
        })

    def get_account_info(self) -> Optional[dict]:
        """Get account information."""
        return self._send_request("get_account_info", {})

    def get_symbol_info(self, symbol: str = "XAUUSD") -> Optional[dict]:
        """Get symbol information."""
        return self._send_request("get_symbol_info", {
            "symbol": symbol,
        })

    def place_order(self, symbol: str = "XAUUSD", order_type: str = "buy",
                    volume: float = 0.01, price: float = 0.0,
                    sl: float = 0.0, tp: float = 0.0,
                    comment: str = "Trading Bot", magic: int = 123456) -> Optional[dict]:
        """Place a trade order."""
        return self._send_request("place_order", {
            "symbol": symbol,
            "type": order_type,
            "volume": volume,
            "price": price,
            "sl": sl,
            "tp": tp,
            "comment": comment,
            "magic": magic,
        })

    def get_positions(self, symbol: Optional[str] = None) -> Optional[list]:
        """Get open positions."""
        return self._send_request("get_positions", {
            "symbol": symbol,
        })

    def close_position(self, ticket: int, symbol: str = "", volume: float = 0.0) -> Optional[dict]:
        """Close a position by ticket."""
        return self._send_request("close_position", {
            "ticket": ticket,
            "symbol": symbol,
            "volume": volume,
        })

    def get_history(self, days: int = 7, from_date: Optional[int] = None,
                    to_date: Optional[int] = None) -> Optional[list]:
        """Get historical deals."""
        return self._send_request("get_history", {
            "days": days,
            "from": from_date,
            "to": to_date,
        })


# ─── Singleton ───────────────────────────────────────────────

_bridge_instance: Optional[WineBridgeClient] = None


def get_bridge() -> WineBridgeClient:
    """Get or create the Wine bridge client singleton."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = WineBridgeClient()
    return _bridge_instance
