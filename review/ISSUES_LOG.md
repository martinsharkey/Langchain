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
- **Status:** open

### 2. EA generator unit tests

- **Severity:** high
- **Theme:** EA / MT5 generation and runtime
- **Files:** scripts/qmmp/ea_generator.py, data/qmmp/*/GoldShark_*.params.json`n- **Observation:** Generator supports --verify but has no automated tests of its output structure.
- **Risk:** Regressions in generated EA inputs or manifest alignment could go unnoticed.
- **Recommendation:** Add tests for grouped inputs, deterministic Magic, --verify pass/fail, and .set/.params.json consistency.
- **GitHub issue:** #89
- **Status:** open

### 3. EA OnTimer reload resilience

- **Severity:** high
- **Theme:** EA / MT5 generation and runtime
- **Files:** scripts/qmmp/ea_generator.py, data/qmmp/*/GoldShark_*.mq5`n- **Observation:** OnTimer(60) reloads model.json without defined behaviour for missing/corrupt/invalid files.
- **Risk:** A bad config file could crash the EA or apply partial, dangerous values.
- **Recommendation:** Implement atomic reload, range checks, graceful degradation, and a harness test.
- **GitHub issue:** #91
- **Status:** open

### 4. Lifecycle log completeness

- **Severity:** medium
- **Theme:** EA / MT5 generation and runtime
- **Files:** scripts/qmmp/ea_generator.py, data/qmmp/*/GoldShark_*.mq5`n- **Observation:** #84 logs entry snapshot only; modify/BE/close/halt events are missing.
- **Risk:** Incomplete post-trade analysis; cannot reconstruct full trade lifecycle from the log alone.
- **Recommendation:** Add log rows for SL modify, BE/trail step, close, and risk halt. Version the schema.
- **GitHub issue:** #92
- **Status:** open

### 5. Dukascopy fidelity validation

- **Severity:** high
- **Theme:** Data & learning
- **Files:** src/trading/scalp_engine.py, src/learning/adaptive_loop.py, Dukascopy source
- **Observation:** #80 uses Dukascopy for adaptive validation. Fidelity vs MT5 ticks is unproven.
- **Risk:** Promotion decisions may be based on history that diverges materially from live MT5.
- **Recommendation:** Compare OHLC/gaps for overlapping windows; set thresholds; add harness.
- **GitHub issue:** #88
- **Status:** open

### 6. Per-session backtest scoring

- **Severity:** high
- **Theme:** Data & learning
- **Files:** src/learning/param_optimizer.py, backtester
- **Observation:** _mutate_session_floors() is disabled because the backtest cannot compute per-session sub-scores.
- **Risk:** Session-specific floor tuning remains blocked, leaving possible edge uncaptured.
- **Recommendation:** Add per-session metric reporting; validate stability; re-enable only after holdout proof.
- **GitHub issue:** #93
- **Status:** open

### 7. Multi-symbol Approach A prototype

- **Severity:** medium
- **Theme:** Operations & multi-symbol
- **Files:** docs/multi_symbol_architecture.md, src/mt5/connector.py, src/config.py, pp.py`n- **Observation:** #85 selected Approach A; no working prototype yet.
- **Risk:** Design assumptions about CPU/latency/isolation remain untested.
- **Recommendation:** Run two terminals side-by-side; document resource impact; refine Approach B triggers.
- **GitHub issue:** #90
- **Status:** open

---

## Theme backlog (for triage)

- Trading safety & execution (mt5_lock, broker adapter, pre-close guard)
- EA / MT5 generation and runtime (config reload, lifecycle logging, verification)
- Data & learning (Dukascopy, ONNX, parameter optimizer, floor/session scoring)
- Operations & multi-symbol (terminals, deployment, monitoring)
- Research & CryptoRTI (whale feed, edge discovery)

