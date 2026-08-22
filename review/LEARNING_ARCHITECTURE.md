# How Learning Works — Our System vs Hermes / TradingAgents

> **SUPERSEDED SECTIONS (2026-08-07):** the "ensemble / 16-strategy weighted-voting"
> model described below is RETIRED. The system is now standardised to ONE entry
> (`OsMA_Confluence`) and ONE exit (`GS_PROVEN`) — see the CORE RULES in `AGENTS.md`
> and `src/core_rules.py` (the authority). `get_ensemble_signal`/`run_all_strategies`/
> `find_suitable` have been removed. Read the ensemble mentions below as HISTORY.

> **Update (2026-08-02): full current architecture — the continual learning loop is
> CLOSED and every loop verified wired end-to-end (audit 2026-08-02).**
>
> **Entry:** M1 7-indicator CONFLUENCE (`confluence_signal.py`, single source of truth)
> — MACD, OsMA, Bears Power, Bulls Power, EMA, ATR, RSI — OsMA zero-cross trigger with
> MACD-lead, hard gates (MACD align + ATR expanding), soft confirmations (EMA slope,
> ATR range, price-stretch, Bulls/Bears, RSI), M5/M15 HTF support. Enter on M1 (early),
> confirmed by HTF.
> **CryptoRTI whale hybrid (BTC):** live boost via `wave_predictor` (conservative,
> capped — not yet walk-forward validated); backtest validation via `feature_align`
> (S3 whale/VPIN attached causally to bars) — see #43 / `validate_whale_backtest.py`.
> **Optimisation:** `param_optimizer` PARAM_SPACE = authoritative mql5-doc ranges
> (OsMA/MACD 5-34/20-144/5-55, EMA 3-200, ATR 5-50, Bulls/Bears 5-26, RSI 2-30);
> mql5-guided candidates + avoids checkpointer failed directions. Tuned params flow
> `tuned_params.json → compute_full_indicators → live entry` (macd_line/ema follow the
> tuned OsMA/EMA periods so ONNX/MTF features match live).
> **Continual researcher** (`continual_researcher.py`, hourly): review results → query
> mql5 RAG → hypothesis → robust random-window optimise (`robust_tester`) → edge
> discovery sweep (`edge_discovery` → `data/edge_weights.json` overlay) → excursion
> exit calibration → auto-file GitHub issues. All applied LIVE via `apply_exit_config`.
> **Safety:** ConfigCheckpointer keeps best-by-realised-expectancy per symbol, auto-
> reverts degrading changes, records failed directions (learn-from-failure). Graduation
> gates sizing (TRAINING = micro lot). Kill-switch + auto-revert. ONNX per-symbol
> (chronological split, scale-free features) nudges confidence conservatively.
> **Testing:** see TESTING.md — unit suite (79) + offline harnesses (backtest_macd_osma,
> iterative_walkforward, robust_tester, validate_whale_backtest) + the live loop.


This document explains, truthfully and in detail, how our agent learns today
(grounded in the actual code), how that compares to the Hermes and TradingAgents
projects you studied, and a concrete plan to make our agent genuinely learn:
add strategies, enhance patterns, and increase trading accuracy over time.

> **Update (2026-07-30):** L1 (real RAG features), L2 (adaptive weights), and the
> strategy-cap removal are now DONE. See the "Implemented" note in §1 and §4.

---

## 1. The honest current state of OUR learning

Our learning system has four real components that ARE wired together, plus one
feedback link that was previously broken and is now fixed by the new scalp engine.

### The four components

**a) StrategyRegistry** (`src/learning/strategy_registry.py`)
- **IMPLEMENTED:** now **16 strategies** (was 7) — the "7" was just how many
  functions were registered, never a real limit. Added Stochastic reversal, ADX
  trend-strength, Williams %R, CCI breakout, Golden Cross (SMA50/EMA200), BB
  squeeze breakout, MACD cross, Volume breakout, RSI momentum.
- **IMPLEMENTED:** `register_custom()` allows adding NEW strategies at runtime
  (status `testing|active|disabled`) — so the library is now open-ended and
  future auto-generated strategies can be added without editing code.
- `run_all_strategies()` runs all; `get_ensemble_signal()` now does **weighted**
  voting using each strategy's learned weight.
- **IMPLEMENTED (was the L2 bug):** `update_weights_from_performance()` is fixed
  (dataclass `.weight`, with a minimum-sample shrinkage so weights don't swing on
  2-3 trades) and is wired into the engine — weights now adapt from real win rates.

**b) PatternVectorStore** (`src/learning/vector_store.py`) — the RAG memory
- Every decision is embedded into a 20-dimension vector and stored in ChromaDB.
- On close, the pattern's outcome (win/loss + P&L) is written back.
- **FIXED (was the L1 weakness):** all 20 vector dimensions now carry REAL values.
  A new `compute_full_indicators()` (`src/strategies/indicators.py`) computes
  volume-vs-average, 5/10-bar price change, volatility ratio, stochastic K/D,
  ADX trend strength, SMA-50 position, and candle body/wick ratios — verified 0
  dimensions remain hardcoded (was 11). Pattern similarity is now meaningful.

**c) PatternMatcher** (`src/learning/pattern_matcher.py`) — the RAG reasoner
- `analyze_current_market()` finds similar past patterns, computes the historical
  win rate of those similar situations, and returns a **confidence adjustment**:
  - ≥70% historical win → +0.15 confidence
  - ≥50% → +0.05
  - ≥30% → −0.05
  - <30% → −0.15
- This adjustment IS folded into the final decision confidence.

**d) MetaStrategyAgent** (`src/learning/meta_strategy_agent.py`) — the "brain"
- 3-stage pipeline: ANALYZE (run strategies + RAG) → REASON (LLM evaluates all
  signals + history) → DECIDE (synthesize LLM + quant + RAG into one action).
- When LLM and quant agree → confidence boosted. When they conflict → HOLD.
- `record_outcome()` writes results to both the vector store and experience DB.

### The feedback loop (now closed on REAL data)

The essential thing that was broken and is now fixed:

- **Before:** execution was fake, positions were never tracked (a `NameError`),
  so outcomes fed to learning were synthetic (computed off the live bid) — the
  system "learned" from numbers it made up.
- **Now (scalp_engine.py):** real orders are placed, tracked by real MT5 ticket,
  and on close the engine **reconciles against real MT5 deal history** and writes
  the true win/loss + P&L to the experience DB and the vector store. The loop is
  finally closed on genuine outcomes.

### What "learning" therefore means today (honest summary)

1. **Memory of outcomes:** every trade's market context + real result is stored
   (SQLite for stats, ChromaDB for similarity search).
2. **Confidence modulation:** before a new trade, the RAG matcher looks up similar
   past situations and nudges confidence up/down by their historical win rate.
3. **LLM reasoning:** an LLM reads the strategy signals + history and argues for a
   decision, acting as a soft arbiter.

That is real, but it is **shallow**: the agent does not yet change WHICH
strategies it trusts, does not tune indicator parameters, does not create new
strategies, and its pattern memory is half-blind (11/20 fake features). It
remembers and modulates; it does not yet truly *adapt its policy*.

---

## 2. What Hermes and TradingAgents did (and their limits)

From the source you studied and our analysis:

**TradingAgents** — a multi-agent debate architecture:
- Specialist agents (fundamentals, sentiment, news, technicals) each produce a
  view; bull vs bear researchers **debate**; a trader agent decides; risk agents
  review; a reflection step critiques outcomes.
- Strength: structured, role-separated reasoning; explicit reflection on losses.
- Limit: the "learning" is mostly LLM reflection appended to a memory/prompt —
  it improves the *narrative*, not necessarily a measurable edge; it's expensive
  (many LLM calls) and hard to validate; no rigorous out-of-sample proof.

**Hermes** — a ReAct/LangGraph agent with feedback loops:
- Analyses each indicator, what it measures, indicator strength, lookback windows,
  combining indicators; a graph-based loop that revisits and adjusts.
- Strength: treats indicators as tunable, examines lookback/combination — closer
  to genuine strategy search.
- Limit (per our review): not foolproof — the feedback loop can overfit to recent
  data, lacks a disciplined train/validate/test separation, and conflates
  "the LLM changed its mind" with "the system got measurably better."

**The common flaw in both:** they lean heavily on LLM reflection as the learning
mechanism. LLM reflection is good at *hypothesis generation* but poor at *honest
evaluation* — it will happily rationalize. Without a walk-forward/out-of-sample
harness and a metric that can't be gamed, "learning" becomes storytelling.

---

## 3. How OURS is different (and where it should borrow)

**Different / better in principle:**
- We separate **decision (LLM+quant)** from **execution (deterministic
  BrokerAdapter)** and from **outcome truth (real MT5 reconciliation)**. Learning
  trains on *real fills*, not the LLM's own account of events. That is the single
  most important property Hermes/TradingAgents lacked rigor on.
- We persist structured outcomes (SQLite) separately from fuzzy memory (vectors),
  so we can compute honest, ungameable metrics (win rate, P&L, drawdown) per
  strategy and per symbol.

**Where we're currently weaker and should borrow:**
- We don't yet **debate/reflect** on losses the way TradingAgents does.
- We don't yet treat **indicators/lookbacks as tunable** the way Hermes does.
- Our pattern memory is half-fake (the 11 hardcoded features).

The goal: keep our discipline (real outcomes, ungameable metrics, deterministic
execution) and add their strengths (reflection, parameter/strategy search) —
but gate every "improvement" behind out-of-sample validation so we never fool
ourselves.

---

## 4. Concrete plan to make the agent truly learn

Ordered by leverage. Each item says WHAT, WHY, and HOW (files).

### L1 — Fix the pattern memory (highest leverage, low effort) — ✅ DONE
- **What:** replace the 11 hardcoded `0.5` vector features with real values
  (volume, %-change over 5/10 bars, volatility ratio, stochastic K/D, ADX/trend
  strength, SMA position, candle body/upper/lower-wick ratios).
- **Status:** implemented via `compute_full_indicators()` + rewritten
  `_indicators_to_vector`; verified 0 dims remain constant.

### L2 — Make strategy weights actually adapt (medium effort) — ✅ DONE
- **What:** drive each strategy's ensemble vote weight from its REAL closed-trade
  win rate, with a minimum-sample shrinkage prior.
- **Status:** fixed the dataclass bug, added shrinkage, wired into the engine
  (`scalp_engine._run_cycle` every 5 cycles), and made ensemble voting weighted.

### Strategy library expansion — ✅ DONE
- Went from 7 → 16 strategies; added `register_custom()` for runtime/auto-generated
  strategies with `testing` status. The "cap" is removed.

### L3 — Per-regime, per-symbol strategy selection (medium effort)
- **What:** learn which strategy performs best in each market regime
  (trending/ranging/volatile/quiet) for each symbol, and bias selection accordingly.
- **Why:** gold in a quiet range and BTC in a volatile trend need different tools.
  This is where real edge lives.
- **How:** we already detect regime (`registry._detect_market_regime`) and store it.
  Aggregate outcomes by (symbol, regime, strategy) in the experience DB; feed the
  best (symbol,regime)→strategy map into the meta-agent prompt and the ensemble
  weighting.

### L4 — Reflection on losses (borrow from TradingAgents; medium effort)
- **What:** after every N closed losers, run an LLM "post-mortem" that inspects the
  indicator snapshot at entry vs what happened, and proposes a concrete, testable
  hypothesis (e.g., "RSI mean-reversion loses when ADX>30 — add a trend filter").
- **Why:** turns losses into structured hypotheses instead of vague vibes.
- **How:** new `src/learning/reflection_agent.py` reading closed trades from the
  experience DB; write hypotheses to the knowledge base as *pending experiments*,
  not as immediate rule changes.

### L5 — Strategy/parameter search with validation (borrow from Hermes; higher effort)
- **What:** treat indicator parameters (RSI period, EMA lengths, lookback windows,
  thresholds) and simple strategy *combinations* as a search space. Generate
  candidate variants (from L4 hypotheses or a grid), and **validate them
  out-of-sample** before they're allowed to trade live.
- **Why:** this is genuine strategy discovery — the thing you actually want. But it
  MUST be gated by validation or it's just overfitting.
- **How:** requires the backtest harness (below). New candidate strategies register
  in the `StrategyRegistry` as `status="testing"` and only get real capital after
  passing walk-forward.

### L6 — The validation harness (the guardrail that makes L2–L5 honest)
- **What:** a walk-forward / out-of-sample backtester (see `BACKTEST_STRATEGY.md`)
  that replays historical bars WITHOUT look-ahead, and a train/validate/test split.
- **Why:** this is precisely what Hermes/TradingAgents lacked. Any weight change,
  new strategy, or tuned parameter must improve out-of-sample metrics, not just
  in-sample. Without this, "learning" overfits and accuracy degrades live.
- **How:** reconstruct indicators at each historical timestamp; run the
  ensemble+meta decision; measure win rate / profit factor / max drawdown on data
  the change was NOT fitted to. Promote a change only if it beats the incumbent
  out-of-sample by a margin.

### L7 — Online confidence calibration (low effort, ongoing)
- **What:** track predicted-confidence vs realized win rate (a calibration curve).
  If "0.7 confidence" trades only win 45% of the time, recalibrate.
- **Why:** makes confidence mean something; improves position sizing and gating.
- **How:** bucket closed trades by predicted confidence in the experience DB;
  compute realized win rate per bucket; apply a correction factor in the meta-agent.

---

## 5. The learning loop we are building toward

```
   live market ──▶ indicators (rich, real) ──▶ 7 strategies + ensemble
                                                     │
                        RAG recall (real 20-dim) ────┤
                        regime + per-symbol stats ───┤
                                                     ▼
                                          Meta-agent decision
                                          (LLM + quant + RAG)
                                                     │
                                     BrokerAdapter (REAL order)
                                                     │
                                        MT5 fill + close (TRUTH)
                                                     │
                        ┌────────── reconcile real outcome ──────────┐
                        ▼                    ▼                        ▼
             experience DB (stats)   vector store (memory)    calibration curve
                        │                    │                        │
                        └──────────► adapt weights (L2) ◄─────────────┘
                                     per-regime selection (L3)
                                     reflection → hypotheses (L4)
                                     candidate strategies (L5)
                                            │
                                   VALIDATE out-of-sample (L6)  ◄── the guardrail
                                            │
                                   promote only if it truly improves
```

**Accuracy improves** because: (1) memory recall becomes sharp (L1), (2) the
ensemble shifts toward what actually wins per regime/symbol (L2/L3), (3) losses
generate testable fixes (L4/L5), and (4) nothing is adopted unless it beats
out-of-sample (L6) — the discipline that Hermes/TradingAgents skipped.

---

## 6. Recommended order

1. **L1** (real vector features) + **L2** (adaptive weights) — biggest edge per
   hour, needs no new infra. Do these while the 100-trade demo sample accumulates.
2. **L6** (backtest harness) — the guardrail; unblocks safe L3/L5.
3. **L3** (per-regime/symbol selection) — real edge.
4. **L7** (calibration) — cheap, always-on quality.
5. **L4/L5** (reflection + strategy search) — the ambitious, high-ceiling work,
   only once L6 can validate them.

Every step trains on REAL closed trades and is judged by ungameable, out-of-sample
metrics — which is exactly how ours is designed to beat the "LLM reflection as
learning" trap that limited Hermes and TradingAgents.


## Directional bias + P&L-trajectory management (2026-07-30)

Problem: 100% long bias. Root cause: trend-following strategies outweigh
mean-reversion ~16:6, so raw weighted-majority voting always favoured the larger
camp in a trend.

Fixes:
- Ensemble now uses CONVICTION scoring (avg weighted confidence per side + mild
  breadth bonus) instead of raw weighted majority. A strong minority (e.g. a 90%
  MACD sell) can now win. Verified: bearish snapshot -> SELL, bullish -> BUY.
  ENSEMBLE_BIAS_DAMPEN env can further tune sell sensitivity if needed.

- P&L-TRAJECTORY GIVEBACK GUARD (the AI edge): the trade manager now tracks each
  open position peak unrealized profit and CUTS when a winner gives back too much
  of its peak (a winner rolling into a loser). Giveback fraction is per-symbol
  and learned.

- TREND-RIDE MODE: positions aligned with the higher-TF trend tolerate more
  giveback (ride the move) instead of being scalped out early.

- PER-SYMBOL PERSONALITY (learned): _refresh_personalities() classifies each
  symbol from real closed trades as aggressive_scalper (small frequent wins ->
  cut givebacks fast, frac 0.3), trend_rider (wins bigger than losses -> tolerate
  more, frac 0.6), or neutral (0.45). Feeds the giveback guard so the bot morphs
  its style per symbol. Refreshed on a cadence once >=8 closed trades exist.

The learning loop refines all of these from real outcomes over time (variant
weights, per-symbol personality, giveback thresholds).


## Learning verification + multi-symbol expansion + proactive researcher (2026-07-30)

VERIFIED real learning is happening (not theatre):
- Strategy weights adapting from real outcomes: EMA_TrendFollow 2 -> 0.885,
  SR_Breakout 2 -> 1.0 (losing strategies down-weighted).
- RAG memory: 1431 patterns stored and read at entry.
- A/B variant signal emerging: SCALP_FIXED (+4.61) & HYBRID_LLM (+0.78) winning;
  TRAIL_ONLY (-3.48) & BE_PLUS_TRAIL (-2.36) losing.
- Reflection produced 2 hypotheses, both correctly rejected by the backtest gate.

Expanded TRADING_SYMBOLS to 8 (XAUUSD, XAGUSD, BTCUSD, ETHUSD, EURUSD, AUDUSD,
USDCAD, GER40) across metals/crypto/FX/index to plug the learning gap and learn
what works per instrument. MAX_OPEN_POSITIONS raised to 6.

Added PerformanceResearcher (src/learning/performance_researcher.py): proactive
INWARD self-analysis of real trading outcomes -> per-symbol/variant/regime/
direction stats + actionable recommendations, written to the knowledge base and
bot_status.json ("performance_research"). Runs on the same cadence as profitability.

News feed: was "red/off" only because NEWSAPI_KEY is unset. Central-bank +
geopolitical sources scrape public sites (no key). Dashboard now reports
"partial (free sources only)" with an amber dot instead of red. Set NEWSAPI_KEY
for full news (or add RSS sources - future).


## Integration proof + researcher-acts + free news + counter-trend (2026-07-30)

- prove_learning.py: repeatable harness proving (A) all components integrate and
  (B) real learning advances. Latest run: ALL INTEGRATION CHECKS PASSED, 44 real
  closed trades, weights adapted, RAG 1441 patterns, variants diverging
  (SCALP_FIXED +1.66 vs TRAIL_ONLY -6.05), researcher produced 4 recommendations.
- New AWS creds (Danny): read whole bucket + WRITE to martin/ shared folder.
  Async channel live: martin/martin_qna.md pushed. s3_client auto-loads
  cryptorti/.env.cryptorti; put_shared/get_shared helpers added.
- Whale-event data now spans Jan 1 -> today (211 days) for richer correlation mining.
- PerformanceResearcher now ACTS: _symbol_paused() pauses new entries on a
  bleeding symbol (config SYMBOL_PAUSE_*). Variant selection already biases to winners.
- Free RSS news (src/data_sources/rss_news.py): Yahoo/CoinDesk/Investing feeds,
  NO api key. 32 live headlines; dashboard shows them + green news dot.
- Long-bias root cause #2: MTF alignment gate blocked ALL shorts in a bull market.
  Now high-conviction counter-trend signals (conf >= MTF_COUNTERTREND_MIN_CONF,
  default 0.7) are allowed through, so the bot can take the other side on strong
  setups instead of only trend-trading.
