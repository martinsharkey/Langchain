# QMMP Onboarding — BTCUSD

## Stage 1: REAL cost model (spread + slippage + commission)
  point=0.01  GBP/pt/0.01=0.000100  spread=1200pt  slippage=100pt/fill  comm=$6.0/lot
  round-turn cost/leg (0.01) = GBP 0.1800

## Stage 2-6: per-timeframe DATA-DRIVEN eval (M1 first) — 70/30 backtest/forward, £5000 base, £50/0.01 compounding+pyramiding
  M1: cyc=4381 mc= 1.9x win= 22%  BACKTEST £5000->£1,605 (-68%, 31d)  FORWARD £5000->£2,316 (-54%, ann -100%, DD 54%, 14d)
  M5: cyc=2239 mc= 6.8x win= 55%  BACKTEST £5000->£20,423 (+308%, 85d)  FORWARD £5000->£5,752 (+15%, ann +325%, DD 6%, 35d)
  M15: cyc= 901 mc=17.4x win= 63%  BACKTEST £5000->£13,928 (+179%, 84d)  FORWARD £5000->£5,879 (+18%, ann +424%, DD 3%, 36d)
  M30: cyc= 459 mc=27.1x win= 69%  BACKTEST £5000->£9,308 (+86%, 81d)  FORWARD £5000->£5,757 (+15%, ann +274%, DD 3%, 39d)
  H1: cyc=1158 mc=41.0x win= 86%  BACKTEST £5000->£2,002,577 (+39952%, 485d)  FORWARD £5000->£47,890 (+858%, ann +4435%, DD 6%, 216d)
  H4: cyc= 409 mc=83.7x win= 89%  BACKTEST £5000->£134,484 (+2590%, 610d)  FORWARD £5000->£19,691 (+294%, ann +469%, DD 2%, 288d)

  -> CHOSEN TIMEFRAME (best FORWARD-TEST compounded return): H1
     forward £5000 -> £47,890 (+858% over 216d, annualized +4435%, maxDD 6%), win 86%, 1158 cycles

## Stage 6: Per-session performance on H1 (1158 cycles)
  Asian    n= 372 win  82% net GBP    +481 /trade +1.293
  London   n= 206 win  86% net GBP    +238 /trade +1.155
  NewYork  n= 457 win  88% net GBP   +1055 /trade +2.308

## Stage 7: Per-indicator floor discovery (kept only if raises net OOS, walk-forward)
  osma_mag : helps 2/2 folds -> KEEP
  ema_align: helps 2/2 folds -> KEEP
  bulls    : helps 2/2 folds -> KEEP
  bears    : helps 0/2 folds -> OFF
  atr      : helps 2/2 folds -> KEEP

## Stage 8: Exit config (from winners' movement on H1): {'sl': 628348, 'be': 11057, 'trail': 11057, 'add': 11057, 'early': 0.15, 'max_legs': 4}

## Overall (H1, real cost): cycles 1158 win 86% net GBP+2003 /trade +1.729