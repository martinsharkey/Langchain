# MT5 Docker Bridge — Research & Fix Plan

## Current State

The bot is running in **simulation mode** because the Docker bridge (silicon-metatrader5) can connect via RPyC but cannot initialize the MetaTrader5 Python API. The core issue is:

1. **Docker container is running** — Colima + QEMU x86_64, container `siliconmt5` is up
2. **Bridge is connected** — `Ping: True`, RPyC connection to `localhost:8001` works
3. **MT5 terminal is running** — `terminal64.exe` is active inside the container, account `1176166` is logged in (window title confirms this)
4. **`initialize()` hangs** — The `MetaTrader5.initialize()` function hangs indefinitely under Wine because it uses Windows IPC (named pipes/shared memory) that Wine doesn't properly support
5. **`login()` returns `False`** — Can't log in programmatically because `initialize()` must be called first
6. **`account_info()` returns `None`** — Returns nothing because MT5 isn't "initialized" from the Python API's perspective

## Research Questions to Investigate

### Phase 1: Why does `initialize()` hang under Wine?

The `MetaTrader5` Python package (v5.0.5735) is a native Windows DLL (`_core.cp313-win_amd64.pyd`). The `initialize()` function uses Windows IPC mechanisms:
- Named pipes (`\\.\pipe\...`)
- Shared memory (memory-mapped files)
- Windows Events (synchronization objects)

Under Wine, these may not work correctly, especially in a headless Xvfb environment.

**Sources to mine:**
- [MetaTrader5 Python package source](https://github.com/mql5/MetaTrader5-Python) — Check how `initialize()` works internally
- [Wine AppDB for MetaTrader 5](https://appdb.winehq.org/objectManager.php?sClass=version&iId=37721) — Known issues with MT5 under Wine
- [silicon-metatrader5 GitHub Issues](https://github.com/bahadirumutiscimen/silicon-metatrader5/issues) — Known issues with the bridge
- [Wine named pipe implementation](https://wiki.winehq.org/Pipes) — How Wine handles named pipes
- [RPyC documentation](https://rpyc.readthedocs.io/) — How RPyC handles remote calls that hang

### Phase 2: Alternative approaches to get MT5 data on macOS

If the `initialize()` hang cannot be fixed, we need alternative approaches:

**Approach A: Bypass `initialize()` entirely**
- The silicon-metatrader5 bridge gives us raw RPyC access to the remote Python interpreter
- We can call `mt5.account_info()`, `mt5.copy_rates_from_pos()`, etc. directly WITHOUT calling `initialize()` first
- The README example shows `initialize()` but it may not be strictly required if the account is already logged in
- **Key question**: Does `copy_rates_from_pos()` work without `initialize()` if the account is already logged in?

**Approach B: Use MT5's Web API / REST API**
- Some brokers provide REST APIs for market data
- VTMarkets might have a REST API alternative
- [MetaTrader Web API](https://www.mql5.com/en/docs/integration) — Check if MT5 provides HTTP-based data access

**Approach C: Use MT5's MQL5 EA to export data**
- Write an MQL5 Expert Advisor that writes market data to a file or socket
- The EA runs inside MT5 and can access all data natively
- The Python bridge reads from the file/socket
- This bypasses the Python `MetaTrader5` package entirely

**Approach D: Use a different MT5 bridge**
- [python-mt5-connector](https://github.com/rosasurfer/mt5-connector) — Alternative MT5 bridge
- [MT5-Linux-Bridge](https://github.com/SheikhAmin/MT5-Linux-Bridge) — Another bridge approach
- [mt5linux](https://pypi.org/project/mt5linux/) — Python package for MT5 on Linux

**Approach E: Use the KasmVNC variant**
- The silicon-metatrader5 repo has a `docker_kasm/` variant that might handle things differently
- Check if the KasmVNC variant has different behavior with `initialize()`

### Phase 3: How to configure MT5 for headless/automated login

The README says: "First Action: Navigate to File > Open an Account, search for your broker, and log in manually."

But we need this to be automated. Research:
- Can MT5 be configured via `.dat` files (accounts.dat, servers.dat)?
- Can we pre-populate the Wine registry with account credentials?
- Can we use `wine` commands to automate the login process?
- Can we use `xdotool` or `xte` to automate the GUI login via Xvfb?

### Phase 4: Wine IPC compatibility

Deep dive into:
- How `MetaTrader5` Python package communicates with `terminal64.exe`
- Whether Wine's named pipe implementation supports this
- Whether there are workarounds (e.g., `wine64` vs `wine`, different Wine versions)
- Whether the `pysiliconwine:3.13.9` base image uses a specific Wine version that might have issues

## Implementation Plan (Draft)

Based on research findings, the implementation will likely involve one of:

### Option 1: Fix `initialize()` by patching the bridge
- Modify `start.sh` to ensure MT5 is fully initialized before starting the bridge
- Add a pre-initialization step that calls `mt5.initialize()` from within the container with proper timeout handling
- Modify the silicon-metatrader5 client to handle the case where `initialize()` hangs

### Option 2: Bypass `initialize()` entirely
- Modify `connector.py` to NOT call `initialize()` on the bridge
- Instead, directly call `account_info()`, `copy_rates_from_pos()`, etc.
- If these work without `initialize()`, this is the simplest fix

### Option 3: Use MQL5 EA for data export
- Write an MQL5 EA that writes market data to a shared file or TCP socket
- The EA runs inside MT5 and has native access to all data
- Python reads from the file/socket via the bridge
- This completely bypasses the `MetaTrader5` Python package

### Option 4: Use broker REST API
- Check if VTMarkets provides a REST API for market data
- Use the REST API directly from Python
- This bypasses MT5 entirely for data, but still needs MT5 for order execution

## Next Steps

1. Research each phase above by mining the listed sources
2. Test the most promising approaches
3. Create a detailed implementation plan
4. Present findings to user for approval
5. Switch to Code mode for implementation
