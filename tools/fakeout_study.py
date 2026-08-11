"""
Fakeout study — were our losing trades avoidable?

For every LOSING trade, tests two counterfactual filters against the captured
entry snapshot, and reports what fraction of losers each would have removed vs
how many WINNERS it would also have cost (the trade-off that matters):

  (1) POWER filter  — require entry-side power >= a threshold derived from the
      winners' own distribution (OsMA/ATR, dominant Bulls/Bears power/ATR).
      Answers: "were the losers just weak-power fakeouts?"

  (2) HTF filter    — require htf_alignment to agree with the trade direction.
      Answers: "would higher-timeframe alignment have filtered the fakeouts?"

  (3) COMBINED      — both together.

For each filter we print: losers removed, winners removed, and the resulting
win-rate — so we can see which lever actually separates fakeouts from real moves
WITHOUT starving the winners. Read-only.
"""

import os
import sys
import json
import sqlite3
import statistics as st
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(REPO, "data", "trading_experience.db")
CUTOFF = os.getenv("FORENSIC_CUTOFF", "2026-08-11T00:00")
OUT = os.path.join(REPO, "tools", f"fakeout_study_{datetime.now():%Y%m%d_%H%M}.txt")

_lines = []
def rec(s=""):
    _lines.append(str(s)); print(s, flush=True)


def _num(d, k):
    try:
        return float(d.get(k))
    except (TypeError, ValueError):
        return None


def _feat(snap, action):
    """Directional, ATR-normalised entry features for one trade."""
    atr = _num(snap, "atr") or 0.0
    o = _num(snap, "osma_closed")
    bulls = _num(snap, "bulls_power"); bears = _num(snap, "bears_power")
    htf = snap.get("htf_alignment")
    f = {"htf": htf, "action": action}
    if atr > 0:
        f["osma_atr"] = abs(o) / atr if o is not None else None
        # dominant-side power in the trade's direction, ATR-normalised
        if action == "buy":
            f["dom_atr"] = (bulls / atr) if bulls is not None else None
        else:
            f["dom_atr"] = (-bears / atr) if bears is not None else None
    return f


def _htf_agrees(htf, action):
    """htf_alignment may be a number (>0 bullish), or a label. Agree = same dir."""
    if htf is None:
        return None
    if isinstance(htf, (int, float)):
        if action == "buy":
            return htf > 0
        return htf < 0
    s = str(htf).lower()
    if action == "buy":
        return "bull" in s or "up" in s or s in ("1", "aligned", "long")
    return "bear" in s or "down" in s or s in ("-1", "short")


def main():
    c = sqlite3.connect(DB)
    rows = c.execute(
        "SELECT symbol,action,outcome,indicators_snapshot FROM trades "
        "WHERE indicators_snapshot IS NOT NULL AND outcome IN ('win','loss') "
        "AND timestamp>=? ORDER BY id DESC", (CUTOFF,)).fetchall()
    wins, losses = [], []
    for sym, action, outcome, snap in rows:
        try:
            d = json.loads(snap)
        except Exception:
            continue
        (wins if outcome == "win" else losses).append(_feat(d, action))
    nW, nL = len(wins), len(losses)
    rec(f"===== FAKEOUT STUDY since {CUTOFF} — {nW} winners, {nL} losers =====")
    if nW < 10 or nL < 10:
        rec("insufficient data"); open(OUT,"w").write("\n".join(_lines)); return

    base_wr = 100 * nW / (nW + nL)
    rec(f"baseline win-rate: {base_wr:.0f}%  ({nW}W/{nL}L)\n")

    # thresholds from the WINNERS' own medians (so we don't invent numbers)
    def med(rows, key):
        v = [r[key] for r in rows if r.get(key) is not None]
        return st.median(v) if v else None
    osma_thr = med(wins, "osma_atr")
    dom_thr = med(wins, "dom_atr")
    rec(f"winner-median thresholds: osma_atr>={osma_thr:.3f}  dom_atr>={dom_thr:.3f}")
    rec(f"(a filter KEEPS a trade only if it meets the threshold / HTF agrees)\n")

    def apply(filt):
        wk = sum(1 for r in wins if filt(r))       # winners kept
        lk = sum(1 for r in losses if filt(r))      # losers kept
        wr = 100 * wk / (wk + lk) if (wk + lk) else 0
        return wk, lk, wr

    def f_power(r):
        ok = True
        if osma_thr is not None:
            ok = ok and (r.get("osma_atr") is not None and r["osma_atr"] >= osma_thr)
        if dom_thr is not None:
            ok = ok and (r.get("dom_atr") is not None and r["dom_atr"] >= dom_thr)
        return ok

    def f_htf(r):
        a = _htf_agrees(r.get("htf"), r["action"])
        return bool(a)   # keep only if HTF agrees (None -> drop, conservative)

    def f_both(r):
        return f_power(r) and f_htf(r)

    for name, filt in (("(1) POWER (OsMA+dominant power >= winner median)", f_power),
                       ("(2) HTF alignment agrees with direction", f_htf),
                       ("(3) BOTH power + HTF", f_both)):
        wk, lk, wr = apply(filt)
        rec(f"{name}")
        rec(f"    winners kept {wk}/{nW} ({100*wk/nW:.0f}%)  "
            f"losers kept {lk}/{nL} ({100*lk/nL:.0f}%)  "
            f"-> win-rate {wr:.0f}%  (baseline {base_wr:.0f}%)")
        rec(f"    losers REMOVED: {nL-lk}  winners sacrificed: {nW-wk}")
        rec("")

    # HTF data availability sanity
    htf_known = sum(1 for r in (wins+losses) if r.get("htf") is not None)
    rec(f"htf_alignment present on {htf_known}/{nW+nL} trades "
        f"({100*htf_known/(nW+nL):.0f}%) — if low, HTF result is unreliable.")
    rec("\nREAD: the filter with the BEST win-rate lift for the FEWEST winners")
    rec("sacrificed is the lever to make tunable + prove in the optimiser.")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))
    rec(f"\nwritten: {OUT}")


if __name__ == "__main__":
    main()
