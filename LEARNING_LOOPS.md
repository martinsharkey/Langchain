# The Bot's Learning Loops — How It Learns

> This document explains how the bot learns from every trade: the full cycle
> (signal → gate → trade → manage → reconcile → record → learn → adapt) and each
> individual learning loop. It complements `CONFLUENCE_STRATEGY.md` (the entry
> rules) and `RESEARCHER.md` (the research layer).

## The one-paragraph summary

Every closed trade is recorded with its entry-time indicator snapshot and its
realised **MFE/MAE** (peak favourable / worst adverse excursion). Those records feed
five learning mechanisms — a pattern RAG, a per-symbol ONNX quality model, a
parameter optimizer, a post-mortem directive engine, and a config checkpointer —
all sitting behind **safety gates** so that learning can only tighten or improve
live behaviour, never blindly loosen it. A key insight the data validated: entry
indicators barely predict *how far* a trade runs (R²≈0.03), so the leverage is in
**exit management** and in **filtering low-quality entries**, not in predicting P&L.

---

## The live cycle (`src/trading/scalp_engine.py`)

`_run_cycle()` (`:858`) each tick:

1. **reconcile closed** (`_reconcile_closed` `:2707`) → record outcomes + MFE/MAE.
2. **manage open positions** (`_manage_open_positions` `:1619`).
3. **adapt** (gated): weight adaptation every 5 cycles (`:883`); every 40 cycles
   run the checkpointer, exit calibration, performance researcher, edge/graduation
   recompute (`:929-944`).
4. **background adaptive thread** (`:978`): post-mortem, optimizer, continual
   researcher, DynamicFixer, ONNX retrain.
5. **evaluate & trade** per symbol (`_evaluate_and_trade` `:1005`).

### Entry gating pipeline (`_evaluate_and_trade`, `:1809`)
```
governor pause? → tuned indicator params → FOCUSED pocket (edge overlay) or ensemble
 → whale hybrid (BTC) → operating-mode confidence floor → RAG pattern adj/veto
 → ONNX win-prob nudge/veto → confidence gate → MTF + directional penalties
 → HTF alignment → final gate → risk gate → phase/mode/graduation-gated sizing
 → place() → record_trade(pending) → track
```
Notable vetoes: RAG hard-veto if historical win-rate < 25% over ≥ 25 similar
patterns (`:2440`); ONNX veto if `p_win < 0.30` over ≥ 120 samples
(`:2461-2462`).

### Reconcile → record (`_reconcile_closed`, `:2135`)
Fetches the real deal result, recovers the `ManagedState` from live **or the
tombstone cache** (so manager-closed trades don't lose their excursion), computes
MFE/MAE/exit-points, then:
```python
update_trade_outcome(trade_id, outcome, profit_loss, exit_price, exit_reason,
                     mfe_points=_mfe, mae_points=_mae, exit_points=_exit_pts)   # :2756
vector_store.store_pattern(... outcome ...)                                     # :2775
```

---

## Loop 1 — Experience DB (the ground truth) `experience_db.py`

- `trades` table; lightweight migrations add `mfe_points`/`mae_points`/`exit_points`
  (`:187-192`) and **`data_source`** provenance (`LIVE_MICRO` /
  `SIMULATED_REAL_TICKS` / `SIMULATED_OHLC`, `:199-211`).
- `record_trade` inserts a pending row (default `data_source=LIVE_MICRO`);
  `update_trade_outcome` (`:420`) fills outcome + excursions on close.
- `capture_stats` (`:500`) computes median MFE/MAE and the **capture ratio**
  (`exit_points / mfe_points`) — the "how much of the favourable move did the exit
  actually capture" metric that quantifies the exit leak.
- **Provenance rule:** every training/analysis read excludes `SIMULATED_OHLC`, so
  the model never learns from fictitious interpolated-OHLC backtests.

Historic GoldShark telemetry can be imported into this same table (tagged
`SIMULATED_REAL_TICKS`) via `src/learning/goldshark_import.py`, with an
anti-look-ahead guard so hindsight columns never become entry features.

## Loop 2 — Pattern RAG `vector_store.py` + `pattern_matcher.py`

- 20-dimension normalized indicator fingerprint stored in ChromaDB.
- `find_similar` retrieves nearest historical patterns and **excludes
  SIMULATED_OHLC** by default (`:342`).
- `PatternMatcher.analyze_current_market` turns "what happened last time this setup
  occurred" into a **confidence adjustment** (+0.15 favour … −0.15 avoid), applied
  at entry only when there are ≥ 10 similar patterns.

## Loop 3 — ONNX quality model `onnx_predictor.py`

- Per-symbol `GradientBoostingClassifier` exported to ONNX, keyed by symbol prefix.
- **Scale-free features** (`_fingerprint`, `:36`): everything in ATR units + RSI
  centered + side-of-zero flags, so it learns entry *quality*, not symbol identity.
- **Chronological 70/30 split** (no shuffle → no leakage, `:193`); kept only if
  holdout **AUC clears `min_auc` (0.58) and beats the incumbent** (`:207`).
- Reads exclude synthetic + SIMULATED_OHLC. Output nudges/vetoes entry confidence.

## Loop 4 — Parameter Optimizer `param_optimizer.py`

- Tunes the `PARAM_SPACE` (see `CONFLUENCE_STRATEGY.md`) via ReAct candidates:
  post-mortem **directives** first, then one **mql5-grounded** candidate, then random
  mutations.
- **Skips failed directions** the checkpointer recorded (`is_failed`).
- **Walk-forward gate:** a candidate is kept only if it *generalizes* across windows
  and beats the incumbent's robust **min-window PF** by > 0.01 (`:237-243`). This is
  what stops overfit "holy-grail" params from going live.

## Loop 5 — Post-mortem `post_mortem.py`

Reconstructs real M1/HTF bars around each closed trade, measures MFE/MAE in ATR
units, and classifies the failure mode (`exited_early`, `stopped_then_recovered`,
`entered_late`). `analyze()` emits structured **directives** (e.g. `tp_rr:+0.5`,
`giveback:+0.15`, `sl_atr:+0.2`) that steer the optimizer and the live giveback.

## Loop 6 — Config Checkpointer `config_checkpointer.py` (the safety spine)

This is what makes adaptation *safe*. `evaluate()` (`:140`) returns:
- **checkpointed** — current config is a new best (by realised expectancy).
- **revert** — current is materially worse than best → restore best + record the
  failed direction. **But never revert to a best that is itself losing.**
- **demoted_stale_best** — *(the fix that broke the "losing on every symbol"
  deadlock)* if we're on the best-known config and it's now negative-expectancy, the
  best was a lucky-window artifact → **demote it** so a better config can take over
  (`:171-180`).
- **hold** — within the noise band.

Failed directions are stored (fingerprinted) and written to the KnowledgeStore as
corrections, so neither the optimizer nor the researcher retries them.

## Loop 7 — Graduation & governance `edge_metrics.py`, `graduation.py`, `symbol_governor.py`, `operating_mode.py`

- **EdgeCalculator** — win rate, profit factor, expectancy(R), drawdown, loss
  streak; Phase 0/1/2 gate (`GATE_MIN_TRADES=200`, `PF≥1.3`, `DD≤20`).
- **Graduation** (#24) — a strictly harder size-up gate (`PF≥1.35`,
  `expectancy_R≥0.10`, `WR≥45`, `DD≤15`, `loss_streak≤8`, `n≥150`). Only a graduated
  symbol may size up; governor/checkpointer can only ever **lower** graduation state.
- **SymbolGovernor** — pauses/fails a symbol that bleeds; advisory in demo so it
  never freezes trading.
- **OperatingMode** — per-symbol TRAINING↔LIVE; LIVE requires proven PF and tightens
  the entry bar, TRAINING loosens it to gather data.

## Loop 8 — Semantic memory & reflection `knowledge_store.py`, `reflection_agent.py`, `htf_context.py`

- **KnowledgeStore** — offline MiniLM ChromaDB of findings/corrections/decisions/
  notes; recalled at startup and written back after learning.
- **ReflectionAgent** — L4 ReAct that proposes ONE testable hypothesis to a
  `hypotheses` DB (`proposed→testing→promoted|rejected`); never edits live rules.
- **HTFContext** — weighted higher-timeframe alignment used at entry (confidence
  bump) and in management (blip → widen stop once; reversal → cut).

---

## Safety floors (apply across every loop)

- `LEARNING_ADAPTATION_ENABLED` — master switch that freezes weight/self-tuning.
- `LEARNING_AUTO_REVERT_ENABLED` — the checkpointer keeps running even when
  adaptation is frozen; it is the mechanism that makes learning safe.
- **Walk-forward gate** (`generalizes` + robust min-window PF) on every applied
  change.
- **`data_source != 'SIMULATED_OHLC'`** on every training/analysis read.
- **Per-account scoping** (#21) so demo/live and different accounts never blend.
- Governor / checkpointer / config-revert can only ever **lower** graduation state.

## The honest limits (validated in-project)

- Entry indicators have near-zero power to predict run *size* (XGBoost R²≈0.0267 on
  1,783 zero-cross events). So the model's job is to **filter weak entries**
  (high-MFE/low-MAE classification), not to forecast profit.
- The dominant P&L leak is **exit management** (small wins, big losers / payoff
  inversion), which is why MFE/MAE capture, the excursion loop, and the
  stale-best-exit fix are the highest-leverage work. Real edge is proven by
  **accumulating live closed trades under these gates**, not by more in-sample sweeps.

## Files
- `src/trading/scalp_engine.py` — the cycle + all wiring/call sites
- `src/learning/{experience_db,vector_store,pattern_matcher,onnx_predictor}.py`
- `src/learning/{param_optimizer,post_mortem,config_checkpointer}.py`
- `src/learning/{edge_metrics,graduation,symbol_governor,operating_mode}.py`
- `src/learning/{knowledge_store,reflection_agent,htf_context}.py`
