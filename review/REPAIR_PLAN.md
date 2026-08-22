# Agentic Trader — Repair & Completion Plan

**Author:** Code review (Opus 4.8)
**Date:** 2026-07-30
**Goal:** Turn the current live-data analysis engine into a real, safe, self-improving agentic trader — first for XAUUSD, then extensible to crypto (Danny's L2 data).

---

## 1. Honest Current-State Assessment

The system is **~70% built and ~30% wired**. The intelligence exists; the connections don't.

### What is REAL (keep, don't rebuild)
- Live MT5 data feed (candles/ticks/account/history) — `src/mt5/data.py`, `account.py`.
- 7 real indicator strategies — `src/learning/strategy_registry.py` + `src/strategies/indicators.py`.
- 3-stage LLM meta-decision engine — `src/learning/meta_strategy_agent.py`.
- RAG pattern store + matcher (feeds confidence) — `src/learning/vector_store.py`, `pattern_matcher.py`.
- Real `place_order()`/`close_order()` — `src/mt5/orders.py` (orphaned).
- Real news/central-bank scrapers + LLM sentiment analyzer — `src/data_sources/`, `src/agents/enhanced_research_agent.py` (orphaned + un-importable).

### The 3 broken seams (why no real trades, no real learning, no adaptation)
1. **Execution seam:** `execute_trade()` narrates via LLM instead of calling `place_order()`. `main.py:852-940`.
2. **Learning seam:** `NameError` on `trade_result` (`main.py:920`) kills position tracking; real outcomes never reconciled from MT5; `update_trade_outcome()` never called.
3. **Sentiment seam:** research/orchestrator pipeline never called by the loop and un-importable (`EconomicCalendarSourceMock`/`CentralBankSourceMock` deleted but still imported).

### Critical safety gaps (MUST fix before any live money)
- No max-open-positions, daily-loss limit, kill switch, spread/margin/session checks.
- Lot sizing wrong for gold (`risk_pips * 10`; should derive from `symbol_info` — ~100/pt/lot for XAUUSD). `main.py:787`.
- Config `RISK_PERCENT` / `MAX_POSITION_SIZE` ignored (hard-coded 1% and 0.1 cap). `main.py:784,789`.
- No symbol-suffix handling — hard-coded `"XAUUSD"` breaks on `XAUUSD-ECN`. Everywhere.

### Runtime-breaking bugs to squash
- `main.py:920` — undefined `trade_result` (NameError every approved cycle).
- `connector.py:429-430` — double `@property` on `bridge_available`.
- `connector.py:397-398` — unreachable code after `return False`.
- `strategy_registry.py:783` — dataclass indexed as dict (TypeError on reweight).
- `strategy_registry.py:439` — `__init__(self)` takes no `exp_db`; registry can't see performance.
- `experience_db.py:395 & 477` — `get_strategy_performance` defined twice (shadowing).
- `economic_calendar.py:155` — `"upstream"` vs `"upcoming"` key bug.
- `meta_strategy_agent.py:606` — malformed log format string.
- `data_sources/__init__.py:5,7` + `market_data_collector.py:26,28,50,52` — dead Mock imports.

---

## 2. Guiding Principles

1. **Safety first, then correctness, then intelligence.** No live order path opens until guards + paper mode exist.
2. **Close the loop on REAL data.** Learning must train on real MT5 fills/closes, never synthetic.
3. **One runtime.** Merge the two disjoint stacks (trading bot vs research/dashboard) so research actually informs trades.
4. **Symbol-agnostic core.** Everything keyed off `symbol_info`, no hard-coded `XAUUSD`, so crypto is a config change, not a rewrite.
5. **Explicit modes:** `OBSERVE` (no orders) → `PAPER` (simulated fills, real logic) → `LIVE_MICRO` (0.01 lot real) → `LIVE`. Gated by readiness + human approval.

---

## 3. Phased Plan

### PHASE 0 — Stabilize & unblock (0.5–1 day)
Make the app boot and stop lying.
- Fix dead Mock imports (`__init__.py`, `market_data_collector.py`) so `app.py` boots as one process.
- Fix `main.py:920` `trade_result` NameError.
- Fix `connector.py` double-property + unreachable code.
- Remove stale "simulation at ~$4,038" prompt text (`research_agent.py:21`).
- Add an explicit `TRADING_MODE` config (`OBSERVE|PAPER|LIVE_MICRO|LIVE`), default `OBSERVE`.
- **Exit criteria:** `python app.py` starts cleanly; dashboard shows real MT5 data (done for trades); no phantom-trade writes in OBSERVE.

### PHASE 1 — Real execution + a proper broker adapter (2–3 days)
Wire the decision to the real order layer, safely.
- Introduce a `BrokerAdapter` that: resolves symbol suffix (`XAUUSD` → broker's `XAUUSD-ECN`), reads `symbol_info` (min/step/max volume, contract size, tick value), and exposes `place`, `close`, `modify`, `positions`.
- Rewrite `execute_trade()` to call `BrokerAdapter.place(...)` (NOT the LLM). Capture the real ticket.
- Correct position sizing: derive $/point/lot from `symbol_info`; honor `RISK_PERCENT`/`MAX_POSITION_SIZE`; round to `volume_step`; clamp to `[min_volume, max_volume]`.
- In `PAPER` mode, `BrokerAdapter` simulates fills using real spread/price but places no order; in `LIVE_*`, it calls `order_send`.
- **Exit criteria:** In PAPER, a decision produces a tracked position with a real entry price and correct lot; in LIVE_MICRO a 0.01 order actually appears in MT5.

### PHASE 2 — Close the learning loop on REAL outcomes (2–3 days)
- Add a **reconciliation service**: poll `get_positions()` + `history_deals_get()` each cycle; when a tracked ticket closes, pull the **real** profit/exit and call `ExperienceDatabase.update_trade_outcome()` + `vector_store.update_pattern_outcome()`.
- Delete the synthetic `OpenPosition.check_if_closed` P&L path (or keep ONLY for PAPER mode, clearly labelled).
- Fix `experience_db` double-definition; fix `strategy_registry` `exp_db` wiring and the dataclass reweight bug so per-strategy win-rates populate from real closed trades.
- Fill the 11 hardcoded `0.5` RAG embedding features with real values (volume, volatility, ADX, stochastic, SMA position, candle ratios) so pattern similarity is meaningful.
- **Exit criteria:** Close a real (micro) trade → its true P&L appears in `trading_experience.db`, updates strategy win-rate, and updates the RAG pattern outcome. Readiness meter moves on real data.

### PHASE 3 — Risk & safety layer (1–2 days) — REQUIRED before LIVE
- Central `RiskManager` enforced at order time: max open positions, max daily loss (equity drawdown halt), per-trade risk cap, spread ceiling, free-margin check, market/session check, duplicate/conflict guard, and a persisted **kill switch** (file/flag the dashboard can toggle).
- Make the existing risk-agent verdict actually gate execution (currently ignored, `main.py:758`).
- **Exit criteria:** Guards demonstrably block orders in unit tests (e.g., spread too wide, daily loss hit, kill switch on).

### PHASE 4 — Connect the sentiment/research brain (2–3 days)
This is the adaptive intelligence you set out to build.
- Repair `data_sources` imports; replace disabled stubs (`geopolitical`, `usd_strength`, `gold_news` mock) with either real sources or an explicit, dashboard-visible "unavailable" state (never silent fake data).
- Run `EnhancedResearchAgent` on a schedule (daily + on-demand) inside the single runtime; persist its `net_bias`/`volatility_risk`/`trading_confidence`.
- Wire `apply_research_to_trade_decision()` into the loop: research bias adjusts confidence / vetoes trades / scales size (e.g., block counter-trend trades into high-impact news, cut size when volatility risk high).
- **Exit criteria:** A high-impact event visibly changes the bot's confidence/size/veto in the decision log and on the dashboard.

### PHASE 5 — Validation, backtest & readiness gating (2–4 days)
- Implement the no-look-ahead backtest from `BACKTEST_STRATEGY.md`: replay the account's 24 real historical deals, reconstruct indicators at each entry time, and measure what the ensemble+meta-agent *would* have done — without future data.
- Define a concrete **readiness gate**: only allow `OBSERVE→PAPER→LIVE_MICRO→LIVE` transitions when thresholds are met (min real closed trades, min win rate, max drawdown, backtest agreement). Make the dashboard meter reflect these real gates.
- **Exit criteria:** Backtest report produced from real history; mode transitions require passing the gate + explicit human confirmation.

### PHASE 6 — Crypto extensibility (after XAUUSD is live-stable)
- Because the core is now symbol-agnostic (`symbol_info`-driven), add crypto symbols via config.
- Define an interface for Danny's **L2 order-book data** as a new `data_source` feeding both features (RAG embedding: imbalance, depth, spread dynamics) and the sentiment layer.
- Add crypto-specific session/volatility handling (24/7 market, no session close).
- **Exit criteria:** Same pipeline runs a crypto symbol in PAPER using L2-derived features.

---

## 4. Recommended Immediate Order of Work
1. Phase 0 (stabilize) — unblocks everything, low risk.
2. Phase 1 (real execution in PAPER) — makes the system honest.
3. Phase 2 (real learning loop) — makes it actually improve.
4. Phase 3 (risk) — mandatory gate before any real money.
5. Phase 4 (sentiment) — delivers the adaptive edge you wanted.
6. Phase 5 (validation/gating), then Phase 6 (crypto).

**Total to first safe LIVE_MICRO on XAUUSD:** ~8–13 focused days across Phases 0–3, with Phase 5 gating before real capital.

---

## 5. What NOT to do
- Do NOT let the LLM "execute" trades via prose. LLM decides; deterministic code places orders.
- Do NOT train learning on synthetic outcomes once real fills are available.
- Do NOT ship any silent mock data to the dashboard — show "unavailable" instead.
- Do NOT go LIVE before Phase 3 guards + Phase 5 readiness gate pass.
