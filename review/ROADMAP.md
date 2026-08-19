# Review Roadmap

> Living enhancement backlog. This is a planning mirror; GitHub Issues is the
> authoritative tracker. Each item should link to one or more GitHub issues once
> it is triaged.

## Themes

### 1. Trading safety & execution

Goal: every live order path is observable, serialized, and fails safely.

| Item | Priority | Notes | GitHub issue(s) |
|---|---|---|---|
| Audit all `mt5.*` calls for `mt5_lock()` coverage | high | #79 added lock to data reads; verify no order path bypasses it. | |
| Add latency dashboards / alerts | medium | `[LATENCY]` logs exist; expose via dashboard endpoint. | |
| Harden pre-close guard with broker timezone tests | medium | #5 is runtime observation; add synthetic session-close test. | |
| Document MT5 IPC failure modes and recovery | low | Connector retry + terminal restart playbook. | |
| Snapshot live proven-state stores before risky ops | high | `scripts/snapshot_state.py`; prerequisite for safe restart/CI. | #97 |
| Isolate tests from live `data/` stores | high | `tests/conftest.py` + temp `DATA_DIR`; protect checkpointer/tuned/graduation/evidence. | #99, #98 |
| Safe automated bot restart with rollback | high | `scripts/restart_bot.py`; snapshot, validate, restore on failure. | #100 |
| Vectorbt/Optuna replay validation on restart | medium | Reuse `vbt_model.py` / `vbt_ordermodel.py` for smoke test after restart. | #101 |
| CI workflow for isolated tests + gated live restart | medium | `.github/workflows/restart_ci.yml`; never auto-restart LIVE_MICRO. | #102 |

### 2. EA / MT5 generation and runtime

Goal: generated EAs are maintainable, verifiable, and safe to run live.

| Item | Priority | Notes | GitHub issue(s) |
|---|---|---|---|
| Add Python source-code hot reload for `app.py` | high | Currently only `model.json` reloads dynamically (`MaybeReloadModel`). Python `.py` changes require full process restart. Use `watchdog` or `importlib`-based reload for `src/` + `scripts/` modules so fixes propagate without manual restart. Must handle stateful objects (MT5 connections, open positions, adapters) safely — snapshot + re-init, not blind reload. | |
| Add unit tests for `ea_generator.py` output structure | high | Verify grouped inputs, magic, and manifest alignment. | |
| Test `OnTimer` reload on missing/corrupt `model.json` | high | EA must not crash or load partial state. | |
| Extend lifecycle log to modify / BE / close events | medium | Currently logs entry; add exit snapshots. | |
| Add SQLite backend option for lifecycle log | low | CSV is MVP; SQLite enables richer queries. | |
| Formalize EA versioning and rollback strategy | low | Tie `EA_Version` to `model.json` build. | |

### 3. Data & learning

Goal: adaptive learning is grounded in clean, independent data.

| Item | Priority | Notes | GitHub issue(s) |
|---|---|---|---|
| Fix backtester point value for FX pairs | critical | `compute_indicator_series()` must pass `point` from MT5 data; backtester falls back to 0.01 breaking FX SL/TP/cost modeling. | #104 |
| Fix vbt_model.py / optuna_floor_optimizer.py hardcoded gold costs | critical | Both use `SPREAD_PTS=1200`, `PT=0.01`, hardcoded paths; must read live MT5 specs and resolve ECN suffixes like `onboard_pipeline.py`. | #105 |
| Fix vbt_model.py zeroed commission | critical | `fees = spread_frac / 2 + ... * 0` ignores round-turn commission. | #106 |
| Validate Dukascopy replay fidelity against MT5 ticks | high | Ensure #80 actually uses equivalent history. | |
| Implement per-session backtest scoring | high | Blocker for re-enabling `_mutate_session_floors()`. | |
| Add test for param_optimizer model.json fallback | high | Valid/malformed/partial model.json coverage. | #107 |
| Add test for ingest.py ECN suffix path handling | high | Regression guard for broker symbol name resolution. | #108 |
| Add end-to-end test for onboard_pipeline.py | high | Smoke test from ingest to EA generation. | #109 |
| Add pipeline cost-model integration test | high | Verify spread/slippage/commission consistency across all backtester entry points. | #117 |
| Retire or fix ONNX outcome predictor | medium | AUC collapses on live floor-filtered trades. | |
| Consolidate session boundaries into single source | medium | `sessions.py` is canonical; `onboard_symbol.py` and `indicator_scorer.py` still duplicate/drift. | #110 |
| Audit conftest.py path patching completeness | medium | May be missing modules that cache `config.DATA_DIR` paths at import time. | #111 |
| Add data-quality tests for parquet files | medium | No tests for duplicates, nulls, timezone, schema consistency, weekend bars. | #112 |
| Document data-source provenance rules for reviewers | low | Extend `TESTING.md`. | |

### 4. Operations & multi-symbol

Goal: move from single-box to fleet-ready with minimal risk.

| Item | Priority | Notes | GitHub issue(s) |
|---|---|---|---|
| Prototype Approach A (one terminal per symbol) | medium | XAUUSD + BTCUSD side-by-side on same host. | |
| Define "Approach B" trigger criteria | low | Document concrete metrics (CPU, latency, symbol count). | |
| Add per-symbol health endpoint | low | `/api/health/<symbol>` for fleet monitoring. | |

### 5. Research & CryptoRTI

Goal: autonomous research produces actionable, validated findings.

| Item | Priority | Notes | GitHub issue(s) |
|---|---|---|---|
| Continual researcher audit of new EA patterns | medium | Feed `docs/ea_pattern_audit.md` into RAG. | |
| Danny-blocked questions (see `AGENTS.md`) | low | External dependency; track only. | |

### 6. Code hygiene (from 2026-08-19 review)

| Item | Priority | Notes | GitHub issue(s) |
|---|---|---|---|
| Fix indicator_scorer.py session names to match canonical | low | Uses `asia`, `london_ny_overlap`, `late_ny` instead of `Asian`, `London`, `NewYork`, `Off`. | #114 |
| Remove dead-code risk in onboard_symbol.py | low | Local `_session()` duplicates canonical function but is never imported. | #115 |

## Milestones

| Milestone | Target | Definition of done |
|---|---|---|
| Review closed | TBD | All `review/ISSUES_LOG.md` findings triaged into GitHub issues or `wontfix`. |
| EA hardened | TBD | `ea_generator.py` has tests, reload is resilient, lifecycle log covers full trade. |
| Multi-symbol MVP | TBD | Two symbols run in parallel on the same host with isolated state. |
| Learning validated | TBD | Per-session scoring + Dukascopy fidelity proven; ONNX path decided. |
| Test isolation + safe restart | 2026-08-26 | `pytest tests/` does not mutate live stores; `restart_bot.py` snapshots, validates, rolls back. |
