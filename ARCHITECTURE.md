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
│                        python -m src.trading.scalp_engine                      │
│                                                                                │
│  every cycle:                                                                  │
│   _adopt_existing_positions()  ── adopts bot+manual open trades on start/cycle │
│   analyse symbols → Signal(s) → BrokerAdapter (mode: OBSERVE/PAPER/LIVE_MICRO) │
│   TradeManager.evaluate() → modify_sl (real) / close (⚠ observe-only exit bug) │
│   HTFContext: blip→widen SL once / reversal→cut                                │
│   HYBRID_LLM review (throttled) → HOLD/TIGHTEN/EXIT                             │
└───────┬───────────────────────┬───────────────────────┬───────────────────────┘
        │                       │                        │
        ▼                       ▼                        ▼
┌────────────────┐   ┌────────────────────────┐   ┌──────────────────────────────┐
│   LLM LAYER    │   │     LEARNING STACK      │   │      CRYPTORTI (whale)        │
│ litellm_       │   │ experience_db (SQLite)  │   │ s3_client (history, Q&A doc)  │
│  providers/    │   │ vector_store (Chroma:   │   │ signal_client (mTLS WS feed*) │
│  provider_     │   │   xauusd_market_patterns)│  │ correlation_miner → table.json│
│  router.py     │   │ pattern_matcher (RAG)   │   │ whale_rag (Chroma:            │
│ modify_params  │   │ post_mortem             │   │   whale_wave_patterns)        │
│  =True (FIXED) │   │ param_optimizer         │   │   ingests 37 profiles +       │
│ 15+ providers  │   │ symbol_governor         │   │   CONFIRMED 6M→~6-candle case │
│ + Kilo Gateway │   │ operating_mode          │   │ strategy → BTCUSD bias        │
└────────────────┘   │ reflection_agent        │   └──────────────────────────────┘
                     │ knowledge_store (Chroma:│    * WebSocket = authoritative
                     │   trading_knowledge_rag │      (Danny: event-driven push,
                     │   local MiniLM, portable)│      no S3 polling — see Q7/Q11)
                     └────────────────────────┘

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
- Runtime code depends only on: MT5, chromadb, sentence-transformers (MiniLM),
  langchain/litellm, boto3. No editor/Kilo dependency in the run path.
- Embedded ChromaDB (no server) = lightning-fast local lookups, offline after the
  one-time MiniLM download.
- Fresh clone bootstrap: run the bot once (creates DBs), then
  `python -m src.cryptorti.correlation_miner` → `python -m src.cryptorti.whale_rag`
  to rebuild the whale RAG, and `python -m src.learning.knowledge_store` to seed
  durable knowledge.

## Known issues (track in GitHub)
- Manager "rolling winner" EXIT is `OBSERVE close (no real order)` even in
  LIVE_MICRO — real close orders not sent; winners ride the trailing broker SL.
- whale_rag / knowledge_store not yet wired into the live engine loop (recall side).
- Edge unproven: PF ~0.44 over 298 trades (Phase 1). Needs sample + tuning.

See `DISTRIBUTED_ARCHITECTURE.md` for the FUTURE multi-box plan (design only; do
not build until edge proven).
```
