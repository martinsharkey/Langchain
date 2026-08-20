"""
MetaTrader 5 connection manager.
Handles the Docker bridge (silicon-metatrader5) on macOS and provides a clean interface for MT5 operations.

Architecture:
  On macOS, the MetaTrader5 Python package is Windows-native and cannot be installed
  directly. Instead, we use a Docker container running MT5 under Wine+QEMU with a
  Python bridge (silicon-metatrader5 project).

  macOS Python (bot)  ←→  RPyC (localhost:8001)  ←→  Docker container (Wine+MT5+Python)
                                                              ↕
                                                      MetaTrader5 package (Windows)
                                                              ↕
                                                      MT5 Terminal (Wine)

  When the Docker bridge is unavailable or no account is logged in, the bot falls
  back to simulation mode.
"""

import os
import sys
import time
import json
import threading
from typing import Optional, Callable, Any
from functools import wraps

from src.config import MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER, MT5_PATH
from src.utils.logger import get_logger

logger = get_logger("mt5")

# Try to import siliconmetatrader5 (Docker bridge client)
try:
    from siliconmetatrader5 import MetaTrader5 as SiliconMetaTrader5
    SILICON_MT5_AVAILABLE = True
except ImportError:
    SILICON_MT5_AVAILABLE = False
    SiliconMetaTrader5 = None

# Try to import native MetaTrader5 (Windows only)
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None


# ─── Constants ───────────────────────────────────────────────

DOCKER_BRIDGE_HOST = os.getenv("MT5_BRIDGE_HOST", "localhost")
DOCKER_BRIDGE_PORT = int(os.getenv("MT5_BRIDGE_PORT", "8001"))
DOCKER_BRIDGE_TIMEOUT = int(os.getenv("MT5_BRIDGE_TIMEOUT", "10"))  # seconds for initial connect
MT5_INIT_TIMEOUT = int(os.getenv("MT5_INIT_TIMEOUT", "8"))  # seconds for remote initialize() call


# ─── Global MT5 Lock ─────────────────────────────────────────
# The MT5 IPC layer (native Windows package and especially the Docker/RPyC bridge)
# is single-channel and prone to head-of-line blocking.  All mt5.* calls that can
# contend with order execution MUST be serialized behind this lock.  It is an RLock
# so nested acquisitions on the same thread do not deadlock (e.g. account info
# inside a position check).
_MT5_LOCK = threading.RLock()


def mt5_lock() -> threading.RLock:
    """Return the module-level MT5 reentrant lock.

    Usage:
        with mt5_lock():
            mt5.order_send(...)
    """
    return _MT5_LOCK


# ─── Error Handling Decorator ───────────────────────────────

def mt5_error_handler(func: Callable) -> Callable:
    """Decorator to handle MT5 errors gracefully."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"MT5 error in {func.__name__}: {str(e)}")
            return {"error": str(e), "success": False}
    return wrapper


# ─── Connection Manager ─────────────────────────────────────

class MT5Connector:
    """
    Manages the connection to MetaTrader 5.
    
    REQUIRED: Must connect to live MT5 to operate.
    Does NOT fall back to simulation mode.
    
    Tries:
    1. silicon-metatrader5 Docker bridge (macOS with Docker + Wine)
    2. Native MetaTrader5 package (Windows)
    
    Raises ConnectionError if unable to connect to live MT5.
    """
    
    def __init__(self):
        self._connected = False
        self._account_info = None
        self._silicon_mt5: Optional[SiliconMetaTrader5] = None
        self._bridge_available = False  # True if Docker bridge is reachable
        self._mt5_api_available = False  # True if remote mt5.initialize() succeeded
        
        if SILICON_MT5_AVAILABLE:
            logger.info(
                f"siliconmetatrader5 client available — will connect to "
                f"Docker bridge at {DOCKER_BRIDGE_HOST}:{DOCKER_BRIDGE_PORT}"
            )
        elif MT5_AVAILABLE:
            logger.info("MetaTrader5 package available — will connect directly")
        else:
            logger.critical(
                "MT5 is not available on this system.\n"
                "  - Silicon MT5 (Docker): Not available\n"
                "  - Native MT5 package: Not installed\n"
                "Ensure MetaTrader5 is installed on Windows or Docker bridge is available on macOS."
            )
    
    def initialize(self, retries: int = 3, delay: int = 2) -> bool:
        """
        Initialize connection to MetaTrader 5.
        
        REQUIRED: Must connect to live MT5. Does NOT fall back to simulation.
        
        Tries:
        1. silicon-metatrader5 Docker bridge (macOS with Docker + Wine)
        2. Native MetaTrader5 package (Windows)
        
        Args:
            retries: Number of connection retry attempts.
            delay: Delay between retries in seconds.
        
        Returns:
            True if connected successfully to live MT5.
            
        Raises:
            ConnectionError: If unable to connect to live MT5
        """
        # Try Docker bridge first (macOS with silicon-metatrader5)
        if SILICON_MT5_AVAILABLE:
            if self._connect_silicon_bridge(retries, delay):
                return True
        
        # Try native MT5 (Windows)
        if MT5_AVAILABLE:
            if self._connect_native(retries, delay):
                return True
        
        # FAIL HARD - NO SIMULATION MODE
        error_msg = (
            "CRITICAL: Cannot connect to MetaTrader 5.\n"
            f"  - Account: {MT5_ACCOUNT}\n"
            f"  - Server: {MT5_SERVER}\n"
            f"  - Silicon MT5 available: {SILICON_MT5_AVAILABLE}\n"
            f"  - Native MT5 available: {MT5_AVAILABLE}\n"
            "\n"
            "TROUBLESHOOTING:\n"
            "  1. Ensure MetaTrader 5 terminal is running\n"
            "  2. Verify account {MT5_ACCOUNT} is logged in to {MT5_SERVER}\n"
            "  3. Check that MT5_ACCOUNT, MT5_PASSWORD, and MT5_SERVER are set in .env\n"
            "  4. On macOS, ensure Docker bridge is running: docker run -d --name metatrader5 ...\n"
            "\n"
            "The bot ONLY operates with live MT5 connection. No simulation mode available."
        )
        logger.critical(error_msg)
        raise ConnectionError(error_msg)
    
    def _remote_call_with_timeout(self, code: str, timeout: int = 5) -> Optional[Any]:
        """
        Execute Python code on the remote (Docker container) side with a timeout.
        
        Uses the silicon-metatrader5 client's execute() method to run code,
        and eval() to retrieve results. The timeout is implemented via a
        threading.Timer that interrupts the remote call if it hangs.
        
        Args:
            code: Python code to execute on the remote side.
            timeout: Maximum time in seconds to wait for the call.
        
        Returns:
            The result of the remote code execution, or None if timed out.
        """
        if not self._silicon_mt5:
            logger.warning("No bridge client available for remote call")
            return None
        
        result = {"success": False, "value": None, "error": None}
        call_complete = threading.Event()
        
        def _do_remote_call():
            """Execute the remote call in a separate thread."""
            try:
                # First, execute the code on the remote side
                self._silicon_mt5.execute(code)
                # Then, try to retrieve a result variable if it was set
                try:
                    val = self._silicon_mt5.eval("_result")
                    result["success"] = True
                    result["value"] = val
                except Exception:
                    # Code executed but no _result variable — that's OK
                    result["success"] = True
                    result["value"] = None
            except Exception as e:
                result["success"] = False
                result["error"] = str(e)
            finally:
                call_complete.set()
        
        # Start the remote call in a daemon thread
        thread = threading.Thread(target=_do_remote_call, daemon=True)
        thread.start()
        
        # Wait for completion with timeout
        completed = call_complete.wait(timeout=timeout)
        
        if not completed:
            logger.warning(f"Remote call timed out after {timeout}s")
            return None
        
        if not result["success"]:
            logger.warning(f"Remote call failed: {result['error']}")
            return None
        
        return result["value"]
    
    def _remote_eval(self, expression: str) -> Optional[Any]:
        """
        Evaluate a Python expression on the remote side.
        
        Uses the silicon-metatrader5 client's eval() method directly.
        This is for simple expressions that return a value immediately.
        
        Args:
            expression: Python expression to evaluate on the remote side.
        
        Returns:
            The result of the expression, or None on failure.
        """
        if not self._silicon_mt5:
            return None
        try:
            return self._silicon_mt5.eval(expression)
        except Exception as e:
            logger.warning(f"Remote eval failed: {e}")
            return None
    
    def _connect_silicon_bridge(self, retries: int, delay: int) -> bool:
        """Connect using the silicon-metatrader5 Docker bridge."""
        if self._connected:
            return True
        
        for attempt in range(1, retries + 1):
            logger.info(
                f"Connecting to MT5 via Docker bridge "
                f"(attempt {attempt}/{retries})..."
            )
            
            try:
                # Connect to the Docker bridge via RPyC
                # Note: The constructor connects immediately via rpyc.classic.connect()
                silicon_mt5 = SiliconMetaTrader5(
                    host=DOCKER_BRIDGE_HOST,
                    port=DOCKER_BRIDGE_PORT,
                    keepalive=True,
                )
                
                # Verify the connection is alive
                if not silicon_mt5.ping():
                    logger.warning("Docker bridge ping failed")
                    silicon_mt5.close()
                    if attempt < retries:
                        time.sleep(delay)
                    continue
                
                self._silicon_mt5 = silicon_mt5
                self._bridge_available = True
                
                # ── Step 1: Try initialize() with timeout protection ──
                # The remote MT5's initialize() hangs indefinitely under Wine
                # because it uses Windows named pipes (IPC). We wrap it in a
                # thread with a configurable timeout to avoid blocking forever.
                logger.info("Attempting remote mt5.initialize() with timeout...")
                
                init_code = """
import MetaTrader5 as mt5
import threading as _thr

_init_result = {"success": False, "error": None}

def _do_init():
    try:
        ok = mt5.initialize()
        _init_result["success"] = ok
    except Exception as e:
        _init_result["error"] = str(e)

_t = _thr.Thread(target=_do_init, daemon=True)
_t.start()
_t.join(timeout=5)  # 5 second timeout for initialize()

if _t.is_alive():
    _init_result["error"] = "initialize() timed out (Wine IPC hang)"
else:
    pass  # _init_result already set

_result = _init_result
"""
                
                init_result = self._remote_call_with_timeout(init_code, timeout=MT5_INIT_TIMEOUT + 2)
                
                if init_result and init_result.get("success"):
                    # initialize() succeeded! MT5 API is fully available
                    self._mt5_api_available = True
                    logger.info("Remote mt5.initialize() succeeded!")
                    
                    # Now try to get account info
                    try:
                        info = silicon_mt5.account_info()
                    except Exception:
                        info = None
                    
                    if info is not None:
                        self._connected = True
                        self._account_info = {
                            "balance": info.balance,
                            "equity": info.equity,
                            "margin": info.margin,
                            "free_margin": info.margin_free,
                            "leverage": info.leverage,
                            "currency": info.currency,
                            "name": info.name,
                            "server": info.server,
                            "simulated": False,
                        }
                        logger.info(
                            f"Connected to MT5 via Docker bridge — "
                            f"Account: {info.name} (${info.balance:.2f})"
                        )
                        return True
                    else:
                        # No account logged in on bridge
                        raise ConnectionError(
                            f"MT5 account not logged in on Docker bridge.\n"
                            f"To log in:\n"
                            f"  1. Open http://localhost:6081/vnc.html in a browser\n"
                            f"  2. In the MT5 window, go to File > Open an Account\n"
                            f"  3. Search for '{MT5_SERVER}'\n"
                            f"  4. Login with Account: {MT5_ACCOUNT}"
                        )
                else:
                    # initialize() timed out or failed
                    error_msg = init_result.get("error") if init_result else "timeout"
                    raise ConnectionError(
                        f"Remote MT5 initialize() failed: {error_msg}.\n"
                        f"Ensure MT5 terminal is running in the Docker container."
                    )
            
            except Exception as e:
                logger.warning(f"Docker bridge connection failed: {e}")
                if self._silicon_mt5:
                    try:
                        self._silicon_mt5.close()
                    except Exception:
                        pass
                    self._silicon_mt5 = None
                    self._bridge_available = False
            
            if attempt < retries:
                logger.info(f"Retrying bridge connection in {delay}s...")
                time.sleep(delay)
        
        logger.warning("Could not connect via Docker bridge")
        return False
    
    def _connect_native(self, retries: int, delay: int) -> bool:
        """Connect using native MetaTrader5 package (Windows only)."""
        if self._connected:
            return True
        
        for attempt in range(1, retries + 1):
            logger.info(f"Connecting to MT5 natively (attempt {attempt}/{retries})...")
            
            # Strategy:
            # 1. Try initialize() WITHOUT path first. If a terminal is already running,
            #    MT5 will attach to it. Passing `path` makes MT5 try to LAUNCH a new
            #    terminal, which fails when one is already running (error -10003).
            # 2. Only fall back to path-based init if no terminal is running yet.
            init_kwargs = {
                "login": MT5_ACCOUNT if MT5_ACCOUNT > 0 else None,
                "password": MT5_PASSWORD if MT5_PASSWORD else None,
                "server": MT5_SERVER if MT5_SERVER else None,
            }
            
            initialized = mt5.initialize(**init_kwargs)
            
            if initialized:
                self._connected = True
                self._account_info = self._get_account_info()
                logger.info(f"Connected to MT5 successfully")
                return True
            
            error = mt5.last_error() if hasattr(mt5, 'last_error') else "Unknown"
            logger.warning(f"MT5 connection failed: {error}")
            
            if not MT5_PATH or attempt < retries:
                if attempt < retries:
                    time.sleep(delay)
                continue
            
            init_kwargs["path"] = MT5_PATH
            logger.info(f"Retrying with explicit terminal path: {MT5_PATH}")
            initialized = mt5.initialize(**init_kwargs)
            
            if initialized:
                self._connected = True
                self._account_info = self._get_account_info()
                logger.info(f"Connected to MT5 successfully via explicit path")
                return True
            
            error = mt5.last_error() if hasattr(mt5, 'last_error') else "Unknown"
            logger.warning(f"MT5 connection with path failed: {error}")
            
            if attempt < retries:
                time.sleep(delay)
        
        logger.warning("Could not connect to MT5")
        return False
    
    def shutdown(self):
        """Shutdown the MT5 connection."""
        if self._silicon_mt5:
            try:
                self._silicon_mt5.close()
            except Exception as e:
                logger.warning(f"Error closing Docker bridge: {e}")
            self._silicon_mt5 = None
            self._bridge_available = False
        
        if self._connected and MT5_AVAILABLE:
            mt5.shutdown()
        
        self._connected = False
        logger.info("MT5 connection closed")
    
    def is_connected(self) -> bool:
        """Check if connected to MT5."""
        if self._silicon_mt5:
            try:
                return self._silicon_mt5.ping()
            except Exception:
                return False

        if MT5_AVAILABLE:
            try:
                return self._connected and mt5.terminal_info() is not None
            except Exception:
                return False

        return self._connected
    
    def ensure_connected(self) -> bool:
        """Ensure MT5 is connected; reconnect if the connection dropped."""
        if self.is_connected():
            return True
        logger.warning("MT5 connection lost — attempting reconnect...")
        self._connected = False
        try:
            if self._connect_native(retries=3, delay=2):
                logger.info("MT5 reconnect successful")
                return True
        except Exception as e:
            logger.warning(f"MT5 reconnect failed: {e}")
        return False
    
    @property
    def bridge_available(self) -> bool:
        """Check if the Docker bridge is available (even if no account logged in)."""
        return self._bridge_available
    
    @property
    def mt5_api_available(self) -> bool:
        """Check if the remote MT5 API (initialize) is available."""
        return self._mt5_api_available
    
    def get_silicon_mt5(self) -> Optional[SiliconMetaTrader5]:
        """Get the silicon-metatrader5 client instance."""
        return self._silicon_mt5
    
    def remote_execute(self, code: str, timeout: int = 10) -> Optional[Any]:
        """
        Execute arbitrary Python code on the remote (Docker container) side.
        
        This provides raw RPyC access to the remote Python interpreter,
        bypassing the silicon-metatrader5 client's method wrappers.
        
        Args:
            code: Python code to execute remotely.
            timeout: Maximum time in seconds to wait.
        
        Returns:
            The value of the _result variable set by the code, or None.
        """
        return self._remote_call_with_timeout(code, timeout=timeout)
    
    def remote_eval(self, expression: str) -> Optional[Any]:
        """
        Evaluate a Python expression on the remote (Docker container) side.
        
        Args:
            expression: Python expression to evaluate remotely.
        
        Returns:
            The result of the expression, or None on failure.
        """
        return self._remote_eval(expression)
    
    def _get_account_info(self) -> Optional[dict]:
        """Get account information from MT5."""
        if self._silicon_mt5:
            try:
                info = self._silicon_mt5.account_info()
                if info is None:
                    return None
                return {
                    "balance": info.balance,
                    "equity": info.equity,
                    "margin": info.margin,
                    "free_margin": info.margin_free,
                    "leverage": info.leverage,
                    "currency": info.currency,
                    "name": info.name,
                    "server": info.server,
                    "simulated": False,
                }
            except Exception as e:
                logger.warning(f"Failed to get account info from bridge: {e}")
                return None
        
        if MT5_AVAILABLE:
            info = mt5.account_info()
            if info is None:
                return None
            return {
                "balance": info.balance,
                "equity": info.equity,
                "margin": info.margin,
                "free_margin": info.margin_free,
                "leverage": info.leverage,
                "currency": info.currency,
                "name": info.name,
                "server": info.server,
                "simulated": False,
            }
        
        return None
    
    def get_account_info(self) -> Optional[dict]:
        """Get current account information."""
        if self._connected:
            return self._get_account_info()
        return None


# ─── Singleton Instance ─────────────────────────────────────

_connector_instance: Optional[MT5Connector] = None


def get_connector() -> MT5Connector:
    """Get or create the MT5 connector singleton."""
    global _connector_instance
    if _connector_instance is None:
        _connector_instance = MT5Connector()
    return _connector_instance
