"""
Whale-order -> 1m-candle correlation study (#43/#46) — VALIDATION ONLY.

Uses Danny's S3 whale-event history (deposits/withdrawals with amount_usd + µs
timestamps) purely to VALIDATE the trader's observed pattern: a large whale order
(~$6M, broken into ~$1M chunks) prints ~6 large 1-minute BTCUSD candles in a window
after the event. For each large whale event we pull MT5 M1 BTC candles around the
event timestamp and measure the candle RESPONSE (how many large candles, net move
in points/bps, direction vs event), then aggregate across events/dates to see if the
pattern REPEATS. Output is catalogued to data/whale_candle_study.json for review.

This is the "compare Danny's data with MT5 candle telemetry on the same date" step,
so we can learn how best to act on live WebSocket whale signals.

Run: python -m scripts.whale_candle_study [MIN_USD] [WINDOW_MIN]
Requires: S3 access (Danny) + MT5 (BTCUSD M1). Run with the live bot stopped.
"""

from __future__ import annotations

import os
import sys
import json
import statistics
from datetime import datetime, timedelta, timezone


def _mt5_day(date_str, mt5):
    """Load a full UTC day of BTC M1 once (cached per date)."""
    import pandas as pd
    d0 = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    r = mt5.copy_rates_range("BTCUSD", mt5.TIMEFRAME_M1, d0 - timedelta(hours=1),
                             d0 + timedelta(days=1, hours=1))
    if r is None or len(r) == 0:
        return None
    df = pd.DataFrame(r)
    df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df


def _candle_response(day_df, event_dt, window_min):
    """Measure the M1 candle response in the window AFTER the event (in-memory slice)."""
    if day_df is None or day_df.empty:
        return None
    from datetime import timedelta as _td
    post = day_df[(day_df["dt"] >= event_dt) & (day_df["dt"] <= event_dt + _td(minutes=window_min))]
    if len(post) < 3:
        return None
    ranges = (post["high"] - post["low"]).abs()
    median_range = float(ranges.median()) or 1e-9
    large = int((ranges >= 1.8 * median_range).sum())
    net_move = float(post["close"].iloc[-1] - post["open"].iloc[0])
    entry_px = float(post["open"].iloc[0]) or 1e-9
    net_bps = net_move / entry_px * 1e4
    max_up = float(post["high"].max() - post["open"].iloc[0])
    max_dn = float(post["open"].iloc[0] - post["low"].min())
    return {"bars": len(post), "large_candles": large,
            "net_move_pts": round(net_move, 1), "net_bps": round(net_bps, 1),
            "max_up_pts": round(max_up, 1), "max_dn_pts": round(max_dn, 1),
            "median_range_pts": round(median_range, 1)}


def _cached_whale_events(date_str):
    """Load whale events for a date, caching Danny's S3 pull locally (slow network)."""
    import pandas as pd
    try:
        from src import config
        cdir = os.path.join(config.DATA_DIR, "whale_cache")
    except Exception:
        cdir = "whale_cache"
    os.makedirs(cdir, exist_ok=True)
    cpath = os.path.join(cdir, f"whale_events_{date_str}.parquet")
    if os.path.exists(cpath):
        try:
            return pd.read_parquet(cpath)
        except Exception:
            pass
    from src.cryptorti import s3_client
    ev = s3_client.load_whale_events(date_str)
    if ev is not None and len(ev):
        try:
            ev.to_parquet(cpath)
        except Exception:
            pass
    return ev


def main():
    from src.cryptorti import s3_client
    min_usd = float(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    window_min = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    only_dates = sys.argv[3].split(",") if len(sys.argv) > 3 else None
    if not s3_client.available():
        print("S3 not available (need Danny's CryptoRTI creds/certs).")
        return

    dates = only_dates or s3_client.list_whale_event_dates()
    print(f"Whale-event dates: {dates}. Scanning for events >= ${min_usd:,.0f} ...", flush=True)
    import MetaTrader5 as mt5
    mt5.initialize(); mt5.symbol_select("BTCUSD", True)
    results = []
    for d in dates:
        ev = _cached_whale_events(d)
        if ev is None or len(ev) == 0:
            continue
        big = ev[ev["amount_usd"] >= min_usd]
        print(f"  {d}: {len(ev)} events, {len(big)} >= ${min_usd:,.0f}", flush=True)
        if len(big) == 0:
            continue
        day_df = _mt5_day(d, mt5)   # load MT5 M1 for this date ONCE
        if day_df is None:
            continue
        for _, row in big.iterrows():
            try:
                event_dt = datetime.fromtimestamp(int(row["timestamp"]) / 1e6, tz=timezone.utc)
            except Exception:
                continue
            resp = _candle_response(day_df, event_dt, window_min)
            if not resp:
                continue
            direction = "sell" if row.get("event_type") == "deposit" else "buy"
            moved_right = (direction == "sell" and resp["net_move_pts"] < 0) or \
                          (direction == "buy" and resp["net_move_pts"] > 0)
            results.append({
                "date": d, "time": event_dt.isoformat(), "exchange": row.get("exchange"),
                "event_type": row.get("event_type"), "amount_usd": round(float(row["amount_usd"])),
                "expected_dir": direction, "moved_right": bool(moved_right), **resp,
            })
    if not results:
        print("No large whale events with overlapping MT5 M1 data found (S3 vs MT5 dates may not align).")
        return

    # aggregate: does the pattern repeat?
    n = len(results)
    right = sum(1 for r in results if r["moved_right"])
    large_counts = [r["large_candles"] for r in results]
    print(f"\n=== {n} large whale events with MT5 candle data ===")
    print(f"  moved in EXPECTED direction: {right}/{n} = {right/n*100:.0f}%")
    print(f"  large 1m candles in {window_min}m window: median {statistics.median(large_counts)}, "
          f"mean {statistics.mean(large_counts):.1f} (trader's observation: ~6 for ~$6M)")
    # bucket by size to test the ~$6M -> ~6 candles claim
    print("  by size bucket:")
    for lo, hi, label in [(1e6, 3e6, "$1-3M"), (3e6, 6e6, "$3-6M"), (6e6, 1e12, ">=$6M")]:
        b = [r for r in results if lo <= r["amount_usd"] < hi]
        if b:
            print(f"    {label:7} n={len(b):3} avg_large_candles={statistics.mean([x['large_candles'] for x in b]):.1f} "
                  f"moved_right={sum(1 for x in b if x['moved_right'])/len(b)*100:.0f}% "
                  f"avg_net_bps={statistics.mean([x['net_bps'] for x in b]):.0f}")

    try:
        from src import config
        p = os.path.join(config.DATA_DIR, "whale_candle_study.json")
    except Exception:
        p = "whale_candle_study.json"
    json.dump({"min_usd": min_usd, "window_min": window_min, "n_events": n,
               "moved_right_pct": round(right / n * 100, 1), "events": results,
               "run_at": datetime.now(timezone.utc).isoformat()}, open(p, "w"), indent=2, default=str)
    print(f"\nCatalogued to {p}")


if __name__ == "__main__":
    main()
