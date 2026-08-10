# The Researcher — How It Works

> The bot runs an autonomous research layer that reviews its own results, forms
> hypotheses grounded in an offline mql5 knowledge base, tests them behind a
> walk-forward gate, and files GitHub issues for anything a human should look at.
> **It never changes live parameters through an un-gated path.**

There are three cooperating research components:

1. `continual_researcher.py` — the daily ReAct loop (markets + our own results).
2. `performance_researcher.py` — inward self-analysis of our own trades.
3. `edge_discovery.py` — the walk-forward sweep that writes the per-symbol edge map.

---

## 1. Continual Researcher (`src/learning/continual_researcher.py`)

### Cadence
`daily_cycle(symbols, force=False)` (`:408`) is **idempotent per UTC day** — it
early-returns if it already ran today (`:413-416`). It is invoked from the engine's
background adaptive thread (`scalp_engine.py:1733`). A faster sub-cadence
(excursion measurement + pattern lock) is driven separately at
`EXIT_CALIBRATION_CYCLES` (`scalp_engine.py:742`).

### The ReAct steps

**REVIEW** — `review_symbol(base, limit=40)` (`:234`) reads recent closed trades,
**excluding synthetic and `SIMULATED_OHLC`** rows (`:242-246`), and computes win
rate, expectancy, net P&L, the **dominant losing exit reason** (failure-mode proxy),
and the worst strategy.

**QUERY + REASON** — `research_symbol(base)` (`:326`) requires ≥ 10 reviewed trades,
then grounds a query in the symbol's *actual* weakness and searches the offline mql5
RAG (`:333-337`):

```
q = "improve XAUUSD trading: win rate 46% expectancy -0.05,
     losers exit via sl; better indicator or parameter?"
knowledge = self.mql5.research(q, n_results=3)
```

**HYPOTHESIS** — combines our results + the retrieved knowledge into a testable
statement and stores it in the KnowledgeStore under a stable key (`:342-349`).

**ACT (gated)** — the researcher hands work to gated mechanisms; it does not poke
live params directly:
- `daily_cycle` runs `edge_discovery.sweep_all(symbols, persist=True)` (`:453-457`).
- `lock_in_pattern` (`:68`) applies an exit config only if the pattern optimizer's
  PF/sample gate passed, then lets the #27 checkpointer verify/revert.
- `measure_excursion` (`:114`) derives `suggested_sl_atr`/`tp_rr` from real MFE/MAE.
- `robust_optimise` (`:187`) applies a full-confluence config **only if it passes a
  majority of random windows** (`pass_rate ≥ 0.6`, `:203`).

**REFLECT** — every finding/lock/excursion/robust result is written to the
KnowledgeStore (`ks.remember`) so learning compounds and failed directions are not
retried.

### Grounding thresholds per symbol
`profile_indicator_scale` (`:272`) measures per-symbol indicator SCALE (ATR as % of
price, `|OsMA|/ATR`) so thresholds are calibrated per instrument rather than assumed.

### Auto-filing GitHub issues (`:356-405`)
- `_gh_available()` checks for the `gh` CLI.
- `_existing_issue_titles()` lists open issues (`gh issue list … --json title`).
- `file_issue()` **dedupes** on a 40-char title-prefix overlap before
  `gh issue create` (`:382-385`).
- **Trigger:** in `daily_cycle`, when a symbol has ≥ 30 recent trades **and negative
  expectancy** (`:440-450`), it files `"[researcher] <SYM> negative expectancy over
  N trades — investigate technique"`. (Issues #48/#49/#51 were filed exactly this
  way.)

Default repo: `martinsharkey/Langchain` (`:45`).

---

## 2. Performance Researcher (`src/learning/performance_researcher.py`)

Analyzes the bot's **own** closed trades (not the market). `analyze()` (`:43`)
requires ≥ 8 closed trades, aggregates by symbol / management variant / market
regime / direction (min sample 4 to rank), and emits **actionable recommendations**:
direction imbalance, the bleeding worst symbol, the best management variant to
weight toward, and good/bad regimes. Results persist to the KnowledgeBase under
topic `self_performance`. Called on cadence at `scalp_engine.py:762`.

---

## 3. Edge Discovery (`src/learning/edge_discovery.py`) — the overlay writer

Replaces hand-edited edge tables with a runtime walk-forward sweep.

**Isolate one strategy×regime** — `_walkforward_single` (`:60`) temporarily patches
`edge_weights.focused_rules` to a single pocket, runs the **same**
`walkforward_focused` backtest used by live tuning, then restores it.

**The gate** — `sweep_symbol` (`:79`) keeps a pocket only if it **generalizes across
all windows AND its robust (min-window) PF ≥ `min_pf` (1.15)** (`:93-97`). Edge
weight scales with proven PF: `1.0 + (best_pf − 1.0)·2`, capped at 2.5.

**Write the overlay** — `sweep_all` (`:129`) builds
`{edge_weights, regime_edge, focused_edge, meta}` keyed by 6-char symbol prefix and
atomically writes `data/edge_weights.json`, then hot-reloads it into the live engine
(`ew.reload_overlay()`, `:155-165`) — no restart needed. An empty focused entry
means "no validated edge → fall back to the weighted ensemble." Findings are written
to the KnowledgeStore.

---

## How research reaches live trading

```
recent trades ─▶ REVIEW ─▶ mql5 RAG query ─▶ HYPOTHESIS ─▶ GATE ─▶ apply/keep
   (exclude SIMULATED_OHLC)                                  │
                                                             ├─ edge_discovery walk-forward → edge_weights.json overlay (hot-reload)
                                                             ├─ pattern/excursion lock → exit config (checkpointer verifies)
                                                             ├─ robust_optimise (≥60% windows) → full config
                                                             └─ file GitHub issue (n≥30 & expectancy<0)
```

Every gate uses the **generalizes + robust min-window PF** rule, and every training/
analysis read excludes `SIMULATED_OHLC` provenance. See `LEARNING_LOOPS.md` for how
the checkpointer then keeps, reverts, or demotes what the researcher applied.

## Files
- `src/learning/continual_researcher.py` — daily ReAct loop, mql5 grounding, auto-issues
- `src/learning/performance_researcher.py` — inward self-analysis
- `src/learning/edge_discovery.py` — walk-forward sweep → `data/edge_weights.json`
- `src/learning/mql5_knowledge.py` — offline mql5 RAG the researcher queries
