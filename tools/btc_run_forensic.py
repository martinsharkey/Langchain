"""BTCUSD run forensic v2 — directional CONFLUENCE at run start + full run extent.

For each MAJOR run in the last 4h it reports, ON THE SAME CANDLE at the run start:
  - OsMA value + sign
  - Bulls Power + Bears Power values + sign
  - whether OsMA / Bulls / Bears are ALIGNED with the run direction
  - the ATR, EMA slope, price-vs-EMA
Then it measures the RUN EXTENT: how many points it travelled and the MAX points
reached before it reversed. All bar times converted broker->UTC.
"""
import os, sys
sys.path.insert(0, os.getcwd())
os.environ.setdefault("USE_SAFE_EMBEDDER", "1")
os.environ.setdefault("FORCE_LOCAL_VECTOR_STORE", "1")

import pandas as pd, numpy as np
from src.mt5.connector import get_connector
import MetaTrader5 as mt5
from src.strategies.indicators import ema, rsi, macd, atr, bulls_power, bears_power, osma
from src.mt5.broker_time import broker_offset_hours

SYM = "BTCUSD"
OSMA_F, OSMA_S, OSMA_SIG = 12, 26, 9
EMA_P, POWER_P, ATR_P = 50, 13, 14

conn = get_connector(); conn.initialize()
bars = mt5.copy_rates_from_pos(SYM, mt5.TIMEFRAME_M1, 0, 240 + 150)
df = pd.DataFrame(bars)
off_h = broker_offset_hours()
df["dt"] = pd.to_datetime(df["time"], unit="s") - pd.to_timedelta(off_h, unit="h")
df = df.rename(columns={"tick_volume": "volume"})
df["ema"] = ema(df["close"], EMA_P)
ml, sigl, _ = macd(df["close"], OSMA_F, OSMA_S, OSMA_SIG)
df["osma"] = osma(df["close"], OSMA_F, OSMA_S, OSMA_SIG)
df["atr"] = atr(df, ATR_P)
df["bulls"] = bulls_power(df, POWER_P)
df["bears"] = bears_power(df, POWER_P)
df["ema_slope_atr"] = df["ema"].diff() / df["atr"]

d = df.iloc[-240:].reset_index(drop=True)
n = len(d)
atr_med = d["atr"].median()
print(f"[broker {off_h:+.1f}h -> UTC]  {SYM} M1 last 4h: {d['dt'].iloc[0]} -> {d['dt'].iloc[-1]} UTC")
print(f"median ATR = {atr_med:.1f} pts;  major-run threshold = 4*ATR = {4*atr_med:.0f} pts\n")

# detect runs and MEASURE full extent + max before reversal
K = 4.0
i = 0; runs = []
while i < n - 3:
    p0 = d["close"].iloc[i]
    win = d["close"].iloc[i:min(i+40, n)]
    up = win.max() - p0; dn = p0 - win.min()
    if max(up, dn) >= K * atr_med:
        direction = "LONG" if up >= dn else "SHORT"
        # extreme point of the run
        j = win.idxmax() if direction == "LONG" else win.idxmin()
        runs.append((i, j, direction))
        i = j + 1
    else:
        i += 1

def aligned(direction, osma_v, bulls_v, bears_v):
    # For a LONG: OsMA>0 (momentum up), Bulls>0 (buyers above EMA), Bears rising/less negative.
    # For a SHORT: OsMA<0, Bears<0 (sellers below EMA), Bulls weak/negative.
    if direction == "LONG":
        return (osma_v > 0, bulls_v > 0, bears_v > 0)
    else:
        return (osma_v < 0, bulls_v < 0, bears_v < 0)

print(f"MAJOR RUNS: {len(runs)}\n" + "="*70)
for (i, j, direction) in runs:
    s = d.iloc[i]                      # SAME candle at run start
    entry = s["close"]
    # full extent in points, and max favourable before reversal
    seg = d.iloc[i:j+1]
    if direction == "LONG":
        max_pts = seg["high"].max() - entry
    else:
        max_pts = entry - seg["low"].min()
    dur = j - i
    ao, ab, abe = aligned(direction, s["osma"], s["bulls"], s["bears"])
    n_aligned = sum([ao, ab, abe])
    print(f"\n{direction} run  {s['dt'].strftime('%H:%M')} UTC  (start close={entry:.1f})")
    print(f"  RUN EXTENT: {max_pts:.0f} pts max  over {dur} min  ({max_pts/atr_med:.1f} ATR)")
    print(f"  --- CONFLUENCE on the START candle (same bar) ---")
    print(f"  OsMA  = {s['osma']:+.3f}   {'ALIGNED' if ao else 'AGAINST'} ({direction})")
    print(f"  Bulls = {s['bulls']:+.2f}   {'ALIGNED' if ab else 'AGAINST'}")
    print(f"  Bears = {s['bears']:+.2f}   {'ALIGNED' if abe else 'AGAINST'}")
    print(f"  --> {n_aligned}/3 aligned with the {direction}")
    print(f"  ATR={s['atr']:.1f}  EMAslope/ATR={s['ema_slope_atr']:+.3f}  price-vs-EMA={entry-s['ema']:+.0f}")

# summary: does full 3-way alignment predict the biggest runs?
print("\n" + "="*70)
print("SUMMARY: alignment vs run size")
for (i, j, direction) in runs:
    s = d.iloc[i]; seg = d.iloc[i:j+1]
    entry = s["close"]
    max_pts = (seg["high"].max()-entry) if direction=="LONG" else (entry-seg["low"].min())
    ao, ab, abe = aligned(direction, s["osma"], s["bulls"], s["bears"])
    print(f"  {direction:5} {s['dt'].strftime('%H:%M')}  {max_pts:5.0f} pts  align={sum([ao,ab,abe])}/3  "
          f"(OsMA {'+' if s['osma']>0 else '-'} Bulls {'+' if s['bulls']>0 else '-'} Bears {'+' if s['bears']>0 else '-'})")
conn.shutdown()
