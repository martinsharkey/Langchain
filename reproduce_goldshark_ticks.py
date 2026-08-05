"""
TICK-BASED reproduction of the GoldShark proven edge (MT5 "Every Tick based on Real
Ticks" model). Entries are decided on CLOSED M1 bars using the exact GoldShark11_v12
rule; SL/TP are then resolved TICK-BY-TICK against real bid/ask, with the real spread
paid on entry/exit — the only faithful way to reproduce an MT5 tick backtest.

Inputs (from data/reprodata/):
  XAUUSD_demo_M1.csv   — M1 bars (epoch time, ohlc) for the entry signal
  XAUUSD_demo_ticks.npy — real ticks (time, bid, ask, ...) for fills

Compounding: baseLot = (balance / 100) * 0.01 (GoldShark EA line 1463).

Usage: python reproduce_goldshark_ticks.py [start_balance]
"""
import sys, os, csv, glob
import numpy as np
import xml.etree.ElementTree as ET

NS = {'ss': 'urn:schemas-microsoft-com:office:spreadsheet'}
REPRO = os.path.join("langchain", "data", "reprodata")
BARS_CSV = os.path.join(REPRO, "XAUUSD_demo_M1.csv")
TICKS_NPY = os.path.join(REPRO, "XAUUSD_demo_ticks.npy")
GOLD_POINT_VALUE = 100.0   # $ per 1.0 price move per 1.0 lot (gold ~100oz/lot)


def _f(d, k, dv=float("nan")):
    try:
        v = d.get(k); return float(v) if v not in (None, "") else dv
    except (TypeError, ValueError):
        return dv


def load_proven_config():
    xmls = sorted(glob.glob(os.path.join("MT5_OLD_EA's", "**", "*GoldShark1131*.xml"), recursive=True)
                  + glob.glob(os.path.join("MT5_OLD_EA's", "**", "ReportOptimizer*.xml"), recursive=True),
                  key=os.path.getsize, reverse=True)
    rows = ET.parse(xmls[0]).getroot().findall('.//ss:Row', NS)
    hdr = [c.text for c in rows[0].findall('.//ss:Data', NS)]
    data = [dict(zip(hdr, [c.text for c in r.findall('.//ss:Data', NS)]))
            for r in rows[1:] if len(r.findall('.//ss:Data', NS)) >= len(hdr)]
    off = [d for d in data if str(d.get("InpEnableBasketStrategy", "")).lower() == "false"
           and 1.5 <= _f(d, "Profit Factor") <= 6 and _f(d, "Trades") >= 100 and _f(d, "Equity DD %") <= 25]
    off.sort(key=lambda d: -(_f(d, "Profit Factor") * _f(d, "Trades") ** 0.5))
    return off[0], os.path.basename(xmls[0])


def ema(vals, p):
    out = []; k = 2 / (p + 1); e = vals[0]
    for v in vals:
        e = v * k + e * (1 - k); out.append(e)
    return out


def indicators(bars, cfg):
    close = [b["close"] for b in bars]; high = [b["high"] for b in bars]; low = [b["low"] for b in bars]
    fast = ema(close, int(cfg["osma_fast"])); slow = ema(close, int(cfg["osma_slow"]))
    macd = [f - s for f, s in zip(fast, slow)]; sig = ema(macd, int(cfg["osma_signal"]))
    osma = [m - s for m, s in zip(macd, sig)]
    ep = ema(close, int(cfg["ema_period"]))
    bulls = [h - e for h, e in zip(high, ep)]; bears = [l - e for l, e in zip(low, ep)]
    tr = [high[0] - low[0]]
    for i in range(1, len(bars)):
        tr.append(max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1])))
    ap = int(cfg["atr_period"]); atr = [sum(tr[max(0, i-ap+1):i+1])/min(i+1, ap) for i in range(len(tr))]
    return osma, ep, bulls, bears, atr


def run(start_balance=100.0):
    gs, xml = load_proven_config()
    POINT = 0.01  # gold point size
    cfg = {"osma_fast": _f(gs, "InpOsmaFast", 12), "osma_slow": _f(gs, "InpOsmaSlow", 50),
           "osma_signal": _f(gs, "InpOsmaSig", 9), "ema_period": _f(gs, "InpEmaPeriod", 13),
           "atr_period": _f(gs, "InpAtrPeriod", 14), "atr_min": _f(gs, "InpMinATR", 0), "atr_max": _f(gs, "InpMaxATR", 0),
           # RAW power/osma floors (GoldShark units, NOT ATR-normalized)
           "osma_min_long": _f(gs, "InpMinOsMALong", 0.57), "bulls_min_long": _f(gs, "InpMinBullsLong", 1.9),
           "bears_max_long": _f(gs, "InpMaxBearsLong", -0.2), "osma_max_short": _f(gs, "InpMaxOsMAShort", -0.8),
           "bulls_max_short": _f(gs, "InpMaxBullsShort", 0), "bears_min_short": _f(gs, "InpMinBearsShort", -1.3),
           # GoldShark FIXED-POINT exits (not ATR): SL / TP(Target1) / trailing / breakeven in points
           "sl_pts": _f(gs, "InpStopLoss", 466), "tp_pts": _f(gs, "InpTarget1", 304),
           "trail_pts": _f(gs, "InpTrailingStop", 608), "be_pts": _f(gs, "InpBreakeven", 24),
           "momentum_age": int(_f(gs, "InpMaxMomentumAge", 10))}
    print(f"GoldShark target: PF={gs['Profit Factor']} trades={gs['Trades']} DD={gs['Equity DD %']}% ({xml})")
    print(f"  fixed-pt exits: SL={cfg['sl_pts']}pts TP={cfg['tp_pts']}pts trail={cfg['trail_pts']}pts BE={cfg['be_pts']}pts")
    print(f"  RAW floors: bullsL>={cfg['bulls_min_long']} bearsL>{cfg['bears_max_long']} osmaL>={cfg['osma_min_long']} | bearsS<={cfg['bears_min_short']} bullsS>{cfg['bulls_max_short']} osmaS<={cfg['osma_max_short']}")

    bars = []
    for r in csv.DictReader(open(BARS_CSV, encoding="utf-8-sig")):
        bars.append({"t": int(float(r["time"])), "open": float(r["open"]), "high": float(r["high"]),
                     "low": float(r["low"]), "close": float(r["close"])})
    ticks = np.load(TICKS_NPY)
    tick_t = ticks["time"].astype("int64"); tick_bid = ticks["bid"].astype("float64"); tick_ask = ticks["ask"].astype("float64")
    print(f"bars={len(bars)}  ticks={len(ticks)}  tick span covers {(tick_t[-1]-tick_t[0])/86400:.1f} days")

    osma, ep, bulls, bears, atr = indicators(bars, cfg)
    balance = start_balance; wins = gw = gl = trades = 0
    peak = balance; maxdd = 0.0
    ti = 0  # tick cursor

    for i in range(30, len(bars) - 1):
        o1, o2 = osma[i-1], osma[i-2]; b1, be1 = bulls[i-1], bears[i-1]
        a1, a2 = atr[i-1], atr[i-2]; e1, e0 = ep[i-1], ep[i-5]
        atr_ok = a1 >= cfg["atr_min"] and (cfg["atr_max"] == 0 or a1 <= cfg["atr_max"]) and a1 > a2
        longR = (b1 >= cfg["bulls_min_long"] and be1 > cfg["bears_max_long"] and o1 >= cfg["osma_min_long"]
                 and o1 > o2 and e1 > e0 and atr_ok)
        shortR = (be1 <= cfg["bears_min_short"] and b1 > cfg["bulls_max_short"] and o1 <= cfg["osma_max_short"]
                  and o1 < o2 and e1 < e0 and atr_ok)
        if not (longR or shortR):
            continue
        d = 1 if longR else -1
        # enter at the NEXT bar's open time, using the real tick bid/ask at that moment
        entry_time = bars[i+1]["t"]
        while ti < len(tick_t) and tick_t[ti] < entry_time:
            ti += 1
        if ti >= len(tick_t):
            break
        entry = tick_ask[ti] if d == 1 else tick_bid[ti]   # pay the spread on entry
        import os as _o
        lot = 0.01 if _o.getenv("NO_COMPOUND")=="1" else max(round((balance / 100.0) * 0.01, 2), 0.01)
        sl = entry - cfg["sl_pts"] * POINT * d
        tp = entry + cfg["tp_pts"] * POINT * d
        trail = cfg["trail_pts"] * POINT
        be = cfg["be_pts"] * POINT
        best = entry
        # resolve TICK-BY-TICK with fixed-point SL/TP + trailing stop + breakeven
        j = ti; exitp = None
        while j < len(tick_t):
            px = tick_bid[j] if d == 1 else tick_ask[j]   # realisable exit price
            # update best + trail
            if d == 1:
                best = max(best, px)
                if best - entry >= be:                       # moved to BE+
                    sl = max(sl, entry + POINT)
                if best - entry >= trail:                    # trail
                    sl = max(sl, best - trail)
                if px <= sl: exitp = sl; break
                if px >= tp: exitp = tp; break
            else:
                best = min(best, px)
                if entry - best >= be:
                    sl = min(sl, entry - POINT)
                if entry - best >= trail:
                    sl = min(sl, best + trail)
                if px >= sl: exitp = sl; break
                if px <= tp: exitp = tp; break
            j += 1
        if exitp is None:
            exitp = tick_bid[-1] if d == 1 else tick_ask[-1]
        pl = (exitp - entry) * d * lot * GOLD_POINT_VALUE
        balance += pl; trades += 1
        if pl > 0: wins += 1; gw += pl
        else: gl += -pl
        peak = max(peak, balance); maxdd = max(maxdd, (peak - balance)/peak*100)
        ti = j  # no overlapping positions (one at a time)

    pf = gw/gl if gl > 0 else float("inf")
    print(f"\nTICK-BASED RESULT: start=£{start_balance} end=£{balance:.2f} return={balance/start_balance:.2f}x "
          f"trades={trades} WR={wins/trades*100:.1f}% PF={pf:.2f} maxDD={maxdd:.1f}%")


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 100.0)
