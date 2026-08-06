"""
Exit-parameter sweep on Dukascopy XAUUSD — proves the auto-tune concept.

Keeps the GoldShark13 ENTRY rule + pass5469 entry floors identical, but sweeps the
EXIT params (be_trig, tp_trig, trail, hard-stop) to find whether PF>1 is recoverable on
this feed. This is exactly what the continuous per-symbol researcher loop will do
automatically on randomised Dukascopy windows.

Usage: python sweep_exits_dukascopy.py [start] [end]
"""
import sys, os, json, itertools, datetime as dt
from datetime import timezone
import numpy as np
from src.data_sources.dukascopy import fetch_ticks, ticks_to_bars

POINT = 0.01
CFG = os.path.join("data", "reprodata", "pass5469_cfg.json")


def ema(v, p):
    o = []; k = 2 / (p + 1); e = v[0]
    for x in v:
        e = x * k + e * (1 - k); o.append(e)
    return o


def build(start_date, end_date):
    c = json.load(open(CFG))
    d0 = dt.datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    d1 = dt.datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + dt.timedelta(days=1)
    raw = fetch_ticks("XAUUSD", d0, d1, use_cache=True, workers=4)
    m1 = ticks_to_bars(raw, 60, use_mid=True)
    bars = [{"t": b["timestamp"], "h": b["high"], "l": b["low"], "cl": b["close"]} for b in m1]
    tt = np.array([int(r[0]) for r in raw]); tb = np.array([r[1] for r in raw]); ta = np.array([r[2] for r in raw])
    close = [b["cl"] for b in bars]; high = [b["h"] for b in bars]; low = [b["l"] for b in bars]
    fast = ema(close, c["osma_fast"]); slow = ema(close, c["osma_slow"])
    macd = [f - s for f, s in zip(fast, slow)]; sig = ema(macd, c["osma_sig"])
    osma = [m - s for m, s in zip(macd, sig)]; ep = ema(close, c["ema"])
    bulls = [h - e for h, e in zip(high, ep)]; bears = [l - e for l, e in zip(low, ep)]
    tr = [high[0] - low[0]]
    for i in range(1, len(bars)):
        tr.append(max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])))
    atr = [sum(tr[max(0, i - 13):i + 1]) / min(i + 1, 14) for i in range(len(tr))]
    # precompute entry signals (list of (bar_i, direction))
    sigs = []
    for i in range(30, len(bars) - 1):
        hr = dt.datetime.utcfromtimestamp(bars[i]["t"]).hour
        if not (hr >= 22 or hr < 8):
            continue
        o1, o2 = osma[i - 1], osma[i - 2]; b1, be1 = bulls[i - 1], bears[i - 1]
        a1, a2 = atr[i - 1], atr[i - 2]; slope = ep[i - 1] - ep[i - 5]
        atr_ok = c["min_atr"] <= a1 <= c["max_atr"] and a1 > a2
        longR = (b1 >= c["minBuL"] and be1 > c["maxBeL"] and o1 >= c["minOsL"] and o1 > o2 and slope >= c["min_slope"] and atr_ok)
        shortR = (be1 <= c["minBeS"] and b1 > c["maxBuS"] and o1 <= c["maxOsS"] and o1 < o2 and slope <= -c["min_slope"] and atr_ok)
        if longR or shortR:
            sigs.append((i, 1 if longR else -1))
    return c, bars, tt, tb, ta, sigs


def simulate(bars, tt, tb, ta, sigs, be_trig, tp_trig, trail, sl_pts, start=100.0, bal_per_lot=31.0):
    bal = start; wins = gw = gl = trades = 0; peak = bal; maxdd = 0; ti = 0
    bt = be_trig * POINT; tpt = tp_trig * POINT; trl = trail * POINT
    for (i, d) in sigs:
        et = bars[i + 1]["t"]
        while ti < len(tt) and tt[ti] < et:
            ti += 1
        if ti >= len(tt):
            break
        entry = ta[ti] if d == 1 else tb[ti]
        lot = max(round((bal / bal_per_lot) * 0.01, 2), 0.01)
        sl = entry - sl_pts * POINT * d; tp = entry + tpt * d
        best = entry; j = ti; exitp = None; mb = False
        while j < len(tt):
            px = tb[j] if d == 1 else ta[j]
            if d == 1:
                best = max(best, px)
                if not mb and best - entry >= bt: sl = entry + POINT; mb = True
                if best - entry >= trl: sl = max(sl, best - trl)
                if px <= sl: exitp = sl; break
                if px >= tp: exitp = tp; break
            else:
                best = min(best, px)
                if not mb and entry - best >= bt: sl = entry - POINT; mb = True
                if entry - best >= trl: sl = min(sl, best + trl)
                if px >= sl: exitp = sl; break
                if px <= tp: exitp = tp; break
            j += 1
        if exitp is None:
            exitp = tb[-1] if d == 1 else ta[-1]
        pl = (exitp - entry) * d * lot * 100
        bal += pl; trades += 1
        if pl > 0: wins += 1; gw += pl
        else: gl += -pl
        peak = max(peak, bal); maxdd = max(maxdd, (peak - bal) / peak * 100)
        ti = j
    pf = gw / gl if gl > 0 else float("inf")
    return dict(trades=trades, wr=(wins / trades * 100 if trades else 0), pf=pf,
                ret=bal / start, maxdd=maxdd)


if __name__ == "__main__":
    a = sys.argv
    start_date = a[1] if len(a) > 1 else "2026-07-13"
    end_date = a[2] if len(a) > 2 else "2026-07-25"
    c, bars, tt, tb, ta, sigs = build(start_date, end_date)
    print(f"entries={len(sigs)}  bars={len(bars)}  window {start_date}..{end_date}")
    print(f"baseline pass5469 exits (be={c['be_trig']} tp={c['tp_trig']} trail={c['trail']} sl=800):")
    r = simulate(bars, tt, tb, ta, sigs, c['be_trig'], c['tp_trig'], c['trail'], 800)
    print(f"  trades={r['trades']} WR={r['wr']:.1f}% PF={r['pf']:.2f} ret={r['ret']:.2f}x maxDD={r['maxdd']:.1f}%")
    print("\nsweeping exits (tighter SL, earlier BE, varied trail)...")
    best = None
    for be, tp, trail, sl in itertools.product([80, 150, 250], [200, 350, 500], [40, 73, 120], [120, 200, 350]):
        r = simulate(bars, tt, tb, ta, sigs, be, tp, trail, sl)
        if r['trades'] < 8:
            continue
        score = r['pf'] if r['pf'] != float('inf') else 99
        if best is None or (score, r['ret']) > (best[0], best[1]['ret']):
            best = (score, r, (be, tp, trail, sl))
    if best:
        _, r, (be, tp, trail, sl) = best
        print(f"BEST: be={be} tp={tp} trail={trail} sl={sl} -> "
              f"trades={r['trades']} WR={r['wr']:.1f}% PF={r['pf']:.2f} ret={r['ret']:.2f}x maxDD={r['maxdd']:.1f}%")
