# Agentic Trader — Persistent Todo List

## Completed
- [x] Explore workspace structure and source code
- [x] Identify VT Markets demo credentials and MT5 paths
- [x] Install/config bot dependencies and environment
- [x] Connect MT5 terminal and verify demo account access
- [x] Full-codebase review (found 3 disconnected seams) — see REPAIR_PLAN.md
- [x] Phase 0: stabilize (fix boot crash, NameError, connector bugs, TRADING_MODE)
- [x] Verify tradable symbol (XAUUSD-ECN) and Algo Trading flag
- [x] Phase 1: BrokerAdapter (symbol resolution, correct sizing, real order_send, algo guard)
- [x] Placed & closed a REAL demo order (proof of execution)
- [x] Phase 2 (partial): scalp engine + real outcome reconciliation to experience DB
- [x] Multi-symbol support (XAUUSD, BTCUSD) with adaptive SL/TP
- [x] Rebuilt dashboard from scratch — real data only
- [x] Deleted old dashboard + 50 stale docs/scripts
- [x] Unified app.py (dashboard + engine, one command)
- [x] Rewrote README + updated SESSION_LOG

## In Progress
- [ ] Accumulate ~100 real closed trades on demo (run `python app.py LIVE_MICRO`)

## Learning improvements — completed
- [x] L1: real RAG vector features (0 hardcoded dims; ADX/stoch/CCI/volume/etc.)
- [x] L2: adaptive strategy weights from real win rates (shrinkage) + weighted ensemble voting
- [x] Expanded strategy library 7 → 16, with real indicator logic
- [x] Removed the strategy cap: `register_custom()` for runtime/auto-generated strategies

## CryptoRTI integration — completed
- [x] S3 client (`src/cryptorti/s3_client.py`) — read features/signals/whale data
- [x] Validation backtest — measured real edge (1h short bias, ~47% vs 39% base; see CRYPTORTI_INTEGRATION.md §6)
- [x] Live mTLS signal client (`src/cryptorti/signal_client.py`) — connected to 3.213.39.89:8443, receiving live signals
- [x] CryptoRTI_WhaleSignal strategy (BTC, status=testing) wired into registry
- [x] Dashboard CryptoRTI panel + `/api/cryptorti`
- [x] app.py auto-starts the signal feed (best-effort); certs git-ignored

## SECURITY — action required
- [ ] ROTATE the AWS key (AKIA537WLRYPCFXW5SQJ) — exposed in chat
- [ ] Ask Danny to reissue the client cert — exposed in chat

## Trade behaviour + per-symbol intelligence — completed
- [x] Per-symbol stats engine (`symbol_stats.py`) — ATR/range/direction per TF (M1..W1), cached
- [x] Multi-timeframe alignment gate before 1m entries (M15/H1/H4)
- [x] Broker-side SL enforced on every entry (refuse naked positions)
- [x] TradeManager with A/B variants per symbol (BE_PLUS_TRAIL / TRAIL_ONLY / SCALP_FIXED / HYBRID_LLM)
- [x] Variant tagged in experience DB (`mgmt_variant`), per-variant performance query
- [x] Learning biases variant selection (explore/exploit) from real outcomes
- [x] Capital-preservation exit on violent reversal
- [x] Fixed get_last_price spread bug

## Phase 3 risk + sessions — completed
- [x] RiskManager: daily-loss halt (% of start-of-day balance; 50% demo, tighter for live), auto daily reset
- [x] Kill switch (data/KILL_SWITCH file), max open positions, min free margin, spread ceiling
- [x] Wired risk gate into every entry + risk status in bot_status.json + dashboard chip
- [x] SessionManager: per-symbol hours (researcher-maintained; gold daily break + weekend, crypto 24/7)
- [x] Pre-close logic (15–30 min): close short-term winners at wick risk, keep losers, let long winners run with widened SL
- [x] Block entries when a symbol's market is closed
- [x] Symbol-profitability scorer (fastest return per symbol)

## Adaptive intelligence (L4/L5/L6 + reflection) — completed
- [x] IndicatorScorer: per-indicator win/loss separation + worst sessions/regimes
- [x] Backtester (L6): vectorized no-look-ahead replay on months of MT5 history; single + combo scoring; promotion gate (verified: rejects mediocre combos)
- [x] ReflectionAgent (L4, ReAct): analyze losers -> form question -> LLM -> testable hypothesis (own hypotheses.db, dedup, markdown-safe JSON parse)
- [x] StrategySynthesizer (L5): hypothesis -> combined candidate strategy via register_custom(status=testing) with optional filter
- [x] AdaptiveLoop: reflect -> synthesize -> backtest -> promote(active)/reject(disabled); runs in background thread, non-blocking
- [x] Ensemble excludes testing strategies (candidates can't affect live trades until backtest-promoted)
- [x] Wired into engine (cadence ADAPTIVE_EVERY_CYCLES) + status in bot_status.json + dashboard "Adaptive AI" tab

## Pending — next phases (see REPAIR_PLAN.md / LEARNING_ARCHITECTURE.md)
- [ ] L3: per-regime, per-symbol strategy selection from real outcomes
- [ ] L7: online confidence calibration (predicted vs realized win rate)
- [ ] Phase 4: wire research/sentiment (news, central banks) into trade decisions
- [ ] Crypto expansion with Danny's L2 order-book data as features
- [ ] Backtest also across multiple timeframes / larger combos in the adaptive search

## Known follow-ups / tech debt
- [ ] Legacy `src/main.py` multi-agent loop is superseded by `src/trading/scalp_engine.py`;
      decide whether to retire it.
- [ ] Tune scalp SL/TP so gold trades don't close at breakeven too quickly.
- [ ] `strategy_registry.update_weights_from_performance` dataclass-as-dict bug (Phase 2).

## ML Authority Pipeline (2026-08-12) � owner-requested

Goal: accumulate backtest/forward-test proof per parameter adjustment, let an ML
engine (XGBoost) mine it nightly, but a discovered pattern only becomes an
AUTHORITATIVE (usable-live) source once it proves enough samples/tests.

- [ ] Append-only ADJUSTMENT LEDGER (DB table `adjustment_ledger`): every param
      change + backtest_pf + fwd_pf + fwd_green + exp_before/after + adopted/reverted,
      per symbol. Wired into ConfigCheckpointer / ParameterOptimizer.
- [ ] Nightly XGBoost pattern engine (`src/learning/ml_pattern_engine.py`): scans
      the ledger + trades + rejected_signals per symbol; emits candidate
      patterns/thresholds with a support count (#backtests/#fwd-tests/#samples).
- [ ] AUTHORITY GATE: a pattern is `provisional` until support >=
      ML_AUTHORITY_MIN_SAMPLES and >= ML_AUTHORITY_MIN_TESTS and OOS score gate;
      only `authoritative` patterns are fed live. Config-driven, per symbol.
- [ ] Nightly scheduler trigger (portable, non-blocking daemon) to run the scan.
- [ ] Tests: ledger append; gate below/above threshold; engine produces+gates.
- [ ] requirements: xgboost; docs updated.

## ML Authority Pipeline � IMPLEMENTED (2026-08-12)

Fully wired, integrated, automated, and tested (162 passing). How it works:

- `adjustment_ledger` (append-only DB table) � every checkpointer adopt/revert is
  recorded with expectancy proof, per symbol. `record_adjustment` /
  `adjustment_history`. Wired in `scalp_engine` at the checkpointer decision point.
- `ml_patterns` (DB table) + XGBoost engine `src/learning/ml_pattern_engine.py` �
  nightly per-symbol classifier (winner vs loser) with OOS ROC-AUC; records top
  feature-importance patterns with SUPPORT (samples + backtests) + OOS score.
- AUTHORITY GATE `promote_ml_patterns(min_samples, min_backtests, min_oos)` � a
  pattern is 'provisional' (ignored live) until it proves support; only
  'authoritative' patterns are exposed via `authoritative_patterns()`. Config:
  ML_AUTHORITY_MIN_SAMPLES / ML_AUTHORITY_MIN_BACKTESTS / ML_AUTHORITY_MIN_OOS.
- Nightly trigger: `app.start_ml_nightly()` daemon runs the scan at ML_NIGHTLY_HOUR
  (non-blocking, portable). Enabled by ML_ENABLED.
- Tests: `tests/test_ml_authority_pipeline.py` (6) � ledger append/per-symbol,
  gate below/above threshold, OOS-block, downgrade.

Next (data-gated): once each symbol accumulates >= ML_AUTHORITY_MIN_SAMPLES real
trades + >= ML_AUTHORITY_MIN_BACKTESTS ledger entries, authoritative patterns will
appear and can feed the confluence/optimiser as a trusted per-symbol source.
