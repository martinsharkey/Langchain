#!/usr/bin/env python3
"""Pull full historical bar+tick data from a live MT5 account and store as parquet.

Usage:
    python scripts/data_acquisition/pull_mt5_history.py
    python scripts/data_acquisition/pull_mt5_history.py --broker vt_markets
    python scripts/data_acquisition/pull_mt5_history.py --symbols XAUUSD,BTCUSD --timeframes M15,H1
    python scripts/data_acquisition/pull_mt5_history.py --ticks-days 30

Data is stored in data/broker_data/<broker>/<SYMBOL>/<TF>.parquet
and data/broker_data/<broker>/<SYMBOL>/ticks.parquet (optional).

A live MT5 account (even zero-balance) stores unlimited bar history.
Tick data is limited by disk space and pull time.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure project root is on sys.path so `src.*` imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pull_mt5_history")

# Default symbols and timeframes from config
from src.config import TRADING_SYMBOLS, MTF_ALIGNMENT_TFS
from src.mt5.broker_adapter import resolve_symbol

# Timeframes to pull bars for
DEFAULT_TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4"]
# How many days of tick history to pull (ticks are large)
DEFAULT_TICKS_DAYS = 30
# Chunk size for tick pulling (days per chunk)
TICK_CHUNK_DAYS = 7


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pull MT5 history to local parquet")
    p.add_argument("--broker", default="vt_markets", help="Broker name for data path")
    p.add_argument("--symbols", default=None, help="Comma-separated symbols (default: all TRADING_SYMBOLS)")
    p.add_argument("--timeframes", default=None, help="Comma-separated TFs (default: all standard TFs)")
    p.add_argument("--ticks-days", type=int, default=DEFAULT_TICKS_DAYS, help="Days of tick history to pull")
    p.add_argument("--skip-ticks", action="store_true", help="Skip tick data acquisition")
    p.add_argument("--skip-bars", action="store_true", help="Skip bar data acquisition")
    p.add_argument("--force", action="store_true", help="Overwrite existing parquet files")
    return p.parse_args()


def connect_mt5():
    """Connect to MT5 terminal. Returns (mt5_module, account_info)."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        log.critical("MetaTrader5 package not installed. pip install MetaTrader5")
        sys.exit(1)

    # Ensure clean state — shut down any previous connection first
    try:
        mt5.shutdown()
    except Exception:
        pass

    # Initialize with the same parameters the connector uses
    from src.config import MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER, MT5_PATH
    init_kwargs = {
        "login": MT5_ACCOUNT if MT5_ACCOUNT > 0 else None,
        "password": MT5_PASSWORD if MT5_PASSWORD else None,
        "server": MT5_SERVER if MT5_SERVER else None,
    }
    if MT5_PATH:
        # Resolve to terminal64.exe if a directory was given
        mt5_path = MT5_PATH
        if not mt5_path.lower().endswith("terminal64.exe"):
            candidate = os.path.join(mt5_path, "terminal64.exe")
            if os.path.isfile(candidate):
                mt5_path = candidate
        init_kwargs["path"] = mt5_path

    if not mt5.initialize(**init_kwargs):
        err = mt5.last_error() if hasattr(mt5, 'last_error') else "Unknown"
        log.critical(f"MT5 initialize failed: {err}")
        sys.exit(1)

    account = mt5.account_info()
    if account is None:
        log.critical("MT5 connected but no account info. Is a terminal logged in?")
        mt5.shutdown()
        sys.exit(1)

    log.info(f"Connected to MT5: {account.server} | account #{account.login} | "
             f"balance={account.balance} {account.currency} | "
             f"company={account.company}")
    return mt5, account


def resolve_symbol_name(base_symbol: str) -> str | None:
    """Find the actual broker-specific symbol name for a base symbol."""
    spec = resolve_symbol(base_symbol)
    if spec is None:
        return None
    return spec.resolved


def pull_bars(mt5, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame | None:
    """Pull bar data for a symbol/timeframe.

    Uses copy_rates_from_pos (fast, limited to ~10k bars per call) with a loop
    to cover the full range, falling back to copy_rates_range for deep history.
    """
    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    tf = tf_map.get(timeframe)
    if tf is None:
        log.warning(f"  Unknown timeframe {timeframe}, skipping")
        return None

    # Ensure symbol is visible in Market Watch
    mt5.symbol_select(symbol, True)

    # Strategy 1: copy_rates_from_pos with looping (reliable up to ~10k per call)
    chunks = []
    pos = 0
    chunk_size = 10000
    while True:
        rates = mt5.copy_rates_from_pos(symbol, tf, pos, chunk_size)
        if rates is None or len(rates) == 0:
            break
        chunks.append(pd.DataFrame(rates))
        if len(rates) < chunk_size:
            break
        pos += chunk_size
        time.sleep(0.1)

    if chunks:
        df = pd.concat(chunks, ignore_index=True)
    else:
        # Strategy 2: copy_rates_range with a safe start date
        # MT5 terminals typically only have history from ~2024 onward
        safe_start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        safe_end = datetime.now(timezone.utc)
        rates = mt5.copy_rates_range(symbol, tf, safe_start, safe_end)
        if rates is None or len(rates) == 0:
            err = mt5.last_error()
            log.warning(f"  No bar data for {symbol} {timeframe} (error: {err})")
            return None
        df = pd.DataFrame(rates)
        log.info(f"  copy_rates_range fallback: {len(df)} bars")

    if df.empty:
        return None

    # Rename MT5 columns to our standard schema
    df = df.rename(columns={
        "time": "timestamp",
        "tick_volume": "volume",
    })
    # Convert epoch to datetime (UTC)
    df["time"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    # Ensure spread exists (some MT5 builds don't include it)
    if "spread" not in df.columns:
        df["spread"] = 0
    # Point value
    info = mt5.symbol_info(symbol)
    point = getattr(info, "point", 0.01) or 0.01 if info else 0.01
    df["point"] = point

    # Reorder columns
    cols = ["time", "timestamp", "open", "high", "low", "close", "volume", "spread", "point"]
    df = df[[c for c in cols if c in df.columns]]

    # Drop duplicates and sort
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    # Filter to requested date range
    if "time" in df.columns:
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        if start_ts.tzinfo is None:
            start_ts = start_ts.tz_localize("UTC")
        else:
            start_ts = start_ts.tz_convert("UTC")
        if end_ts.tzinfo is None:
            end_ts = end_ts.tz_localize("UTC")
        else:
            end_ts = end_ts.tz_convert("UTC")
        mask = (df["time"] >= start_ts) & (df["time"] <= end_ts)
        df = df.loc[mask]

    if df.empty:
        log.warning(f"  No bar data in range {start.date()} to {end.date()}")
        return None

    return df


def pull_ticks(mt5, symbol: str, start: datetime, end: datetime, max_ticks: int = 5_000_000) -> pd.DataFrame | None:
    """Pull tick data for a symbol using copy_ticks_range."""
    ticks = mt5.copy_ticks_range(symbol, start, end, mt5.COPY_TICKS_ALL)
    if ticks is None or len(ticks) == 0:
        return None

    df = pd.DataFrame(ticks)
    df = df.rename(columns={"time": "timestamp"})
    df = df[["timestamp", "bid", "ask"]].drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def store_parquet(df: pd.DataFrame, path: Path, force: bool = False) -> bool:
    """Store a DataFrame as parquet, merging with existing data if present."""
    if path.exists() and not force:
        # Merge: load existing, concatenate, deduplicate, sort
        try:
            existing = pd.read_parquet(path)
            df = pd.concat([existing, df], ignore_index=True)
            df = df.drop_duplicates(subset=["timestamp"] if "timestamp" in df.columns else ["time"])
            if "timestamp" in df.columns:
                df = df.sort_values("timestamp").reset_index(drop=True)
            elif "time" in df.columns:
                df = df.sort_values("time").reset_index(drop=True)
            log.info(f"  Merged with existing: {len(existing)} existing + {len(df) - len(existing)} new = {len(df)} total")
        except Exception as e:
            log.warning(f"  Could not merge with existing: {e}")

    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, compression="snappy")
    return True


def main():
    args = parse_args()
    symbols = [s.strip().upper() for s in (args.symbols.split(",") if args.symbols else TRADING_SYMBOLS)]
    timeframes = [s.strip().upper() for s in (args.timeframes.split(",") if args.timeframes else DEFAULT_TIMEFRAMES)]

    log.info(f"Broker: {args.broker}")
    log.info(f"Symbols: {symbols}")
    log.info(f"Timeframes: {timeframes}")
    log.info(f"Ticks: {args.ticks_days}d {'(skipped)' if args.skip_ticks else ''}")

    mt5, account = connect_mt5()
    base_path = Path("data/broker_data") / args.broker

    # ── pull bars ───────────────────────────────────────────────────
    if not args.skip_bars:
        log.info("=== Pulling bar data ===")
        # For live accounts, pull all available history
        # Use a start date far enough back; MT5 will return whatever it has
        start = datetime(2000, 1, 1, tzinfo=timezone.utc)
        end = datetime.now(timezone.utc)

        for base_sym in symbols:
            resolved = resolve_symbol_name(base_sym)
            if resolved is None:
                log.warning(f"  {base_sym}: not found in MT5 terminal, skipping")
                continue

            for tf in timeframes:
                path = base_path / base_sym / f"{tf}.parquet"
                if path.exists() and not args.force:
                    log.info(f"  {base_sym} {tf}: already exists ({path.name}), use --force to overwrite")
                    continue

                log.info(f"  Pulling {resolved} {tf} (stored as {base_sym})...")
                df = pull_bars(mt5, resolved, tf, start, end)
                if df is None or df.empty:
                    continue

                store_parquet(df, path, force=args.force)
                log.info(f"  Stored {len(df)} bars -> {path}")

    # ── pull ticks ──────────────────────────────────────────────────
    if not args.skip_ticks:
        log.info("=== Pulling tick data ===")
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=args.ticks_days)

        for base_sym in symbols:
            resolved = resolve_symbol_name(base_sym)
            if resolved is None:
                continue

            path = base_path / base_sym / "ticks.parquet"
            if path.exists() and not args.force:
                log.info(f"  {base_sym} ticks: already exists, use --force to overwrite")
                continue

            log.info(f"  Pulling {resolved} ticks ({args.ticks_days}d, stored as {base_sym})...")
            all_ticks = []
            chunk_start = start
            while chunk_start < end:
                chunk_end = min(chunk_start + timedelta(days=TICK_CHUNK_DAYS), end)
                log.info(f"    Chunk {chunk_start.date()} to {chunk_end.date()}...")
                df = pull_ticks(mt5, resolved, chunk_start, chunk_end)
                if df is not None and not df.empty:
                    all_ticks.append(df)
                    log.info(f"    Got {len(df)} ticks")
                else:
                    log.info(f"    No ticks in this chunk")
                chunk_start = chunk_end
                time.sleep(0.5)  # polite pause between chunks

            if all_ticks:
                combined = pd.concat(all_ticks, ignore_index=True)
                combined = combined.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
                store_parquet(combined, path, force=args.force)
                log.info(f"  Stored {len(combined)} ticks -> {path}")
            else:
                log.warning(f"  No tick data for {resolved}")

    mt5.shutdown()
    log.info("Done. MT5 connection closed.")


if __name__ == "__main__":
    main()
