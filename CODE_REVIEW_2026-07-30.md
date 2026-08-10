# Codebase Review — Fresh-Eyes Audit (2026-07-30)

> **UPDATE (same day):** C1 and C2 are now FIXED. See "Fixes applied" at the top.
> Manual-trade takeover was also added per user request.

## Fixes applied (post-review)
- **C1 (loop closed):** `mt5_ticket` is now persisted on every trades row; added
  `_reconcile_pending_from_db()` (startup + every 10 cycles) that resolves pending
  trades from MT5 deal history regardless of in-memory tracking; adopted positions
  get a real `db_trade_id`; stale un-findable pending rows are marked `unknown`.
  One-time cleanup marked 14 legacy/synthetic rows `unknown` so stats start clean.
- **Manual-trade takeover:** `_adopt_existing_positions()` now adopts ALL open
  positions (any magic, incl. hand-placed trades) whose symbol is in the trading
  set, records a DB row, assigns a management variant, and manages them (SL/BE/
  trail/capital-preservation). `BOT_MAGIC` is configurable.
- **C2 (RAG reads at entry):** `PatternMatcher.analyze_current_market()` is now
  called in `_evaluate_and_trade`; confidence is adjusted from similar historical
  patterns, with a hard veto only on strong evidence + real sample (win rate <25%
  over >=25 similar) so early/biased history can't freeze trading.
- **Verified live:** adopted 2 positions, moved one to BE+ (broker SL modified),
  RAG actively influenced/vetoed entries, new trades persist tickets and reconcile.

Remaining from this review: I2 (dead duplicate `get_strategy_performance` +
`get_learning_insights` bug + avg_confidence off-by-one), M1 (HYBRID_LLM fake arm),
M3 (silent exception swallowing), M4 (logger propagate), H1 (log rotation),
H2/H3 (data prune). These are unchanged below.

---

Reviewer perspective: as if seeing the code for the first time, comparing the
running service against the design docs (REPAIR_PLAN, LEARNING_ARCHITECTURE,
CRYPTORTI_INTEGRATION, README) and hunting for breaks, unclosed loops, learning
hazards, and data/housekeeping problems.

**Overall:** the system is genuinely working — it connects to live MT5, places
real demo orders with broker-side SL, assigns A/B management variants, and the
risk/session layers behave correctly. But there are **two critical learning-loop
defects** that mean the bot is currently *acting* but not truly *learning*, plus
several important correctness issues and housekeeping gaps.

---

## CRITICAL (fix before trusting the learning loop)

### C1. Trades get stuck `pending` forever — the learning loop is not closed
- **Where:** `scalp_engine.py` `_reconcile_closed` (only reconciles trades in the
  in-memory `self.open_positions`), `_adopt_existing_positions` (adopts only
  currently-OPEN positions, and gives them `db_trade_id=None`).
- **Symptom (verified):** 9 of 15 DB trades are `outcome='pending'` permanently —
  including trades from prior runs closed manually or by SL/TP between runs.
- **Why it's critical:** every learning query filters `WHERE outcome IN
  ('win','loss')`. Pending rows contribute **zero** signal. The bot "learns" only
  from the biased subset of trades whose entire lifecycle happened within one
  uptime window. The MT5 **ticket is never persisted on the trades row**, so a
  restart cannot recover a pending trade from history.
- **Fix:** persist the MT5 ticket on the trades row; add a **DB-driven
  reconciliation** (startup + periodic) that finds `pending` rows, looks up the
  ticket in `mt5.history_deals_get`, writes the real outcome, and marks
  truly-unfindable old rows as `unknown` so they stop skewing counts. Give adopted
  positions a real `db_trade_id`.

### C2. The RAG memory is write-only — it never influences a decision
- **Where:** `scalp_engine._evaluate_and_trade` builds the signal only from the
  ensemble + MTF gate. The vector store is used **only** at `scalp_engine.py:543`
  (`store_pattern` on close). There is **no** `find_similar` / `pattern_matcher`
  read anywhere in `src/trading/` (grep-confirmed).
- **Why it's critical:** LEARNING_ARCHITECTURE.md sells RAG confidence-modulation
  as a core learning mechanism. Storing patterns but never reading them means the
  "learn from similar past trades" loop does nothing in the live engine.
- **Fix:** in `_evaluate_and_trade`, after the ensemble signal, call
  `vector_store.find_similar(indicators)` (or PatternMatcher) and nudge/veto
  confidence before the `SCALP_CONFIDENCE_MIN` gate; update the pattern outcome on
  close via `update_pattern_outcome`.

---

## IMPORTANT

### I1. Variant A/B learning is inert until C1 is fixed
- Chain: reconciliation stalls → `get_variant_performance()` returns `{}` →
  `_variant_weights_for` returns the uniform floor → `assign_variant` is
  **uniform random forever**. Also the `trades >= 3` per (symbol,variant) gate is
  essentially unreachable with a broken reconciler.
- **Fix:** fix C1; log when the variant cache is empty so "no learning" is visible;
  consider annealing the 3-trade threshold.

### I2. Duplicate/dead `get_strategy_performance` + wrong `strategy_performance` table
- Two definitions (`experience_db.py:499` list-form is **dead**; `:581` dict-form
  wins). `get_learning_insights` (`:548`) expects the list form → will `TypeError`
  / degrade silently. Live weight path reads the **trades** table, so the
  `strategy_performance` table is maintained but unused; `avg_confidence` running
  average is off-by-one.
- **Fix:** delete the dead method, standardise on the trades table as the single
  source of truth, fix `get_learning_insights`, fix the avg_confidence math.

### I3. RAG lifecycle half-wired
- `update_pattern_outcome` is never called by the engine (only meta_strategy_agent).
  Consistent with C2. Fix as part of C2.

---

## MINOR

### M1. `HYBRID_LLM` is a fake A/B arm
- In `trade_manager.py` it shares the exact branch as `BE_PLUS_TRAIL` with no LLM
  call. ~25% of variant exploration is wasted on a duplicate arm.
- **Fix:** implement the LLM review, or remove it from `VARIANTS` until it exists.

### M2. `ManagedState.opened_at` mis-ages adopted trades
- Set to `time.time()` at *register* time, not real open time. A days-old adopted
  position looks brand-new → `preclose_decision` may misclassify a long-runner as
  short-term and close it early.
- **Fix:** pass the real open time (parse `TrackedPosition.opened_at` or MT5
  `position.time`) into `register()`.

### M3. Silent exception swallowing hides learning failures
- Weight/variant refresh failures are `logger.debug` (hidden at default level);
  `_set_trade_variant` uses bare `except: pass`. A broken learning step disappears
  silently.
- **Fix:** raise to `warning`, surface a stalled-learning flag in `bot_status.json`.

### M4. Duplicated log lines (cosmetic, not doubled trading)
- `src/utils/logger.py` adds handlers to every named logger and never sets
  `propagate=False`, so `mt5.*` child loggers emit twice (via parent `mt5`).
  **Confirmed the engine is NOT running twice — only logs are doubled.**
- **Fix:** add `logger.propagate = False` in `setup_logger`.

---

## HOUSEKEEPING / DATA

### H1. No log rotation — unbounded growth
- `logger.py:59` uses plain `FileHandler`. Logs will grow forever (already ~1MB).
- **Fix:** use `RotatingFileHandler(maxBytes=…, backupCount=…)` or Timed rotation.

### H2. ChromaDB + JSON state growth
- Vector store (`.bin`/`.sqlite3`, ~2MB) grows per stored pattern; `bot_status.json`,
  `cryptorti_signals.json`, `symbol_stats.json` are rewritten each cycle (fine).
- **Fix:** periodic prune of very old / low-value patterns; cap CryptoRTI stored
  signals (already sliced to 50). Add a small `housekeeping` routine.

### H3. Stale/duplicate DBs from the pre-rebuild era
- `data/` holds multiple DBs (experience, knowledge, version_management,
  handoff_protocol) — some from the legacy multi-agent system. The 6 old `XAUUSD`
  (non-ECN) synthetic trades still sit in the experience DB skewing early stats.
- **Fix:** one-time cleanup: mark/delete the pre-rebuild synthetic `XAUUSD` rows;
  decide whether version_management/handoff DBs are still needed.

### H4. Doc drift (minor)
- `LEARNING_ARCHITECTURE.md:212` flow diagram still says "7 strategies" while the
  text (correctly) says 16. Cosmetic.

---

## Priority order to fix
1. **C1** (close the learning loop — persist ticket + DB-driven reconciliation).
2. **C2** (read RAG at entry — make the memory actually affect decisions).
3. **I2** (remove dead/duplicate stats method; single source of truth).
4. **I1** (falls out of C1; add visibility).
5. **M4 + H1** (logger propagate + rotation — quick wins).
6. **M1/M2/M3, H2/H3/H4** (polish + housekeeping).

Note: C1 is the single highest-leverage fix — it is the root cause of the "not
learning" behaviour and the dependency that also disables I1 and biases I2.
