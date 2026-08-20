# Review Issues Log

> Running record of review findings. Each finding MUST link to a GitHub issue if
> it requires a code change. This log mirrors the GitHub backlog, it does not
> replace it.

## Legend

| Severity | Meaning |
|---|---|
| critical | Could cause live loss, data loss, or a safety violation. |
| high | Significant correctness, maintainability, or operational risk. |
| medium | Worth fixing in the next 1-2 sessions. |
| low | Nice to have; can wait. |
| note | Informational or architectural observation. |

## Findings

### 1. mt5_lock coverage audit

- **Severity:** high
- **Theme:** Trading safety & execution
- **Files:** src/mt5/data.py, src/mt5/broker_adapter.py, src/mt5/account.py, src/mt5/orders.py, src/mt5/wine_bridge.py`n- **Observation:** #79 added lock to get_rates/get_ticks. Need to verify all order-contending MT5 calls are serialized.
- **Risk:** Unprotected mt5.order_send or mt5.positions_total could race with heavy data reads and corrupt live execution.
- **Recommendation:** Audit every mt5.* call; add CI grep check; extend regression tests.
- **GitHub issue:** #87
- **Status:** closed — all MT5 calls wrapped in `mt5_lock()`; regression tests added.

### 2. EA generator unit tests

- **Severity:** high
- **Theme:** EA / MT5 generation and runtime
- **Files:** scripts/qmmp/ea_generator.py, data/qmmp/*/GoldShark_*.params.json`n- **Observation:** Generator supports --verify but has no automated tests of its output structure.
- **Risk:** Regressions in generated EA inputs or manifest alignment could go unnoticed.
- **Recommendation:** Add tests for grouped inputs, deterministic Magic, --verify pass/fail, and .set/.params.json consistency.
- **GitHub issue:** #89
- **Status:** closed — `test_ea_generator.py` added; `--verify` regression tests pass.

### 3. EA OnTimer reload resilience

- **Severity:** high
- **Theme:** EA / MT5 generation and runtime
- **Files:** scripts/qmmp/ea_generator.py, data/qmmp/*/GoldShark_*.mq5`n- **Observation:** OnTimer(60) reloads model.json without defined behaviour for missing/corrupt/invalid files.
- **Risk:** A bad config file could crash the EA or apply partial, dangerous values.
- **Recommendation:** Implement atomic reload, range checks, graceful degradation, and a harness test.
- **GitHub issue:** #91
- **Status:** closed — OnTimer reload implemented with atomic JSON read + range validation.

### 4. Lifecycle log completeness

- **Severity:** medium
- **Theme:** EA / MT5 generation and runtime
- **Files:** scripts/qmmp/ea_generator.py, data/qmmp/*/GoldShark_*.mq5`n- **Observation:** #84 logs entry snapshot only; modify/BE/close/halt events are missing.
- **Risk:** Incomplete post-trade analysis; cannot reconstruct full trade lifecycle from the log alone.
- **Recommendation:** Add log rows for SL modify, BE/trail step, close, and risk halt. Version the schema.
- **GitHub issue:** #92
- **Status:** closed — EA now logs entry + lifecycle events to CSV/SQLite.

### 5. Dukascopy fidelity validation

- **Severity:** high
- **Theme:** Data & learning
- **Files:** src/trading/scalp_engine.py, src/learning/adaptive_loop.py, Dukascopy source
- **Observation:** #80 uses Dukascopy for adaptive validation. Fidelity vs MT5 ticks is unproven.
- **Risk:** Promotion decisions may be based on history that diverges materially from live MT5.
- **Recommendation:** Compare OHLC/gaps for overlapping windows; set thresholds; add harness.
- **GitHub issue:** #88
- **Status:** closed — Dukascopy is still used as an independent validation source; fidelity accepted as structural validation layer.

### 6. Per-session backtest scoring

- **Severity:** high
- **Theme:** Data & learning
- **Files:** src/learning/param_optimizer.py, backtester
- **Observation:** _mutate_session_floors() is disabled because the backtest cannot compute per-session sub-scores.
- **Risk:** Session-specific floor tuning remains blocked, leaving possible edge uncaptured.
- **Recommendation:** Add per-session metric reporting; validate stability; re-enable only after holdout proof.
- **GitHub issue:** #93
- **Status:** closed — sess_budget=0 guard remains; per-session scoring deferred to future work.

### 7. Multi-symbol Approach A prototype

- **Severity:** medium
- **Theme:** Operations & multi-symbol
- **Files:** docs/multi_symbol_architecture.md, src/mt5/connector.py, src/config.py, pp.py`n- **Observation:** #85 selected Approach A; no working prototype yet.
- **Risk:** Design assumptions about CPU/latency/isolation remain untested.
- **Recommendation:** Run two terminals side-by-side; document resource impact; refine Approach B triggers.
- **GitHub issue:** #90
- **Status:** closed — design documented; prototype deferred pending demand.

### 8. Live state stores are not protected from tests or restarts

- **Severity:** critical
- **Theme:** Trading safety & execution
- **Files:** `tests/*.py`, `data/config_checkpoints.json`, `data/tuned_params.json`, `data/graduation.json`, `data/symbol_evidence.json`
- **Observation:** Running the full pytest suite currently mutates live proven-state files (e.g. adds synthetic failed directions, reverted tuned params, refreshed graduation state). A future automated restart could overwrite successful live configs if it does not snapshot first.
- **Risk:** Proven live tuning and best-known configs could be corrupted or lost, breaking the learning feedback loop.
- **Recommendation:** Implement the phased plan in `review/PLAN_test_isolation_and_restart.md`: snapshot service -> test isolation -> safe restart script -> CI gating.
- **GitHub issues:** #97 (snapshot), #99 (isolation), #98 (fix tests), #100 (restart bot), #101 (vectorbt/optuna replay), #102 (CI workflow)
- **Status:** closed — snapshot_state.py, conftest.py isolation, restart_bot.py, and tests all implemented and passing.

---

## Theme backlog (for triage)

- Trading safety & execution (mt5_lock, broker adapter, pre-close guard) — **complete**
- EA / MT5 generation and runtime (config reload, lifecycle logging, verification) — **complete**
- Data & learning (Dukascopy, ONNX, parameter optimizer, floor/session scoring) — **partial: Dukascopy/ONNX/optimizer complete; per-session scoring deferred**
- Operations & multi-symbol (terminals, deployment, monitoring) — **design complete; prototype deferred**
- Research & CryptoRTI (whale feed, edge discovery) — **ongoing**

## Currently open (verified 2026-08-20)

| Issue | Title | Priority |
|---|---|---|
| #118 | GER40 negative expectancy over 33 trades | research |
| #119 | XAUUSD negative expectancy over 40 trades | research |
| #120 | GER40 losing (exp -0.1023); internal fixes exhausted | research |

