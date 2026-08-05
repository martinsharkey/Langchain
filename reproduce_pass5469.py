"""
Reproduce pass5469 (the proven .set) with the EXACT GoldShark13 rule on our tick data.
LONG:  bulls>=MinBullsLong AND bears>MaxBearsLong AND osma>=MinOsMALong AND osma rising
       AND emaSlope>=MinEmaSlope AND ATR in range AND atr rising
SHORT: mirror. Fixed-point BE/TP/trail exits. Asian-session filter. £31/0.01-lot compounding.
Tick-by-tick fills (bid/ask). Usage: python reproduce_pass5469.py [start_balance]
"""
import sys, os, csv, json
import numpy as np

REPRO = os.path.join("langchain", "data", "reprodata")
POINT = 0.01


def ema(vals, p):
    out = []; k = 2/(p+1); e = vals[0]
    for v in vals:
        e = v*k + e*(1-k); out.append(e)
    return out


def run(start=100.0):
    c = json.load(open(os.path.join(REPRO, "pass5469_cfg.json")))
    bars = []
    for r in csv.DictReader(open(os.path.join(REPRO, "XAUUSD_demo_M1.csv"), encoding="utf-8-sig")):
        bars.append({"t": int(float(r["time"])), "o": float(r["open"]), "h": float(r["high"]),
                     "l": float(r["low"]), "cl": float(r["close"])})
    ticks = np.load(os.path.join(REPRO, "XAUUSD_demo_ticks.npy"))
    tt = ticks["time"].astype("int64"); tb = ticks["bid"].astype("float64"); ta = ticks["ask"].astype("float64")
    close = [b["cl"] for b in bars]; high = [b["h"] for b in bars]; low = [b["l"] for b in bars]
    fast = ema(close, c["osma_fast"]); slow = ema(close, c["osma_slow"])
    macd = [f-s for f, s in zip(fast, slow)]; sig = ema(macd, c["osma_sig"])
    osma = [m-s for m, s in zip(macd, sig)]
    ep = ema(close, c["ema"])
    bulls = [h-e for h, e in zip(high, ep)]; bears = [l-e for l, e in zip(low, ep)]
    tr = [high[0]-low[0]]
    for i in range(1, len(bars)):
        tr.append(max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1])))
    ap = c["atrp"]; atr = [sum(tr[max(0,i-ap+1):i+1])/min(i+1,ap) for i in range(len(tr))]

    import datetime
    bal = start; wins = gw = gl = trades = 0; peak = bal; maxdd = 0; ti = 0
    for i in range(30, len(bars)-1):
        # Asian session filter (roughly 22:00-08:00 UTC) — the .set traded Asian only
        hr = datetime.datetime.utcfromtimestamp(bars[i]["t"]).hour
        if not (hr >= 22 or hr < 8):
            continue
        o1, o2 = osma[i-1], osma[i-2]; b1, be1 = bulls[i-1], bears[i-1]
        a1, a2 = atr[i-1], atr[i-2]
        slope = (ep[i-1]-ep[i-5])
        atr_ok = c["min_atr"] <= a1 <= c["max_atr"] and a1 > a2
        longR = (b1 >= c["minBuL"] and be1 > c["maxBeL"] and o1 >= c["minOsL"] and o1 > o2
                 and slope >= c["min_slope"] and atr_ok)
        shortR = (be1 <= c["minBeS"] and b1 > c["maxBuS"] and o1 <= c["maxOsS"] and o1 < o2
                  and slope <= -c["min_slope"] and atr_ok)
        if not (longR or shortR):
            continue
        d = 1 if longR else -1
        et = bars[i+1]["t"]
        while ti < len(tt) and tt[ti] < et: ti += 1
        if ti >= len(tt): break
        entry = ta[ti] if d == 1 else tb[ti]
        lot = max(round((bal / c["bal_per_lot"]) * 0.01, 2), 0.01)
        be_trig = c["be_trig"]*POINT; tp_trig = c["tp_trig"]*POINT; trail = c["trail"]*POINT
        sl = entry - c.get("sl_pts", 800)*POINT*d   # hard stop if never trails
        tp = entry + tp_trig*d
        best = entry; j = ti; exitp = None; moved_be = False
        while j < len(tt):
            px = tb[j] if d == 1 else ta[j]
            if d == 1:
                best = max(best, px)
                if not moved_be and best-entry >= be_trig: sl = entry + POINT; moved_be = True
                if best-entry >= trail: sl = max(sl, best-trail)
                if px <= sl: exitp = sl; break
                if px >= tp: exitp = tp; break
            else:
                best = min(best, px)
                if not moved_be and entry-best >= be_trig: sl = entry - POINT; moved_be = True
                if entry-best >= trail: sl = min(sl, best+trail)
                if px >= sl: exitp = sl; break
                if px <= tp: exitp = tp; break
            j += 1
        if exitp is None: exitp = tb[-1] if d == 1 else ta[-1]
        pl = (exitp-entry)*d*lot*100
        bal += pl; trades += 1
        if pl > 0: wins += 1; gw += pl
        else: gl += -pl
        peak = max(peak, bal); maxdd = max(maxdd, (peak-bal)/peak*100)
        ti = j
    pf = gw/gl if gl > 0 else float("inf")
    print(f"pass5469 repro (Asian-only, tick fills, £{c['bal_per_lot']}/lot compounding):")
    print(f"  start=£{start} end=£{bal:.2f} return={bal/start:.2f}x trades={trades} "
          f"WR={wins/trades*100:.1f}% PF={pf:.2f} maxDD={maxdd:.1f}%" if trades else "  NO TRADES")


if __name__ == "__main__":
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 100.0)
