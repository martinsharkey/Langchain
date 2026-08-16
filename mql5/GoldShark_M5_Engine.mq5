//+------------------------------------------------------------------+
//|                                     GoldShark_M5_Engine.mq5       |
//| ================================================================ |
//| CORRECTED build: entry gate on M1 per design. Indicator gates are |
//| FLOORS ONLY (no ceilings/pockets): ATR floor 1.4, OsMA/Bulls/Bears |
//| directional sign+floor gates, EMA13 trend.                        |
//|                                                                  |
//| ENTRY: v9.06 gate (EMA13 trend, ATR floor 1.4 (no cap),          |
//|        Bulls/Bears/OsMA sign gates)                              |
//| EXIT:  v13 dynamic peak trailing (MFE 20 activate, 50/30 runner) |
//|        + dead-money time decay + 400pt hard stop                 |
//|        + HTF 3-indicator exhaustion matrix (>=2 of 3)            |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026"
#property version   "2.00"
#property strict

#include <Trade\Trade.mqh>
CTrade trade;

//--- 0. GENERAL ---
input group "=== GENERAL ==="
input long   InpMagic          = 950705;       // Magic number
input double InpLots           = 0.01;         // Fixed lot size
input ENUM_TIMEFRAMES InpEntryTF = PERIOD_M1;  // Entry timeframe (M1 = design)
input ENUM_TIMEFRAMES InpExitTF  = PERIOD_M5;  // Exhaustion-matrix timeframe

//--- 1. ENTRY INPUTS (v9.06 gate) ---
input group "=== ENTRY: GATE THRESHOLDS ==="
input int    InpEMAPeriod     = 13;
input double InpMinATR        = 1.40;   // ATR floor (price units) - per design (floor only)

input double InpLongBullsMin  = 1.00;   // LONG: Bulls >= 1.0
input double InpLongBearsMin  = -1.00;  // LONG: Bears > -1.0 (anti tug-of-war)
input double InpMinOsMALong   = 0.00;   // LONG: OsMA >= 0.0

input double InpShortBearsMax = -1.00;  // SHORT: Bears <= -1.0
input double InpShortBullsMin = -1.00;  // SHORT: Bulls > -1.0 (anti tug-of-war)
input double InpMaxOsMAShort  = 0.00;   // SHORT: OsMA <= 0.0

//--- 2. EXIT INPUTS (v13) ---
input group "=== EXIT: DYNAMIC PEAK TRACKING (v13) ==="
input double InpMfeActivationPts   = 20.0;   // Pts to activate trailing
input double InpMfeRunnerThreshold = 50.0;   // Pts to classify as "Runner"
input double InpScalpTrailPts      = 15.0;   // Trail distance for scalps
input double InpRunnerTrailPts     = 30.0;   // Trail distance for runners
input double InpBreakEvenArmPts    = 20.0;   // MFE pts to ARM break-even lock (0=off)
input double InpBreakEvenLockPts   = 2.0;    // Pts above entry to lock once armed
input int    InpTimeDecayMins      = 90;     // Dead-money decay timer (minutes)
input double InpHardStopLossPts    = 400.0;  // Hard stop (points)
input bool   InpUseExhaustion      = true;   // Use HTF exhaustion exit

//--- GLOBAL STATE & HANDLES ---
int handleEMA, handleBulls, handleBears, handleOsMA, handleATR;
int handleEMA_H, handleBulls_H, handleBears_H, handleMACD_H;
ulong  liveTicket = 0;
double highestPrice = 0.0, lowestPrice = 0.0, virtualEntryPrice = 0.0;
datetime virtualEntryTime = 0;
double activeStopPrice = 0.0;

//+------------------------------------------------------------------+
int OnInit()
{
    trade.SetExpertMagicNumber(InpMagic);

    handleEMA   = iMA(_Symbol, InpEntryTF, InpEMAPeriod, 0, MODE_EMA, PRICE_CLOSE);
    handleBulls = iBullsPower(_Symbol, InpEntryTF, InpEMAPeriod);
    handleBears = iBearsPower(_Symbol, InpEntryTF, InpEMAPeriod);
    handleOsMA  = iOsMA(_Symbol, InpEntryTF, 12, 26, 9, PRICE_CLOSE);
    handleATR   = iATR(_Symbol, InpEntryTF, 14);

    handleEMA_H   = iMA(_Symbol, InpExitTF, InpEMAPeriod, 0, MODE_EMA, PRICE_CLOSE);
    handleBulls_H = iBullsPower(_Symbol, InpExitTF, InpEMAPeriod);
    handleBears_H = iBearsPower(_Symbol, InpExitTF, InpEMAPeriod);
    handleMACD_H  = iMACD(_Symbol, InpExitTF, 12, 26, 9, PRICE_CLOSE);

    if(handleEMA==INVALID_HANDLE || handleOsMA==INVALID_HANDLE || handleATR==INVALID_HANDLE ||
       handleBulls==INVALID_HANDLE || handleBears==INVALID_HANDLE ||
       handleMACD_H==INVALID_HANDLE)
    {
        Print("GoldShark M5: indicator handle init failed");
        return INIT_FAILED;
    }

    // Recover an existing position on restart
    if(PositionSelect(_Symbol) && PositionGetInteger(POSITION_MAGIC)==InpMagic)
    {
        liveTicket        = (ulong)PositionGetInteger(POSITION_TICKET);
        virtualEntryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
        highestPrice      = virtualEntryPrice;
        lowestPrice       = virtualEntryPrice;
        virtualEntryTime  = (datetime)PositionGetInteger(POSITION_TIME);
        activeStopPrice   = PositionGetDouble(POSITION_SL);
    }

    Print("GoldShark M5 Engine online: entry=", EnumToString(InpEntryTF),
          " exhaustion=", EnumToString(InpExitTF));
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnTick()
{
    if(PositionSelectByTicket(liveTicket) && PositionGetInteger(POSITION_MAGIC)==InpMagic)
    {
        ManageExits();
        return;
    }
    else
    {
        liveTicket = 0;
    }

    // one evaluation per new entry-TF candle
    static datetime lastCandleTime = 0;
    datetime currentCandle = iTime(_Symbol, InpEntryTF, 0);
    if(currentCandle == lastCandleTime) return;
    lastCandleTime = currentCandle;

    EvaluateEntry();
}

//+------------------------------------------------------------------+
//| ENTRY LOGIC (uses last CLOSED bar = index 1)                     |
//+------------------------------------------------------------------+
void EvaluateEntry()
{
    double ema[], osma[], bulls[], bears[], atr[];
    ArraySetAsSeries(ema, true); ArraySetAsSeries(osma, true);
    ArraySetAsSeries(bulls, true); ArraySetAsSeries(bears, true); ArraySetAsSeries(atr, true);

    int need = 6;
    if(CopyBuffer(handleEMA,   0, 0, need, ema)   < need) return;
    if(CopyBuffer(handleOsMA,  0, 0, need, osma)  < need) return;
    if(CopyBuffer(handleBulls, 0, 0, need, bulls) < need) return;
    if(CopyBuffer(handleBears, 0, 0, need, bears) < need) return;
    if(CopyBuffer(handleATR,   0, 0, need, atr)   < need) return;

    // index 1 = last closed bar; index 2 = prior closed bar
    bool isEmaUp   = (ema[1] > ema[2]);
    bool isEmaDown = (ema[1] < ema[2]);

    // ATR floor only (no ceiling, per design).
    bool volOk = (atr[1] >= InpMinATR);

    if(!volOk) return;

    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

    if(isEmaUp &&
       bulls[1] >= InpLongBullsMin &&
       bears[1] >  InpLongBearsMin &&
       osma[1]  >= InpMinOsMALong)
    {
        ExecuteTrade(ORDER_TYPE_BUY, ask);
        return;
    }

    if(isEmaDown &&
       bears[1] <= InpShortBearsMax &&
       bulls[1] >  InpShortBullsMin &&
       osma[1]  <= InpMaxOsMAShort)
    {
        ExecuteTrade(ORDER_TYPE_SELL, bid);
        return;
    }
}

//+------------------------------------------------------------------+
//| EXIT LOGIC (v13)                                                 |
//+------------------------------------------------------------------+
void ManageExits()
{
    double pt = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
    long   type = PositionGetInteger(POSITION_TYPE);
    double curPrice = (type==POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                                : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

    if(type==POSITION_TYPE_BUY)
    {
        if(curPrice > highestPrice) highestPrice = curPrice;
        if(lowestPrice==0.0 || curPrice < lowestPrice) lowestPrice = curPrice;
    }
    else
    {
        if(lowestPrice==0.0 || curPrice < lowestPrice) lowestPrice = curPrice;
        if(highestPrice==0.0 || curPrice > highestPrice) highestPrice = curPrice;
    }

    double mfePts = (type==POSITION_TYPE_BUY) ? (highestPrice - virtualEntryPrice)/pt
                                              : (virtualEntryPrice - lowestPrice)/pt;
    double curPts = (type==POSITION_TYPE_BUY) ? (curPrice - virtualEntryPrice)/pt
                                              : (virtualEntryPrice - curPrice)/pt;
    int ageMin = (int)((TimeCurrent() - virtualEntryTime)/60);

    // PHASE 1: hard stop + dead-money decay
    if(curPts <= -InpHardStopLossPts)
    { trade.PositionClose(liveTicket); liveTicket=0; return; }

    if(ageMin > InpTimeDecayMins && mfePts < InpMfeActivationPts && curPts < 10.0)
    { trade.PositionClose(liveTicket); liveTicket=0; return; }

    // PHASE 1b: BREAK-EVEN LOCK (evidence: 306 live losers went >=20pt green then reversed).
    // Once MFE arms, lock SL at entry+lock so a green trade can't become a full loss.
    double beLevel = 0.0;
    if(InpBreakEvenArmPts > 0.0 && mfePts >= InpBreakEvenArmPts)
    {
        beLevel = (type==POSITION_TYPE_BUY)
                  ? NormalizeDouble(virtualEntryPrice + InpBreakEvenLockPts*pt, _Digits)
                  : NormalizeDouble(virtualEntryPrice - InpBreakEvenLockPts*pt, _Digits);
        bool beUpd = (activeStopPrice==0.0)
                     || (type==POSITION_TYPE_BUY  && beLevel > activeStopPrice)
                     || (type==POSITION_TYPE_SELL && beLevel < activeStopPrice);
        if(beUpd)
        {
            activeStopPrice = beLevel;
            trade.PositionModify(liveTicket, activeStopPrice, 0.0);
        }
    }

    // PHASE 2: 50/30 dynamic peak trailing (never regresses below the BE lock)
    if(mfePts >= InpMfeActivationPts)
    {
        double trailDist = (mfePts < InpMfeRunnerThreshold) ? InpScalpTrailPts : InpRunnerTrailPts;
        double trailSL = (type==POSITION_TYPE_BUY)
                         ? NormalizeDouble(curPrice - trailDist*pt, _Digits)
                         : NormalizeDouble(curPrice + trailDist*pt, _Digits);
        // clamp trail so it never sits worse than the armed break-even lock
        if(beLevel != 0.0)
        {
            if(type==POSITION_TYPE_BUY  && trailSL < beLevel) trailSL = beLevel;
            if(type==POSITION_TYPE_SELL && trailSL > beLevel) trailSL = beLevel;
        }
        bool upd = (activeStopPrice==0.0)
                   || (type==POSITION_TYPE_BUY  && trailSL > activeStopPrice)
                   || (type==POSITION_TYPE_SELL && trailSL < activeStopPrice);
        if(upd)
        {
            activeStopPrice = trailSL;
            trade.PositionModify(liveTicket, activeStopPrice, 0.0);
        }
    }

    // PHASE 3: HTF exhaustion matrix
    if(InpUseExhaustion && CheckTrendExhaustion(type))
    { trade.PositionClose(liveTicket); liveTicket=0; return; }
}

//+------------------------------------------------------------------+
//| HTF 3-INDICATOR EXHAUSTION MATRIX (>=2 of 3)                     |
//+------------------------------------------------------------------+
bool CheckTrendExhaustion(long positionType)
{
    double macdMain[], macdSig[], emaH[], bullsH[], bearsH[];
    ArraySetAsSeries(macdMain, true); ArraySetAsSeries(macdSig, true);
    ArraySetAsSeries(emaH, true); ArraySetAsSeries(bullsH, true); ArraySetAsSeries(bearsH, true);

    if(CopyBuffer(handleMACD_H, 0, 0, 5, macdMain) < 5) return false;
    if(CopyBuffer(handleMACD_H, 1, 0, 5, macdSig)  < 5) return false;
    if(CopyBuffer(handleEMA_H,  0, 0, 5, emaH)     < 5) return false;
    if(CopyBuffer(handleBulls_H,0, 0, 5, bullsH)   < 5) return false;
    if(CopyBuffer(handleBears_H,0, 0, 5, bearsH)   < 5) return false;

    // avg EMA slope over last 3 closed bars
    double slope = ((emaH[1]-emaH[2]) + (emaH[2]-emaH[3]) + (emaH[3]-emaH[4]))/3.0;
    int cnt = 0;

    if(positionType==POSITION_TYPE_BUY)
    {
        if(macdMain[1] < macdSig[1] && macdMain[2] >= macdSig[2]) cnt++;
        else if(macdMain[1] < macdMain[2] && macdMain[2] < macdMain[3]) cnt++;
        if(slope <= 0.02) cnt++;
        if(bullsH[1] < 0 || (bullsH[1] < bullsH[2] && bullsH[2] < bullsH[3])) cnt++;
    }
    else
    {
        if(macdMain[1] > macdSig[1] && macdMain[2] <= macdSig[2]) cnt++;
        else if(macdMain[1] > macdMain[2] && macdMain[2] > macdMain[3]) cnt++;
        if(slope >= -0.02) cnt++;
        if(bearsH[1] > 0 || (bearsH[1] > bearsH[2] && bearsH[2] > bearsH[3])) cnt++;
    }
    return (cnt >= 2);
}

//+------------------------------------------------------------------+
//| EXECUTION HELPER                                                 |
//+------------------------------------------------------------------+
void ExecuteTrade(ENUM_ORDER_TYPE type, double price)
{
    bool ok = (type==ORDER_TYPE_BUY) ? trade.Buy(InpLots, _Symbol)
                                     : trade.Sell(InpLots, _Symbol);
    if(ok && trade.ResultRetcode()==TRADE_RETCODE_DONE)
    {
        liveTicket        = trade.ResultOrder();
        // resolve real fill price if available
        if(PositionSelectByTicket(liveTicket))
            virtualEntryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
        else
            virtualEntryPrice = price;
        highestPrice     = virtualEntryPrice;
        lowestPrice      = virtualEntryPrice;
        virtualEntryTime = TimeCurrent();
        activeStopPrice  = 0.0;
    }
    else
    {
        Print("Order failed: retcode=", trade.ResultRetcode(), " ", trade.ResultRetcodeDescription());
    }
}
//+------------------------------------------------------------------+
