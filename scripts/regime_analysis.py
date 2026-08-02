"""
Regime analysis (#50) — does a detectable regime separate winning months from losing?

BASELINE.md showed the technical confluence is profitable in only ~30% of months over
5 years. Before any more param tuning, this asks the honest question: do the PROFITABLE
months share a measurable REGIME (volatility band, trend strength/direction, range) that
we could GATE on? If yes -> add a gate. If no clear separator -> the entry edge isn't
there and needs rework (say so plainly).

Streamed from S3 (no local cache). For each sampled month it computes regime descriptors
from the SAME OHLCV used for the baseline, runs the unified confluence, and reports
month-PF alongside the regime features so the separation (or lack of it) is visible.

Run: python -m scripts.regime_analysis [SYMBOL] [TF] [MONTHS_STEP]
"""

from __future__ import annotations

import sys
import statistics
import pandas as pd

from src.strategies.confluence_signal import find_confluence_triggers, DEFAULT_CFG
from scripts.baseline_history import _stream_window_rows, _rows_to_df, _simulate


def _regime(m1: pd.DataFrame) -> dict:
    """Regime descriptors from a month of M1 OHLCV (all normalized, symbol-agnostic)."""
    close = m1["close"]; hi = m1["high"]; lo = m1["low"]
    ret = close.pct_change().dropna()
    px0, px1 = float(close.iloc[0]), float(close.iloc[-1])
    month_ret = (px1 / px0 - 1) * 100 if px0 else 0.0
    # realised volatility: annualised-ish stdev of 1m returns (bps)
    vol_bps = float(ret.std() * 1e4) if len(ret) else 0.0
    # ATR% of price (median true range / price)
    tr = (hi - lo).abs()
    atr_pct = float((tr.median() / close.median()) * 100) if close.median() else 0.0
    # trend strength: |net move| / sum of |bar moves| (0=choppy, 1=clean trend)
    moves = close.diff().abs().sum()
    trend_eff = abs(px1 - px0) / moves if moves else 0.0
    return {"month_ret_pct": round(month_ret, 1), "vol_bps": round(vol_bps, 1),
            "atr_pct": round(atr_pct, 3), "trend_efficiency": round(trend_eff, 3),
            "direction": "up" if month_ret > 0 else "down"}


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTC-USD"
    tf = sys.argv[2] if len(sys.argv) > 2 else "1m"
    step = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    from datetime import datetime, timezone
    from src.cryptorti import s3_client
    c = s3_client._client()
    key = f"data/history_bars/coinbase/{symbol}/{tf}/{symbol}_{tf}_historical.csv"
    head = c.get_object(Bucket=s3_client.BUCKET, Key=key, Range="bytes=0-200")["Body"].read().decode("utf-8", "replace")
    first_ts = head.splitlines()[1].split(",")[0]
    y0, m0 = int(first_ts[:4]), int(first_ts[5:7])
    now = datetime.now(timezone.utc)
    months = []
    y, m = y0, m0
    while (y, m) <= (now.year, now.month):
        months.append((y, m)); m += step
        while m > 12: m -= 12; y += 1
    cfg = dict(DEFAULT_CFG); cfg.update({"sl_atr": 3.0, "tp_rr": 0.7, "require_m5": True})
    print(f"Regime analysis {symbol} {tf}: {len(months)} months, streamed once...")
    buckets = _stream_window_rows(symbol, tf, set(months))

    rows_out = []
    for ym in months:
        rws = buckets.get(ym, [])
        if len(rws) < 500:
            continue
        m1 = _rows_to_df(rws)
        reg = _regime(m1)
        d = m1.copy(); d["_dt"] = pd.to_datetime(d["time"], unit="s", utc=True); d = d.set_index("_dt")
        def rs(rule):
            o = d.resample(rule).agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna().reset_index()
            o["time"] = o["_dt"].astype("int64")//10**9; return o[["time","open","high","low","close","volume"]]
        trg,_ = find_confluence_triggers(m1, rs("5min"), rs("15min"), cfg)
        r = _simulate(trg, m1, cfg)
        if not r or r["trades"] < 10:
            continue
        rows_out.append({"month": f"{ym[0]}-{ym[1]:02d}", "pf": r["profit_factor"],
                         "win": r["profit_factor"] >= 1.2 and r["expectancy"] > 0, **reg})

    if not rows_out:
        print("no months with enough data"); return
    win = [x for x in rows_out if x["win"]]; lose = [x for x in rows_out if not x["win"]]
    print(f"\n{'month':9} {'PF':>5} {'ret%':>6} {'vol_bps':>7} {'atr%':>6} {'trend_eff':>9} dir  win")
    for x in rows_out:
        print(f"{x['month']:9} {x['pf']:>5} {x['month_ret_pct']:>6} {x['vol_bps']:>7} {x['atr_pct']:>6} {x['trend_efficiency']:>9} {x['direction']:>4} {'WIN' if x['win'] else '.'}")

    def avg(g, k): return round(statistics.mean([x[k] for x in g]), 3) if g else 0
    print(f"\n=== SEPARATION: winning ({len(win)}) vs losing ({len(lose)}) months ===")
    for k in ("month_ret_pct", "vol_bps", "atr_pct", "trend_efficiency"):
        print(f"  {k:16} win avg {avg(win,k):>8}  |  lose avg {avg(lose,k):>8}")
    up_win = sum(1 for x in win if x['direction']=='up'); up_lose = sum(1 for x in lose if x['direction']=='up')
    print(f"  direction        win: {up_win}/{len(win)} up  |  lose: {up_lose}/{len(lose)} up")
    print("\nVERDICT: if winning months cluster on a descriptor (clear avg gap), gate on it; "
          "if the win/lose averages overlap, there is NO detectable regime edge and the entry needs rework.")


if __name__ == "__main__":
    main()
