# Architecture Overview (current)

> Authoritative, current map of the system after the confluence consolidation,
> data-provenance, and dead-path cleanup. For deep detail, follow the links.
> Live task tracking is in **GitHub Issues** (`martinsharkey/Langchain`).

## What it is

A self-learning, single-box, single-writer trading bot (Python + LangChain) that
trades XAUUSD / GER40 / BTCUSD via **MetaTrader 5** (VT Markets demo). MT5 is the
source of truth for positions; all storage is local/embedded and portable.

## Entry point

```
python app.py [LIVE_MICRO|OBSERVE|PAPER|LIVE]
 ├─ dashboard (:5000)                     dashboard/app.py
 ├─ scalp execution engine                src/trading/scalp_engine.py   ← the core
 ├─ cryptorti whale feed (websocket)      src/cryptorti/*
 └─ research scheduler (best-effort)      src/orchestration/*  → enhanced_research_agent
    NOTE: the orchestrator is started by app.py but is NOT wired into the
    trading engine. The active research loop is ContinualResearcher inside
    scalp_engine.py.
```

`src/trading/scalp_engine.py` is the process that actually trades: it adopts live
positions, evaluates signals, manages exits, reconciles closes, records outcomes,
and drives all learning loops. `python -m src.trading.scalp_engine LIVE_MICRO` runs
the engine alone for debugging.

## The trading + learning cycle

```
signal ─▶ gate ─▶ trade ─▶ manage ─▶ reconcile ─▶ record ─▶ learn ─▶ adapt
  │        │        │         │           │          │         │        │
  │        │        │         │           │          │         │        └─ checkpointer keep/revert/demote; graduation; governor; DynamicFixer
  │        │        │         │           │          │         └─ post-mortem, optimizer, researcher, ONNX retrain, edge-discovery
  │        │        │         │           │          └─ update_trade_outcome(MFE/MAE) + vector_store.store_pattern
  │        │        │         │           └─ fetch real deal result; recover ManagedState (tombstone cache)
  │        │        │         └─ trade-manager exits; HTF blip→widen / reversal→cut
  │        │        └─ phase/mode/graduation-gated sizing → place() → record_trade(pending)
  │        └─ whale → operating-mode floor → RAG → ONNX → conf gate → MTF/dir penalties → HTF → risk gate
  └─ FOCUSED edge pocket (edge_weights.json overlay) or weighted ensemble
```

## Component map

### Strategy (entry)
- **`OsMA_Confluence`** — the single live entry strategy: a 7-indicator confluence
  (MACD, OsMA, Bulls/Bears Power, EMA, ATR, RSI). One rule set in
  `confluence_signal.py`, thin live adapter in `osma_confluence.py`.
- Full detail: **[`CONFLUENCE_STRATEGY.md`](CONFLUENCE_STRATEGY.md)** — what we
  measure/tune/adjust + the deliberate Bulls/Bears direction logic.

### Learning (how it improves)
- Experience DB (+MFE/MAE +`data_source`), pattern RAG, per-symbol ONNX quality
  model, parameter optimizer, post-mortem, config checkpointer, graduation/governor/
  operating-mode, semantic KnowledgeStore, reflection, HTF context.
- Full detail: **[`LEARNING_LOOPS.md`](LEARNING_LOOPS.md)**.

### Research (autonomous investigation)
- Continual researcher (daily ReAct + mql5 RAG + auto GitHub issues), performance
  researcher (self-analysis), edge-discovery (walk-forward → `data/edge_weights.json`).
- Full detail: **[`RESEARCHER.md`](RESEARCHER.md)**.

### CryptoRTI (whale signal)
- Websocket whale feed → wave predictor → confidence boost/dampen for BTCUSD.
- Detail: `CRYPTORTI_WAVE_DESIGN.md`.

## Data & provenance

- `data/trading_experience.db` — the `trades` table (entry snapshot + MFE/MAE +
  `data_source`). **Training/analysis excludes `SIMULATED_OHLC`** so the model never
  learns from fictitious interpolated-OHLC backtests.
- `data/edge_weights.json` — discovered per-symbol edge overlay (hot-reloaded).
- `data/config_checkpoints.json` — best-known configs + failed directions.
- ChromaDB stores — pattern RAG + KnowledgeStore (offline MiniLM).
- All of `data/` is machine-local (gitignored).

## Safety model

- `LEARNING_ADAPTATION_ENABLED` (freeze self-tuning) and
  `LEARNING_AUTO_REVERT_ENABLED` (checkpointer always on) are the master safety
  switches.
- Every applied learning change passes a **walk-forward gate** (generalizes + robust
  min-window PF).
- Governor / checkpointer / config-revert can only ever **lower** a symbol's
  graduation state; only a graduated symbol may size up.
- Per-account scoping (#21) keeps demo/live and different accounts separate.

## Security

Demo credentials only; no rotation required. Secrets live in a local gitignored
`.env` or **GitHub Secrets** (CI/VPS). See **[`SECURITY.md`](SECURITY.md)** and
`ci_templates/ci.yml.template` (copy to `.github/workflows/` with a workflow-scoped token).

## Recently removed (dead-path cleanup, #46/#38)

The legacy full-agent path was deleted: `src/main.py`, `run_trader.py`,
`src/core/agent.py`, `src/learning/curiosity_agent.py`,
`src/learning/meta_strategy_agent.py`, and `src/agents/{research,strategy,risk,
execution,env_setup,base}_agent.py` + the two orphaned duplicates
(`environment_setup_agent.py`, `risk_management_agent.py`). The live `KnowledgeBase`,
`enhanced_research_agent`, and `orchestration` were **kept in the repo** but are
**not started automatically** by `app.py` — the active research loop is
`ContinualResearcher` inside `scalp_engine.py`.

## Doc index

| Doc | Covers |
|---|---|
| [`CONFLUENCE_STRATEGY.md`](CONFLUENCE_STRATEGY.md) | Entry indicators, tuning, Bulls/Bears direction logic |
| [`RESEARCHER.md`](RESEARCHER.md) | The autonomous research layer |
| [`LEARNING_LOOPS.md`](LEARNING_LOOPS.md) | How the bot learns + every loop |
| [`SECURITY.md`](SECURITY.md) | Secrets / GitHub Secrets approach |
| `LEARNING_ARCHITECTURE.md` | Prior deep learning-architecture notes |
| `TESTING.md` | Test/backtest harnesses |
| `AGENTS.md` | Next-session signpost + ground rules |
