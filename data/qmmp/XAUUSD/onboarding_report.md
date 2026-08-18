# QMMP Onboarding — XAUUSD

## Stage 1: REAL cost model (spread + slippage + commission)
  point=0.001  GBP/pt/0.01=0.000740  spread=200pt  slippage=100pt/fill  comm=$6.0/lot
  round-turn cost/leg (0.01) = GBP 0.2080

## Stage 2-6: per-timeframe DATA-DRIVEN eval (M1 first) — 70/30 backtest/forward, £5000 base, £50/0.01 compounding+pyramiding
  M1: cyc=2939 mc= 8.4x win= 54%  BACKTEST £5000->£19,565 (+291%, 31d)  FORWARD £5000->£12,384 (+148%, ann +1000000%, DD 5%, 14d)
  M5: cyc=1550 mc=23.0x win= 76%  BACKTEST £5000->£908,532 (+18071%, 84d)  FORWARD £5000->£31,577 (+532%, ann +1000000%, DD 8%, 35d)
  M15: cyc= 611 mc=38.5x win= 84%  BACKTEST £5000->£113,781 (+2176%, 84d)  FORWARD £5000->£13,726 (+175%, ann +1000000%, DD 4%, 38d)
  M30: cyc= 295 mc=40.7x win= 84%  BACKTEST £5000->£23,522 (+370%, 82d)  FORWARD £5000->£8,317 (+66%, ann +12193%, DD 1%, 39d)
  H1: cyc= 793 mc=56.4x win= 88%  BACKTEST £5000->£855,337 (+17007%, 479d)  FORWARD £5000->£1,008,241 (+20065%, ann +673818%, DD 3%, 220d)
  H4: cyc= 314 mc=110.7x win= 89%  BACKTEST £5000->£74,177 (+1384%, 638d)  FORWARD £5000->£88,074 (+1661%, ann +5859%, DD 6%, 256d)

  -> CHOSEN TIMEFRAME (best FORWARD-TEST compounded return): H1
     forward £5000 -> £1,008,241 (+20065% over 220d, annualized +673818%, maxDD 3%), win 88%, 793 cycles

## Stage 6: Per-session performance on H1 (793 cycles)
  Asian    n= 237 win  88% net GBP    +565 /trade +2.386
  London   n= 164 win  85% net GBP    +489 /trade +2.984
  NewYork  n= 312 win  92% net GBP    +965 /trade +3.093

## Stage 7: Per-indicator floor discovery (kept only if raises net OOS, walk-forward)
  osma_mag : helps 2/2 folds -> KEEP
  ema_align: helps 2/2 folds -> KEEP
  bulls    : helps 1/2 folds -> OFF
  bears    : helps 1/2 folds -> OFF
  atr      : helps 1/2 folds -> OFF

## Stage 8: Exit config (from winners' movement on H1): {'sl': 148200, 'be': 2376, 'trail': 2376, 'add': 2376, 'early': 0.15, 'max_legs': 4}

## Overall (H1, real cost): cycles 793 win 88% net GBP+2242 /trade +2.827

## Stage 9: Money-management on FORWARD (OOS) trades: n=238, 14 losers (6%), SL £109.7/0.01 leg
  [9a] starting-balance sweep (fixed £50/0.01, ruin-aware):
       £  100 -> £      21,199 (+21099%, DD 6%)
       £  500 -> £     129,244 (+25749%, DD 6%)
       £ 1000 -> £     264,870 (+26387%, DD 6%)
       £ 5000 -> £   1,008,241 (+20065%, DD 3%)
  [9b] £100 -> £100k dream: Monte Carlo P(target)/P(ruin) + adverse stress, per sizing:
                fixed £50: P(£100k)   0.5%  P(ruin)  0.0%  median £   20,556  | stress worst-first 19906  streak-ruin 0.0%
                fixed £25: P(£100k) 100.0%  P(ruin)  0.0%  median £  104,049  | stress worst-first 100561  streak-ruin 0.0%
         taper 10->25->50: P(£100k)  99.9%  P(ruin)  0.0%  median £  101,996  | stress worst-first 100012  streak-ruin 0.0%
                fixed £10: P(£100k) 100.0%  P(ruin)  0.0%  median £  108,490  | stress worst-first 107653  streak-ruin 0.0%
                 fixed £5: P(£100k) 100.0%  P(ruin)  0.0%  median £  109,365  | stress worst-first 107479  streak-ruin 0.0%
       -> lowest-risk viable-for-£100k schedule: fixed £25

WROTE C:\Users\MartinSharkey\Documents\Langchain\langchain\data\qmmp\XAUUSD\model.json + onboarding_report.md
## Stage 10: generated MT5 EA -> GoldShark_XAUUSD.mq5 (+ .set optimiser ranges, .params.json)
## Stage 11: EA VERIFICATION PASSED -- all EA inputs exactly match model.json