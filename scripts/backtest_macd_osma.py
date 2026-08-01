"""
BTCUSD MACD-then-OsMA MTF backtest (trader's pattern).

Tests the exact trigger the trader described:
  M1 MACD line crosses ZERO first, then M1 OsMA crosses zero the SAME direction
  shortly after (MACD leads, OsMA confirms), with optional M5/M15 MACD ALIGNMENT.

For every trigger it simulates the outcome across SL/TP variations (in ATR units)
so we can separate ENTRY edge from EXIT tuning — i.e. answer "is the signal good but
the stop too tight?" vs "is the entry itself wrong?".

Run:  python -m scripts.backtest_macd_osma  [SYMBOL]  [BARS]
Prints per-variation win rate / profit factor / expectancy and the best cell.
Purely offline analysis; places no orders.
"""

from __future__ import annotations

import sys
import pandas as pd

from src.mt5.data import get_rates
from src.strategies.indicators import macd as macd_fn, osma as osma_fn, atr as atr_fn


def _series(rates, fast=12, slow=26, sig=9):
    df = pd.DataFrame(rates)
    close = df["close"]
    macd_line, macd_signal, _ = macd_fn(close, fast, slow, sig)
    osma = osma_fn(close, fast, slow, sig)
    a = atr_fn(df, 14)
    return df, macd_line.reset_index(drop=True), osma.reset_index(drop=True), a.reset_index(drop=True)


def _macd_side_at(ts, htf_df, htf_macd):
    """Sign of the HTF MACD line at/just before the M1 timestamp ts (+1/-1/0)."""
    idx = htf_df.index[htf_df["time"] <= ts]
    if len(idx) == 0:
        return 0
    v = htf_macd.iloc[idx[-1]] if idx[-1] < len(htf_macd) else 0
    return 1 if v > 0 else (-1 if v < 0 else 0)


def find_triggers(m1_rates, m5_rates, m15_rates, macd_lead_bars=5):
    """Return list of trigger dicts: M1 MACD zero-cross THEN M1 OsMA zero-cross same dir."""
    df1, macd1, osma1, atr1 = _series(m1_rates)
    df5, macd5, _o5, _a5 = _series(m5_rates)
    df15, macd15, _o15, _a15 = _series(m15_rates)
    triggers = []
    for i in range(30, len(df1) - 1):
        # M1 OsMA zero-cross on this bar
        cu = osma1[i - 1] <= 0 < osma1[i]
        cd = osma1[i - 1] >= 0 > osma1[i]
        if not (cu or cd):
            continue
        direction = "buy" if cu else "sell"
        # did M1 MACD cross zero the SAME direction within the preceding N bars (MACD LEADS)?
        lead = False
        for k in range(1, macd_lead_bars + 1):
            j = i - k
            if j < 1:
                break
            mu = macd1[j - 1] <= 0 < macd1[j]
            md = macd1[j - 1] >= 0 > macd1[j]
            if (direction == "buy" and mu) or (direction == "sell" and md):
                lead = True
                break
        if not lead:
            continue
        ts = df1["time"].iloc[i]
        m5_side = _macd_side_at(ts, df5, macd5)
        m15_side = _macd_side_at(ts, df15, macd15)
        want = 1 if direction == "buy" else -1
        triggers.append({
            "i": i, "direction": direction, "entry": float(df1["close"].iloc[i]),
            "atr": float(atr1[i] or 0),
            "m5_aligned": m5_side == want, "m15_aligned": m15_side == want,
        })
    return triggers, df1


def simulate(triggers, df1, sl_atr, tp_atr, require_m5=False, require_m15=False, max_hold=60):
    wins = losses = 0
    gross_w = gross_l = 0.0
    closes = df1["close"].values
    highs = df1["high"].values
    lows = df1["low"].values
    n = len(closes)
    for t in triggers:
        if require_m5 and not t["m5_aligned"]:
            continue
        if require_m15 and not t["m15_aligned"]:
            continue
        atr = t["atr"]
        if atr <= 0:
            continue
        i = t["i"]
        entry = t["entry"]
        if t["direction"] == "buy":
            sl = entry - sl_atr * atr; tp = entry + tp_atr * atr
        else:
            sl = entry + sl_atr * atr; tp = entry - tp_atr * atr
        outcome = None
        for k in range(i + 1, min(i + 1 + max_hold, n)):
            hi, lo = highs[k], lows[k]
            if t["direction"] == "buy":
                if lo <= sl: outcome = -sl_atr * atr; break
                if hi >= tp: outcome = tp_atr * atr; break
            else:
                if hi >= sl: outcome = -sl_atr * atr; break
                if lo <= tp: outcome = tp_atr * atr; break
        if outcome is None:
            outcome = (closes[min(i + max_hold, n - 1)] - entry) * (1 if t["direction"] == "buy" else -1)
        if outcome > 0: wins += 1; gross_w += outcome
        else: losses += 1; gross_l += abs(outcome)
    n_tr = wins + losses
    if n_tr == 0:
        return None
    pf = gross_w / gross_l if gross_l > 0 else (gross_w or 0)
    return {"trades": n_tr, "win_rate": round(wins / n_tr * 100, 1),
            "profit_factor": round(pf, 2), "expectancy": round((gross_w - gross_l) / n_tr, 2)}


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSD"
    bars = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    # ensure MT5 is connected (standalone script — the engine normally does this)
    try:
        from src.mt5.connector import get_connector
        get_connector().initialize()
    except Exception as e:
        print(f"MT5 init failed: {e}")
    print(f"Fetching {symbol} M1/M5/M15 ({bars} M1 bars)...")
    m1 = get_rates(symbol, timeframe="M1", count=bars)
    m5 = get_rates(symbol, timeframe="M5", count=max(bars // 5, 500))
    m15 = get_rates(symbol, timeframe="M15", count=max(bars // 15, 400))
    if not m1 or not m5 or not m15 or len(m1) < 100:
        print("Could not fetch rates (MT5 not connected, or the live bot holds the "
              "single MT5 connection). Stop the bot first, or run this inside the bot process.")
        return
    triggers, df1 = find_triggers(m1, m5, m15)
    print(f"\nFound {len(triggers)} MACD-then-OsMA M1 triggers "
          f"({sum(t['m5_aligned'] for t in triggers)} M5-aligned, "
          f"{sum(t['m15_aligned'] for t in triggers)} M15-aligned)\n")

    print(f"{'filter':16} {'sl_atr':>6} {'tp_atr':>6} {'trades':>7} {'WR%':>6} {'PF':>6} {'exp':>7}")
    best = None
    for label, rm5, rm15 in [("all", False, False), ("m5_aligned", True, False),
                             ("m5+m15", True, True)]:
        for sl_atr in (0.5, 1.0, 1.5, 2.0):
            for tp_atr in (1.0, 2.0, 3.0):
                r = simulate(triggers, df1, sl_atr, tp_atr, rm5, rm15)
                if not r:
                    continue
                print(f"{label:16} {sl_atr:6.1f} {tp_atr:6.1f} {r['trades']:7d} "
                      f"{r['win_rate']:6.1f} {r['profit_factor']:6.2f} {r['expectancy']:7.2f}")
                if r["trades"] >= 20 and (best is None or r["profit_factor"] > best[1]["profit_factor"]):
                    best = (f"{label} sl{sl_atr} tp{tp_atr}", r)
    if best:
        print(f"\nBEST (>=20 trades): {best[0]} -> {best[1]}")


if __name__ == "__main__":
    main()
