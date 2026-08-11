# AGENTS.md — Start Here (Next-Session Signpost)

> This file is the FIRST thing to read in a new chat. It tells you what this
> project is, what we're building, what's broken, what's next, and the rules.

> ⚠️ **READ `AGENT_ORIENTATION.md` FIRST.** It is the ownership charter for every
> agentic developer: **all code in this workspace is your responsibility, even
> what you did not write.** Reuse existing components, never build parallel
> systems, clean up your scratch files, keep docs truthful, and verify before you
> commit. This signpost assumes you have read it.

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

1. **CryptoRTI whale-wave prediction — now SELF-SUSTAINING.** Large whale orders
   (≥$6M) move BTC in the expected direction ~78% (validated vs Danny S3 +MT5
   candles, `docs/whale_candle_correlation.md`). The bot records every live
   WebSocket whale signal + its realised candle outcome (`WhaleOutcomeStore`,
   `data/whale_outcomes.db`), learns a size-gated model (Danny-seeded, grows from
   live events), and feeds it to `wave_predictor` — no reliance on Danny history at
   decision time. Design: `docs/whale_self_learning.md`. Tracking: #43/#44/#46.
2. **Prove the edge in backtest + forward test.** Harnesses: `robust_tester`
   (random-window, mql5 ranges), `iterative_walkforward` (chronological OOS),
   `validate_whale_backtest`, `whale_candle_study`. Full reference: **`TESTING.md`**.
3. **Keeping the live bot healthy** while it accumulates real closed trades.

> **Latest state (2026-08-02):** on `main` (pushed). Full 7-indicator confluence is
> the single source of truth (`confluence_signal.py`); optimizer uses authoritative
> mql5 ranges; all learning loops audited WIRED end-to-end; ONNX per-symbol; CryptoRTI
> whale wired into BOTH live + backtest paths. 82 tests passing. Architecture:
> `LEARNING_ARCHITECTURE.md`; testing: `TESTING.md`.

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

## What we built THIS session (2026-08-01) — the continual ReAct learning loop

Branch `fix/17-11-manage-live-positions` (not merged). Full continual-learning
loop, all with unit tests (59 passing):
- **OsMA 7-indicator confluence (#29)** `src/strategies/osma_confluence.py` — the
  PRIMARY, symbol-agnostic entry: OsMA zero-cross (confirmed/anticipated) +
  fresh-momentum runway + MACD/ATR hard gates + EMA/price-stretch/Bulls-Bears/RSI.
  Ported from the proven GoldShark EAs (PF 1.46-1.62). Plus momentum-exhaustion +
  Playbook-A POC exits in `trade_manager.py`.
- **ConfigCheckpointer (#27)** `src/learning/config_checkpointer.py` — revert to the
  most-profitable config by realised expectancy + learn-from-failure (records failed
  directions to the KnowledgeStore). Kill-switch `LEARNING_ADAPTATION_ENABLED` is the
  safety floor. Wired live.
- **mql5 knowledge RAG (#22)** `src/learning/mql5_knowledge.py` — offline seeded RAG
  (+ optional Playwright crawler) grounding tuning/technique decisions.
- **Continual researcher (#32)** `src/learning/continual_researcher.py` — DAILY ReAct:
  review per-symbol results → query mql5 RAG → hypothesis → gate-enforced edge sweep →
  AUTO-FILE GitHub issues for dev-worthy findings.
- **Edge discovery (#31)** `src/learning/edge_discovery.py` — walk-forward sweep →
  `data/edge_weights.json` overlay (replaces hand-edited `edge_weights.py`).
- **ReAct alt-tuning (#25)** — optimizer draws mql5-grounded candidates + skips the
  checkpointer's failed directions (PARAM_SPACE widened to reach the proven cluster).
- **Whale confidence model (#26)** `src/cryptorti/wave_predictor.py` — historic-trained
  confidence-to-enter, wired into the CryptoRTI strategy.
- **#13** knowledge recall at startup + reflection write-back.
- **Fixes:** giveback loosened + winner-cutting fixed (#11); long-bias guard (#3);
  governor advisory in demo so it never freezes trading; per-account scoping +
  demo/live switch safety (#21); same-level re-entry guard (#20); RSS-flood startup fix.

## Live trade / bot state

- Run the bot (SINGLE launcher): `python app.py LIVE_MICRO` (from `langchain/`, venv).
  This starts dashboard (:5000) + engine + research + CryptoRTI feed together.
  `python -m src.trading.scalp_engine LIVE_MICRO` is engine-only (debug).
  It calls `_adopt_existing_positions()` on start AND every cycle.
- Mode is `TRADING_MODE` env (`.env`): `LIVE_MICRO` (real orders, 0.01 cap).
  `.env` also sets `DISABLED_SYMBOLS` (focus = XAUUSD + GER40 + BTCUSD) and
  `GOVERNOR_PAUSE_BLOCKS_ENTRIES=false` (advisory in demo/training).
- Modes: OBSERVE / PAPER / LIVE_MICRO / LIVE (`src/config.py`).
- **FIXED this session:** the "manager exits OBSERVE-only in LIVE_MICRO" bug —
  manager close/modify now sends REAL orders and logs SIMULATED vs real accurately;
  winners are actively closed, not just left to the broker SL.

## TODO (next session) — mirror these into GitHub Issues

- [ ] #24 graduation criteria (per-symbol edge → size-up gate) — spec ready.
- [ ] #19/#30 dashboard as control panel (mode/scalping/config/account) + fix the
      misleading "algo blocked" message; VPS deployment.
- [ ] Apply the #21 `_account_clause` filter to every stats read (foundation is in).
- [ ] #22 run the real mql5 Playwright crawl to populate the RAG beyond the seed.
- [ ] Prove edge on XAUUSD + GER40 + BTCUSD with the new OsMA strategy (accumulate
      real closed trades under it; watch the #27 checkpointer keep/revert).
- [ ] Merge `fix/17-11-manage-live-positions` to main once reviewed; push.
- [ ] `webhook_listener.py` once Danny provides the webhook spec (Q2).
- [ ] Standalone-app packaging / VPS (remove editor assumptions; #14/#19).

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
