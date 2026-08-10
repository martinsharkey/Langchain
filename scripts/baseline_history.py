"""
Long-history baseline (#47) — STREAMED from S3, no local storage.

Constraint: the 5-year OHLCV CSVs are large (BTC 1m ~195MB) and Danny keeps them in
S3 precisely so we DON'T store them locally. This harness STREAMS the history from
S3 in bounded chunks (never writes the full file to disk, never holds it all in
memory beyond a rolling need) and re-baselines the UNIFIED confluence across the
full 2021->2026 span, per year, so we always know where we stand.

Approach: read the CSV via the S3 streaming body, parse rows lazily, and process
one BOUNDED date-window at a time (default: sample every Nth month across the span
+ optionally the last M months), running the shared confluence + a simple exit sim
on each window, then discard it. Writes a durable data/history_baseline.json.

Run: python -m scripts.baseline_history [SYMBOL] [TF] [MONTHS_STEP]
Needs S3 creds only (no MT5, no local cache).
"""

from __future__ import annotations

import os
import sys
import io
import csv
import json
import statistics
from datetime import datetime, timezone

import pandas as pd

from src.strategies.confluence_signal import find_confluence_triggers, DEFAULT_CFG


def _stream_window_rows(symbol, tf, want_year_month: set):
    """Yield rows (dicts) for the requested (year, month) buckets by STREAMING the
    S3 CSV line-by-line — never downloads/holds the whole file. Rows are chronological."""
    from src.cryptorti import s3_client
    c = s3_client._client()
    key = f"data/history_bars/coinbase/{symbol}/{tf}/{symbol}_{tf}_historical.csv"
    body = c.get_object(Bucket=s3_client.BUCKET, Key=key)["Body"]
    reader = csv.reader(io.TextIOWrapper(body, encoding="utf-8"))
    header = next(reader, None)
    buckets = {ym: [] for ym in want_year_month}
    for row in reader:
        if not row or len(row) < 5:
            continue
        ts = row[0]
        ym = (int(ts[:4]), int(ts[5:7]))
        if ym in buckets:
            buckets[ym].append(row)
    return buckets


def _rows_to_df(rows):
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["timestamp"], utc=True).astype("int64") // 10**9
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna().reset_index(drop=True)


def _simulate(triggers, df, cfg, max_hold=120):
    highs = df["high"].values; lows = df["low"].values; closes = df["close"].values
    n = len(closes); sl_atr = cfg["sl_atr"]; tp_atr = cfg["sl_atr"] * cfg["tp_rr"]
    wins = losses = 0; gw = gl = 0.0
    for t in triggers:
        i = t["i"]; atr = t["atr"]
        if atr <= 0:
            continue
        entry = t["entry"]; buy = t["direction"] == "buy"
        sl = entry - sl_atr * atr if buy else entry + sl_atr * atr
        tp = entry + tp_atr * atr if buy else entry - tp_atr * atr
        res = None
        for k in range(i + 1, min(i + 1 + max_hold, n)):
            if buy:
                if lows[k] <= sl: res = -sl_atr * atr; break
                if highs[k] >= tp: res = tp_atr * atr; break
            else:
                if highs[k] >= sl: res = -sl_atr * atr; break
                if lows[k] <= tp: res = tp_atr * atr; break
        if res is None:
            res = (closes[min(i + max_hold, n - 1)] - entry) * (1 if buy else -1)
        if res > 0: wins += 1; gw += res
        else: losses += 1; gl += abs(res)
    ntr = wins + losses
    if ntr == 0:
        return None
    return {"trades": ntr, "win_rate": round(wins / ntr * 100, 1),
            "profit_factor": round(gw / gl, 2) if gl else (gw or 0),
            "expectancy": round((gw - gl) / ntr, 2)}




def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTC-USD"
    tf = sys.argv[2] if len(sys.argv) > 2 else "1m"
    step = int(sys.argv[3]) if len(sys.argv) > 3 else 3   # sample every Nth month
    cfg = dict(DEFAULT_CFG); cfg.update({"sl_atr": 3.0, "tp_rr": 0.7, "require_m5": True})

    # discover the span cheaply: first + last timestamp via ranged GET
    from src.cryptorti import s3_client
    c = s3_client._client()
    key = f"data/history_bars/coinbase/{symbol}/{tf}/{symbol}_{tf}_historical.csv"
    head = c.get_object(Bucket=s3_client.BUCKET, Key=key, Range="bytes=0-200")["Body"].read().decode("utf-8", "replace")
    first_ts = head.splitlines()[1].split(",")[0]
    y0, m0 = int(first_ts[:4]), int(first_ts[5:7])
    now = datetime.now(timezone.utc); y1, m1_ = now.year, now.month
    # sampled (year,month) buckets across the span, every `step` months
    months = []
    y, m = y0, m0
    while (y, m) <= (y1, m1_):
        months.append((y, m)); m += step
        while m > 12: m -= 12; y += 1
    print(f"Baselining {symbol} {tf} across {first_ts[:7]}..{y1}-{m1_:02d} "
          f"({len(months)} sampled months, every {step}) — streamed ONCE, no local cache")

    # SINGLE streaming pass: collect all sampled months' rows in one read of the S3 body
    buckets = _stream_window_rows(symbol, tf, set(months))

    per_month = {}
    for ym in months:
        rows = buckets.get(ym, [])
        if len(rows) < 500:
            continue
        try:
            m1 = _rows_to_df(rows)
            def resample(df, rule):
                d = df.copy()
                d["_dt"] = pd.to_datetime(d["time"], unit="s", utc=True)
                d = d.set_index("_dt")
                o = d.resample(rule).agg({"open": "first", "high": "max", "low": "min",
                                          "close": "last", "volume": "sum"}).dropna()
                o = o.reset_index()
                o["time"] = o["_dt"].astype("int64") // 10**9
                return o[["time", "open", "high", "low", "close", "volume"]]
            m5 = resample(m1, "5min"); m15 = resample(m1, "15min")
            trg, _ = find_confluence_triggers(m1, m5, m15, cfg)
            r = _simulate(trg, m1, cfg)
        except Exception as e:
            print(f"  {ym[0]}-{ym[1]:02d}: skip ({str(e)[:50]})"); continue
        if not r:
            continue
        per_month[f"{ym[0]}-{ym[1]:02d}"] = {**r, "triggers": len(trg)}
        print(f"  {ym[0]}-{ym[1]:02d}: PF {r['profit_factor']} WR {r['win_rate']}% "
              f"exp {r['expectancy']} n {r['trades']} (triggers {len(trg)})")

    # aggregate across sampled months (regime-agnostic robustness)
    pfs = [v["profit_factor"] for v in per_month.values() if v["trades"] >= 10]
    passes = sum(1 for v in per_month.values() if v["trades"] >= 10 and v["profit_factor"] >= 1.2 and v["expectancy"] > 0)
    baseline = {
        "symbol": symbol, "tf": tf, "span": f"{first_ts[:7]}..{y1}-{m1_:02d}",
        "config": cfg, "months_sampled": len(per_month),
        "pass_rate": round(passes / len(pfs), 2) if pfs else 0,
        "median_pf": round(statistics.median(pfs), 2) if pfs else 0,
        "per_month": per_month, "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    p = os.path.join("data", "history_baseline.json")
    json.dump(baseline, open(p, "w"), indent=2, default=str)
    print(f"\n=== {symbol} {tf} LONG-HISTORY BASELINE ===")
    print(f"  sampled months: {len(per_month)} | pass_rate {baseline['pass_rate']} | median PF {baseline['median_pf']}")
    print(f"  written -> {p} (durable; commit to record where we stand)")


if __name__ == "__main__":
    main()
