# QMMP Onboarding — XAUUSD

## Stage 1: REAL cost model (spread + slippage + commission)
  point=0.001  GBP/pt/0.01=0.000740  spread=260pt  slippage=100pt/fill  comm=$6.0/lot
  round-turn cost/leg (0.01) = GBP 0.2524

## Stage 2-6: per-timeframe DATA-DRIVEN eval (M1 first) — 70/30 backtest/forward, £5000 base, £50/0.01 compounding+pyramiding
  M1: cyc=2939 mc= 6.9x win= 49%  BACKTEST £5000->£12,410 (+148%, 31d)  FORWARD £5000->£10,185 (+104%, ann +1000000%, DD 5%, 14d)
  M5: cyc=1550 mc=19.0x win= 74%  BACKTEST £5000->£787,671 (+15653%, 84d)  FORWARD £5000->£28,455 (+469%, ann +1000000%, DD 8%, 35d)
  M15: cyc= 611 mc=31.7x win= 82%  BACKTEST £5000->£103,597 (+1972%, 84d)  FORWARD £5000->£13,174 (+163%, ann +1000000%, DD 4%, 38d)
  M30: cyc= 295 mc=33.5x win= 83%  BACKTEST £5000->£22,491 (+350%, 82d)  FORWARD £5000->£8,153 (+63%, ann +10074%, DD 1%, 39d)
  H1: cyc= 793 mc=46.5x win= 86%  BACKTEST £5000->£792,640 (+15753%, 479d)  FORWARD £5000->£981,427 (+19529%, ann +644306%, DD 3%, 220d)
  H4: cyc= 314 mc=91.2x win= 88%  BACKTEST £5000->£70,556 (+1311%, 638d)  FORWARD £5000->£86,288 (+1626%, ann +5688%, DD 6%, 256d)

  -> CHOSEN TIMEFRAME (best FORWARD-TEST compounded return): H1
     forward £5000 -> £981,427 (+19529% over 220d, annualized +644306%, maxDD 3%), win 86%, 793 cycles

## Stage 6: Per-session performance on H1 (793 cycles)
  Asian    n= 237 win  86% net GBP    +555 /trade +2.341
  London   n= 164 win  84% net GBP    +482 /trade +2.940
  NewYork  n= 312 win  90% net GBP    +951 /trade +3.049

## Stage 7: Per-indicator floor discovery (kept only if raises net OOS, walk-forward)
  osma_mag : helps 2/2 folds -> KEEP
  ema_align: helps 2/2 folds -> KEEP
  bulls    : helps 1/2 folds -> OFF
  bears    : helps 0/2 folds -> OFF
  atr      : helps 1/2 folds -> OFF

## Stage 8: Exit config (from winners' movement on H1): {'sl': 148200, 'be': 2376, 'trail': 2376, 'add': 2376, 'early': 0.15, 'max_legs': 4}

## Overall (H1, real cost): cycles 793 win 86% net GBP+2206 /trade +2.782

## Stage 9: Money-management on FORWARD (OOS) trades: n=238, 20 losers (8%), SL £109.7/0.01 leg
  [9a] starting-balance sweep (fixed £50/0.01, ruin-aware):
       £  100 -> £      19,777 (+19677%, DD 6%)
       £  500 -> £     121,003 (+24101%, DD 6%)
       £ 1000 -> £     250,643 (+24964%, DD 6%)
       £ 5000 -> £     981,427 (+19529%, DD 3%)
  [9b] £100 -> £100k dream: Monte Carlo P(target)/P(ruin) + adverse stress, per sizing:
                fixed £50: P(£100k)   0.5%  P(ruin)  0.0%  median £   19,605  | stress worst-first 18755  streak-ruin 0.0%
                fixed £25: P(£100k) 100.0%  P(ruin)  0.0%  median £  103,855  | stress worst-first 105093  streak-ruin 0.0%
         taper 10->25->50: P(£100k) 100.0%  P(ruin)  0.0%  median £  101,938  | stress worst-first 101387  streak-ruin 0.0%
                fixed £10: P(£100k) 100.0%  P(ruin)  0.0%  median £  109,021  | stress worst-first 100914  streak-ruin 0.0%
                 fixed £5: P(£100k) 100.0%  P(ruin)  0.0%  median £  110,603  | stress worst-first 157922  streak-ruin 0.0%
       -> lowest-risk viable-for-£100k schedule: fixed £25