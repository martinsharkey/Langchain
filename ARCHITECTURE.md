# ARCHITECTURE — Current State (2026-07-31)

Single-box, single-writer trading bot. The BROKER (MT5) is the source of truth for
positions. All storage is local/embedded and portable (target: standalone app
outside VS Code). Live task tracking is in **GitHub Issues**.

```
                           ┌───────────────────────────────────────────────┐
                           │                MT5 TERMINAL                     │
                           │   VT Markets demo · terminal64.exe (GUI)        │
                           │   ← source of truth for positions/fills →       │
                           └───────────────▲───────────────┬─────────────────┘
                                           │ order_send /   │ ticks / rates /
                                           │ modify / close │ positions_get
                                           │                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     SCALP EXECUTION ENGINE  (the process we run)                │
│                        python app.py [LIVE_MICRO|OBSERVE|PAPER]                 │
│                                                                                │
│  app.py starts 3 daemon threads:                                               │
│   1. dashboard (Flask :5000) — real-data UI                                    │
│   2. engine (ScalpEngine) — the trading loop                                    │
│   3. cryptorti (optional) — whale-signal WebSocket feed                         │
│                                                                                │
│  engine.initialize() (blocking, ~5-10s):                                       │
│   - MT5 connect + account resolve                                              │
│   - resolve BrokerAdapter per symbol (tradable check)                          │
│   - adopt existing positions + reconcile pending DB rows                       │
│   - load seeded reversal signatures                                             │
│   - onboard new symbols (auto-discover strength floors)                        │
│   - restore growth/capital state                                               │
│   - init learning stack (registry, experience DB, vector store,                │
│     pattern matcher, checkpointer, researcher, edge, graduation)               │
│                                                                                │
│  every SCALP_CYCLE_SECONDS (default 60s):                                      │
│   _adopt_existing_positions() → reconcile closed → manage open                 │
│   → adapt weights → refresh stats → evaluate symbols → trade                   │
│                                                                                │
│  between cycles, every SCALP_MANAGE_SECONDS (default 15s):                     │
│   _fast_manage_until() → reconcile + manage open positions                     │
│     (ratchet / trail / HTF blip-or-reversal / pre-close)                       │
└──────────────────────────────────────────────────────────────────────────────┘

  LOCAL STORAGE (all under data/, gitignored, machine-local, portable):
    data/chromadb_store/         3 Chroma collections (xauusd / whale / knowledge)
    data/trading_experience.db   closed-trade journal + strategy performance
    data/cryptorti_correlation.json   mined whale→candle table (re-mine on clone)
    data/*.json                  bot_status, risk_state, tuned_params, ...
```

## Data-source decision (CryptoRTI)
Authoritative real-time source = **mTLS WebSocket, event-driven push only**. Do NOT
poll S3 / `dashboard.json` in the hot path. The push should carry the confidence/tape
payload (Danny to embed — Q7). S3 is for async collaboration (`martin_qna.md`) only.

## Portability (standalone-app goal)
- Runtime code depends only on: MT5, chromadb, numpy, pandas. No editor/Kilo
  dependency in the run path.
- Embedded ChromaDB (no server) = lightning-fast local lookups.
- Torch/sentence-transformers may be unavailable on some Windows hosts; the bot
  falls back to a deterministic hash-based embedding function so vector stores
  still operate without an ML runtime.
- Fresh clone bootstrap: run the bot once (creates DBs), then
  `python -m src.cryptorti.correlation_miner` → `python -m src.cryptorti.whale_rag`
  to rebuild the whale RAG, and `python -m src.learning.knowledge_store` to seed
  durable knowledge.

## Known issues (track in GitHub)
- Edge unproven: PF ~0.44 over 298 trades (Phase 1). Needs sample + tuning.
- KnowledgeStore / MQL5Knowledge / vector_store embeddings may fall back to
  safe hash-based mode if torch DLLs fail to load on Windows.

See `DISTRIBUTED_ARCHITECTURE.md` for the FUTURE multi-box plan (design only; do
not build until edge proven).
```
