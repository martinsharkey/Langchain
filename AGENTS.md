# AGENTS.md — Start Here (Next-Session Signpost)

> This file is the FIRST thing to read in a new chat. It tells you what this
> project is, what we're building, what's broken, what's next, and the rules.

## Workspace Rules

**`WORKSPACE_RULES.md` is the authoritative rulebook for sessions, commits,
testing, security, and code hygiene.** It covers:
- Session logging & history preservation (SESSION_LOG.md protocol)
- Todo tracking (GitHub Issues as source of truth)
- Commit & push discipline (push after every session)
- Testing requirements (all changes must have tests, CI must pass)
- Code hygiene (no redundant code, scheduled housekeeping, stale file cleanup)
- Architecture maintenance (docs must track code)
- Tool & dependency approval (no new tools without human approval)
- Security (secrets hygiene, credential rotation)
- Live trading safety (kill switch, readiness gate)

Read `WORKSPACE_RULES.md` alongside this file. When they conflict,
`WORKSPACE_RULES.md` wins.

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

## CORE RULES (standardised — enforced at startup by `src/core_rules.py`)

These are the fixed, evidence-derived rules the system MUST follow. `assert_core_rules()`
runs at engine startup and logs `[CORE-RULES]` loud on any drift. Portable (pure Python,
VPS-ready — no editor/Kilo dependency). Change `src/core_rules.py` first if a rule changes.

- **R1 ONE ENTRY** — sole signal is `OsMA_Confluence`. No ensemble/voting; MACD/CCI/BB/RSI are removed.
- **R2 ONE EXIT** — every symbol uses `GS_PROVEN`: wide data-derived broker SL + BE-lock + trailing stop, and the broker **TP is removed once trailing arms**. No per-symbol exit A/B variants.
- **R3 PER-SYMBOL SL AT ONBOARDING** — SL/TP/BE/trail derived from the symbol's OsMA-cycle excursion (`FloorDiscovery.sample_osma_cycles`, ~20 cycles), then live-tuned. Never borrow magnitudes across symbols.
- **R4 CLEAN-DATA LEARNING** — learning reads exclude all simulated sources (`experience_db.learning_window_clause`).
- **R5 STRUCTURE SYMBOL-AGNOSTIC, MAGNITUDES SYMBOL-SPECIFIC.**
- **R6 BROKER-SIDE SL ALWAYS** — wide safety-TP is a connectivity failsafe only.
- **R7 BTCUSD** may use the CryptoRTI whale websocket to augment ENTRY confidence only (not the exit).
- **R8 KNOWN-GOOD PRESERVED** — winning baseline in RAG + `data/winning_baseline.json`; checkpointer reverts to best realised-expectancy config.
- **R9 AUTOMATIC ONBOARDING** — new symbols onboard automatically (Dukascopy-primary, MT5 fallback); no manual step.
- **R10 EVIDENCE FIRST — NEVER GUESS** — every tunable magnitude (pyramid legs, SL, floors, thresholds) comes from HARD evidence (GoldShark XML BT/FT, RAG, live data, or a backtest), cited — never a hardcoded guess. If no evidence, TEST it. Applies to the assistant, researcher, and bot.

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

> **Latest state (2026-08-18):** on `main` (pushed). Full 7-indicator confluence is
> the single source of truth (`confluence_signal.py`); optimizer uses authoritative
> mql5 ranges; all learning loops audited WIRED end-to-end; ONNX per-symbol; CryptoRTI
> whale wired into BOTH live + backtest paths. 151 tests passing (2 skipped). CI
> active (`.github/workflows/ci.yml`). Workspace rules codified in
> `WORKSPACE_RULES.md` (authoritative rulebook). Architecture: `ARCHITECTURE.md` +
> `ARCHITECTURE_OVERVIEW.md`; testing: `TESTING.md`.
>
> **ONNX outcome-predictor finding (2026-08-18):** the per-symbol ONNX models show
> coin-flip AUC (0.45–0.52) on live floor-filtered OsMA_Confluence trades despite
> 0.69–0.78 holdout AUC. Do NOT wire ONNX into the Optuna floor optimizer — it adds
> noise, not value. Diagnostic: `scripts/qmmp/onnx_signal_diagnostic.py`.

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

## TODO — GitHub Issues are the live list (`gh issue list`)

> Reconciled 2026-08-07. This is a signpost only; the authoritative backlog is GitHub.

Done/closed this session: **#53** (exit leak — broker-SL-at-entry + 2s fast management
loop), **#14** (standalone packaging — DEPLOY.md + run_bot.bat, no editor deps).

Open, with current status commented on the issues:
- **#16** prove edge (100+ clean trades, PF≥1.3) — top goal; all the machinery (validation
  gate, GS_PROVEN exit, per-symbol onboarding SL, evolutionary+cluster tuning, self-correction)
  is now wired; needs clean trades to accumulate.
- **#48 / #49 / #51** per-symbol negative-expectancy research threads (BTC / GER40 / XAU) —
  the researcher now investigates each cycle (preventive post-mortem + evidence + validated tuning).
- **#50** regime analysis — only 1 clean live month so far; re-run at ≥3 months.
- **#5** verify pre-close protection on a real session close (code complete; runtime observation).
- **#19 / #1** VPS live cutover + distributed split (DEPLOY.md documents both; MT5 is Windows-only).
- **#44 / #15** CryptoRTI whale accumulation + optional Danny enhancements (non-blocking, external).

When starting work: `gh issue list`; open new findings as issues immediately.

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
