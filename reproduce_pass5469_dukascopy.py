"""
Reproduce pass5469 (the proven GoldShark13 .set) on DUKASCOPY bar + tick data.

This is the Dukascopy twin of reproduce_pass5469.py. It runs the EXACT same
GoldShark13 rule and the EXACT same pass5469 config, but sources XAUUSD M1 bars and
bid/ask ticks from the Dukascopy datafeed (via src/data_sources/dukascopy.py) instead
of the committed MT5 .npy/.csv. Goal: see whether the proven edge survives on a second,
independent, high-quality data source.

GoldShark13 rule (identical to reproduce_pass5469.py):
  LONG:  bulls>=minBuL AND bears>maxBeL AND osma>=minOsL AND osma rising
         AND emaSlope>=min_slope AND ATR in [min_atr,max_atr] AND atr rising
  SHORT: mirror. Fixed-point BE/TP/trail exits. Asian-session filter (22:00-08:00 UTC).
  £bal_per_lot/0.01-lot compounding. Tick-by-tick bid/ask fills.

CAVEAT: Dukascopy is a different broker to VT Markets MT5. Gold price/spread/tick
granularity differ, so absolute magnitudes (and therefore the MT5-tuned strength floors)
will NOT line up 1:1. Treat a positive result as STRUCTURAL confirmation that the edge
is not an MT5 artefact, not as a re-derivation of the live floors.

Usage:
  python reproduce_pass5469_dukascopy.py [start_balance] [start_date] [end_date]
  e.g. python reproduce_pass5469_dukascopy.py 100 2024-04-01 2024-05-31
"""
import sys
import os
import json
import datetime as dt
from datetime import timezone

import numpy as np

from src.data_sources.dukascopy import fetch_ticks, ticks_to_bars

POINT = 0.01  # gold point (Dukascopy XAUUSD scale=3 -> prices like 2345.678)
CFG = os.path.join("data", "reprodata", "pass5469_cfg.json")


def ema(vals, p):
    out = []
    k = 2 / (p + 1)
    e = vals[0]
    for v in vals:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def run(start=100.0, start_date="2024-04-01", end_date="2024-05-31", recalibrate=False):
    c = json.load(open(CFG))

    # MT5-derived percentiles of each pass5469 floor (measured on XAUUSD_demo_M1.csv):
    # this is the "meaning" of each floor — its selectivity — independent of feed scale.
    # Used only when recalibrate=True to place equivalent floors on the Dukascopy dist.
    MT5_FLOOR_PCTILES = {
        "min_atr": 26.4,   # ATR
        "minOsL": 98.9,    # |OsMA| (very selective long trigger by design)
        "minBuL": 49.4,    # Bulls
        "maxBeL": 92.4,    # Bears (long requires bears > this)
    }

    d0 = dt.datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    d1 = dt.datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + dt.timedelta(days=1)

    print(f"[dukascopy] fetching XAUUSD ticks {start_date} .. {end_date} (cached after first run)...")
    raw_ticks = fetch_ticks("XAUUSD", d0, d1, use_cache=True)
    if not raw_ticks:
        print("  NO TICKS returned from Dukascopy for this range.")
        return

    # M1 bars from the same ticks (mid price), matching the MT5 M1 CSV semantics.
    m1 = ticks_to_bars(raw_ticks, 60, use_mid=True)
    bars = [{"t": b["timestamp"], "o": b["open"], "h": b["high"],
             "l": b["low"], "cl": b["close"]} for b in m1]

    # tick arrays for fills (bid/ask)
    tt = np.array([int(r[0]) for r in raw_ticks], dtype="int64")
    tb = np.array([r[1] for r in raw_ticks], dtype="float64")  # bid
    ta = np.array([r[2] for r in raw_ticks], dtype="float64")  # ask

    print(f"  ticks={len(tt)}  M1 bars={len(bars)}")
    if len(bars) < 40:
        print("  Not enough bars to run the rule.")
        return

    close = [b["cl"] for b in bars]
    high = [b["h"] for b in bars]
    low = [b["l"] for b in bars]
    fast = ema(close, c["osma_fast"])
    slow = ema(close, c["osma_slow"])
    macd = [f - s for f, s in zip(fast, slow)]
    sig = ema(macd, c["osma_sig"])
    osma = [m - s for m, s in zip(macd, sig)]
    ep = ema(close, c["ema"])
    bulls = [h - e for h, e in zip(high, ep)]
    bears = [l - e for l, e in zip(low, ep)]
    tr = [high[0] - low[0]]
    for i in range(1, len(bars)):
        tr.append(max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])))
    ap = c["atrp"]
    atr = [sum(tr[max(0, i - ap + 1):i + 1]) / min(i + 1, ap) for i in range(len(tr))]

    # Optional recalibration: keep the STRUCTURAL rule identical, but re-place the
    # magnitude floors at the SAME percentile of the Dukascopy distribution that they
    # occupied on MT5. This adapts feed/regime scale without curve-fitting the logic.
    if recalibrate:
        import bisect
        def q(vals, pct):
            s = sorted(vals)
            return s[min(len(s) - 1, max(0, int(pct / 100.0 * len(s))))]
        absosma = [abs(x) for x in osma]
        old = dict(c)
        c["min_atr"] = round(q(atr, MT5_FLOOR_PCTILES["min_atr"]), 4)
        c["minOsL"] = round(q(absosma, MT5_FLOOR_PCTILES["minOsL"]), 4)
        c["maxOsS"] = -c["minOsL"]  # mirror short trigger
        c["minBuL"] = round(q(bulls, MT5_FLOOR_PCTILES["minBuL"]), 4)
        c["maxBeL"] = round(q(bears, MT5_FLOOR_PCTILES["maxBeL"]), 4)
        c["maxBuS"] = -c["minBuL"]
        c["minBeS"] = -c["maxBeL"] if False else c["minBeS"]  # keep short bears floor
        print(f"  [recalibrated floors to Dukascopy scale] "
              f"min_atr {old['min_atr']}->{c['min_atr']}, minOsL {old['minOsL']}->{c['minOsL']}, "
              f"minBuL {old['minBuL']}->{c['minBuL']}, maxBeL {old['maxBeL']}->{c['maxBeL']}")

    bal = start
    wins = gw = gl = trades = 0
    peak = bal
    maxdd = 0
    ti = 0
    for i in range(30, len(bars) - 1):
        # Asian session filter (22:00-08:00 UTC) — the .set traded Asian only
        hr = dt.datetime.utcfromtimestamp(bars[i]["t"]).hour
        if not (hr >= 22 or hr < 8):
            continue
        o1, o2 = osma[i - 1], osma[i - 2]
        b1, be1 = bulls[i - 1], bears[i - 1]
        a1, a2 = atr[i - 1], atr[i - 2]
        slope = (ep[i - 1] - ep[i - 5])
        atr_ok = c["min_atr"] <= a1 <= c["max_atr"] and a1 > a2
        longR = (b1 >= c["minBuL"] and be1 > c["maxBeL"] and o1 >= c["minOsL"] and o1 > o2
                 and slope >= c["min_slope"] and atr_ok)
        shortR = (be1 <= c["minBeS"] and b1 > c["maxBuS"] and o1 <= c["maxOsS"] and o1 < o2
                  and slope <= -c["min_slope"] and atr_ok)
        if not (longR or shortR):
            continue
        d = 1 if longR else -1
        et = bars[i + 1]["t"]
        while ti < len(tt) and tt[ti] < et:
            ti += 1
        if ti >= len(tt):
            break
        entry = ta[ti] if d == 1 else tb[ti]
        lot = max(round((bal / c["bal_per_lot"]) * 0.01, 2), 0.01)
        be_trig = c["be_trig"] * POINT
        tp_trig = c["tp_trig"] * POINT
        trail = c["trail"] * POINT
        sl = entry - c.get("sl_pts", 800) * POINT * d
        tp = entry + tp_trig * d
        best = entry
        j = ti
        exitp = None
        moved_be = False
        while j < len(tt):
            px = tb[j] if d == 1 else ta[j]
            if d == 1:
                best = max(best, px)
                if not moved_be and best - entry >= be_trig:
                    sl = entry + POINT
                    moved_be = True
                if best - entry >= trail:
                    sl = max(sl, best - trail)
                if px <= sl:
                    exitp = sl
                    break
                if px >= tp:
                    exitp = tp
                    break
            else:
                best = min(best, px)
                if not moved_be and entry - best >= be_trig:
                    sl = entry - POINT
                    moved_be = True
                if entry - best >= trail:
                    sl = min(sl, best + trail)
                if px >= sl:
                    exitp = sl
                    break
                if px <= tp:
                    exitp = tp
                    break
            j += 1
        if exitp is None:
            exitp = tb[-1] if d == 1 else ta[-1]
        pl = (exitp - entry) * d * lot * 100
        bal += pl
        trades += 1
        if pl > 0:
            wins += 1
            gw += pl
        else:
            gl += -pl
        peak = max(peak, bal)
        maxdd = max(maxdd, (peak - bal) / peak * 100)
        ti = j

    pf = gw / gl if gl > 0 else float("inf")
    print(f"\npass5469 / GoldShark13 repro on DUKASCOPY (Asian-only, tick fills, "
          f"£{c['bal_per_lot']}/lot compounding):")
    if trades:
        print(f"  start=£{start} end=£{bal:.2f} return={bal / start:.2f}x trades={trades} "
              f"WR={wins / trades * 100:.1f}% PF={pf:.2f} maxDD={maxdd:.1f}%")
    else:
        print("  NO TRADES (rule never fired on this window)")
    print("  (proven MT5 baseline for comparison: ~2.73x, WR ~94%, PF ~1.48 on XAUUSD MT5 ticks)")


if __name__ == "__main__":
    a = sys.argv
    recal = "--recal" in a
    a = [x for x in a if x != "--recal"]
    run(float(a[1]) if len(a) > 1 else 100.0,
        a[2] if len(a) > 2 else "2024-04-01",
        a[3] if len(a) > 3 else "2024-05-31",
        recalibrate=recal)
