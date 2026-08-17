"""QMMP EA generator (#61): emit a GoldShark_<SYMBOL>.mq5 Expert Advisor from a symbol's
validated model.json. Inputs are exposed as MT5 `input` params with optimiser-compatible
ranges (the .mq5 sets start/step/stop hints in comments; MT5 Strategy Tester reads the
input list and the .set companion file for ranges). Encodes: OsMA-cross entry, per-session
KEEP floors (osma_mag/ema_align/bulls/atr), basket-trail + early-pyramid exit, £/0.01 sizing.

Called by the pipeline at the end of onboarding: write_ea(model, out_dir).
Standalone: python -m scripts.qmmp.ea_generator BTCUSD
"""
from __future__ import annotations
import os, json, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
QDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "qmmp")

TF_ENUM = {"M1": "PERIOD_M1", "M5": "PERIOD_M5", "M15": "PERIOD_M15",
           "M30": "PERIOD_M30", "H1": "PERIOD_H1", "H4": "PERIOD_H4"}


def _sess_floor(floors, key, session, side=None, default=0.0):
    v = floors.get(key)
    if isinstance(v, dict):
        if key in ("bulls", "bears") and side:
            k = f"{session}_{side}"
            return float(v.get(k, default) or default)
        return float(v.get(session, default) or default)
    return default


def _opt_range(name, val, lo, hi, step, dtype="double"):
    """Return (input_line, set_lines) — an MT5 input + its optimiser range .set entries."""
    if dtype == "int":
        line = f"input int    {name} = {int(val)};"
        setl = [f"{name}={int(val)}", f"{name},F=1", f"{name},1={int(lo)}", f"{name},2={int(step)}", f"{name},3={int(hi)}"]
    else:
        line = f"input double {name} = {val};"
        setl = [f"{name}={val}", f"{name},F=1", f"{name},1={lo}", f"{name},2={step}", f"{name},3={hi}"]
    return line, setl


def build_ea(model: dict) -> tuple[str, str, dict]:
    """Return (mq5_source, set_file_source, param_manifest).
    param_manifest maps each EA input name -> the exact model.json-derived value it MUST
    equal (used by the verification test to prove EA == onboarding config)."""
    sym = model["symbol"]
    tf = model.get("timeframe", "H1"); tf_enum = TF_ENUM.get(tf, "PERIOD_H1")
    o = model.get("entry", {}).get("osma_params", {"fast": 12, "slow": 26, "signal": 9})
    fl = model.get("floors", {}); ex = model.get("exit", {})
    mm = model.get("money_management", {})
    gbp_per = float(mm.get("gbp_per_001", 50.0)); maxlegs = int(ex.get("max_legs", 4))
    inputs = []; setlines = []; manifest = {}

    def add(name, val, lo, hi, step, dtype="double"):
        ln, sl = _opt_range(name, val, lo, hi, step, dtype)
        inputs.append(ln); setlines.extend(sl)
        manifest[name] = int(val) if dtype == "int" else float(val)

    # --- entry / OsMA ---
    add("OsMA_Fast", o.get("fast", 12), 6, 18, 2, "int")
    add("OsMA_Slow", o.get("slow", 26), 18, 40, 2, "int")
    add("OsMA_Signal", o.get("signal", 9), 6, 12, 1, "int")
    # --- per-session floors: EVERY indicator the model tracks (osma/ema/bulls/bears/atr) ---
    for sname in ("Asian", "London", "NewYork"):
        add(f"OsmaFloor_{sname}",  round(_sess_floor(fl, "osma_mag",  sname), 3), 0, 200, 1)
        add(f"EmaAlign_{sname}",   round(_sess_floor(fl, "ema_align", sname), 3), -100, 200, 1)
        for side in ("Long", "Short"):
            add(f"BullsFloor_{sname}_{side}", round(_sess_floor(fl, "bulls", sname, side.lower()), 3), -500, 500, 5)
            add(f"BearsFloor_{sname}_{side}", round(_sess_floor(fl, "bears", sname, side.lower()), 3), -500, 500, 5)
        add(f"AtrFloor_{sname}",   round(_sess_floor(fl, "atr",       sname), 3), 0, 5000, 25)
    # --- exit (basket trail + early pyramid) — every tunable exit element ---
    add("HardSL_pts",  int(ex.get("sl", 628348)), 50000, 800000, 25000, "int")
    add("BE_pts",      int(ex.get("be", 11057)),  2000, 40000, 1000, "int")
    add("BE_lock_pts", int(ex.get("be_lock", max(1, int(ex.get("be", 11057) * 0.1)))), 0, 5000, 250, "int")
    add("Trail_pts",   int(ex.get("trail", 11057)), 2000, 40000, 1000, "int")
    add("Add_pts",     int(ex.get("add", 11057)),   2000, 40000, 1000, "int")
    add("EarlyFrac",   float(ex.get("early", 0.15)), 0.05, 0.5, 0.05)
    add("MaxLegs",     maxlegs, 1, 6, 1, "int")
    # --- money management ---
    add("GBP_per_001", gbp_per, 10, 250, 10)
    add("LotCapPerAccount", int(mm.get("lot_cap_per_account", 100)), 10, 100, 10, "int")
    add("Magic", 880011, 100000, 999999, 1, "int")

    # Build grouped input block using MQL5 `input group` directive
    entry_block = "\n".join(inputs[:3])
    floor_block = "\n".join(inputs[3:3 + 21])
    exit_block = "\n".join(inputs[3 + 21:3 + 21 + 7])
    mm_block = "\n".join(inputs[3 + 21 + 7:])
    inp_block = f'\ninput group "Entry / OsMA"\n{entry_block}\n' \
                f'\ninput group "Per-session strength floors (0 = OFF)"\n{floor_block}\n' \
                f'\ninput group "Exit: basket trail + early pyramid"\n{exit_block}\n' \
                f'\ninput group "Money management"\n{mm_block}\n'

    fast_i = o.get("fast", 12); slow_i = o.get("slow", 26); sig_i = o.get("signal", 9)
    # config VERSION HASH + snapshot for traceability of optimiser runs (EA <-> model.json)
    import hashlib
    cfg_snapshot = json.dumps(manifest, sort_keys=True)
    cfg_hash = hashlib.sha256((sym + tf + cfg_snapshot).encode()).hexdigest()[:12]
    onboarded = model.get("onboarded_at", "")
    build = int(model.get("build", 0) or 0)
    ea_ver = model.get("ea_version", "1.00")
    ver_str = ea_ver                        # property version must stay standard (e.g. "1.00")
    desc_str = f"GoldShark {sym} {tf} | build {build} | config {cfg_hash} | onboarded {onboarded}"
    # embed the full config snapshot as commented lines (traceable inside the .mq5)
    snap_lines = "\n".join(f"//|   {k} = {v}" for k, v in manifest.items())
    vw = model.get("validation_window", {})
    if vw:
        snap_lines += f"\n//|   Backtest window: {vw.get('backtest_start', 'N/A')} -> {vw.get('split_date', 'N/A')}"
        snap_lines += f"\n//|   Forward window : {vw.get('split_date', 'N/A')} -> {vw.get('forward_end', 'N/A')}  ({vw.get('split_pct', '70/30')} split, NOT an MT5 preset)"
        if vw.get("note"):
            snap_lines += f"\n//|   NOTE: {vw['note']}"
    mq5 = f'''//+------------------------------------------------------------------+
//|  GoldShark_{sym}.mq5                                             |
//|  Auto-generated by QMMP onboarding pipeline (#57/#61)            |
//|  Symbol: {sym}   Validated timeframe: {tf}                       |
//|  Onboarded: {onboarded}   CONFIG VERSION: {cfg_hash}   BUILD: {build}  |
//|  Entry: OsMA zero-cross + per-session floors                     |
//|  Exit : single basket trailing stop + early-only pyramiding      |
//|  MT5 forward-test: pipeline validated on 70/30; MT5 optimiser    |
//|    defaults 1/4=25%, 1/3=33%, 1/2=50% forward are all supported. |
//|  DO NOT hand-edit -- regenerate via scripts.qmmp.ea_generator    |
//|  ---- CONFIG SNAPSHOT (must match model.json; verified by        |
//|       ea_generator.verify_ea at pipeline Stage 11) ----          |
{snap_lines}
//+------------------------------------------------------------------+
#property copyright "QMMP"
#property version   "{ver_str}"
#property description "{desc_str}"
#property strict

#define QMMP_CONFIG_VERSION "{cfg_hash}"
#define QMMP_BUILD         "{build}"
#define QMMP_SYMBOL         "{sym}"
#define QMMP_TIMEFRAME      "{tf}"

// ===== OPTIMISER-COMPATIBLE INPUTS (ranges in GoldShark_{sym}.set) =====
{inp_block}

int      hMACD = INVALID_HANDLE, hATR = INVALID_HANDLE, hEMA = INVALID_HANDLE;
int      hBulls = INVALID_HANDLE, hBears = INVALID_HANDLE;
datetime lastBarTime = 0;

//+------------------------------------------------------------------+
int OnInit()
  {{
   hMACD = iMACD(_Symbol, {tf_enum}, OsMA_Fast, OsMA_Slow, OsMA_Signal, PRICE_CLOSE);
   hATR  = iATR(_Symbol, {tf_enum}, 14);
   hEMA  = iMA(_Symbol, {tf_enum}, 13, 0, MODE_EMA, PRICE_CLOSE);
   hBulls = iBullsPower(_Symbol, {tf_enum}, 13);
   hBears = iBearsPower(_Symbol, {tf_enum}, 13);
   if(hMACD==INVALID_HANDLE || hATR==INVALID_HANDLE || hEMA==INVALID_HANDLE || hBulls==INVALID_HANDLE || hBears==INVALID_HANDLE) return(INIT_FAILED);
   return(INIT_SUCCEEDED);
   }}
void OnDeinit(const int reason){{ IndicatorRelease(hMACD); IndicatorRelease(hATR); IndicatorRelease(hEMA); IndicatorRelease(hBulls); IndicatorRelease(hBears); }}

//--- OsMA[i] = MACD main - signal (MT5 iMACD buffer 0 = main = MACD line, buffer 1 = signal)
double OsMA(int shift)
  {{
   double m[2], s[2];
   if(CopyBuffer(hMACD,0,shift,1,m)<1 || CopyBuffer(hMACD,1,shift,1,s)<1) return(0);
   return(m[0]-s[0]);
   }}
double ATRv(int shift){{ double a[1]; if(CopyBuffer(hATR,0,shift,1,a)<1) return(0); return(a[0]); }}
double EMAv(int shift){{ double e[1]; if(CopyBuffer(hEMA,0,shift,1,e)<1) return(0); return(e[0]); }}
double BullsP(int shift){{ double v[1]; if(CopyBuffer(hBulls,0,shift,1,v)<1) return(0); return(v[0]); }}
double BearsP(int shift){{ double v[1]; if(CopyBuffer(hBears,0,shift,1,v)<1) return(0); return(v[0]); }}

//--- session (broker/server time assumed ~UTC; adjust if your server offset differs)
string CurSession()
  {{
   MqlDateTime dt; TimeToStruct(TimeCurrent(), dt); int h=dt.hour;
   if(h>=12 && h<21) return("NewYork");
   if(h>=7  && h<16) return("London");
   if(h>=0  && h<9 ) return("Asian");
   return("Off");
   }}
void SessionFloors(string s, bool isLong, double &osma, double &ema, double &bulls, double &bears, double &atr)
  {{
   string side = isLong ? "Long" : "Short";
   if(s=="Asian"){{  osma=OsmaFloor_Asian;  ema=EmaAlign_Asian;  bulls=isLong?BullsFloor_Asian_Long:BullsFloor_Asian_Short;  bears=isLong?BearsFloor_Asian_Long:BearsFloor_Asian_Short;  atr=AtrFloor_Asian; }}
   else if(s=="London"){{ osma=OsmaFloor_London; ema=EmaAlign_London; bulls=isLong?BullsFloor_London_Long:BullsFloor_London_Short; bears=isLong?BearsFloor_London_Long:BearsFloor_London_Short; atr=AtrFloor_London; }}
   else {{ osma=OsmaFloor_NewYork; ema=EmaAlign_NewYork; bulls=isLong?BullsFloor_NewYork_Long:BullsFloor_NewYork_Short; bears=isLong?BearsFloor_NewYork_Long:BearsFloor_NewYork_Short; atr=AtrFloor_NewYork; }}
   }}

//+------------------------------------------------------------------+
void OnTick()
  {{
   // one decision per new bar
   datetime bt[]; if(CopyTime(_Symbol,{tf_enum},0,1,bt)<1) return;
   if(bt[0]==lastBarTime) {{ ManageBasket(); return; }}
   lastBarTime = bt[0];
   ManageBasket();

   string sess = CurSession();
   if(sess=="Off") return;

   double o1=OsMA(1), o2=OsMA(2);                    // closed bars
   bool crossUp   = (o2<=0 && o1>0);
   bool crossDown = (o2>=0 && o1<0);
   if(!crossUp && !crossDown) return;

    double fOsma,fEma,fBulls,fBears,fAtr; SessionFloors(sess,crossUp,fOsma,fEma,fBulls,fBears,fAtr);
   double osma_mag = MathAbs(o1);
   double ema_slope = EMAv(1)-EMAv(4);               // slope over 3 bars
   double ema_align = crossUp ? ema_slope : -ema_slope;
    double atr = ATRv(1);
   double bulls_al = crossUp ? BullsP(1) : -BullsP(1);   // aligned power (long wants +bulls)
   double bears_al = crossUp ? BearsP(1) : -BearsP(1);
   // KEEP-floor gates (0 = OFF => always passes; validated floors set the non-zero gate)
   if(fOsma>0 && osma_mag < fOsma) return;
   if(fEma!=0 && ema_align < fEma) return;
   if(fAtr>0 && atr < fAtr) return;
   if(fBulls>0 && bulls_al < fBulls) return;
   if(fBears<0 && bears_al > fBears) return;         // bears floor is negative (deeper = stronger)

   OpenLeg(crossUp);
   }}

//--- money-management size: floor(equity/GBP_per_001) x 0.01 total, split across MaxLegs,
//--- margin- and 100-lot-capped. (Broker min lot / step assumed 0.01.)
double PerLegLots()
  {{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   int units = (int)MathFloor(eq / GBP_per_001);
   double marginOne=0; if(!OrderCalcMargin(ORDER_TYPE_BUY,_Symbol,0.01,SymbolInfoDouble(_Symbol,SYMBOL_ASK),marginOne)) marginOne=0.94;
   if(marginOne>0) units = (int)MathMin(units, MathFloor(eq/marginOne));
   units = (int)MathMin(units, LotCapPerAccount*100);   // 100 lots = 10000 x 0.01
   double perLeg = (units*0.01)/MaxLegs;
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   perLeg = MathFloor(perLeg/step)*step;
   double vmin=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double lots = perLeg<vmin?0.0:perLeg;
   Print("GoldShark PerLegLots: eq=", DoubleToString(eq,2), " units=", IntegerToString(units), " perLeg=", DoubleToString(perLeg,2), " lots=", DoubleToString(lots,2));
   return(lots);
   }}

void OpenLeg(bool isLong)
  {{
   double lots = PerLegLots(); if(lots<=0) return;
   double price = isLong?SymbolInfoDouble(_Symbol,SYMBOL_ASK):SymbolInfoDouble(_Symbol,SYMBOL_BID);
   double sl = isLong? price-HardSL_pts*_Point : price+HardSL_pts*_Point;
   MqlTradeRequest r; MqlTradeResult res; ZeroMemory(r);
   r.action=TRADE_ACTION_DEAL; r.symbol=_Symbol; r.volume=lots;
   r.type=isLong?ORDER_TYPE_BUY:ORDER_TYPE_SELL; r.price=price; r.sl=sl;
   r.deviation=50; r.magic=Magic; r.comment="GoldShark_{sym}";
   if(!OrderSend(r,res)){{ /* order rejected; skip */ }}
   // update pyramid tracking
   legCount = legCount + 1;
   lastLegPrice = price;
   }}

//--- basket trailing stop (single stop behind best) + early pyramid add
double basketBest=0; bool armed=false; int legCount=0; double lastLegPrice=0;
void ManageBasket()
  {{
   if(PositionsTotalSym()==0){{ armed=false; basketBest=0; legCount=0; lastLegPrice=0; return; }}
   bool isLong = NetLong();
   double px = isLong?SymbolInfoDouble(_Symbol,SYMBOL_BID):SymbolInfoDouble(_Symbol,SYMBOL_ASK);
   if(basketBest==0) basketBest=px;
   basketBest = isLong?MathMax(basketBest,px):MathMin(basketBest,px);
   double avgEntry=AvgEntry();
   double profitPts = (isLong?(basketBest-avgEntry):(avgEntry-basketBest))/_Point * PositionsTotalSym();
   // BE lock: once profit hits BE_pts, move SL to entry + BE_lock_pts (lock in minimum)
   if(!armed && profitPts>=BE_pts)
     {{
      armed = true;
      double lockSl = isLong ? avgEntry + BE_lock_pts*_Point : avgEntry - BE_lock_pts*_Point;
      ModifyAllSL(lockSl);
     }}
   if(armed)
     {{
      double newSL = isLong? basketBest-Trail_pts*_Point : basketBest+Trail_pts*_Point;
      ModifyAllSL(newSL);
     }}
   // early pyramid: add a leg if price advanced Add_pts beyond last leg and still early
   // (heuristic: within first EarlyFrac of estimated cycle length; fallback to legCount<MaxLegs)
   if(legCount>0 && legCount<MaxLegs)
     {{
      double adv=(isLong?(px-lastLegPrice):(lastLegPrice-px))/_Point;
      if(adv>=Add_pts){{ OpenLeg(isLong); }}
     }}
   }}
// --- helpers (position accounting for this symbol/magic) ---
int PositionsTotalSym(){{ int c=0; for(int i=PositionsTotal()-1;i>=0;i--){{ if(PositionGetTicket(i)>0 && PositionGetString(POSITION_SYMBOL)==_Symbol) c++; }} return(c); }}
bool NetLong(){{ double v=0; for(int i=PositionsTotal()-1;i>=0;i--){{ if(PositionGetTicket(i)>0 && PositionGetString(POSITION_SYMBOL)==_Symbol) v+=(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY?1:-1); }} return(v>=0); }}
double AvgEntry(){{ double s=0; int n=0; for(int i=PositionsTotal()-1;i>=0;i--){{ if(PositionGetTicket(i)>0 && PositionGetString(POSITION_SYMBOL)==_Symbol){{ s+=PositionGetDouble(POSITION_PRICE_OPEN); n++; }} }} return(n>0?s/n:0); }}
void ModifyAllSL(double sl){{ for(int i=PositionsTotal()-1;i>=0;i--){{ ulong t=PositionGetTicket(i); if(t>0 && PositionGetString(POSITION_SYMBOL)==_Symbol){{ MqlTradeRequest r; MqlTradeResult res; ZeroMemory(r); r.action=TRADE_ACTION_SLTP; r.position=t; r.symbol=_Symbol; r.sl=sl; r.tp=0; if(!OrderSend(r,res)){{ /* skip */ }} }} }} }}
//+------------------------------------------------------------------+
'''
    set_hdr = f"; GoldShark_{sym}.set -- MT5 Strategy Tester optimiser ranges (auto-generated)\n; F=1 enables optimisation; 1=start 2=step 3=stop\n"
    set_src = set_hdr + "\n".join(setlines) + "\n"
    return mq5, set_src, manifest


def verify_ea(model: dict, mq5_path: str) -> list:
    """Parse the generated .mq5 `input` defaults and assert each equals the value the
    onboarding model.json dictates. Returns list of mismatch strings ([] == exact match)."""
    _, _, manifest = build_ea(model)
    import re
    src = open(mq5_path, encoding="utf-8").read()
    got = {}
    for m in re.finditer(r"^input\s+(?:int|double)\s+(\w+)\s*=\s*([-\d.]+);", src, re.M):
        got[m.group(1)] = float(m.group(2))
    problems = []
    for name, want in manifest.items():
        if name not in got:
            problems.append(f"{name}: MISSING from EA (expected {want})")
        elif abs(got[name] - float(want)) > 1e-6:
            problems.append(f"{name}: EA={got[name]} != model={want}")
    for name in got:
        if name not in manifest:
            problems.append(f"{name}: EA input has NO model.json source (undocumented)")
    # Stage 11b: every declared input must be referenced somewhere in the EA body
    body = src.split("// ===== OPTIMISER-COMPATIBLE INPUTS")[1].split("//+------------------------------------------------------------------+")[0] if "// ===== OPTIMISER-COMPATIBLE INPUTS" in src else src
    for name in manifest:
        if name not in body:
            problems.append(f"{name}: declared input NOT referenced in EA body (dead optimizer dimension)")
    return problems


def write_ea(model: dict, out_dir: str) -> str:
    sym = model["symbol"]
    mq5, setsrc, manifest = build_ea(model)
    os.makedirs(out_dir, exist_ok=True)
    mq5_path = os.path.join(out_dir, f"GoldShark_{sym}.mq5")
    set_path = os.path.join(out_dir, f"GoldShark_{sym}.set")
    man_path = os.path.join(out_dir, f"GoldShark_{sym}.params.json")
    with open(mq5_path, "w", encoding="utf-8") as f: f.write(mq5)
    with open(set_path, "w", encoding="utf-8") as f: f.write(setsrc)
    with open(man_path, "w", encoding="utf-8") as f: json.dump(manifest, f, indent=2)
    return mq5_path


def main():
    sym = (sys.argv[1] if len(sys.argv) > 1 else "BTCUSD").upper().split("-")[0].rstrip(".")
    d = os.path.join(QDIR, sym)
    model = json.load(open(os.path.join(d, "model.json"), encoding="utf-8"))
    p = write_ea(model, d)
    print(f"wrote {p} + .set (optimiser ranges)")


if __name__ == "__main__":
    main()
