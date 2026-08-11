# PROJECT RULES — Engineering Rules & Mission

> Renamed from `RULES.md`. This is the **engineering rule book** for the trading
> bot as it exists TODAY. Read `AGENT_ORIENTATION.md` first (ownership charter),
> then `AGENTS.md` (current state), then this file.
>
> **History note:** the original `RULES.md` described a legacy multi-agent
> architecture (`src/main.py`, `MetaStrategyAgent`, per-phase Research/Strategy/
> Risk/Execution agents, and a macOS→Docker/Wine RPyC bridge on port 8001). **All
> of that was deleted.** The bot now runs a single fast execution engine on
> native Windows MT5. This document reflects the real system.

---

## Core Mission

Build an **autonomous, self-learning trading bot** that:
1. Connects **directly** to MetaTrader 5 (native Windows `terminal64.exe`).
2. Places **real orders** on the demo account (`LIVE_MICRO`, 0.01 lots) to
   accumulate genuine outcomes on live spreads/slippage.
3. Trades a fast, deterministic **OsMA confluence** entry (the proven "GoldShark"
   momentum logic) — no LLM on the trigger.
4. Learns from every closed trade (MFE/MAE, capture ratio, rejected-signal
   telemetry) and self-tunes parameters in the background.
5. Is symbol-agnostic but currently focused on **XAUUSD + BTCUSD**.

---

## System Architecture (current)

```
python app.py LIVE_MICRO
 ├─ dashboard (:5000)                dashboard/app.py
 ├─ scalp execution engine           src/trading/scalp_engine.py   ← the core loop
 ├─ CryptoRTI whale feed (ws)         src/cryptorti/*
 └─ knowledge ingestion (bg)          src/learning/mql5_knowledge.py
```

Data flow:

```
MT5 terminal64.exe (native Windows)
    ↓ MetaTrader5 python package
src/mt5/connector.py  → data.py / account.py / orders.py / broker_adapter.py
    ↓
src/strategies/confluence_signal.py   (OsMA 4-gate entry — LLM-free)
    ↓
src/trading/scalp_engine.py           (execute + manage + reconcile outcomes)
    ↓
src/learning/*   (experience_db, param_optimizer, continual_researcher,
                  langgraph_researcher, knowledge_store, edge_discovery, ...)
```

The **cognitive loop** (`ContinualResearcher`, wrapped by the LangGraph
`langgraph_researcher.py`) runs asynchronously ABOVE the engine — it never sits
on the trade-trigger path.

---

## The Entry Engine — Rules

1. **The entry path is LLM-free and synchronous.** No LLM call, no network call,
   no LangGraph reasoning on the trigger. Latency there destroys the edge.
2. **The single entry signal is `confluence_signal.py`** (4-gate GoldShark):
   - **Gate 1** — clean OsMA/MACD zero-cross (fresh momentum flip).
   - **Gate 2** — signed, INDEPENDENT per-side strength floors (never a
     Bulls/Bears "power ratio").
   - **Gate 3** — ATR is a MINIMUM kinetic floor only; **never cap volatility**
     (no `atr_max` ceiling — it blocks the mega-run outliers that carry the edge).
   - **Gate 4** — trend infancy (`max_momentum_age`): enter early, not into an
     exhausted move.
3. **No second signal function, no ensemble voting on the trigger.** Extend the
   one confluence function.

---

## Trading Modes (master safety gate)

`TRADING_MODE` in `.env`: `OBSERVE` (analyse only) · `PAPER` (simulated fills) ·
`LIVE_MICRO` (real demo orders, 0.01 cap) · `LIVE` (full sizing). The
`BrokerAdapter` is the single execution boundary; the manager sends REAL
close/modify orders in `LIVE_MICRO` and logs SIMULATED vs real accurately.

---

## Learning System — Rules

1. Every trade + outcome (incl. tick **MFE/MAE** and `exit_points`) is recorded in
   `experience_db.py` at ENTRY (millisecond snapshot), reconciled at close.
2. **Rejected signals** (a valid trigger a gate blocked) are logged to the
   `rejected_signals` table so the researcher can tell "saved from whipsaw" from
   "blocked a mega-run."
3. `param_optimizer.py` tunes in small `0.01`/`0.1` steps — never `±1` swings.
4. `continual_researcher.py` runs the Observe→Reason→Act→Adopt loop; the formal
   LangGraph state graph is `langgraph_researcher.py` (a wrapper — it delegates,
   it does NOT reimplement).
5. Knowledge sources, in query order: **NotebookLM** (`notebooklm_provider.py`) →
   local `knowledge_store.py` → `mql5_knowledge.py`.
6. `config_checkpointer.py` adopts a tuned config only if it beats the baseline
   out-of-sample, else reverts. `LEARNING_ADAPTATION_ENABLED` is the kill-switch.
7. **Backtests must use real ticks** (`copy_ticks`), never interpolated 1-min OHLC.

---

## Data-Access Rules

1. **MT5 is the only live data source**, via the `MetaTrader5` package through
   `connector.py` / `data.py` / `broker_adapter.py`.
2. No file-based `.hcc/.hst/.dat` scraping, no MQL5 EA exports, no broker REST as
   primary source.
3. Simulated data is acceptable ONLY for backtests (and must be real-tick), never
   for a live trade decision.
4. `data/` (SQLite DBs, `chromadb_store/`, tuned params) is machine-local and
   gitignored — a fresh clone re-baselines via the EXISTING `FloorDiscovery`
   pipeline.

---

## Coding Standards

1. **Reuse the canonical component** (see `AGENT_ORIENTATION.md` table) — never
   build a rival engine/optimizer/RAG/researcher.
2. All MT5 config in `connector.py`; data in `data.py`; orders in `orders.py`;
   account in `account.py`; execution boundary in `broker_adapter.py`.
3. Use the project logger (`src/utils/logger.py`).
4. ChromaDB access goes through the shared `chroma_client.py` singleton (avoids
   the Windows native-crash race).
5. Remove scratch files before finishing. No dead parallel code paths.

---

## Testing Rules

1. The baseline is **all tests passing**. A session that lowers the pass count is
   a regression. See `TESTING.md` for the harness.
2. Syntax-check every changed file, instantiate the engine, and run `pytest`
   before declaring work done.
3. Test layers independently: connector → data → confluence signal → engine →
   learning.

---

## Source of Truth & Safety

1. **GitHub Issues** is the single tracker (`martinsharkey/Langchain`).
2. Never delete learning/baselines to force trades — toggle via
   `TRADING_SYMBOLS`/`DISABLED_SYMBOLS`, re-baseline via `FloorDiscovery`.
3. Be exact about state: "committed locally" ≠ "pushed."
