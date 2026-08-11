# Intelligent Pyramiding Basket + LangGraph Supervisor — Design & Wiring Spec

> Status: DESIGN (pre-implementation). Purpose: prove on the VT Markets **demo**
> account, then graduate to a real account only once demo results + backtest +
> forward test confirm the edge and the drawdown envelope hold.
>
> **This ENHANCES existing components. Nothing here is rebuilt.** See the
> "Existing pieces reused" section — every primitive already exists.

---

## 1. Objective (owner's words)

Small losing trades were bleeding the account; the winners could have carried far
more if we *pyramided* into them. We want an **intelligent trader** that, once in a
trade, continuously reasons across ALL indicators/timeframes (OsMA, MACD,
Bulls/Bears power + direction, RSI, ATR, HTF alignment) using knowledge/experience
for that specific symbol, and decides: HOLD / TIGHTEN / EXIT / ADD-LEG / CUT-ALL.

Pyramiding rule (owner-specified):
1. **Leg 1 trades normally** (GoldShark confluence entry; can take a normal stop).
2. **A basket is created ONLY once Leg 1 has (a) reached +X profit AND (b) already
   moved its stop to breakeven.**
3. **Each additional leg requires full multi-timeframe indicator re-confirmation**
   (still travelling the same direction) AND all existing legs in profit.
4. **The whole basket is cut together** on a confirmed reversal.
5. **Compounding is allowed** (balance-based sizing) **within a proven drawdown
   envelope** — the optimiser discovers the safe ceiling from real-tick backtests.
6. **No arbitrary leg cap** — the profit-per-leg + breakeven rule self-limits.

---

## 2. Existing pieces reused (DO NOT REBUILD)

| Need | Already exists | File |
|---|---|---|
| Pyramiding / add-to-winner | PYRAMIDING block (currently gated by `GROWTH_ENABLED`, default off) | `scalp_engine.py:2635` |
| Balance-based compounding + capital extraction | GROWTH sizing | `scalp_engine.py:1097`, `config.py GROWTH_*` |
| Per-leg breakeven state | `TrackedPosition.moved_to_be` | `scalp_engine.py` |
| Multi-timeframe alignment (M5/M15/M30/H1) | `HTFContext.read` / `blip_or_reversal` | `src/learning/htf_context.py` |
| Confirmed-reversal group cut primitive | HTF reversal exit | `scalp_engine.py:1749` |
| Learned per-symbol reversal signature | `ReversalSignatureAnalyzer` | `src/learning/reversal_signature.py` |
| Throttled LLM trade review (to be enriched) | `_llm_trade_review` (HYBRID_LLM) | `scalp_engine.py:1845` |
| Async reasoning loop | `LangGraphResearcher` | `src/learning/langgraph_researcher.py` |
| Real-tick backtest + walk-forward | `Backtester`, `robust_tester`, `iterative_walkforward` | `src/learning/backtester.py`, `scripts/` |
| Daily-loss circuit breaker | `GROWTH_DAILY_LOSS_HALT_PCT` | `config.py` |

**The only genuinely NEW capability:** multi-leg basket simulation inside the
existing `Backtester` (today it models a single position at a time).

---

## 3. Enhancements (in place, per file)

### 3a. Pyramid leg rule — `scalp_engine.py:2635`
- Replace the flat "all legs in profit" check with the owner rule:
  - basket may start only if **leg 1 `moved_to_be` is True AND leg-1 profit ≥
    `PYRAMID_LEG1_TRIGGER_ATR × ATR`** (tunable, discovered by optimiser).
  - each new leg requires **`HTFContext.read(...)` still aligned same direction**
    (OsMA+MACD across M1/M5/M15) AND every existing leg in profit AND the newest
    leg ≥ `PYRAMID_ADD_ATR × ATR` in profit and at breakeven.
- Remove the hard `GROWTH_PYRAMID_MAX` cap (rule self-limits); keep a broker/margin
  sanity ceiling only.

### 3b. Group management — `_manage_open_positions`
- Add a **basket-aware group cut**: when `htf.blip_or_reversal` returns `reversal`
  (or the learned reversal-signature fires) for a symbol holding ≥1 leg, close
  ALL legs of that symbol together (deterministic, per-tick — NOT LLM-gated).
- Add an **aggregate drawdown halt**: if basket aggregate P&L drawdown from its
  peak exceeds the proven `PYRAMID_MAX_DD_*` envelope, cut all legs.

### 3c. Intelligent supervisor — enrich `_llm_trade_review` via `LangGraphResearcher`
- Observe: full multi-TF indicator snapshot (reuse `HTFContext` + live indicators).
- Recall: this symbol's experience (RAG/experience DB) — "when all TFs aligned and
  OsMA strong, past trades ran +X pts N% of time".
- Reason (ReAct) → Decide: HOLD / TIGHTEN / EXIT / ADD_LEG / CUT_ALL.
- Act: the fast Python layer executes; **the deterministic per-tick layer always
  owns the stop, the group-cut and the drawdown halt** — the LLM never owns safety.
- Cadence: throttled (~20–30s per position or on a significant move).

### 3d. Backtester — multi-leg sim (`backtester.py`)
- Extend the single-`open_trade` model to a list of legs; simulate leg adds on the
  same real-tick path; compute **aggregate basket equity curve + worst-case
  drawdown** per parameter set. Never use 1-min OHLC.

### 3e. Optimiser envelope (`param_optimizer` / walk-forward)
- New tunables (all discovered, none hardcoded): `PYRAMID_LEG1_TRIGGER_ATR`,
  `PYRAMID_ADD_ATR`, `PYRAMID_MAX_DD` (aggregate), reversal-cut sensitivity.
- 70/30 train/test; **approve a setting only if out-of-sample worst-case basket
  drawdown stays within the ceiling** AND aggregate PF improves.

---

## 4. Safety invariants (non-negotiable)
1. Entry trigger stays LLM-free and instant.
2. **The entry extension guard (`max_stretch_atr`) gates FRESH leg-1 entries only.**
   Forensic on real ticks showed 76% of losers were late entries into
   already-extended moves — so leg 1 must respect the stretch ceiling. But a
   pyramid ADD is by definition into an extended winning move, so when a winning
   same-direction position is already open the signal is re-evaluated with the
   stretch ceiling lifted. The extension guard therefore reduces late-entry
   losers WITHOUT constraining pyramiding (`scalp_engine._evaluate_and_trade`).2. The deterministic per-tick layer owns: stop-loss, group reversal-cut, drawdown
   halt. The LLM only *adds* intelligence (hold longer / add a leg / exit sooner).
3. Nothing runs live (even on demo compounding) until backtest + forward test prove
   the drawdown envelope. Demo proving precedes any real-money account.
4. `GROWTH_DAILY_LOSS_HALT_PCT` remains an absolute circuit breaker.

---

## 5. Build order (tracked in the session todo)
1. Enhance pyramid leg rule (3a) + group cut/DD halt (3b).
2. Multi-leg backtester (3d).
3. Optimiser envelope discovery + forward test (3e).
4. LangGraph supervisor enrichment (3c).
5. Enable within proven envelope; full test harness; demo verification.
