"""
Generic per-symbol reproduction / baseline on DUKASCOPY data.

Runs the GoldShark13 confluence rule using EACH symbol's own SYMBOL_BASELINES config
(XAUUSD uses raw pass5469 floors; BTCUSD/GER40 use their ATR-scaled discovered floors),
on Dukascopy bar+tick data. Reports WR / PF / return so we can establish the Dukascopy
baseline per symbol and hand it to the auto-tuner.

Usage:
  python reproduce_symbol_dukascopy.py SYMBOL [start] [end] [start_balance]
  e.g. python reproduce_symbol_dukascopy.py BTCUSD 2026-07-13 2026-07-25
"""
import sys, os, datetime as dt
from datetime import timezone
import numpy as np

from src.data_sources.dukascopy import fetch_ticks, ticks_to_bars, resolve
from src.learning.param_optimizer import SYMBOL_BASELINES, DEFAULTS

# per-symbol POINT (price increment) for points-based exits
POINTS = {"XAUUSD": 0.01, "BTCUSD": 0.1, "GER40": 0.01}


def ema(v, p):
    o = []; k = 2 / (p + 1); e = v[0]
    for x in v:
        e = x * k + e * (1 - k); o.append(e)
    return o


def run(symbol, start_date, end_date, start=100.0):
    base = symbol.upper().split("-")[0]
    cfg = dict(DEFAULTS); cfg.update(SYMBOL_BASELINES.get(base, {}))
    raw_floors = bool(cfg.get("floors_raw", False))
    POINT = POINTS.get(base, 0.01)
    # exits: use proven fixed points if present (gold), else ATR-relative defaults
    be_pts = cfg.get("be_trigger_pts"); tp_pts = cfg.get("tp_points")
    trail_pts = cfg.get("trail_points"); hard_sl = cfg.get("hard_sl_points", 800)
    bal_per_lot = cfg.get("bal_per_lot", 31.0)

    d0 = dt.datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    d1 = dt.datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + dt.timedelta(days=1)
    print(f"[{base}] fetch Dukascopy ticks {start_date}..{end_date} (raw_floors={raw_floors} POINT={POINT})")
    raw = fetch_ticks(base, d0, d1, use_cache=True, workers=4)
    if not raw:
        print("  NO TICKS"); return
    m1 = ticks_to_bars(raw, 60, use_mid=True)
    bars = [{"t": b["timestamp"], "h": b["high"], "l": b["low"], "cl": b["close"]} for b in m1]
    tt = np.array([int(r[0]) for r in raw]); tb = np.array([r[1] for r in raw]); ta = np.array([r[2] for r in raw])
    print(f"  ticks={len(tt)} bars={len(bars)}")
    if len(bars) < 40:
        print("  too few bars"); return

    close = [b["cl"] for b in bars]; high = [b["h"] for b in bars]; low = [b["l"] for b in bars]
    fast = ema(close, cfg["osma_fast"]); slow = ema(close, cfg["osma_slow"])
    macd = [f - s for f, s in zip(fast, slow)]; sig = ema(macd, cfg["osma_signal"])
    osma = [m - s for m, s in zip(macd, sig)]; ep = ema(close, cfg["ema_period"])
    bulls = [h - e for h, e in zip(high, ep)]; bears = [l - e for l, e in zip(low, ep)]
    tr = [high[0] - low[0]]
    for i in range(1, len(bars)):
        tr.append(max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])))
    ap = cfg["atr_period"]
    atr = [sum(tr[max(0, i - ap + 1):i + 1]) / min(i + 1, ap) for i in range(len(tr))]

    minOsL = cfg.get("osma_min_long", 0.0); minBuL = cfg.get("bulls_min_long", 0.0)
    maxBeL = cfg.get("bears_min_long", 0.0); maxOsS = cfg.get("osma_max_short", 0.0)
    maxBuS = cfg.get("bulls_max_short", 0.0); minBeS = cfg.get("bears_max_short", 0.0)
    minSlope = cfg.get("min_ema_slope", 0.0)
    aMin = cfg.get("atr_min", 0.0); aMax = cfg.get("atr_max", 0.0) or 1e9

    bal = start; wins = gw = gl = trades = 0; peak = bal; maxdd = 0; ti = 0
    for i in range(30, len(bars) - 1):
        a1, a2 = atr[i - 1], atr[i - 2]
        af = 1.0 if raw_floors else (a1 if a1 > 0 else 1.0)  # ATR-scale floors unless raw
        o1, o2 = osma[i - 1], osma[i - 2]; b1, be1 = bulls[i - 1], bears[i - 1]
        slope = ep[i - 1] - ep[i - 5]
        atr_ok = (aMin <= a1 <= aMax) and a1 > a2
        longR = (b1 >= minBuL * af and be1 > maxBeL * af and o1 >= minOsL * af and o1 > o2
                 and slope >= minSlope and atr_ok)
        shortR = (be1 <= minBeS * af and b1 > maxBuS * af and o1 <= maxOsS * af and o1 < o2
                  and slope <= -minSlope and atr_ok)
        if not (longR or shortR):
            continue
        d = 1 if longR else -1; et = bars[i + 1]["t"]
        while ti < len(tt) and tt[ti] < et:
            ti += 1
        if ti >= len(tt):
            break
        entry = ta[ti] if d == 1 else tb[ti]
        lot = max(round((bal / bal_per_lot) * 0.01, 2), 0.01)
        # exits: fixed points if configured, else ATR-relative
        bt = (be_pts * POINT) if be_pts else (1.5 * a1)
        tp = (tp_pts * POINT) if tp_pts else (2.0 * a1)
        trl = (trail_pts * POINT) if trail_pts else (1.2 * a1)
        sl = entry - hard_sl * POINT * d; tpp = entry + tp * d
        best = entry; j = ti; exitp = None; mb = False
        while j < len(tt):
            px = tb[j] if d == 1 else ta[j]
            if d == 1:
                best = max(best, px)
                if not mb and best - entry >= bt: sl = entry + POINT; mb = True
                if best - entry >= trl: sl = max(sl, best - trl)
                if px <= sl: exitp = sl; break
                if px >= tpp: exitp = tpp; break
            else:
                best = min(best, px)
                if not mb and entry - best >= bt: sl = entry - POINT; mb = True
                if entry - best >= trl: sl = min(sl, best + trl)
                if px >= sl: exitp = sl; break
                if px <= tpp: exitp = tpp; break
            j += 1
        if exitp is None:
            exitp = tb[-1] if d == 1 else ta[-1]
        pl = (exitp - entry) * d * lot * (100 if base == "XAUUSD" else (10 if base == "BTCUSD" else 100))
        bal += pl; trades += 1
        if pl > 0: wins += 1; gw += pl
        else: gl += -pl
        peak = max(peak, bal); maxdd = max(maxdd, (peak - bal) / peak * 100)
        ti = j

    pf = gw / gl if gl > 0 else float("inf")
    print(f"\n{base} Dukascopy baseline (tick fills, {'raw' if raw_floors else 'ATR-scaled'} floors):")
    if trades:
        print(f"  start={start} end={bal:.2f} return={bal / start:.2f}x trades={trades} "
              f"WR={wins / trades * 100:.1f}% PF={pf:.2f} maxDD={maxdd:.1f}%")
    else:
        print("  NO TRADES (rule never fired)")


if __name__ == "__main__":
    a = sys.argv
    if len(a) < 2:
        print("usage: reproduce_symbol_dukascopy.py SYMBOL [start] [end] [bal]"); sys.exit(1)
    run(a[1], a[2] if len(a) > 2 else "2026-07-13", a[3] if len(a) > 3 else "2026-07-25",
        float(a[4]) if len(a) > 4 else 100.0)
