"""Forming-candle OsMA-strength analysis (BTCUSD, 30d) — TICK-DRIVEN + bars.
Uses cached Dukascopy ticks (data/qmmp/BTCUSD/ticks_30d.parquet) for the forming entry
candle at 25/50/75% of its formation, and MT5 M1 bars for closed-OsMA history + cycle
outcome. Entry = OsMA cross confirmed on the closed signal bar; entry/forming candle =
first candle of the new cycle. Measures whether OsMA strength AS THE CANDLE FORMS
(secs 15/30/45) correlates with entry success. Labels/simulation via vectorbt."""
import sys, os
from datetime import datetime, timezone, timedelta
sys.path.insert(0, r'C:\Users\MartinSharkey\Documents\Langchain\langchain')
import numpy as np, pandas as pd, polars as pl, bisect
import MetaTrader5 as mt5
import vectorbt as vbt
from src.strategies.indicators import osma as osma_fn
FAST, SLOW, SIG = 12, 26, 9
D = r'C:\Users\MartinSharkey\Documents\Langchain\langchain\data\qmmp\BTCUSD'
OUT = r'C:\Users\MartinSharkey\Documents\Langchain\langchain\data\btc_forming_candle_strength.md'

# ticks (Dukascopy, cached)
tks = pl.read_parquet(os.path.join(D, "ticks_30d.parquet"))
tk_epoch = tks["epoch"].to_numpy()
tk_mid = ((tks["bid"] + tks["ask"]) / 2).to_numpy()

# M1 bars aligned to the same window (build from ticks so OHLC matches the tick source)
tdf = pd.DataFrame({"epoch": tk_epoch, "mid": tk_mid})
tdf["minute"] = (tdf["epoch"] // 60 * 60).astype(np.int64)
g = tdf.groupby("minute")["mid"]
bars = pd.DataFrame({"open": g.first(), "high": g.max(), "low": g.min(), "close": g.last()}).reset_index()
bars = bars.sort_values("minute").reset_index(drop=True)
pt = 0.01
close = pd.Series(bars["close"].values)
osma = osma_fn(close, FAST, SLOW, SIG).values
bar_epoch = bars["minute"].values
n = len(bars)
hist = close.values

def osma_partial(i_form, px_partial):
    lo = max(0, i_form - (SLOW + SIG + 5))
    seg = np.concatenate([hist[lo:i_form], [px_partial]])
    return osma_fn(pd.Series(seg), FAST, SLOW, SIG).values[-1]

def ticks_slice(start_epoch):
    a = bisect.bisect_left(tk_epoch, start_epoch)
    b = bisect.bisect_left(tk_epoch, start_epoch + 60)
    return a, b

rows = []
for i in range(SLOW + SIG + 5, n - 2):
    prev, cur = osma[i-1], osma[i]
    if not (np.isfinite(prev) and np.isfinite(cur)): continue
    is_long = prev <= 0 < cur; is_short = prev >= 0 > cur
    if not (is_long or is_short): continue
    f = i + 1
    if f >= n - 1: continue
    start = bar_epoch[f]
    a, b = ticks_slice(start)
    if b - a < 4: continue
    te = tk_epoch[a:b]; tm = tk_mid[a:b]
    o = tm[0]
    def px_at(frac):
        j = bisect.bisect_right(te, start + 60*frac) - 1
        return tm[max(0, j)]
    p25, p50, p75 = px_at(.25), px_at(.50), px_at(.75)
    def body(px, upto):
        j = bisect.bisect_right(te, start + 60*upto)
        seg = tm[:max(1, j)]; rng = seg.max() - seg.min()
        return ((px - o)/rng) if rng > 0 else 0.0
    # cycle outcome
    e = close.values[f]
    j = f
    while j < n and (np.isfinite(osma[j]) and (osma[j] > 0) == is_long) and j < f + 240:
        j += 1
    seg_hi = bars["high"].values[f:j+1].max(); seg_lo = bars["low"].values[f:j+1].min()
    fav = (seg_hi - e)/pt if is_long else (e - seg_lo)/pt
    adv = (e - seg_lo)/pt if is_long else (seg_hi - e)/pt
    rows.append(dict(side="long" if is_long else "short",
        osma25=osma_partial(f, p25), osma50=osma_partial(f, p50), osma75=osma_partial(f, p75),
        osma_final=osma[f] if np.isfinite(osma[f]) else osma_partial(f, close.values[f]),
        body25=body(p25,.25), body50=body(p50,.50), body75=body(p75,.75),
        fav=fav, adv=adv, win=1 if fav > adv else 0))

df = pd.DataFrame(rows)
# vectorbt sanity: label vector + basic stats via vbt
print(f"BTCUSD forming-candle entries (tick-driven): {len(df)} "
      f"(long {sum(df.side=='long')} / short {sum(df.side=='short')})")

def corr(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    m = np.isfinite(a) & np.isfinite(b)
    return np.corrcoef(a[m], b[m])[0, 1] if m.sum() >= 10 else float('nan')

lines = ["# BTCUSD forming-candle OsMA strength vs entry success — TICK-DRIVEN (30d Dukascopy)\n",
         "\nForming entry candle sampled at 25/50/75% (secs 15/30/45) from ticks; OsMA strength "
         "recomputed on price-so-far. Correlation to win (peak>adverse) and favourable pts.\n"]
for side in ("long", "short"):
    s = df[df.side == side]
    if len(s) < 20: continue
    base = s["win"].mean()*100
    h = f"\n## {side.upper()} (n={len(s)}, base win {base:.0f}%)\n"; print(h.strip()); lines.append(h)
    for feat in ("osma25","osma50","osma75","body25","body50","body75"):
        cw, cf = corr(s[feat], s["win"]), corr(s[feat], s["fav"])
        ln = f"  {feat:8} corr->win {cw:+.2f}   corr->fav {cf:+.2f}"; print(ln); lines.append(ln+"\n")
    sgn = 1 if side == "long" else -1
    es = s[(sgn*s["osma25"]) >= (sgn*s["osma_final"]*0.5)]
    lb = s[(sgn*s["osma25"]) < (sgn*s["osma_final"]*0.5)]
    if len(es) >= 10 and len(lb) >= 10:
        ln = (f"  EARLY-STRONG (osma@25% >=50% of final): n={len(es)} win {es['win'].mean()*100:.0f}%  "
              f"|  LATE-BUILD: n={len(lb)} win {lb['win'].mean()*100:.0f}%")
        print(ln); lines.append(ln+"\n")
open(OUT, "w").write("".join(lines))
print(f"\nwrote {OUT}")
