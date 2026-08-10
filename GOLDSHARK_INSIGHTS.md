# Insights from the GoldShark MT5 EAs (why they failed live)

Source: MT5_OLD_EA's/ (GoldShark3 v3.04/3.05, GoldShark9/11/12/14/15, optimizer
archives). Reviewed to (a) reuse the genuinely good ideas and (b) avoid the traps
that made them blow up live despite great backtests.

## The core (reusable) idea — GoldShark3 v3.04, the cleanest version
Multi-timeframe OsMA zero-cross momentum-reversal on gold:
  * M1 OsMA zero-cross = final entry TRIGGER; M5/M15/M30/H1 OsMA sign ARMS the
    direction (higher TF must agree). -> exactly the MTF-MACD idea we value.
  * Bulls/Bears Power VALUE thresholds with CORRECT zero-line logic:
    LONG needs Bears >= +ve (neutralised in uptrend), SHORT needs Bulls <= -ve.
    (matches the zero-line math we already encoded — validation that it's right.)
  * EMA trend + price "room to move" (not overextended) + ATR-in-band & rising.
  * "Momentum infancy / freshness": only enter when OsMA JUST crossed (fresh),
    not stale. Their own ML analysis: OsMA ACCELERATION correlates -0.68 with
    drawdown vs -0.07 for raw level. => acceleration/signal-age are the real edge.

## Why they FAILED LIVE (the expensive lessons)
1. MARTINGALE/PYRAMIDING/BASKET-HEDGING manufactured a fake ~100% win rate by
   holding losers (up to 35-46 stacked legs) until recovery, with stops of
   15,000-67,000 points (effectively no stop). One non-recovering trade = wipeout.
   This is the #1 reason great backtests died live.
2. OVER-OPTIMISATION: optimizer "winners" showed Profit Factor 151-378 on 3-33
   trades, Sharpe 42, with the STOP LOSS and MAX DRAWDOWN themselves optimized to
   absurd values (removing risk controls to inflate profit). Extreme fitted
   periods (EMA 123, OsMA 72-131-79) tuned to a 3-day window.
3. Even the ROBUST cluster (v3.05: 524 passes top-quartile on BOTH back AND
   forward) only had Back-vs-Forward correlation ~0.54 and still overshot its 4%
   drawdown kill-switch by ~3x. => even walk-forward-validated params only ~half
   transfer to live; costs/slippage erode a thin gold M1 edge (trades peak ~6-7
   min, where spread+commission dominate).

## How OUR bot already avoids these traps (and what to carry over)
AVOID (confirmed anti-patterns — never add):
  * No martingale / pyramiding into losers / basket hedging.
  * Never optimize SL or drawdown limits as free params (we only tune signal
    params; risk rules are fixed).
  * Reject too-good metrics: enforce MIN TRADE COUNT + walk-forward (we do).
  * Fixed-fractional risk sized off the stop, not balance-scaled compounding.

CARRY OVER (test in our walk-forward framework):
  * MTF OsMA/MACD agreement as a direction ARM + higher-TF regime gate
    (we have MTF alignment; add M30/H1 arming for BTC — post-mortem now uses
    M15/M30/H1 for crypto).
  * Momentum ACCELERATION + signal-age as features (their strongest predictor).
  * "Room to move" / price-stretch guard: reject entries already >2 ATR extended
    (our post-mortem already detects 'entered late / extended' as a failure mode).
  * Volatility-expansion gate (ATR in-band AND rising).
  * Early profit protection matters more than entry precision for fast scalps
    (our giveback/BE + payoff-RR work targets this).

## Bottom line
GoldShark proves the THESIS behind this whole project: the EA entry idea was
sound, but MT5 EAs failed live because of martingale risk architecture +
over-fitted backtests with no honest out-of-sample discipline. Our bot keeps the
good features, hard-bans the risk traps, and gates every change behind
walk-forward validation with minimum-sample + realistic-cost checks — which is
exactly why an AI loop can succeed where the EA didn't.
