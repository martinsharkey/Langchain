# Symbol Onboarding & Floor Auto-Tuning

> Canonical process (2026-08-13) for adding a tradable symbol and keeping each
> symbol above the target win rate. This is AUTOMATED — do not hand-tune per symbol.

## The proven strategy (what every symbol uses)

**Entry — strict directional alignment (immutable):**
- LONG: OsMA **> 0** AND Bulls **> 0** AND Bears **> 0** (all above the per-symbol floor)
- SHORT: OsMA **< 0** AND Bulls **< 0** AND Bears **< 0** (all below the per-symbol ceiling)
- The DOMINANT power carries the strong floor (Bulls for long, Bears for short); the
  secondary power carries a smaller floor but must still be correctly signed.
- Direction can NEVER be reversed by any tuning. Enforced in
  `src/strategies/confluence_signal.py` via `alignment_floors.directional_gate`.

**Exit — wide SL + break-even + trailing, NO fixed take-profit:**
- A fixed TP caps winners and makes "let runners run" impossible, so there is NO TP.
- WIDE broker-side SL (room to breathe so entries aren't wicked out).
- Move to BREAK-EVEN at a profit trigger; TRAIL activates at a further threshold, then
  follows a fixed point distance behind the peak.
- Fixed-point geometry beats ATR-scaled (validated: PF 1.23 vs 0.96 on gold).
- Config: `SCALP_SL_MIN_POINTS_BY_SYMBOL`, `SCALP_BE_TRIGGER_POINTS_BY_SYMBOL`,
  `SCALP_TRAIL_ACTIVATE_POINTS_BY_SYMBOL`, `SCALP_TRAIL_POINTS_BY_SYMBOL`.

## Proven per-symbol baselines (owner NotebookLM / telemetry, 2026-08-13)

| | XAUUSD LONG | XAUUSD SHORT | BTCUSD LONG | BTCUSD SHORT |
|---|---|---|---|---|
| OsMA | ≥ 0.30 | ≤ −0.35 | ≥ 2.80 | ≤ −1.35 |
| Bulls | ≥ 2.40 | ≤ −0.50 | ≥ 12.70 | ≤ −0.50 |
| Bears | ≥ 0.60 | ≤ −1.30 | ≥ 0.50 | ≤ −13.00 |
| Exit SL / BE / trail-act / trail (pts) | 500 / 150 / 250 / 150 | | 8000 / 800 / — / 1000 | |

Source of truth: `src/strategies/alignment_floors.py` (`_BASELINES`) and
`src/learning/golden_baseline.py` (`GOLDEN`). BTC point magnitudes are ~15× gold.

**Validated results (multi-week, be_trail exit):**
- XAUUSD: **79.1% WR**, PF 1.39, 12.6 trades/week over 7.2 weeks.
- BTCUSD: **85.4% WR**, PF 1.52, 19.3 trades/week over 5.0 weeks.

## Validation method (why the old backtest was wrong)

- Validate over a **MULTI-WEEK** window (≥ 1 week; default ~5–7 weeks of M1). The old
  harness judged on ~2.8-day windows and required ≥15 trades PER window — this wrongly
  rejected high-quality, low-frequency strategies. There is **no per-window
  min-trade gate**; a strategy doing 15–20 trades/week at >70% is a VALID result.
- Auto-escalation principle (owner): **higher indicator floors → higher entry
  quality.** If WR < target, raise LONG floors (+step) and lower SHORT ceilings
  (−step) and re-test until WR ≥ target or entries dry up.
- Implemented once in `src/learning/floor_validator.py::discover_high_quality_floors`
  and reused by both the researcher and onboarding (single source of truth).

## Automated onboarding process (new symbol)

```
python tools/onboard_symbol.py <SYMBOL>            # dry run: validate + report
python tools/onboard_symbol.py <SYMBOL> --promote  # validate + persist floors + enable
```

Steps the tool performs (`tools/onboard_symbol.py`):
1. **Seed** baseline floors (from telemetry/winners; directional-safe default otherwise).
2. **Validate + auto-escalate** over multi-week data to reach the target WR.
3. **Promote** if a ≥ target level is found: persist floors via
   `alignment_floors.propose_rebaseline` (can only tighten, never reverse) + remove
   from `DISABLED_SYMBOLS`. Otherwise the symbol stays DISABLED with a report.
4. Set the symbol's **exit geometry** (wide SL/BE/trail, scaled to its point size).

## Live self-tuning (the bot holds ≥ target WR on its own)

- The researcher runs `revalidate_floors(symbol)` on a slow cadence
  (`FLOOR_REVALIDATE_CYCLES`, target `FLOOR_TARGET_WR`, default 70%). It re-validates
  each symbol over the multi-week window and, if WR has slipped below target,
  auto-escalates the floors and persists them (tighten-only).
- Frozen while `MANUAL_TUNING_LOCK=true` (owner hand-tuning). Set it `false` to let
  the bot self-tune.

## Safety guarantees

- **Directional alignment** is immutable — no tuning/XGBoost/revert can flip a floor's sign.
- **Tuning is stricter-only** — longs move up, shorts move down; `clamp_floors` blocks
  any move back toward zero below the baseline.
- **Frequency-starvation** falls back to the **golden baseline** (proven, trades),
  never a weak "last-firing" config (`_revert_to_last_firing`).
- **Manual lock** (`MANUAL_TUNING_LOCK`) freezes all auto-tuning for owner control.
