# AGENTS.md — Start Here (Next-Session Signpost)

> This file is the FIRST thing to read in a new chat. It tells you what this
> project is, what we're building, what's broken, what's next, and the rules.

## GROUND RULE — GitHub is the single source of truth

All issues, features, bugs, and TODOs live in **GitHub Issues** on
`https://github.com/martinsharkey/Langchain`. Do NOT invent a parallel tracker.

- Before starting work: `gh issue list` to see the backlog.
- New bug/feature/idea discovered → open an issue immediately: `gh issue create`.
- Reference issues in commits (`fix(#12): ...`, `feat(#7): ...`) and close via PR/commit.
- `TODO.md` is a historical log only; the LIVE task list is GitHub Issues.
- Labels: `bug`, `feature`, `learning`, `cryptorti`, `danny-blocked`, `infra`.

## What this is

A self-learning, multi-symbol algorithmic **trading bot** (Python + LangChain)
that trades via **MetaTrader 5** (VT Markets demo, account CHRISTOPHER MARTIN
SHARKEY, server VTMarkets-Demo, GBP). It combines:
- a fast **scalp execution engine** (`src/trading/scalp_engine.py`) — the process
  we actually run; it adopts & manages live positions, no "council" needed;
- a **learning stack** (RAG pattern store, experience DB, post-mortem, parameter
  optimizer, symbol governor, operating-mode controller, reflection agent);
- a **CryptoRTI whale-signal integration** (Danny's feed) to predict BTCUSD waves.

Goal: turn this into a **standalone application that runs OUTSIDE VS Code**. Keep
all runtime code editor-agnostic and offline-capable (no Kilo/editor deps at runtime).

## What we are doing (current focus)

1. **CryptoRTI whale-wave prediction.** A large whale movement (e.g. ~$6M) is
   broken into ~$1M chunks that print ~6 large BTCUSD candles in a window after
   the event. We mine this correlation and store it in RAG so the bot surfs the wave.
2. **Local, lightning-fast, portable knowledge** via embedded ChromaDB (no server).
3. **Keeping the live bot healthy** while it accumulates real closed trades.

## What we fixed / built THIS session (2026-07-31)

- **LLM/Bedrock bug FIXED** (`litellm_providers/provider_router.py`): `modify_params`
  / `drop_params` must be `litellm` module globals, NOT nested in
  `ChatLiteLLM(model_kwargs={"litellm_settings": {...}})` (silently ignored).
  Set once at import. Bedrock/gateway tool-calling errors gone; live LLM reviews
  now succeed (`[HYBRID_LLM] LLM review -> TIGHTEN`).
- **Whale RAG** (`src/cryptorti/whale_rag.py`): new ChromaDB collection
  `whale_wave_patterns`. Ingests all 37 profiles from
  `data/cryptorti_correlation.json` + a HUMAN-CONFIRMED observation (the ~$6M →
  ~6×$1M chunk → ~6 M1 candles pattern). `lookup(usd, exchange, direction)` for
  the live predictor. Embedding = EVENT identity only (size/exchange/direction);
  response metrics (hit_rate/peak_bps/n_large/lag) live in metadata.
- **Knowledge store** (`src/learning/knowledge_store.py`): portable, embedded,
  offline semantic memory (local MiniLM `all-MiniLM-L6-v2`). Categories:
  finding / correction / decision / note. Already holds the corrected whale
  finding, the WebSocket decision, and the LLM-fix note.
- **CORRECTION recorded:** the earlier claim "no single whale wallet movement
  produced a successful BTCUSD move" was WRONG. Whale tx dates/times DO map to
  real 1m BTCUSD trades (chunked). Stored in the knowledge RAG.
- **Danny decision recorded** in `cryptorti/martin_qna.md` (Q11 + Decision Log).

## Live trade / bot state

- Run the bot: `python -m src.trading.scalp_engine` (from `langchain/`, venv active).
  It calls `_adopt_existing_positions()` on start AND every cycle, so it manages
  any open trades (bot-opened or manual) after a restart.
- Mode is `TRADING_MODE` env (`.env`): currently `LIVE_MICRO` (real orders, 0.01
  cap). Modes: OBSERVE / PAPER / LIVE_MICRO / LIVE (`src/config.py`).
- **KNOWN ISSUE:** the trade-manager "rolling winner" EXIT path logs
  `OBSERVE close (no real order)` even in LIVE_MICRO — manager-initiated exits are
  simulated, so winners are left to the trailing broker SL instead of being
  actively closed. Entries + SL trailing ARE real. Needs an issue + fix (decide:
  should manager exits send real close orders in LIVE_MICRO?).

## TODO (next session) — mirror these into GitHub Issues

- [ ] File the "manager exits are OBSERVE-only in LIVE_MICRO" bug + decide behaviour.
- [ ] Wire `whale_rag.lookup()` into the live CryptoRTI wave predictor / strategy.
- [ ] Wire `knowledge_store` recall into the engine startup + reflection loop.
- [ ] Build `src/cryptorti/wave_predictor.py` (Phase B) per CRYPTORTI_WAVE_DESIGN.md.
- [ ] `webhook_listener.py` once Danny provides the webhook spec (Q2).
- [ ] Accumulate ~100 real closed trades; edge currently PF 0.44 (Phase 1, not proven).
- [ ] Standalone-app packaging (remove any editor assumptions; entrypoint + config).

## Danny's issues (CryptoRTI side) — see `cryptorti/martin_qna.md`

Async Q&A doc synced to S3. Open questions blocking us (label `danny-blocked`):
- Q1 direction semantics (deposit=sell / withdrawal=buy) — confirm edge cases.
- Q2 **webhook payload schema + endpoint/auth** (low-latency trigger) — needed.
- Q3/Q10 tape trigger separating real sells from expiring windows; why 454/455
  deposits "expired, no selling" — is `selling_confirmed` wired?
- Q7 **embed confidence/tape payload IN the WebSocket push** (so we never poll S3).
- Q11 **ANSWERED:** authoritative source = mTLS WebSocket, event-driven push only.
- Q12 real-exchange CVD/VPIN/delta per signal.

## API keys / configuration (values are NOT in git — see examples)

- `.env` (gitignored) — `TRADING_MODE`, `LIVE_MICRO_MAX_LOT`, LLM provider keys
  (`DEEPSEEK_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, ... or
  `USE_KILO_GATEWAY=true`). Template: none committed for the main `.env` — infer
  from `litellm_providers/provider_router.py` docstring.
- `cryptorti/.env.cryptorti` (gitignored) — `AWS_ACCESS_KEY_ID` /
  `AWS_SECRET_ACCESS_KEY` (or `AWS_PROFILE`), `CRYPTORTI_BUCKET`
  (default `crypto-rti-prod-us-east-1`), `AWS_DEFAULT_REGION`. Template:
  `cryptorti/.env.cryptorti.example`.
- `cryptorti/certs/*.pem` (gitignored) — mTLS client certs for the WebSocket feed
  (`wss://3.213.39.89:8443`).
- MT5 terminal: `Langchain/MT5/VT Markets (Pty) MT5 Terminal/terminal64.exe` must
  be running & logged in before starting the bot.
- **Portability note:** `data/` (incl. `chromadb_store/`, `cryptorti_correlation.json`,
  the SQLite DBs) is gitignored — machine-local. A fresh clone must re-mine the
  correlation table (`python -m src.cryptorti.correlation_miner`) then
  `python -m src.cryptorti.whale_rag` to rebuild the whale RAG.

## Key paths

- Engine: `src/trading/scalp_engine.py` · `src/trading/trade_manager.py`
- LLM: `litellm_providers/provider_router.py` (re-exported by `src/core/llm.py`)
- Learning: `src/learning/{vector_store,pattern_matcher,experience_db,knowledge_store,post_mortem,param_optimizer,symbol_governor,operating_mode,htf_context}.py`
- CryptoRTI: `src/cryptorti/{s3_client,correlation_miner,whale_rag,strategy}.py`
- Config: `src/config.py` · Docs: `README.md`, `CRYPTORTI_WAVE_DESIGN.md`,
  `LEARNING_ARCHITECTURE.md`, `DISTRIBUTED_ARCHITECTURE.md`, `SESSION_LOG.md`
