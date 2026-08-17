"""Fetch 30 days of BTCUSD Dukascopy ticks and cache to Parquet for the forming-candle
analysis. Runs standalone (slow, network-bound) so it can go in the background."""
import sys, os
from datetime import datetime, timezone, timedelta
sys.path.insert(0, r'C:\Users\MartinSharkey\Documents\Langchain\langchain')
import polars as pl
from src.data_sources.dukascopy import fetch_ticks

OUT = r'C:\Users\MartinSharkey\Documents\Langchain\langchain\data\qmmp\BTCUSD'
os.makedirs(OUT, exist_ok=True)
end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
start = end - timedelta(days=30)
print(f"Dukascopy BTCUSD ticks {start} .. {end}", flush=True)

def prog(d, t):
    print(f"  {d}/{t} hours ({100*d/t:.0f}%)", flush=True)

ticks = fetch_ticks("BTCUSD", start, end, workers=8, progress_cb=prog)
print(f"fetched {len(ticks)} ticks", flush=True)
if ticks:
    df = pl.DataFrame({
        "epoch": [t[0] for t in ticks],
        "bid": [t[1] for t in ticks],
        "ask": [t[2] for t in ticks],
    })
    df.write_parquet(os.path.join(OUT, "ticks_30d.parquet"))
    print(f"wrote {os.path.join(OUT,'ticks_30d.parquet')} ({len(df)} rows)", flush=True)
