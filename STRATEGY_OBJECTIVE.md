# Strategy Objective & Robustness Framework

## The goal (honest framing)
The aspiration is to grow a small stake (~£250) substantially over ~6 months.
£250 -> £100k is a 400x return. At our current win rate (~35-53%) that target,
pursued directly, REQUIRES ruinous position sizing and guarantees eventual ruin.
So we do NOT optimise for 400x. We optimise for a PROVEN, ROBUST EDGE, then let
disciplined compounding take the account as far as a real edge allows. £100k is a
stretch outcome of compounding a validated edge — never the thing we size for.

Rule 0: **Survival first.** A strategy that can't blow up compounds; one that can
blow up eventually returns to zero regardless of interim gains.

## Success is measured in PHASES with hard gates
Each phase must be PASSED (on real closed trades) before the next unlocks. This
is enforced in code — sizing/compounding cannot escalate past the current phase.

### Phase 0 — Data integrity (PASSED)
- Real MT5 reconciliation, no phantom trades, dashboard == terminal.
- KPI: recorded P&L matches broker to the penny.

### Phase 1 — PROVE AN EDGE  (current phase; success = this)
- Objective: demonstrate positive expectancy that is not noise.
- GATE to advance:
    * >= 200 real closed trades
    * Profit Factor >= 1.3
    * Expectancy > 0 (positive average R per trade)
    * Max drawdown < 20% of peak equity
    * No single day losing > the daily-loss limit
- Sizing during Phase 1: FIXED tiny (0.01 lots). NO compounding.
- This is the real definition of "success" for now: a validated edge.

### Phase 2 — STABILISE
- Objective: edge holds out-of-sample and across >=3 symbols/regimes.
- GATE: Phase 1 metrics hold over a further 200 trades AND backtest agreement
  on held-out data; win rate & PF stable (not decaying).
- Sizing: fixed-fractional risk 1% per trade. Gentle compounding begins.

### Phase 3 — COMPOUND (controlled)
- Objective: grow the account while never risking ruin.
- Rules: fixed-fractional 1-2% risk; hard equity floor; auto de-risk to 0.5% risk
  after any 10% drawdown; halt for the day at the daily-loss limit.
- Success metric: CAGR with max drawdown < 25%. This is where account growth
  actually happens — only ever on a proven edge.

### Phase 4 — SCALE / LIVE
- Only after Phase 3 sustained. Move to a live account (with realistic
  spread/slippage modelling already in place). Re-validate — demo != live.

## Core KPIs (tracked continuously, on REAL closed trades)
- Profit Factor (gross win / gross loss) — target >= 1.3
- Expectancy in R (avg (win% * avgWin - loss% * avgLoss) / risk) — must be > 0
- Win rate & average win/loss ratio
- Max drawdown (% of peak) — the survival metric
- Longest losing streak (sanity-check sizing against it)
- Sharpe-like consistency (std of daily R)

## Robustness rules (non-negotiable, enforced in code)
1. Risk of ruin must stay negligible: position size derived from fixed-fractional
   risk, never from a growth target. (No martingale, no revenge sizing.)
2. Hard daily-loss halt + persisted kill switch (already built).
3. De-risk automatically on drawdown; never increase size to "catch up".
4. Every promotion (strategy, size, phase) gated by out-of-sample proof.
5. Demo results are treated as optimistic; a spread/slippage haircut is applied
   so we never trust clean demo fills as live-realistic.
6. The bot may be curious but must not gridlock: analysis paralysis is a failure
   mode — decisions are time-boxed, hold is a valid action, missing a trade is
   cheaper than a bad one.

## Why this still serves the £100k dream
A validated edge with PF 1.3 compounded at controlled risk is the ONLY path that
could ever reach a large number without blowing up first. If the edge is real,
compounding does the rest and we scale. If it isn't real yet, chasing 400x would
just have destroyed the £250 faster. Edge first is how you keep the dream alive.


## Prioritised learning pattern: MTF-MACD + OsMA timing + Bulls/Bears (trader spec)

Encode and PRIORITISE this observed methodology (to be learned/validated, not
blindly trusted):

1. MACD zero-line cross = directional momentum reversal trigger (esp. on M1).
2. MULTI-TIMEFRAME context boosts/reduces confidence:
   - If M1 MACD just reversed, but M5 MACD is about to reverse the OPPOSITE way
     and M15 is already deep into a counter pattern, the M1 move is unlikely to
     persist -> LOW confidence / avoid.
   - Aligned MTF MACD -> HIGH confidence.
3. After MACD reverses, read OsMA + Bulls/Bears Power for TIMING:
   - MACD just turned long + OsMA cycle weakening & about to cross zero =
     potential scalp setup. As OsMA BURSTS across zero, timing is everything.
   - Confirm: Bulls Power strong AND Bears Power pulled across zero to POSITIVE
     (remember: positive bears in an uptrend is NORMAL and CONFIRMS long).
4. EARLY ENTRY is the edge: look for the setup BEFORE the OsMA zero-burst �
   watch OsMA histogram for a declining pattern (for long reversal) / rising
   pattern (for short reversal) so entry is timed ahead of the crowd.
5. EMA direction + ATR activity are secondary confirmations. When ATR plummets
   it can signal a sellers' market, especially when MACD/OsMA/Bulls/Bears align.
6. Liquidity windows: the generic "avoid Asian session" advice is NOT reliably
   true for our instruments (empirically fine to trade). Treat session
   suitability as DATA-DRIVEN (learned per symbol from real outcomes), not a
   hardcoded rule.
7. Anti-gridlock: be curious but time-box the decision. Hold is valid; missing a
   trade is cheaper than a bad one. Do not stack so many confirmations that no
   trade ever qualifies.

Implementation status: Bulls/Bears Power + OsMA + MACD-zero confluence strategy
is built (MACD_OsMA_Power_Confluence, correct zero-line math). STILL TO BUILD:
the multi-timeframe MACD/OsMA agreement scorer and the early OsMA-histogram-slope
entry trigger (point 4) � these should become a high-weight learned pattern once
validated on the Jan-onward history via the backtester.
