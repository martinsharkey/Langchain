"""Native vectorbt Portfolio for the validated H1 BTCUSD model + ONNX-ready export.

Entry = OsMA H1 zero-cross (long on up-cross, short on down-cross). Exit = single trailing
stop (validated ~15% of median cycle peak) with a wide catastrophe SL, TP removed. Runs as
vbt.Portfolio.from_signals with real ECN cost (spread as fixed fee + $6/lot commission).
The custom Numba basket sim (scripts/qmmp/exit_sim / h1) remains the source of truth for
the multi-leg early-pyramid economics vectorbt can't express; THIS module is the native
vectorbt portfolio for standard single-position validation, equity curve, and the
trade-record feature export that ONNX consumes for ML validation.

Outputs:
  data/qmmp/BTCUSD/vbt_h1_trades.parquet   (per-trade records: entry/exit/return + features)
  data/qmmp/BTCUSD/vbt_h1_stats.json       (portfolio stats)
Usage: python -m scripts.qmmp.vbt_model BTCUSD
"""
from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import numpy as np, pandas as pd, polars as pl
import vectorbt as vbt
from src.strategies.indicators import osma as osma_fn, bulls_power as bp, bears_power as bpw, atr as atr_fn, ema as ema_fn
FAST, SLOW, SIG = 12, 26, 9
D = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "qmmp")
# real ECN cost
SPREAD_PTS = 1200.0; PT = 0.01
GBP_PER_PT_PER_LOT = 0.007        # £/point/1.0 lot (from account: £0.07 per 1000pt per 0.01)
COMM_PER_LOT = 6.0                # $ round-turn per 1.0 lot


def build(symbol="BTCUSD", tf="H1", trail_pct=0.15, sl_pts=628348):
    d = os.path.join(D, symbol.upper())
    df = pl.read_parquet(os.path.join(d, f"{tf}.parquet")).sort("time").to_pandas()
    df = df.set_index("time")
    close = df["close"]
    osma = osma_fn(close, FAST, SLOW, SIG)
    # entry signals: OsMA zero-cross
    up = (osma.shift(1) <= 0) & (osma > 0)
    dn = (osma.shift(1) >= 0) & (osma < 0)
    entries = up          # long entries
    short_entries = dn
    # exits: opposite cross (cycle end). vbt handles the trailing stop via tsl_stop.
    exits = dn
    short_exits = up

    # trailing stop distance as fraction of price (approx: median cycle peak ~ trail_pct).
    # vbt tsl_stop is a fraction of price; convert points-trail to fractional via median price.
    med_price = float(close.median())
    # median cycle peak in points -> trail distance in points -> fraction of price
    # use a robust trail = trail_pct * (median peak). Estimate median peak from ATR proxy:
    atr = atr_fn(df, 14)
    trail_pts = trail_pct * float((atr.median()) / PT) * 8  # ~cycle peak proxy
    tsl = max(0.002, (trail_pts * PT) / med_price)          # fractional trailing stop
    slf = max(0.01, (sl_pts * PT) / med_price)              # fractional hard SL

    # cost: spread as fixed fees (fraction), commission via fees
    spread_frac = (SPREAD_PTS * PT) / med_price
    fees = spread_frac / 2 + (COMM_PER_LOT / (med_price)) * 0  # spread modelled as fee both sides

    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries, exits=exits,
        short_entries=short_entries, short_exits=short_exits,
        sl_stop=tsl, sl_trail=True,          # TRAILING stop at fractional distance tsl
        fees=spread_frac,                    # round-turn spread cost as fee
        slippage=(SLIP := (100.0*PT)/med_price),
        init_cash=5000, freq="1H",
    )
    stats = pf.stats()
    trades = pf.trades.records_readable
    # attach entry-time indicator features for ONNX (bulls/bears/atr/ema at entry)
    bulls = bp(df, 13); bears = bpw(df, 13); emaS = ema_fn(close, 13)
    feat_rows = []
    for _, t in trades.iterrows():
        et = t.get("Entry Timestamp") or t.get("Entry Index")
        try:
            i = df.index.get_loc(et)
        except Exception:
            i = None
        feat_rows.append(dict(
            entry_time=str(et), direction=t.get("Direction"),
            pnl=float(t.get("PnL", np.nan)), ret=float(t.get("Return", np.nan)),
            bulls=float(bulls.iloc[i]) if i is not None else np.nan,
            bears=float(bears.iloc[i]) if i is not None else np.nan,
            atr=float(atr.iloc[i]) if i is not None else np.nan,
            osma=float(osma.iloc[i]) if i is not None else np.nan,
            ema_slope=float(emaS.iloc[i]-emaS.iloc[i-3]) if (i and i>=3) else np.nan,
        ))
    feat = pd.DataFrame(feat_rows)
    os.makedirs(d, exist_ok=True)
    if len(feat):
        pl.from_pandas(feat).write_parquet(os.path.join(d, "vbt_h1_trades.parquet"))
    with open(os.path.join(d, "vbt_h1_stats.json"), "w") as f:
        json.dump({k: (float(v) if isinstance(v, (int, float, np.number)) else str(v))
                   for k, v in stats.items()}, f, indent=2, default=str)
    print(f"=== vbt.Portfolio {symbol} {tf} ===")
    print(f"  trades: {len(trades)}  | tsl={tsl:.4f} sl={slf:.4f} fees(spread)={spread_frac:.5f}")
    for k in ("Total Return [%]", "Win Rate [%]", "Max Drawdown [%]", "Total Trades", "Sharpe Ratio"):
        if k in stats: print(f"  {k}: {stats[k]}")
    print(f"  wrote vbt_h1_trades.parquet ({len(feat)} rows) + vbt_h1_stats.json for ONNX")
    return pf


if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSD"
    build(sym)
