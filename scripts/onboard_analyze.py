"""
onboard_analyze.py — READ-ONLY per-symbol onboarding analysis (owner spec 2026-08-16).

Reads the last N (default 5000) M1 candles for a symbol, segments them into OsMA
cycles (long = OsMA > 0 span, short = OsMA < 0 span), and derives:

  EXIT (blunt, per-symbol):
    * broker SL for LONG entries  = top-10% average of the ADVERSE (downward) points
      travelled during LONG cycles (how far long cycles dip against you);
    * broker SL for SHORT entries = top-10% average of the ADVERSE (upward) points
      during SHORT cycles;
    * average cycle MOVEMENT (favourable floor->ceiling) per direction — the basis for
      the trailing %s: break-even at 25%, trail trigger ~20%, add-leg at 40%.

  ENTRY PROFILE (measured on the FIRST candle of each cycle, averaged):
    * osma candle size, bulls power, bears power, ATR (+direction), EMA (+direction),
      MACD M1 direction+strength, MACD M5 direction+strength — long and short.

Nothing is written or traded. Prints a per-symbol summary for review. Run with the
live bot STOPPED (single MT5 connection):
    python -m scripts.onboard_analyze
    python -m scripts.onboard_analyze BTCUSD 5000
"""
from __future__ import annotations

import sys
import statistics
from datetime import datetime, timezone

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

import pandas as pd
import MetaTrader5 as mt5

from src.strategies.indicators import osma as osma_fn, macd as macd_fn, atr as atr_fn, \
    ema as ema_fn, bulls_power as bulls_fn, bears_power as bears_fn

# indicator params (match live confluence defaults)
OSMA_FAST, OSMA_SLOW, OSMA_SIG = 12, 26, 9
EMA_PERIOD, ATR_PERIOD, POWER_PERIOD = 13, 14, 13
TOP_PCT = 0.10          # top-10% average for the SL
BE_PCT, TRAIL_PCT, ADD_PCT = 0.25, 0.20, 0.40   # of average cycle movement


def _bars_df(symbol, timeframe, count):
    mt5.symbol_select(symbol, True)
    bars = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if bars is None or len(bars) < 200:
        # fall back to an explicit wide range if from_pos is thin
        bars = mt5.copy_rates_range(symbol, timeframe,
                                    datetime(2026, 6, 1, tzinfo=timezone.utc),
                                    datetime.now(timezone.utc))
    if bars is None or len(bars) == 0:
        return None
    df = pd.DataFrame(bars)
    return df


def _point(symbol):
    info = mt5.symbol_info(symbol)
    return (info.point if info and info.point else 0.01)


def _segment_cycles(osma_series):
    """Return list of (start_idx, end_idx_exclusive, is_long) OsMA cycles = sign spans."""
    cycles = []
    n = len(osma_series)
    if n < 3:
        return cycles
    start = 0
    cur_long = osma_series.iloc[0] > 0
    for i in range(1, n):
        is_long = osma_series.iloc[i] > 0
        if is_long != cur_long:
            if i - start >= 2:
                cycles.append((start, i, cur_long))
            start = i
            cur_long = is_long
    if n - start >= 2:
        cycles.append((start, n, cur_long))
    return cycles


def analyze(symbol, count=5000):
    df_m1 = _bars_df(symbol, mt5.TIMEFRAME_M1, count)
    if df_m1 is None:
        return {"symbol": symbol, "error": "no M1 data"}
    df_m5 = _bars_df(symbol, mt5.TIMEFRAME_M5, max(1200, count // 5))
    pt = _point(symbol)

    close = df_m1["close"]
    high = df_m1["high"].values
    low = df_m1["low"].values
    closes = close.values
    osma_s = osma_fn(close, OSMA_FAST, OSMA_SLOW, OSMA_SIG).reset_index(drop=True)
    ema_s = ema_fn(close, EMA_PERIOD).reset_index(drop=True)
    atr_s = atr_fn(df_m1, ATR_PERIOD).reset_index(drop=True)
    bulls_s = bulls_fn(df_m1, POWER_PERIOD).reset_index(drop=True)
    bears_s = bears_fn(df_m1, POWER_PERIOD).reset_index(drop=True)
    macd_m1 = macd_fn(close, OSMA_FAST, OSMA_SLOW, OSMA_SIG)[0].reset_index(drop=True)
    # MACD M5 aligned onto M1 timestamps (as-of, causal): map each M1 time to the last M5 macd
    macd_m5_map = None
    if df_m5 is not None and len(df_m5) > 40:
        m5_line = macd_fn(df_m5["close"], OSMA_FAST, OSMA_SLOW, OSMA_SIG)[0].reset_index(drop=True)
        macd_m5_map = list(zip(df_m5["time"].values, m5_line.values))

    def macd_m5_at(ts):
        if not macd_m5_map:
            return None
        val = None
        for t, v in macd_m5_map:
            if t <= ts:
                val = v
            else:
                break
        return val

    cycles = _segment_cycles(osma_s)
    if len(cycles) < 5:
        return {"symbol": symbol, "error": f"only {len(cycles)} cycles"}

    long_fav, long_adv = [], []   # favourable(up) / adverse(down) points in LONG cycles
    short_fav, short_adv = [], []
    prof = {"long": _blank_profile(), "short": _blank_profile()}

    for a, b, is_long in cycles:
        entry = closes[a]
        seg_hi = max(high[a:b]); seg_lo = min(low[a:b])
        up_pts = (seg_hi - entry) / pt
        dn_pts = (entry - seg_lo) / pt
        if is_long:
            long_fav.append(up_pts); long_adv.append(dn_pts)
            side = "long"
        else:
            # short cycle: favourable = downward move, adverse = upward move
            short_fav.append(dn_pts); short_adv.append(up_pts)
            side = "short"
        # first-candle entry profile
        p = prof[side]
        p["osma"].append(abs(float(osma_s.iloc[a])))
        p["bulls"].append(float(bulls_s.iloc[a]))
        p["bears"].append(float(bears_s.iloc[a]))
        p["atr"].append(float(atr_s.iloc[a]))
        # ema direction: slope over prior 3 bars
        if a >= 3:
            p["ema_slope"].append(float(ema_s.iloc[a] - ema_s.iloc[a - 3]))
        p["macd_m1"].append(float(macd_m1.iloc[a]))
        m5v = macd_m5_at(df_m1["time"].iloc[a])
        if m5v is not None:
            p["macd_m5"].append(float(m5v))

    def top_pct_avg(vals):
        if not vals:
            return 0.0
        k = max(1, int(len(vals) * TOP_PCT))
        return statistics.mean(sorted(vals, reverse=True)[:k])

    # SL: long entries stopped by the adverse (down) move in long cycles; shorts by
    # the adverse (up) move in short cycles. Owner spec step 3 = top-10% average.
    sl_long = top_pct_avg(long_adv)
    sl_short = top_pct_avg(short_adv)
    avg_move_long = statistics.mean(long_fav) if long_fav else 0.0
    avg_move_short = statistics.mean(short_fav) if short_fav else 0.0

    return {
        "symbol": symbol, "point": pt, "m1_bars": len(df_m1),
        "n_cycles": len(cycles), "n_long": len(long_fav), "n_short": len(short_fav),
        "LONG": _exit_block(sl_long, avg_move_long),
        "SHORT": _exit_block(sl_short, avg_move_short),
        "long_profile": _avg_profile(prof["long"]),
        "short_profile": _avg_profile(prof["short"]),
    }


def _blank_profile():
    return {"osma": [], "bulls": [], "bears": [], "atr": [], "ema_slope": [],
            "macd_m1": [], "macd_m5": []}


def _avg_profile(p):
    def m(x):
        vals = [v for v in x if v is not None and v == v]  # drop None + NaN
        return round(statistics.mean(vals), 3) if vals else None
    return {
        "osma_candle": m(p["osma"]), "bulls": m(p["bulls"]), "bears": m(p["bears"]),
        "atr": m(p["atr"]), "ema_slope": m(p["ema_slope"]),
        "macd_m1": m(p["macd_m1"]), "macd_m5": m(p["macd_m5"]),
        "macd_m1_dir": _dir(m(p["macd_m1"])), "macd_m5_dir": _dir(m(p["macd_m5"])),
        "ema_dir": _dir(m(p["ema_slope"])),
    }


def _dir(v):
    if v is None:
        return "n/a"
    return "long" if v > 0 else ("short" if v < 0 else "flat")


def _exit_block(sl_pts, avg_move):
    return {
        "broker_sl_pts": round(sl_pts, 0),
        "avg_cycle_move_pts": round(avg_move, 0),
        "be_trigger_pts": round(avg_move * BE_PCT, 0),
        "trail_trigger_pts": round(avg_move * TRAIL_PCT, 0),
        "add_leg_at_pts": round(avg_move * ADD_PCT, 0),
    }


def main():
    args = sys.argv[1:]
    symbols = [a for a in args if not a.isdigit()] or ["BTCUSD", "XAUUSD-ECN", "GER40."]
    count = next((int(a) for a in args if a.isdigit()), 5000)
    if not mt5.initialize():
        print("MT5 init failed:", mt5.last_error()); return
    ai = mt5.account_info()
    print(f"account {ai.login} {ai.server}  |  reading last {count} M1 candles\n")
    for sym in symbols:
        r = analyze(sym, count)
        if r.get("error"):
            print(f"=== {sym}: {r['error']} ==="); continue
        print(f"===== {r['symbol']}  ({r['m1_bars']} M1 bars, {r['n_cycles']} OsMA cycles: "
              f"{r['n_long']} long / {r['n_short']} short, point={r['point']}) =====")
        for side in ("LONG", "SHORT"):
            e = r[side]
            print(f"  {side}: broker SL {e['broker_sl_pts']:.0f}pt | avg cycle move "
                  f"{e['avg_cycle_move_pts']:.0f}pt -> BE {e['be_trigger_pts']:.0f} / "
                  f"trail {e['trail_trigger_pts']:.0f} / add-leg {e['add_leg_at_pts']:.0f}")
        lp, sp = r["long_profile"], r["short_profile"]
        print(f"  LONG entry profile:  osma~{lp['osma_candle']} bulls~{lp['bulls']} "
              f"bears~{lp['bears']} atr~{lp['atr']} ema~{lp['ema_dir']} "
              f"macdM1~{lp['macd_m1']}({lp['macd_m1_dir']}) macdM5~{lp['macd_m5']}({lp['macd_m5_dir']})")
        print(f"  SHORT entry profile: osma~{sp['osma_candle']} bulls~{sp['bulls']} "
              f"bears~{sp['bears']} atr~{sp['atr']} ema~{sp['ema_dir']} "
              f"macdM1~{sp['macd_m1']}({sp['macd_m1_dir']}) macdM5~{sp['macd_m5']}({sp['macd_m5_dir']})")
        print()
    mt5.shutdown()


if __name__ == "__main__":
    main()
