# Confluence Entry Strategy — How It Works

> The single live entry strategy is **`OsMA_Confluence`**. This document explains
> exactly what it measures, what it tunes, what it adjusts, and — importantly — the
> deliberate Bulls/Bears Power sign logic that AI code generators keep trying to
> "fix" back into a bug.

## Single source of truth

There is **one** rule set, `src/strategies/confluence_signal.py`, consumed two ways:

- **Live:** `src/strategies/osma_confluence.py::osma_confluence_signal()` builds a
  single-bar snapshot and calls `evaluate_confluence_bar()`
  (`confluence_signal.py:107`).
- **Backtest:** `find_confluence_triggers()` (`confluence_signal.py:153`) runs the
  identical logic across an M1 series with the full MACD-lead window.

Both share `_soft_checks()` (`confluence_signal.py:78`), so backtest == live. A
guardrail test (`tests/test_confluence_unified.py`) asserts the live adapter only
*delegates* and never re-implements the rules.

---

## The seven indicators — what we MEASURE

All math is in `src/strategies/indicators.py`. Periods flow from `DEFAULT_CFG`
(`confluence_signal.py:27-38`).

| Indicator | Formula | Default period | Source |
|---|---|---|---|
| **EMA (trend)** | `close.ewm(span=p)` | 50 (`ema_period`) | `indicators.py:41` |
| **MACD line** | `EMA(close,12) − EMA(close,26)` | 12/26 | `indicators.py:93-95` |
| **OsMA** | `MACD_line − signal(9)` (= MACD histogram) | 12/26/9 | `indicators.py:315-318` |
| **ATR** | mean of TrueRange | 14 (`atr_period`) | `indicators.py:141-146` |
| **RSI** | Wilder-smoothed | 14 (`rsi_period`) | `indicators.py:46-72` |
| **Bulls Power** | `High − EMA(13)` | 13 (`power_period`) | `indicators.py:305` |
| **Bears Power** | `Low − EMA(13)` | 13 (`power_period`) | `indicators.py:311` |

Note the Bulls/Bears EMA (period 13) is a **separate** EMA from the trend EMA
(period 50).

---

## The entry decision — order of operations

Direction is decided **only** by the OsMA trigger; everything after it either
confirms or vetoes — nothing can flip the direction.

### 1. OsMA zero-cross trigger (sets direction) — `confluence_signal.py:174-187`

- **Confirmed cross up (`cu`):** prev OsMA ≤ 0 and current > 0 → candidate **buy**.
- **Confirmed cross down (`cd`):** prev ≥ 0 and current < 0 → candidate **sell**.
- **Anticipated up (`au`):** not yet crossed, OsMA in `−band…0` and *rising*.
- **Anticipated down (`ad`):** not yet crossed, OsMA in `0…band` and *falling*.
- `band = osma_anticipate_atr × ATR`, default `0.15 × ATR`.

`direction = "buy" if (cu or au) else "sell"`; `trigger_kind = "cross"` (confirmed)
or `"anticipated"`. Anticipated triggers are kept but scored as lower conviction
(below) and tracked separately so the learning loop can compare them.

### 2. MACD must LEAD (hard) — `confluence_signal.py:188-197`

Within the last `macd_lead_bars` (default **5**) bars, the **MACD line itself must
have crossed the zero line in the same direction**. "MACD leads OsMA" means the
momentum (MACD) turned first and the OsMA cross confirms it. In the live single-bar
path (which cannot see the window) this falls back to MACD *alignment*
(`osma_confluence.py:19-21`, `confluence_signal.py:134-137`).

### 3. Hard gates (all must pass) — `confluence_signal.py:198-203`

| Gate | Condition |
|---|---|
| MACD aligned | buy: `macd_line > 0`; sell: `macd_line < 0` (side of **zero**, not signal line) |
| ATR expanding | `atr > atr_prev` (volatility must be opening up) |
| (live) valid bar | `atr > 0 and close > 0` |

If any hard gate fails → **hold** (no partial credit).

### 4. Soft confirmations (need ≥ `min_confluence` of 5) — `_soft_checks`, `:78-104`

For a **buy** (mirror for sell):

| # | Soft check | Condition (buy) | Tunable |
|---|---|---|---|
| S1 | EMA trend + price side | `(ema − ema_prev) ≥ min_ema_slope·atr` AND `close > ema` | `min_ema_slope` |
| S2 | ATR in range (+ rel. floor) | not below `atr_min_rel·med_atr`, within `atr_min…atr_max` | `atr_min/atr_max` |
| S3 | Price not over-stretched | `abs(close − ema) ≤ price_stretch_mult·atr` | `price_stretch_mult` |
| S4 | Bulls/Bears control | **`bulls > 0 AND bears > 0`** (see below) | — |
| S5 | RSI not exhausted | `rsi < rsi_long_max` (72) | — |

Entry fires only if `sum(soft checks) ≥ min_confluence` (default **4/5**). The
relative-volatility floor (`atr_min_rel = 0.7 × median ATR`) is symbol-agnostic and
active from day one, so a symbol needs no per-symbol tuning to reject dead markets.

---

## Bulls Power & Bears Power — the direction logic that matters

**This is the most important and most misunderstood part.** See the guarded comment
at `indicators.py:284-301`.

```
Bulls Power = High − EMA(13)      Bears Power = Low − EMA(13)
```

Because Bulls uses the candle **High** and Bears uses the candle **Low**:

- **In a strong UPTREND**, the entire candle — *including its Low* — sits **above**
  the EMA. So `Bears Power = Low − EMA` becomes **POSITIVE**. This is normal and
  *confirms* strength; it does not mean bears are in control.
- **In a strong DOWNTREND**, the entire candle — *including its High* — sits
  **below** the EMA. So `Bulls Power = High − EMA` becomes **NEGATIVE**. Also
  normal, and confirms downside strength.

### Why this is a trap for AI generators

The legacy/textbook forex rule is "buy only when Bears Power < 0." Applied here that
would **block buys during the strongest part of an uptrend** (exactly when Bears
Power has gone positive). LLMs repeatedly "correct" the code back to that bug.

**The correct rules (do not flip):**

- **Live confluence S4** (`confluence_signal.py:95,102`): LONG requires
  `bulls > 0 AND bears > 0` (whole candle above the EMA); SHORT requires
  `bears < 0 AND bulls < 0` (whole candle below the EMA).
- **Retired reference** (`strategy_registry.py:588-598`, kept only as documented
  math, not registered): the *neutralised* form — LONG needs `bears >= 0.0`, SHORT
  needs `bulls <= 0.0`. The `>=`/`<=` operators are flagged `[CORRECT: >= not <]`.

Both encode the same idea ("in a strong uptrend both oscillators sit above zero");
the live check is the stricter of the two. Project memory key
`bulls_bears_power_logic` records this so it is not re-broken.

Similarly, MACD is checked against the **zero line**, never its signal line
(memory `macd_zero_line_not_signal`).

---

## Confidence — how conviction is scored

`osma_confluence.py:59-70`:

- **Base = confluence fraction** = `passed_soft_checks / 5`.
- **Confirmed cross:** `+0.15` (capped at 1.0).
- **Anticipated cross:** `× 0.85` (lower conviction, tracked separately).

Example: 4/5 + confirmed → `0.8 + 0.15 = 0.95`; 4/5 + anticipated → `0.68`. On a
hold, confidence is still surfaced as `confluence/5`. Registered with
`min_confidence=0.4`, `weight=1.5` (`osma_confluence.py:90-91`). Downstream, the
engine further adjusts this confidence with RAG patterns, the ONNX model, HTF
alignment, and operating-mode floors (see `LEARNING_LOOPS.md`).

---

## What we TUNE — the optimizer's PARAM_SPACE

`src/learning/param_optimizer.py:37-55`. Ranges are the authoritative mql5-doc
ranges, deliberately widened to reach the proven GoldShark cluster.

| Param | Range (lo,hi,step) | Default | Affects |
|---|---|---|---|
| `osma_fast` | 5–34, 1 | 12 | MACD/OsMA fast EMA |
| `osma_slow` | 20–144, 2 | 26 | MACD/OsMA slow EMA |
| `osma_signal` | 5–55, 1 | 9 | MACD signal → OsMA |
| `ema_period` | 3–200, 1 | 14* | trend EMA + Bulls/Bears base |
| `atr_period` | 5–50, 1 | 14 | ATR |
| `power_period` | 5–26, 1 | 13 | Bulls/Bears EMA |
| `rsi_period` | 2–30, 1 | 14 | RSI |
| `atr_min` / `atr_max` | 0–4 / 0–12 | 0 (off) | S2 absolute band |
| `min_ema_slope` | 0–0.5, 0.02 | 0.02 | S1 slope threshold |
| `price_stretch_mult` | 1–4, 0.5 | 2.0 | S3 stretch cap |
| `min_confluence` | 1–5, 1 | 4 | # soft checks required |
| `sl_atr` | 0.5–3.0, 0.5 | 2.0 | **exit** stop distance (ATR) |
| `tp_rr` | 0.5–3.0, 0.5 | 1.0 | **exit** reward:risk |

\* Two naming/default nuances to know: the optimizer default `ema_period=14` but the
confluence's own trend-EMA default is `50`; and the optimizer key `min_ema_slope`
maps to the confluence's `min_ema_slope_atr`. The optimizer only changes a param if
the walk-forward gate proves the new value generalizes (see `LEARNING_LOOPS.md`).

The optimizer keeps `osma_fast < osma_slow` (`param_optimizer.py:128-131`) and skips
any config the checkpointer has recorded as a failed direction.

---

## What we ADJUST live (not backtest tuning)

- **Exit `sl_atr`/`tp_rr`** can be overridden live by the researcher's
  excursion/pattern lock or the DynamicFixer (`_apply_exit_config`), separate from
  the tuned indicator params.
- **Edge weight / focused pocket** per symbol comes from the discovered overlay
  `data/edge_weights.json` (see `RESEARCHER.md`); XAUUSD and GER40 both point their
  focused pocket at `OsMA_Confluence`.

## Files

- `src/strategies/confluence_signal.py` — the rule set (measure + gates + soft checks)
- `src/strategies/osma_confluence.py` — live thin adapter + confidence
- `src/strategies/indicators.py` — indicator formulas + the Bulls/Bears guard comment
- `src/learning/param_optimizer.py` — PARAM_SPACE (what we tune)
