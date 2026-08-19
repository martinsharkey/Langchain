"""
onboard_symbol.py — GENERAL per-symbol onboarding (applies everything learned 2026-08-16).

Point it at ANY symbol; it derives that symbol's tradeable profile from its OWN data
(R5: structure is shared, magnitudes are symbol-specific), with the guardrails this
session's analysis taught us:

  * Use a LARGE weekday sample (up to 60k M1 = ~30 trading days), weekend excluded.
  * Entry set = fresh MACD-M1 zero-cross -> FIRST directionally-aligned OsMA cycle.
  * Robustness first: report SAMPLE SIZES, use MEDIAN + SPEARMAN (rank) so a few monster
    cycles can't manufacture a fake "edge" (the 1-week bears/ema edge vanished at 30d).
  * Only FLAG an indicator edge if |Spearman| >= 0.30 AND n >= 40 (else 'not significant').

Outputs, per direction (long/short) and per session (Asian/London/NY, UTC):
  EXIT:  broker SL = top-10% avg adverse; avg cycle move; BE(25%)/trail(20%)/add(40%) pts.
  QUALITY: net-positive setup rate (fav>adv) — the crude win-quality of the raw entry.
  EDGE:  which entry indicators (osma/bulls/bears/atr/ema) actually predict run size.

READ-ONLY. Run with the live bot STOPPED. Usage:
    python -m scripts.onboard_symbol BTCUSD
    python -m scripts.onboard_symbol XAUUSD-ECN GER40. --bars 60000
"""
from __future__ import annotations
import argparse
import statistics as st
from datetime import datetime, timezone
import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

import pandas as pd
import MetaTrader5 as mt5
from src.strategies.indicators import (osma as osma_fn, macd as macd_fn, atr as atr_fn,
                                       ema as ema_fn, bulls_power as bulls_fn,
                                       bears_power as bears_fn)

FAST, SLOW, SIG = 12, 26, 9
EMA_P, ATR_P, POW_P = 13, 14, 13
TOP_PCT = 0.10
BE_PCT, TRAIL_PCT, ADD_PCT = 0.25, 0.20, 0.40
EDGE_MIN_RHO, EDGE_MIN_N = 0.30, 40   # significance guardrails


def session_of(ts):
    from src.strategies.sessions import session_of as _canonical
    return _canonical(datetime.fromtimestamp(ts, timezone.utc).hour)


def is_weekday(ts):
    return datetime.fromtimestamp(ts, timezone.utc).weekday() < 5


def segment_cycles(osma):
    cy, start = [], 0
    cur = osma.iloc[0] > 0
    for i in range(1, len(osma)):
        lng = osma.iloc[i] > 0
        if lng != cur:
            if i - start >= 2:
                cy.append((start, i, cur))
            start, cur = i, lng
    if len(osma) - start >= 2:
        cy.append((start, len(osma), cur))
    return cy


def macd_crosses(macd):
    out = []
    for i in range(1, len(macd)):
        p, n = macd.iloc[i - 1], macd.iloc[i]
        if p <= 0 < n:
            out.append((i, +1))
        elif p >= 0 > n:
            out.append((i, -1))
    return out


def spearman(xs, ys):
    pts = [(x, y) for x, y in zip(xs, ys) if x is not None and x == x and y == y]
    if len(pts) < 4:
        return None
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for rank, i in enumerate(order):
            r[i] = rank
        return r
    xr, yr = ranks([p[0] for p in pts]), ranks([p[1] for p in pts])
    n = len(xr)
    mx, my = sum(xr) / n, sum(yr) / n
    sx = sum((a - mx) ** 2 for a in xr) ** .5
    sy = sum((a - my) ** 2 for a in yr) ** .5
    if sx == 0 or sy == 0:
        return None
    return sum((xr[i] - mx) * (yr[i] - my) for i in range(n)) / (sx * sy)


def build_entries(symbol, bars):
    mt5.symbol_select(symbol, True)
    info = mt5.symbol_info(symbol)
    pt = (info.point if info and info.point else 0.01)
    raw = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, bars)
    if raw is None or len(raw) < 500:
        return None, pt, None
    df = pd.DataFrame(raw)
    close = df["close"]
    osma = osma_fn(close, FAST, SLOW, SIG).reset_index(drop=True)
    macd = macd_fn(close, FAST, SLOW, SIG)[0].reset_index(drop=True)
    ema = ema_fn(close, EMA_P).reset_index(drop=True)
    atr = atr_fn(df, ATR_P).reset_index(drop=True)
    bulls = bulls_fn(df, POW_P).reset_index(drop=True)
    bears = bears_fn(df, POW_P).reset_index(drop=True)
    hi, lo, cl, tm = df["high"].values, df["low"].values, close.values, df["time"].values

    cycles = segment_cycles(osma)
    crosses = macd_crosses(macd)
    used, entries = set(), []
    for cidx, cdir in crosses:
        for k in range(len(cycles)):
            a, b, is_long = cycles[k]
            if k in used or a < cidx:
                continue
            aligned = (is_long and cdir > 0) or ((not is_long) and cdir < 0)
            if aligned:
                used.add(k)
                ts = int(tm[a])
                if not is_weekday(ts):
                    break
                entry = cl[a]
                seg_hi, seg_lo = max(hi[a:b]), min(lo[a:b])
                fav = (seg_hi - entry) / pt if is_long else (entry - seg_lo) / pt
                adv = (entry - seg_lo) / pt if is_long else (seg_hi - entry) / pt
                eslope = float(ema.iloc[a] - ema.iloc[a - 3]) if a >= 3 else 0.0
                entries.append(dict(
                    side="long" if is_long else "short", sess=session_of(ts),
                    fav=fav, adv=adv, osma=float(osma.iloc[a]), bulls=float(bulls.iloc[a]),
                    bears=float(bears.iloc[a]), atr=float(atr.iloc[a]), ema=eslope))
            break
    span = (datetime.fromtimestamp(int(tm[0]), timezone.utc),
            datetime.fromtimestamp(int(tm[-1]), timezone.utc))
    return entries, pt, span


def exit_block(rows):
    if not rows:
        return None
    adv = sorted((r["adv"] for r in rows), reverse=True)
    k = max(1, int(len(adv) * TOP_PCT))
    sl = st.mean(adv[:k])
    avg_move = st.mean(r["fav"] for r in rows)
    med_move = st.median(r["fav"] for r in rows)
    return dict(sl=round(sl), avg=round(avg_move), med=round(med_move),
                be=round(avg_move * BE_PCT), trail=round(avg_move * TRAIL_PCT),
                add=round(avg_move * ADD_PCT))


def edges(rows):
    """Spearman of each indicator vs favourable move; flag only if significant."""
    out = {}
    fav = [r["fav"] for r in rows]
    for ind in ("osma", "bulls", "bears", "atr", "ema"):
        rho = spearman([r[ind] for r in rows], fav)
        sig = rho is not None and abs(rho) >= EDGE_MIN_RHO and len(rows) >= EDGE_MIN_N
        out[ind] = (rho, sig)
    return out


def report(symbol, bars):
    entries, pt, span = build_entries(symbol, bars)
    if entries is None:
        print(f"=== {symbol}: insufficient data ==="); return
    print(f"===== {symbol}  ({span[0].date()}..{span[1].date()}, weekday-only, "
          f"point={pt}, {len(entries)} entries) =====")
    for side in ("long", "short"):
        ss = [r for r in entries if r["side"] == side]
        e = exit_block(ss)
        if not e:
            print(f"  {side.upper()}: no entries"); continue
        npos = sum(1 for r in ss if r["fav"] > r["adv"])
        print(f"  {side.upper()}: n={len(ss)}  net-positive {npos}/{len(ss)} "
              f"({100*npos/len(ss):.0f}%)  | avg move {e['avg']} / median {e['med']} pts")
        print(f"    EXIT: broker SL {e['sl']}pt  BE {e['be']} / trail {e['trail']} / "
              f"add-leg {e['add']} pts")
        eg = edges(ss)
        flagged = [f"{k} {v[0]:+.2f}" for k, v in eg.items() if v[1]]
        weak = [f"{k} {v[0]:+.2f}" for k, v in eg.items() if not v[1] and v[0] is not None]
        print(f"    EDGE (Spearman vs run size): "
              f"{'SIGNIFICANT: ' + ', '.join(flagged) if flagged else 'none significant'}")
        print(f"           (weak/ns: {', '.join(weak)})")
        # session ranking by net-positive rate (min 15 samples)
        srows = {}
        for s in ("Asian", "London", "NewYork"):
            g = [r for r in ss if r["sess"] == s]
            if len(g) >= 15:
                srows[s] = (len(g), sum(1 for r in g if r["fav"] > r["adv"]) / len(g),
                            st.median(r["fav"] for r in g))
        if srows:
            best = max(srows.items(), key=lambda kv: kv[1][1])
            rank = " | ".join(f"{s}: {v[1]*100:.0f}% (n={v[0]}, med {v[2]:.0f})"
                              for s, v in sorted(srows.items(), key=lambda kv: -kv[1][1]))
            print(f"    SESSION (net-positive rate): {rank}  -> best: {best[0]}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", default=["BTCUSD"])
    ap.add_argument("--bars", type=int, default=60000)
    args = ap.parse_args()
    if not mt5.initialize():
        print("MT5 init failed:", mt5.last_error()); return
    ai = mt5.account_info()
    print(f"account {ai.login} {ai.server}  |  onboarding analysis, up to {args.bars} M1 bars\n")
    for s in (args.symbols or ["BTCUSD"]):
        report(s, args.bars)
    mt5.shutdown()


if __name__ == "__main__":
    main()
