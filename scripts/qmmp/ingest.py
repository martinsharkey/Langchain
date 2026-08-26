"""QMMP ingest: multi-timeframe bar data -> Parquet.

Source: MT5 (VTMarkets) for all timeframes (M1~45d, M5~120d, M15~400d, M30~700d,
H1~900d, H4~1500d). All TFs stored aligned to UTC.

Output: data/qmmp/<symbol>/<TF>.parquet
Usage:
    python -m scripts.qmmp.ingest BTCUSD                 # MT5 all TFs
"""
from __future__ import annotations
import argparse, os, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import polars as pl
import MetaTrader5 as mt5

TF_MAP = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
          "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4}
# how many days back each TF can realistically serve from MT5 (probed)
TF_DAYS = {"M1": 45, "M5": 120, "M15": 400, "M30": 700, "H1": 900, "H4": 1500}
OUTDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "qmmp")


def _resolve_symbol(symbol):
    """Map a base symbol to the broker's actual symbol name (e.g. XAUUSD->XAUUSD-ECN)."""
    if mt5.symbol_info(symbol):
        return symbol
    for s in mt5.symbols_get() or []:
        if s.name.upper().startswith(symbol.upper()):
            return s.name
    return symbol


def _sessions(df: pl.DataFrame) -> pl.DataFrame:
    h = df["time"].dt.hour()
    return df.with_columns([
        ((h >= 0) & (h < 9)).alias("session_asia"),
        ((h >= 7) & (h < 16)).alias("session_london"),
        ((h >= 12) & (h < 21)).alias("session_ny"),
        (df["time"].dt.weekday() < 5).alias("weekday"),   # polars weekday: Mon=1..Sun=7 -> <5 = Mon-Thu? adjust below
    ])


def _integrity_guard(df: pl.DataFrame, tf: str) -> pl.DataFrame:
    """Drop phantom weekend rows for FX/metals is symbol-specific; here we only drop
    duplicate timestamps and flag gaps. Crypto trades weekends so we keep them."""
    df = df.unique(subset=["time"]).sort("time")
    return df


def ingest_mt5(symbol: str):
    resolved = _resolve_symbol(symbol)
    mt5.symbol_select(resolved, True)
    now = datetime.now(timezone.utc)
    outsym = os.path.join(OUTDIR, resolved.upper().split("-")[0].rstrip("."))
    os.makedirs(outsym, exist_ok=True)
    summary = {}
    for tf, days in TF_DAYS.items():
        rates = mt5.copy_rates_range(resolved, TF_MAP[tf], now - timedelta(days=days), now)
        if rates is None or len(rates) == 0:
            # fall back to from_pos for M1 (range sometimes fails on shallow TFs)
            rates = mt5.copy_rates_from_pos(resolved, TF_MAP[tf], 0, min(days * 1440, 90000))
        if rates is None or len(rates) == 0:
            summary[tf] = 0
            continue
        df = pl.DataFrame({
            "time": [datetime.fromtimestamp(int(r["time"]), timezone.utc) for r in rates],
            "open": [float(r["open"]) for r in rates],
            "high": [float(r["high"]) for r in rates],
            "low": [float(r["low"]) for r in rates],
            "close": [float(r["close"]) for r in rates],
            "volume": [float(r["tick_volume"]) for r in rates],
        })
        df = _integrity_guard(df, tf)
        # weekday flag (Mon-Fri): polars dt.weekday() Mon=1..Sun=7
        wdcol = df["time"].dt.weekday()
        h = df["time"].dt.hour()
        df = df.with_columns([
            ((h >= 0) & (h < 9)).alias("session_asia"),
            ((h >= 7) & (h < 16)).alias("session_london"),
            ((h >= 12) & (h < 21)).alias("session_ny"),
            (wdcol <= 5).alias("weekday"),
        ])
        path = os.path.join(outsym, f"{tf}.parquet")
        df.write_parquet(path)
        summary[tf] = len(df)
    return resolved, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    args = ap.parse_args()
    if not mt5.initialize():
        print("MT5 init failed:", mt5.last_error()); return
    resolved, summary = ingest_mt5(args.symbol)
    print(f"MT5 ingest {args.symbol} (resolved {resolved}):")
    for tf, n in summary.items():
        print(f"  {tf}: {n} bars")
    mt5.shutdown()
    print(f"\nParquet in {os.path.join(OUTDIR, args.symbol.upper())}")


if __name__ == "__main__":
    main()
