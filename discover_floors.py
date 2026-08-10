"""
Per-symbol strength-floor DISCOVERY (independent backtest).

The indicator combination is symbol-agnostic but strength MAGNITUDES are not: gold's
pass5469 floors fail on BTC/GER40. This finds each symbol's OWN floors by incrementally
sweeping the magnitudes on that symbol's own bar+tick data, scoring a BALANCE of:
  frequency (trades/day, must not choke) x entry-success (went green) x capture (exit).

Rule = the GoldShark13 confluence: OsMA on side + rising/falling + Bulls/Bears sign +
EMA slope + ATR in range. We add a magnitude FLOOR on |OsMA| and the dominant power,
expressed in ATR units (scale-free), and search the floor level per symbol.

Fills: tick-by-tick (real bid/ask). Usage: python discover_floors.py BTCUSD GER40
"""
import sys, os, csv, statistics
import numpy as np

REPRO = os.path.join("langchain", "data", "reprodata")


def ema(vals, p):
    out = []; k = 2/(p+1); e = vals[0]
    for v in vals:
        e = v*k + e*(1-k); out.append(e)
    return out


def load(sym):
    bp = os.path.join(REPRO, f"{sym}_M1.csv"); tp = os.path.join(REPRO, f"{sym}_ticks.npy")
    bars = [{"t": int(float(r["time"])), "o": float(r["open"]), "h": float(r["high"]),
             "l": float(r["low"]), "c": float(r["close"])}
            for r in csv.DictReader(open(bp, encoding="utf-8-sig"))]
    ticks = np.load(tp) if os.path.exists(tp) else None
    return bars, ticks


def indicators(bars):
    close = [b["c"] for b in bars]; high = [b["h"] for b in bars]; low = [b["l"] for b in bars]
    fast = ema(close, 12); slow = ema(close, 26); macd = [f-s for f, s in zip(fast, slow)]
    sig = ema(macd, 9); osma = [m-s for m, s in zip(macd, sig)]
    ep = ema(close, 13); bulls = [h-e for h, e in zip(high, ep)]; bears = [l-e for l, e in zip(low, ep)]
    tr = [high[0]-low[0]]
    for i in range(1, len(bars)):
        tr.append(max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1])))
    atr = [sum(tr[max(0,i-13):i+1])/min(i+1, 14) for i in range(len(tr))]
    return osma, ep, bulls, bears, atr


def backtest(bars, ticks, osma, ep, bulls, bears, atr, floor_osma, floor_dom, slope_min=0.05,
             sl_atr=1.0, tp_rr=2.0, green_atr=0.3):
    tt = ticks["time"].astype("int64"); tb = ticks["bid"].astype("float64"); ta = ticks["ask"].astype("float64")
    trades = wins = green = gw = gl = 0; ti = 0; caps = []; days = set()
    # GoldShark-style FIXED-POINT exits (what actually worked in pass5469): BE trigger,
    # trailing, and a wide hard stop. Scaled to the symbol via its median ATR so points
    # are meaningful (gold ATR~2.3 -> 466pt SL; a big-ATR symbol scales up).
    med_atr = statistics.median([a for a in atr[30:] if a > 0]) or 1.0
    point = 0.01
    be_trig = 1.5 * med_atr        # move to BE+ after ~1.5 ATR profit
    tp_dist = 2.0 * med_atr        # take profit target
    trail = 1.2 * med_atr          # trail distance once armed
    hard_sl = 3.0 * med_atr        # wide hard stop
    for i in range(30, len(bars)-1):
        a1 = atr[i-1]
        if a1 <= 0:
            continue
        o1, o2 = osma[i-1], osma[i-2]; b1, be1 = bulls[i-1], bears[i-1]
        slope = (ep[i-1]-ep[i-5]) / a1
        longR = (o1 > 0 and o1 > o2 and b1 > 0 and be1 > 0 and slope >= slope_min
                 and (abs(o1)/a1) >= floor_osma and (b1/a1) >= floor_dom)
        shortR = (o1 < 0 and o1 < o2 and be1 < 0 and b1 < 0 and slope <= -slope_min
                  and (abs(o1)/a1) >= floor_osma and (-be1/a1) >= floor_dom)
        if not (longR or shortR):
            continue
        d = 1 if longR else -1
        et = bars[i+1]["t"]
        while ti < len(tt) and tt[ti] < et: ti += 1
        if ti >= len(tt): break
        entry = ta[ti] if d == 1 else tb[ti]
        sl = entry - hard_sl*d; tp = entry + tp_dist*d
        j = ti; exitp = None; peak = entry; moved_be = False
        while j < len(tt):
            px = tb[j] if d == 1 else ta[j]
            if d == 1:
                peak = max(peak, px)
                if not moved_be and peak-entry >= be_trig: sl = entry + point; moved_be = True
                if peak-entry >= trail: sl = max(sl, peak-trail)
                if px <= sl: exitp = sl; break
                if px >= tp: exitp = tp; break
            else:
                peak = min(peak, px)
                if not moved_be and entry-peak >= be_trig: sl = entry - point; moved_be = True
                if entry-peak >= trail: sl = min(sl, peak+trail)
                if px >= sl: exitp = sl; break
                if px <= tp: exitp = tp; break
            j += 1
        if exitp is None: exitp = tb[-1] if d == 1 else ta[-1]
        mfe = (peak - entry)*d
        pl = (exitp - entry)*d
        trades += 1; days.add(bars[i]["t"] // 86400)
        if mfe >= green_atr*a1: green += 1
        if pl > 0: wins += 1; gw += pl
        else: gl += -pl
        if mfe > 0: caps.append(max(pl, 0)/mfe)
        ti = j
    nd = max(len(days), 1)
    pf = gw/gl if gl > 0 else (99 if gw else 0)
    return {"trades": trades, "per_day": round(trades/nd, 1), "wr": round(wins/trades*100, 1) if trades else 0,
            "green_pct": round(green/trades*100, 1) if trades else 0, "pf": round(pf, 2),
            "capture": round(statistics.median(caps)*100, 0) if caps else 0}


def discover(sym):
    bars, ticks = load(sym)
    if ticks is None:
        print(f"{sym}: no ticks"); return None
    osma, ep, bulls, bears, atr = indicators(bars)
    span_days = (bars[-1]["t"] - bars[0]["t"]) / 86400
    print(f"\n===== {sym}: {len(bars)} bars / {len(ticks)} ticks / {span_days:.0f} days — floor search =====")
    print(f"{'osma_fl':>7} {'dom_fl':>6} | {'/day':>5} {'green%':>6} {'WR%':>5} {'PF':>5} {'cap%':>5} {'score':>6}")
    best = None
    for fo in (0.0, 0.1, 0.2, 0.3, 0.5):
        for fd in (0.0, 0.5, 1.0, 1.5):
            r = backtest(bars, ticks, osma, ep, bulls, bears, atr, fo, fd)
            # BALANCED objective: reward green-rate + PF, require >= ~3 trades/day (no choke)
            if r["per_day"] < 3:
                score = -1
            else:
                score = round(r["green_pct"]/100 * r["pf"] * min(r["per_day"]/10, 1.5), 3)
            flag = ""
            if best is None or (score > best[0] and r["per_day"] >= 3):
                best = (score, fo, fd, r); flag = " <=="
            print(f"{fo:>7.1f} {fd:>6.1f} | {r['per_day']:>5} {r['green_pct']:>6} {r['wr']:>5} {r['pf']:>5} {r['capture']:>5} {score:>6}{flag}")
    if best:
        _, fo, fd, r = best
        print(f"  BEST {sym}: osma_floor={fo} dom_floor={fd} -> {r['per_day']}/day green {r['green_pct']}% PF {r['pf']}")
        return {"symbol": sym, "osma_min_long": fo, "bulls_min_long": fd,
                "osma_max_short": -fo, "bears_max_short": -fd, "result": r}
    return None


if __name__ == "__main__":
    syms = sys.argv[1:] or ["BTCUSD", "GER40"]
    out = {}
    for s in syms:
        r = discover(s)
        if r: out[s] = r
    import json
    json.dump(out, open(os.path.join(REPRO, "discovered_floors.json"), "w"), indent=2)
    print("\nsaved -> discovered_floors.json")
