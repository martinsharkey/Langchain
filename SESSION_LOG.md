# Trading Bot — Session Log

## Session Start
**Date:** 2026-07-29  
**Time:** 20:29 CET  
**Goal:** Implement, connect, test, and run the LangChain XAUUSD trading bot on VT Markets demo.

---

## Phase 1: Environment Discovery
- **Action:** Listed workspace contents under `C:\Users\MartinSharkey\Documents\Langchain`.
- **Rationale:** Needed to locate source code, MT5 terminal, and credentials.
- **Outcome:** Found `langchain/` project with full bot source and `MT5/` folder containing `terminal64.exe`.
- **Files of interest:**
  - `langchain/src/main.py`
  - `langchain/src/mt5/connector.py`
  - `langchain/.env`

---

## Phase 2: Credential & Path Verification
- **Action:** Read `.env` and identified demo credentials.
- **Rationale:** Required for MT5 login and bot configuration.
- **Outcome:**
  - Account: `1176166`
  - Server: `VTMarkets-Demo`
  - MT5 Terminal: `C:\Users\MartinSharkey\Documents\Langchain\MT5\VT Markets (Pty) MT5 Terminal\terminal64.exe`

---

## Phase 3: Dependency Installation
- **Action:** Created venv and installed requirements.
- **Rationale:** Bot requires isolated Python environment with specific package versions.
- **Outcome:**
  - venv created with `--system-site-packages` to reuse globally installed packages.
  - Key packages verified: `MetaTrader5`, `langchain`, `langgraph`, `litellm`, `chromadb`, `pandas`, `rich`, `httpx`, `beautifulsoup4`, `pytest`.
- **Note:** Unpinned `langchain`/`langgraph` caused resolver backtracking; system-site-packages workaround used.

---

## Phase 4: MT5 Connection
- **Action:** Launched `terminal64.exe` and tested connector.
- **Rationale:** End-to-end test requires live MT5 connection.
- **Outcome:**
  - MT5 terminal started successfully (PID 1328, 7400).
  - Native MT5 connection succeeded.
  - Account info retrieved:
    - Name: `CHRISTOPHER MARTIN SHARKEY`
    - Balance: `$5,141.38`
    - Server: `VTMarkets-Demo`
    - Leverage: `1:500`
    - Currency: `GBP`
  - Market data fetch verified:
    - Last XAUUSD bid: `4039.11`
    - Last XAUUSD ask: `4041.09`
    - Spread: `20.0` pips

---

## Phase 5: Strategy Verification
- **Action:** Imported and initialized `XAUUSDStrategy`.
- **Rationale:** Confirms strategy module loads without errors.
- **Outcome:** Strategy `XAUUSD_Multi_Indicator` initialized with default parameters.

---

## Phase 6: End-to-End Test (In Progress)
- **Next:** Run full `TradingBot` lifecycle:
  1. `check_environment()`
  2. `setup_environment()`
  3. `build_team()`
  4. `connect_mt5()`
  5. `initialize_strategy()`
  6. `run_trading_cycle()`
- **Success criteria:** Bot completes at least one full cycle without exceptions, logs decisions, and records outcomes.

---

## Phase 7: Autonomous Learning Mode
- **Pending:** Enable confidence-based trading:
  - Bot runs continuous cycles.
  - Learns from outcomes via meta-strategy system.
  - Adjusts position sizing and strategy weights based on performance.

---

## Rationale Summary
1. **Why native MT5 on Windows?** The host OS is Windows (`win32`), so the native `MetaTrader5` Python package works directly. No Docker/Wine bridge needed.
2. **Why system-site-packages venv?** Avoided dependency resolver conflicts from unpinned `langchain`/`langgraph` by reusing already-installed compatible versions.
3. **Why launch terminal64 manually?** The demo account requires the terminal to be running for the Python package to initialize and fetch live data.

---

## Session End
**Status:** MT5 connected, dependencies installed, end-to-end test pending.

---

## Session 2 — Real Execution, Learning Loop & New Dashboard
**Date:** 2026-07-30

### Full-codebase review (Opus 4.8)
Found the system was a sophisticated **analysis engine disconnected at 3 seams**:
1. Execution was fake — an LLM narrated trades; the real `place_order` was orphaned.
2. Learning loop never closed — a `NameError` killed position tracking; outcomes were synthetic.
3. Sentiment/research pipeline was orphaned and un-importable.
Plus critical safety gaps (wrong gold lot math, no algo/kill/spread checks, no symbol-suffix handling).
See `REPAIR_PLAN.md`.

### Phase 0 — Stabilize (done)
- Fixed dead `EconomicCalendarSourceMock`/`CentralBankSourceMock` imports (app now boots).
- Fixed `main.py` `trade_result` NameError; connector double-`@property` + unreachable code.
- Added `TRADING_MODE` (OBSERVE|PAPER|LIVE_MICRO|LIVE), default OBSERVE.
- `NewsAggregatorSource` degrades gracefully (no boot crash without NEWSAPI_KEY).
- Reordered `app.py` so dashboard starts first; research is non-fatal.

### Diagnosis of "why it never traded" (verified with live MT5)
- The tradable gold symbol is **`XAUUSD-ECN`** (`trade_mode=4`, order_check "Done").
- `XAUUSD.crp` is **trade-disabled** (`trade_mode=0`, retcode 10017) — must be skipped.
- `BTCUSD` is tradable (viable for crypto phase).
- **Algo Trading** flag is readable via `terminal_info().trade_allowed` (green/red button).

### Phase 1 — Real execution (done)
- Built `src/mt5/broker_adapter.py`: resolves tradable symbol, correct `tick_value`-based
  sizing, Algo-Trading guard, real `order_send`, mode-gated.
- **Placed & closed a REAL demo order**: BUY XAUUSD-ECN 0.01 @ 4088.13, ticket 551306623, retcode 10009.

### Phase 2 (partial) — Real learning loop (done)
- Built `src/trading/scalp_engine.py`: multi-symbol loop (XAUUSD, BTCUSD), 0.01-lot scalping,
  adaptive SL/TP per symbol spread, tracks positions by real ticket, and **reconciles closed
  trades against real MT5 deal history** → writes true win/loss to experience DB + vector store.
- Adopts pre-existing open positions on restart (no orphans).
- Fixed `get_rates` native bug (`numpy.void` field access).
- Writes `data/bot_status.json` for the dashboard.
- Verified: real trades on XAUUSD-ECN and BTCUSD flow into the experience DB with outcomes.

### New dashboard (done)
- **Deleted** old dashboard code: `dashboard_clean.py`, `dashboard_fixed.py`, and 4 stale
  dashboard docs. Rewrote `dashboard/app.py` from scratch.
- Real-data endpoints: `/api/status` (account + Algo light + engine), `/api/trades/history`
  (live MT5 deals), `/api/trades/bot`, `/api/strategies` (+ best per symbol), `/api/learning`
  (progress to 100), `/api/research`, `/api/readiness`. Auto-refresh ~4s.

### Cleanup
- Removed 50 stale docs/scripts (old completion reports, fix guides, `run_bot.py`,
  `run_system.py`, `monitor.py`, `mt5_proof.py`, `diagnostics.py`, `check_*.py`, etc.).
- Unified `app.py` now starts dashboard + engine in one process.
- Rewrote `README.md` to describe the actual current system.

### How to run
```
python app.py LIVE_MICRO     # real 0.01-lot demo trading + dashboard at :5000
```

### Next (see REPAIR_PLAN.md)
- Phase 3: RiskManager (daily-loss halt, max positions, spread ceiling, kill switch).
- Phase 4: wire research/sentiment into decisions.
- Phase 5: no-look-ahead backtest + readiness gate before any real capital.
