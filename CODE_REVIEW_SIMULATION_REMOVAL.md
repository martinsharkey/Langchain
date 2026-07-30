# COMPLETE CODE REVIEW: SIMULATION DATA REMOVAL PLAN

**Date**: 2026-07-30  
**Project**: LangChain Trading Bot  
**Scope**: Full codebase analysis for fake/simulated data  

---

## EXECUTIVE SUMMARY

The codebase has **EXTENSIVE simulation mode fallbacks** that generate fake data in 15+ locations. This fake data pollutes the system when MT5 connections fail or are unavailable.

**Total Locations with Fake Data Generation**: 17+  
**Status**: Requires complete removal and refactoring  
**Recommendation**: Fail hard on MT5 connection errors instead of silently falling back to simulation  

---

## PART 1: ALL SIMULATION DATA LOCATIONS

### 1. MT5 CONNECTOR - Automatic Simulation Fallback
**File**: `src/mt5/connector.py:104-134`

```python
def initialize(self, retries: int = 3, delay: int = 2) -> bool:
    # Try Docker bridge first (macOS with silicon-metatrader5)
    if SILICON_MT5_AVAILABLE:
        if self._connect_silicon_bridge(retries, delay):
            return True
    
    # Try native MT5 (Windows)
    if MT5_AVAILABLE:
        if self._connect_native(retries, delay):
            return True
    
    # ❌ FALLBACK TO SIMULATION
    self._simulation_mode = True
    self._connected = True
    logger.info("Simulation mode: MT5 connection simulated")
    return True  # ← RETURNS TRUE EVEN IN SIMULATION
```

**Problem**: Returns `True` even when simulated. System doesn't know it's using fake data.

**Lines Affected**: 104-134

---

### 2. MARKET DATA - Simulated OHLCV Candles
**File**: `src/mt5/data.py:304-336`

```python
def _generate_simulated_rates(count: int = 100) -> list[dict]:
    """Generate simulated OHLCV data for testing."""
    import random
    
    base_price = CURRENT_GOLD_PRICE  # 4038.0 hardcoded
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
```

**Problem**: Generates random price data that doesn't match actual market. Used 3 times in get_rates().

**Lines Affected**: 304-336, plus calls at 123, 128, 135

---

### 3. PRICE TICKS - Simulated Bid/Ask
**File**: `src/mt5/data.py:339-353`

```python
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
```

**Problem**: Random data. Used 4 times as fallback when MT5 unavailable.

**Lines Affected**: 339-353, plus calls at 192, 196, 200

---

### 4. ACCOUNT POSITIONS - Empty Fallback
**File**: `src/mt5/account.py:60-61`

```python
if connector.in_simulation_mode:
    return []  # No simulated positions
```

**Problem**: Returns empty list instead of failing. Hides connection status.

**Lines Affected**: 60-61

---

### 5. ACCOUNT HISTORY - Empty Fallback  
**File**: `src/mt5/account.py:146-147`

```python
if connector.in_simulation_mode:
    return []  # No simulated history
```

**Problem**: Returns empty list. Hides connection problems.

**Lines Affected**: 146-147

---

### 6. ORDERS - Simulated Order Placement
**File**: `src/mt5/orders.py:87-108`

```python
def place_order(
    symbol: str = "XAUUSD",
    order_type: str = "buy",
    volume: float = 0.1,
    price: Optional[float] = None,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
    comment: str = "",
) -> dict:
    
    connector = get_connector()
    
    if not connector.is_connected():
        return {"error": "Not connected to MT5"}
    
    try:
        # Check if account is logged in (not simulation mode)
        if not connector.in_simulation_mode:  # ← CHECKS SIMULATION
            # Real order code...
        
        # ❌ FALLBACK TO SIMULATION
        # Fall back to simulation
        if connector.in_simulation_mode:
            logger.warning(f"Simulating order: {order_type} {volume} {symbol}")
            return {
                "success": True,
                "simulated": True,  # ← FLAGS AS SIMULATED
                "ticket": int(time.time()),
                "price": price or 0,
                "volume": volume,
            }
```

**Problem**: Places simulated orders instead of real ones. System records fake trades.

**Lines Affected**: 87-108, 106-120

---

### 7. ORDERS - Cancel Order Simulation
**File**: `src/mt5/orders.py:291-310`

```python
def cancel_order(ticket: int) -> dict:
    # ...
    if not connector.in_simulation_mode:
        # Real cancel code...
    
    # ❌ FALLBACK TO SIMULATION
    if connector.in_simulation_mode:
        logger.warning(f"Simulating order cancellation: ticket {ticket}")
        return {
            "success": True,
            "simulated": True,
            "ticket": ticket,
        }
```

**Problem**: Cancels simulated orders instead of real ones.

**Lines Affected**: 291-310

---

### 8-12. DATA SOURCES - Multiple Mock Fallbacks

#### **news_aggregator.py:88** - Mock news
```python
if not self.has_api_key:
    return await self._collect_mock()

async def _collect_mock(self) -> Dict[str, Any]:
    """Return mock news data."""
    logger.info("Using mock news data (API key not available)")
```

#### **economic_calendar.py:297-343** - Mock calendar
```python
async def _collect_mock(self) -> Dict[str, Any]:
    """Return mock economic calendar data."""
    logger.info("Using mock economic calendar (web scraping unavailable)")
    mock_events = [...]  # Hardcoded events
```

#### **central_banks.py:211-220** - Mock central bank data
```python
def _collect_mock(self) -> Dict[str, Any]:
    """Return mock central bank data."""
    logger.info("Using mock central bank data")
```

#### **geopolitical.py:69-154** - Mock geopolitical data
```python
if self.use_mock:
    return await self._collect_mock()

async def _collect_mock(self) -> Dict[str, Any]:
    """Return mock geopolitical data."""
    mock_events = {...}  # Hardcoded events
```

#### **usd_strength.py:53-58** - Mock USD strength
```python
# For now, return mock data
return await self._collect_mock()

async def _collect_mock(self) -> Dict[str, Any]:
    """Return mock USD strength data."""
    logger.info("Using mock USD strength data")
```

**Problem**: All data sources have hardcoded mock data fallbacks.

**Lines Affected**: Multiple files in `src/data_sources/`

---

### 13-17. MAIN BOT - Simulation Mode Messages

**File**: `src/main.py`

#### Line 166 - Simulation banner
```python
console.print("[bold cyan]║[/bold cyan]  [bold]SIMULATION MODE:[/bold] No MT5 — synthetic data         [bold cyan]║[/bold cyan]")
```

#### Line 241 - Mode tracking
```python
"mode": "simulation" if (self.connector and self.connector.in_simulation_mode) else "live",
```

#### Line 347-364 - Handles simulation
```python
if self.connector.in_simulation_mode:
    console.print("  [bold yellow]SIMULATION MODE[/bold yellow]")
    # Continue anyway
```

#### Line 911-914 - Records simulated trades
```python
if self.connector and self.connector.in_simulation_mode:
    console.print(f"    [dim]This is a simulation. No real order was placed.[/dim]")

# In simulation, we record with pending outcome
```

**Problem**: Bot continues to operate in simulation mode, recording fake trades.

---

## PART 2: HOW FAKE DATA ENTERED THE SYSTEM

### Root Cause Chain:

```
1. MT5 Connection Fails (Docker unavailable, MT5 not installed, etc.)
   ↓
2. connector.initialize() reaches line 130-134
   ↓
3. Automatically sets: self._simulation_mode = True
   ↓
4. Returns: True (saying success)
   ↓
5. Bot thinks it's connected and continues
   ↓
6. Every data request checks connector.in_simulation_mode
   ↓
7. Falls back to _generate_simulated_* functions
   ↓
8. Fake data inserted into bot's decision-making
   ↓
9. Trades recorded to database with fake data
   ↓
10. Dashboard displays fake trades as if real
```

### Why It Happened:

1. **Graceful Degradation Pattern**: Code was designed to "fail gracefully" by continuing in simulation mode
2. **Development Convenience**: Made local development possible without MT5 installed
3. **Lack of Data Source Validation**: No system to detect and flag when fake data is used
4. **Silent Failures**: Simulation mode doesn't loud-fail, just quietly returns fake data

---

## PART 3: REMOVAL PLAN

### Phase 1: Mandatory MT5 Connection (FAIL HARD)

#### 1.1 Update `src/mt5/connector.py:104-134`

**Current (Graceful Fallback)**:
```python
def initialize(self, retries: int = 3, delay: int = 2) -> bool:
    # Try Docker bridge first
    if SILICON_MT5_AVAILABLE:
        if self._connect_silicon_bridge(retries, delay):
            return True
    
    # Try native MT5
    if MT5_AVAILABLE:
        if self._connect_native(retries, delay):
            return True
    
    # Fall back to simulation mode ← REMOVE THIS
    self._simulation_mode = True
    self._connected = True
    logger.info("Simulation mode: MT5 connection simulated")
    return True
```

**New (Fail Hard)**:
```python
def initialize(self, retries: int = 3, delay: int = 2) -> bool:
    """
    Initialize connection to MetaTrader 5.
    
    REQUIRED: Must connect to live MT5.
    Does NOT fall back to simulation mode.
    
    Tries:
    1. silicon-metatrader5 Docker bridge (macOS with Docker + Wine)
    2. Native MetaTrader5 package (Windows)
    
    Raises:
        ConnectionError: If MT5 cannot be reached
    
    Returns:
        True if connected successfully
    """
    # Try Docker bridge first (macOS with silicon-metatrader5)
    if SILICON_MT5_AVAILABLE:
        if self._connect_silicon_bridge(retries, delay):
            return True
    
    # Try native MT5 (Windows)
    if MT5_AVAILABLE:
        if self._connect_native(retries, delay):
            return True
    
    # ❌ FAIL HARD - NO SIMULATION
    error_msg = (
        "CRITICAL: Cannot connect to MetaTrader5.\n"
        f"  - Silicon MT5 available: {SILICON_MT5_AVAILABLE}\n"
        f"  - Native MT5 available: {MT5_AVAILABLE}\n"
        f"  - Account configured: {bool(MT5_ACCOUNT)}\n"
        f"  Ensure MT5 terminal is running and account {MT5_ACCOUNT} is logged in."
    )
    logger.critical(error_msg)
    raise ConnectionError(error_msg)
```

**Changes**:
- Line 130-134: Remove simulation fallback
- Add explicit error message
- Raise ConnectionError instead of silently succeeding

---

#### 1.2 Remove Simulation from `src/mt5/connector.py` Init

**Remove**:
- Line 85: `self._simulation_mode = True` initialization
- Update docstring (line 80): Remove "Falls back to simulation mode"

---

### Phase 2: Remove All Fake Data Generation Functions

#### 2.1 Delete `src/mt5/data.py:304-353`

**Remove Functions**:
```python
def _generate_simulated_rates(count: int = 100) -> list[dict]:
    # DELETE THIS ENTIRE FUNCTION (lines 304-336)

def _generate_simulated_tick() -> dict:
    # DELETE THIS ENTIRE FUNCTION (lines 339-353)
```

**Remove Constant**:
```python
CURRENT_GOLD_PRICE = 4038.0  # Line 301 - DELETE
```

**Remove All Fallback Calls**:
- Line 123: Remove `return _generate_simulated_rates(count)`
- Line 128: Remove `return _generate_simulated_rates(count)`
- Line 135: Remove `return _generate_simulated_rates(count)`
- Line 192: Remove `return _generate_simulated_tick()`
- Line 196: Remove `return _generate_simulated_tick()`
- Line 200: Remove `return _generate_simulated_tick()`

**New get_rates()**:
```python
@mt5_error_handler
def get_rates(
    symbol: str = "XAUUSD",
    timeframe: str = "H1",
    count: int = 100,
) -> list[dict]:
    """
    Get OHLCV (Open, High, Low, Close, Volume) rate data.
    
    REQUIRED: Must connect to live MT5.
    Does NOT fall back to simulated data.
    
    Args:
        symbol: Trading symbol (default: XAUUSD).
        timeframe: Timeframe string (M1, M5, M15, M30, H1, H4, D1, W1, MN1).
        count: Number of candles to fetch.
    
    Raises:
        ConnectionError: If MT5 not connected
    
    Returns:
        List of candle dictionaries with o, h, l, c, v, time fields.
    """
    connector = get_connector()
    
    if not connector.is_connected():
        raise ConnectionError("MT5 not connected")
    
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
                    f"No data for {symbol} {timeframe} via Docker bridge. "
                    f"Check MT5 terminal and account login."
                )
        except Exception as e:
            raise ConnectionError(f"Docker bridge get_rates failed: {e}")
    
    # Try native MT5 (Windows)
    if not connector.is_connected():
        raise ConnectionError("MT5 not connected")
    
    tf = TIMEFRAMES.get(timeframe, mt5.TIMEFRAME_H1)
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
    
    if rates is None or len(rates) == 0:
        raise ConnectionError(
            f"No data for {symbol} {timeframe}. "
            f"Check MT5 terminal and account login."
        )
    
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
```

**New get_last_price()**:
```python
@mt5_error_handler
def get_last_price(symbol: str = "XAUUSD") -> Optional[dict]:
    """
    Get the latest price tick for a symbol.
    
    REQUIRED: Must connect to live MT5.
    Does NOT fall back to simulated data.
    
    Args:
        symbol: Trading symbol (default: XAUUSD).
    
    Raises:
        ConnectionError: If MT5 not connected
    
    Returns:
        Dict with bid, ask, spread, and time
    """
    connector = get_connector()
    
    if not connector.is_connected():
        raise ConnectionError("MT5 not connected")
    
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
                    f"Check MT5 terminal and account login."
                )
        except Exception as e:
            raise ConnectionError(f"Docker bridge get_last_price failed: {e}")
    
    # Try native MT5 (Windows)
    if not connector.is_connected():
        raise ConnectionError("MT5 not connected")
    
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise ConnectionError(
            f"No tick data for {symbol}. "
            f"Check MT5 terminal and account login."
        )
    
    return {
        "symbol": symbol,
        "bid": tick.bid,
        "ask": tick.ask,
        "spread": tick.spread,
        "time": str(datetime.fromtimestamp(tick.time)),
        "last": tick.last,
        "volume": tick.volume,
    }
```

---

### Phase 3: Remove Simulated Orders

#### 3.1 Update `src/mt5/orders.py`

**Remove all simulation fallbacks**:
- Line 87-97: Remove check for simulation, just place real order
- Line 106-120: Remove simulated order return
- Line 291-310: Remove simulated cancel order

**New place_order()**:
```python
def place_order(
    symbol: str = "XAUUSD",
    order_type: str = "buy",
    volume: float = 0.1,
    price: Optional[float] = None,
    sl: Optional[float] = None,
    tp: Optional[float] = None,
    comment: str = "",
) -> dict:
    """
    Place a real order on MT5.
    
    REQUIRED: Must place real order on live account.
    Does NOT simulate.
    
    Raises:
        ConnectionError: If MT5 not connected
    """
    connector = get_connector()
    
    if not connector.is_connected():
        raise ConnectionError("MT5 not connected")
    
    try:
        # Use native MT5 (Windows)
        if MT5_AVAILABLE:
            order_type_int = mt5.ORDER_TYPE_BUY if order_type.lower() == "buy" else mt5.ORDER_TYPE_SELL
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type_int,
                "price": price,
                "sl": sl,
                "tp": tp,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }
            
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                raise Exception(f"Order failed: {result.comment}")
            
            return {
                "success": True,
                "ticket": result.order,
                "price": result.price,
                "volume": result.volume,
            }
    
    except Exception as e:
        logger.error(f"Failed to place order: {e}")
        raise ConnectionError(f"Order placement failed: {e}")
```

---

### Phase 4: Remove Mock Data Sources

#### 4.1 Update `src/data_sources/news_aggregator.py`

**Remove mock fallback**:
- Line 87-88: Remove `if not self.has_api_key: return await self._collect_mock()`
- Lines 182-220: Delete entire `_collect_mock()` function

**New collect()**:
```python
async def collect(self) -> Dict[str, Any]:
    """
    Collect financial news relevant to XAUUSD.
    
    REQUIRED: NEWSAPI_KEY environment variable must be set.
    Does NOT use mock data.
    
    Raises:
        ConnectionError: If API key not configured
    """
    logger.info("Collecting financial news...")
    
    if not self.has_api_key:
        raise ConnectionError(
            "NEWSAPI_KEY environment variable not set. "
            "Cannot collect real news data."
        )
    
    try:
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            # ... real API calls ...
```

#### 4.2 Update `src/data_sources/economic_calendar.py`

**Remove**:
- Line 297: Delete comment "# This uses a mock/cached approach"
- Lines 302-341: Delete entire `_collect_mock()` function

**New collect()**:
```python
async def collect(self) -> Dict[str, Any]:
    """
    Collect economic calendar events.
    
    REQUIRED: Must scrape real data or use real API.
    Does NOT use mock data.
    
    Raises:
        ConnectionError: If cannot reach data source
    """
    logger.info("Collecting economic calendar data...")
    
    try:
        # Real scraping/API implementation
        ...
    except Exception as e:
        raise ConnectionError(f"Cannot collect economic calendar: {e}")
```

#### 4.3 Similar updates for:
- `src/data_sources/central_banks.py` - Remove `_collect_mock()`
- `src/data_sources/geopolitical.py` - Remove `_collect_mock()` and `use_mock` flag
- `src/data_sources/usd_strength.py` - Remove `_collect_mock()`

---

### Phase 5: Update Main Bot

#### 5.1 `src/main.py` - Remove all simulation checks

**Remove**:
- Line 166: Remove simulation mode banner
- Line 241: Remove mode tracking to simulation option
- Line 347-364: Remove simulation mode handling
- Line 911-914: Remove simulation trade recording message
- Line 919: Remove "In simulation" comment

**Update initialization**:
```python
def __init__(self):
    """Initialize trading bot."""
    self.main_agent = None
    self.team = {}
    self.strategy = None
    
    # Initialize MT5 - REQUIRED to succeed
    try:
        self.connector = get_connector()
        ok = self.connector.initialize()
        if not ok:
            raise ConnectionError("Failed to initialize MT5 connector")
    except ConnectionError as e:
        logger.critical(f"FATAL: {e}")
        raise
    
    # Rest of initialization...
```

---

### Phase 6: Configuration Updates

#### 6.1 `src/config.py:136-142` - Remove simulation warnings

**Current**:
```python
# MT5 warnings (optional - simulation mode works without these)
if not MT5_ACCOUNT:
    warnings.append("MT5_ACCOUNT is not set. Running in simulation mode.")
if not MT5_PASSWORD:
    warnings.append("MT5_PASSWORD is not set. Running in simulation mode.")
if not MT5_SERVER:
    warnings.append("MT5_SERVER is not set. Running in simulation mode.")
```

**New**:
```python
# MT5 configuration - REQUIRED
if not MT5_ACCOUNT:
    warnings.append("CRITICAL: MT5_ACCOUNT not set. Cannot start bot.")
    raise ValueError("MT5_ACCOUNT environment variable required")
if not MT5_PASSWORD:
    warnings.append("CRITICAL: MT5_PASSWORD not set. Cannot start bot.")
    raise ValueError("MT5_PASSWORD environment variable required")
if not MT5_SERVER:
    warnings.append("CRITICAL: MT5_SERVER not set. Cannot start bot.")
    raise ValueError("MT5_SERVER environment variable required")
```

---

### Phase 7: Dashboard Updates

#### 7.1 `dashboard_fixed.py:69` and `dashboard_clean.py`

**Remove all simulation checks**:
```python
# Remove
if c.is_connected() and not c.in_simulation_mode:

# Replace with
if not c.is_connected():
    raise ConnectionError("Dashboard requires live MT5 connection")

# Simple: if we got here, it's live
```

---

## PART 4: IMPLEMENTATION ORDER

### Step 1: Configuration (Safe)
- [ ] Update `src/config.py` to require MT5 credentials
- Time: 30 minutes

### Step 2: Fail Hard on Connection (Critical)
- [ ] Update `src/mt5/connector.py:initialize()` to raise error instead of falling back
- [ ] Add clear error messages
- Time: 30 minutes

### Step 3: Remove Data Generation (Mechanical)
- [ ] Delete `_generate_simulated_rates()` from `src/mt5/data.py`
- [ ] Delete `_generate_simulated_tick()` from `src/mt5/data.py`
- [ ] Remove all fallback calls in `get_rates()` and `get_last_price()`
- [ ] Update functions to raise errors on connection failure
- Time: 45 minutes

### Step 4: Remove Simulated Orders (Critical)
- [ ] Update `src/mt5/orders.py:place_order()` to fail on simulation
- [ ] Update `src/mt5/orders.py:cancel_order()` to fail on simulation
- [ ] Remove all simulated return paths
- Time: 45 minutes

### Step 5: Remove Mock Data Sources (Parallel)
- [ ] `src/data_sources/news_aggregator.py` - Remove mock, require API key
- [ ] `src/data_sources/economic_calendar.py` - Remove mock, implement real scraping or require API
- [ ] `src/data_sources/central_banks.py` - Remove mock
- [ ] `src/data_sources/geopolitical.py` - Remove mock and use_mock flag
- [ ] `src/data_sources/usd_strength.py` - Remove mock
- Time: 1.5 hours

### Step 6: Update Main Bot (Cleanup)
- [ ] Remove all `in_simulation_mode` checks from `src/main.py`
- [ ] Remove simulation banners and messages
- [ ] Update error handling to fail fast
- Time: 30 minutes

### Step 7: Dashboard Updates (Cleanup)
- [ ] Update `dashboard_fixed.py` to remove simulation checks
- [ ] Update `dashboard_clean.py` to remove simulation checks
- Time: 30 minutes

### Step 8: Testing (Verification)
- [ ] Test with valid MT5 credentials - should work
- [ ] Test with invalid MT5 credentials - should fail with clear error
- [ ] Test with MT5 unavailable - should fail with clear error
- Time: 45 minutes

---

## PART 5: EXPECTED BEHAVIOR AFTER CLEANUP

### Before (Current)
```
MT5 Connection Fails
  → Falls back to simulation mode
  → Generates random prices
  → Records fake trades
  → Dashboard shows fake data
  → User thinks system is working (it's not)
```

### After (New)
```
MT5 Connection Fails
  → Raises ConnectionError immediately
  → Clear error message explaining issue
  → Bot exits with visible error
  → User knows to fix MT5 connection
  → No fake data ever created
```

---

## PART 6: SUMMARY OF CHANGES

| File | Action | Reason |
|------|--------|--------|
| `src/mt5/connector.py` | Remove simulation fallback | Fail hard on connection errors |
| `src/mt5/data.py` | Delete _generate_simulated_* functions | No fake price data |
| `src/mt5/orders.py` | Remove simulated order returns | No fake order execution |
| `src/data_sources/*.py` | Remove all mock/fallback methods | Only real data sources |
| `src/main.py` | Remove simulation checks/messages | Cleaner code, no false positives |
| `dashboard_fixed.py` | Remove simulation UI | Only show real data |
| `dashboard_clean.py` | Remove simulation UI | Only show real data |
| `src/config.py` | Make MT5 credentials required | Force real connection |

---

## PART 7: RISK ASSESSMENT

**Risks**:
1. Bot won't start if MT5 not running - **MITIGATED BY**: Clear error messages
2. Requires MT5 terminal always running - **MITIGATED BY**: Document as requirement
3. Previous code relied on simulation fallback - **MITIGATED BY**: Explicit search and replacement

**Benefits**:
1. ✅ No fake data ever enters system
2. ✅ Immediate failure on connection problems
3. ✅ Dashboard shows only real data
4. ✅ Clear distinction between development and production
5. ✅ No silent failures or data pollution

---

## CONCLUSION

The codebase has **17+ locations** where fake data is silently generated. This needs to be completely removed and replaced with fail-fast error handling. The system should only operate when connected to live MT5, never with simulated data.

**Total Implementation Time**: ~5 hours  
**Lines to Delete**: ~500+ lines of simulation code  
**Lines to Modify**: ~50+ error handling updates  
**Complexity**: Medium (mechanical changes, good error handling coverage)

