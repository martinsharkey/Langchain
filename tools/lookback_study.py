"""
Lookback-window study — does reading N candles back actually help?

Owner's MT5 EAs read a variable number of candles back (5..1000) for the
indicators, and the best N differed by market/symbol — a FIXED N failed because it
wasn't adaptive. This tests that hypothesis on OUR real closed trades using the
WIDE per-entry windows captured at trade time (wide_osma/wide_bulls/wide_bears/
wide_macd in indicators_snapshot). For each trade and each N in WINDOWS it computes
the indicator slope over the last N bars AT ENTRY, then measures per symbol whether
that slope separates winners from losers. If the best N differs by symbol => a
fixed lookback fails => the window must be adaptive/tunable (owner's experience).

Requires trades captured AFTER the wide-window capture was added (older trades are
skipped). Read-only; writes tools/lookback_study_<ts>.txt.
"""
import os
import sys
import json
import sqlite3
import statistics as st
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

DB = os.path.join(REPO, "data", "trading_experience.db")
CUTOFF = os.getenv("LOOKBACK_CUTOFF", "2026-08-12T00:00")
WINDOWS = [5, 10, 20, 50, 100, 200]
OUT = os.path.join(REPO, "tools", f"lookback_study_{datetime.now():%Y%m%d_%H%M}.txt")

_lines = []
def rec(s=""):
    _lines.append(str(s)); print(s, flush=True)


def _slope(series, n):
    vals = [float(x) for x in series[-n:] if x is not None]
    if len(vals) < 2:
        return None
    return (vals[-1] - vals[0]) / (len(vals) - 1)


def main():
    c = sqlite3.connect(DB)
    rows = c.execute(
        "SELECT symbol, outcome, indicators_snapshot FROM trades "
        "WHERE outcome IN ('win','loss') AND indicators_snapshot IS NOT NULL "
        "AND timestamp>=? ORDER BY id DESC LIMIT 2000", (CUTOFF,)).fetchall()

    by_sym = {}
    n_wide = 0
    for sym, outcome, snap in rows:
        try:
            d = json.loads(snap)
        except Exception:
            continue
        if "wide_bulls" not in d:
            continue  # pre-capture trade
        n_wide += 1
        by_sym.setdefault(sym, {"win": [], "loss": []})[outcome].append(d)

    rec(f"===== LOOKBACK STUDY since {CUTOFF} — {n_wide} trades WITH wide capture =====")
    if n_wide < 20:
        rec(f"Only {n_wide} trades have the wide-window capture yet — accumulate more")
        rec("(the capture was just added; let the bot trade, then re-run). No verdict.")
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines))
        rec(f"written: {OUT}")
        return

    SERIES = {"osma": "wide_osma", "macd": "wide_macd",
              "bulls": "wide_bulls", "bears": "wide_bears"}
    for sym, groups in by_sym.items():
        nW, nL = len(groups["win"]), len(groups["loss"])
        if nW < 8 or nL < 8:
            rec(f"\n=== {sym}: too few ({nW}W/{nL}L) — skip ==="); continue
        rec(f"\n=== {sym}  ({nW}W / {nL}L) ===")
        rec(f"{'indicator':<8}{'N':<6}{'win-slope':<14}{'loss-slope':<14}{'gap':<12}{'best?'}")
        for ind, key in SERIES.items():
            best_n = None; best_gap = 0
            gaps = {}
            for n in WINDOWS:
                w = [_slope(d.get(key, []), n) for d in groups["win"]]
                l = [_slope(d.get(key, []), n) for d in groups["loss"]]
                w = [x for x in w if x is not None]; l = [x for x in l if x is not None]
                if not w or not l:
                    continue
                wm, lm = st.median(w), st.median(l)
                gap = wm - lm
                gaps[n] = (wm, lm, gap)
                if abs(gap) > abs(best_gap):
                    best_gap = gap; best_n = n
            for n in WINDOWS:
                if n in gaps:
                    wm, lm, gap = gaps[n]
                    mark = "  <== best-N" if n == best_n else ""
                    rec(f"{ind:<8}{n:<6}{round(wm,4):<14}{round(lm,4):<14}{round(gap,4):<12}{mark}")

    rec("\n--- VERDICT GUIDE ---")
    rec("If the best-N (largest winner/loser slope gap) DIFFERS across symbols or")
    rec("indicators, a fixed lookback cannot be optimal => the window must be")
    rec("adaptive/tunable per symbol (the owner's EA lesson, now measured).")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))
    rec(f"\nwritten: {OUT}")


if __name__ == "__main__":
    main()
