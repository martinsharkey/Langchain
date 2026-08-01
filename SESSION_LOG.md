# Trading Bot â€” Session Log

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

## Session 2 â€” Real Execution, Learning Loop & New Dashboard
**Date:** 2026-07-30

### Full-codebase review (Opus 4.8)
Found the system was a sophisticated **analysis engine disconnected at 3 seams**:
1. Execution was fake â€” an LLM narrated trades; the real `place_order` was orphaned.
2. Learning loop never closed â€” a `NameError` killed position tracking; outcomes were synthetic.
3. Sentiment/research pipeline was orphaned and un-importable.
Plus critical safety gaps (wrong gold lot math, no algo/kill/spread checks, no symbol-suffix handling).
See `REPAIR_PLAN.md`.

### Phase 0 â€” Stabilize (done)
- Fixed dead `EconomicCalendarSourceMock`/`CentralBankSourceMock` imports (app now boots).
- Fixed `main.py` `trade_result` NameError; connector double-`@property` + unreachable code.
- Added `TRADING_MODE` (OBSERVE|PAPER|LIVE_MICRO|LIVE), default OBSERVE.
- `NewsAggregatorSource` degrades gracefully (no boot crash without NEWSAPI_KEY).
- Reordered `app.py` so dashboard starts first; research is non-fatal.

### Diagnosis of "why it never traded" (verified with live MT5)
- The tradable gold symbol is **`XAUUSD-ECN`** (`trade_mode=4`, order_check "Done").
- `XAUUSD.crp` is **trade-disabled** (`trade_mode=0`, retcode 10017) â€” must be skipped.
- `BTCUSD` is tradable (viable for crypto phase).
- **Algo Trading** flag is readable via `terminal_info().trade_allowed` (green/red button).

### Phase 1 â€” Real execution (done)
- Built `src/mt5/broker_adapter.py`: resolves tradable symbol, correct `tick_value`-based
  sizing, Algo-Trading guard, real `order_send`, mode-gated.
- **Placed & closed a REAL demo order**: BUY XAUUSD-ECN 0.01 @ 4088.13, ticket 551306623, retcode 10009.

### Phase 2 (partial) â€” Real learning loop (done)
- Built `src/trading/scalp_engine.py`: multi-symbol loop (XAUUSD, BTCUSD), 0.01-lot scalping,
  adaptive SL/TP per symbol spread, tracks positions by real ticket, and **reconciles closed
  trades against real MT5 deal history** â†’ writes true win/loss to experience DB + vector store.
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


---

## Session 2026-07-31 (evening) — LLM fix, whale RAG, portable knowledge store, GitHub handoff

Context recovered from disk + memory (prior session context was large; do not rely
on chat scrollback — use AGENTS.md + this log + GitHub Issues).

### Fixed
- **LLM/Bedrock unsupported-params bug** (`litellm_providers/provider_router.py`).
  `modify_params`/`drop_params` set as `litellm` module globals at import (the
  nested `model_kwargs={"litellm_settings":{...}}` form was silently ignored, so
  Bedrock kept failing "tool calling without tools="). Live LLM reviews now work.

### Built
- **Whale RAG** `src/cryptorti/whale_rag.py` — ChromaDB `whale_wave_patterns`.
  Ingests 37 mined profiles + the human-CONFIRMED ~$6M?~6×$1M?~6 M1-candle pattern.
  `lookup(usd, exchange, direction)`; retrieval matches on event identity, response
  in metadata. Confirmed observation retrieves at similarity 1.00.
- **Knowledge store** `src/learning/knowledge_store.py` — portable, embedded,
  offline semantic memory (local MiniLM). finding/correction/decision/note.
  Stored: the corrected whale finding, WebSocket decision, LLM-fix note.

### Corrected (important)
- Earlier "no whale wallet movement ? successful BTCUSD move" was WRONG. Whale tx
  dates/times DO map to real (chunked) 1m BTCUSD trades. Now in the knowledge RAG.

### Decisions
- Danny: authoritative feed = mTLS WebSocket, event-driven push only (no S3 polling).
  Recorded in `cryptorti/martin_qna.md` (Q11 + Decision Log).
- Storage: embedded ChromaDB (no server) — must stay portable for a standalone
  app that lives OUTSIDE VS Code.
- **GitHub Issues = single source of truth** for issues/features/bugs/todos.

### Live bot
- Running `python -m src.trading.scalp_engine` (standalone, no council). It adopted
  the 2 open positions after reboot and is trailing them into profit. LLM TIGHTEN
  reviews firing cleanly.
- KNOWN ISSUE: manager "rolling winner" exits log `OBSERVE close (no real order)`
  even in LIVE_MICRO — needs a GitHub issue + decision.

### Next
See AGENTS.md "TODO" — mirror into GitHub Issues.

---

## Session 2026-08-01 — Continual ReAct learning loop + proven OsMA strategy

Branch: fix/17-11-manage-live-positions (not merged). Full test suite: 59 passing.

### Diagnosis (on CLEAN data: 294 real trades, synthetic/dup/legacy rows purged)
- Root cause of losses: exit manager cut winners early (only 5 TP hits vs 198 early
  "closed"), realised payoff 0.74 vs placed RR 2.0; long bias (buy -73 vs sell -19);
  XAGUSD biggest bleeder. The bot was also silently running OBSERVE (no TRADING_MODE
  in .env) so manager exits were simulated. Learning loop was NET-HARMFUL — every
  symbol degraded 2nd-half; XAUUSD went +0.117 -> -0.669 as the loop engaged.
- "No BTCUSD trades" root cause: NOT algo-blocked — the SymbolGovernor hard-paused
  every symbol on old losing history. Fixed with advisory-in-demo.

### Built (all with unit tests)
- #29 OsMA 7-indicator confluence (PRIMARY strategy) ported from proven GoldShark
  EAs (PF 1.46-1.62) + momentum-exhaustion & Playbook-A POC exits.
- #27 ConfigCheckpointer: revert-to-best-config + learn-from-failure + kill-switch.
- #22 mql5 knowledge RAG (offline seeded + optional Playwright crawler).
- #32 continual daily ReAct researcher (review -> mql5 query -> hypothesis -> gated
  edge sweep -> auto-file GitHub issues).
- #31 automated per-symbol edge discovery -> data/edge_weights.json overlay.
- #25 ReAct alt-tuning (mql5-grounded candidates + avoid failed directions;
  PARAM_SPACE widened to reach the proven cluster).
- #26 whale confidence model (historic-trained confidence-to-enter) wired into CryptoRTI.
- #13 knowledge recall at startup + reflection write-back.
- Fixes: #11 real manager closes + winner-cut fix; #3 long-bias guard; #21 per-account
  scoping + demo/live switch safety; #20 same-level re-entry guard + purged synthetic/
  legacy rows; governor advisory in demo; RSS-flood startup fix; single launcher (app.py).

### Learning loop is now CLOSED (no open loops)
mql5 RAG (#22) -> researcher (#32) -> edge discovery (#31) -> optimizer (#25 grounded,
avoids failed) -> checkpointer keep/revert+learn (#27) -> knowledge store read/write (#13),
with #29 OsMA confluence as the primary strategy. Every discovery auto-applies (if
validated) or becomes a tracked GitHub issue.

### Live bot
- Run: `python app.py LIVE_MICRO` (single launcher: dashboard :5000 + engine + research +
  CryptoRTI). Focus symbols XAUUSD + GER40 + BTCUSD. Restarted on the new code;
  positions adopted; learning active (adaptation + auto-revert on).

### Backlog filed this session: GitHub Issues #17-#32.

### Next
See AGENTS.md "TODO". Priorities: #24 graduation, #19/#30 dashboard control panel,
apply #21 account filter to all stats reads, run the real mql5 crawl, prove edge on
the 3 focus symbols under the new strategy, then merge the branch.
