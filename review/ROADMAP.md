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

### 2. EA / MT5 generation and runtime

Goal: generated EAs are maintainable, verifiable, and safe to run live.

| Item | Priority | Notes | GitHub issue(s) |
|---|---|---|---|
| Add unit tests for `ea_generator.py` output structure | high | Verify grouped inputs, magic, and manifest alignment. | |
| Test `OnTimer` reload on missing/corrupt `model.json` | high | EA must not crash or load partial state. | |
| Extend lifecycle log to modify / BE / close events | medium | Currently logs entry; add exit snapshots. | |
| Add SQLite backend option for lifecycle log | low | CSV is MVP; SQLite enables richer queries. | |
| Formalize EA versioning and rollback strategy | low | Tie `EA_Version` to `model.json` build. | |

### 3. Data & learning

Goal: adaptive learning is grounded in clean, independent data.

| Item | Priority | Notes | GitHub issue(s) |
|---|---|---|---|
| Validate Dukascopy replay fidelity against MT5 ticks | high | Ensure #80 actually uses equivalent history. | |
| Implement per-session backtest scoring | high | Blocker for re-enabling `_mutate_session_floors()`. | |
| Retire or fix ONNX outcome predictor | medium | AUC collapses on live floor-filtered trades. | |
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

## Milestones

| Milestone | Target | Definition of done |
|---|---|---|
| Review closed | TBD | All `review/ISSUES_LOG.md` findings triaged into GitHub issues or `wontfix`. |
| EA hardened | TBD | `ea_generator.py` has tests, reload is resilient, lifecycle log covers full trade. |
| Multi-symbol MVP | TBD | Two symbols run in parallel on the same host with isolated state. |
| Learning validated | TBD | Per-session scoring + Dukascopy fidelity proven; ONNX path decided. |
