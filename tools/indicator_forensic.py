"""
Indicator forensic — how to avoid fakeouts and capture more profit.

Reads the CAPTURED per-trade indicator snapshots (entry / peak / exit) from the
experience DB for recent trades and answers two questions with real numbers:

  FAKEOUTS  : what do LOSERS look like AT ENTRY vs WINNERS? Which indicator
              values/settings separate the fakeouts (e.g. weak OsMA vs ATR,
              stretched from EMA, MACD histogram already rolling, Bulls/Bears
              not dominant)? -> tighter entry thresholds that would have skipped
              the losers while keeping the winners.

  CAPTURE   : how much of the favourable move (MFE) did winners actually keep
              (exit_points / mfe_points)? Where did we exit vs the peak? -> is
              the leak early exits (low capture ratio) rather than bad entries?

Read-only. Prints a report + writes tools/indicator_forensic_<ts>.txt.
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
OUT = os.path.join(REPO, "tools", f"indicator_forensic_{datetime.now():%Y%m%d_%H%M}.txt")

# indicator fields we care about for fakeout separation
FIELDS = ["osma_closed", "osma_prev", "macd_line", "macd_signal", "macd_histogram",
          "bulls_power", "bears_power", "rsi", "atr", "ema_fast", "close",
          "adx", "cci", "stoch_k", "stoch_d", "williams_r"]

_lines = []
def rec(s=""):
    _lines.append(str(s)); print(s, flush=True)


def _load(snap):
    if not snap:
        return {}
    try:
        return json.loads(snap)
    except Exception:
        return {}


def _num(d, k):
    v = d.get(k)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _derived(snap):
    """Normalised, comparable features (ATR-scaled) from a raw entry snapshot."""
    atr = _num(snap, "atr") or 0.0
    o = _num(snap, "osma_closed"); op = _num(snap, "osma_prev")
    ml = _num(snap, "macd_line"); msig = _num(snap, "macd_signal")
    bulls = _num(snap, "bulls_power"); bears = _num(snap, "bears_power")
    close = _num(snap, "close"); ema = _num(snap, "ema_fast")
    f = {}
    if atr > 0:
        if o is not None: f["osma_atr"] = abs(o) / atr
        if o is not None and op is not None: f["osma_accel_atr"] = abs(o - op) / atr
        if bulls is not None: f["bulls_atr"] = bulls / atr
        if bears is not None: f["bears_atr"] = bears / atr
        if close is not None and ema is not None: f["stretch_atr"] = abs(close - ema) / atr
    if ml is not None and msig is not None:
        f["macd_hist"] = ml - msig
    f["rsi"] = _num(snap, "rsi")
    return f


def _summ(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return "n/a"
    vals.sort()
    med = st.median(vals)
    return f"med={med:.3f} mean={sum(vals)/len(vals):.3f} n={len(vals)}"


def main():
    if not os.path.exists(DB):
        rec(f"DB not found: {DB}"); return
    c = sqlite3.connect(DB)
    rows = c.execute(
        "SELECT symbol,action,outcome,mfe_points,mae_points,exit_points,"
        "indicators_snapshot FROM trades WHERE indicators_snapshot IS NOT NULL "
        "AND outcome IN ('win','loss') AND timestamp>=? ORDER BY id DESC", (CUTOFF,)
    ).fetchall()
    rec(f"===== INDICATOR FORENSIC since {CUTOFF} — {len(rows)} closed trades =====")
    if not rows:
        rec("no snapshotted trades in range"); open(OUT,"w").write("\n".join(_lines)); return

    by = {"win": [], "loss": []}
    capture = []   # winners: exit/mfe
    per_symbol = {}
    for (sym, action, outcome, mfe, mae, expts, snap) in rows:
        d = _load(snap); feat = _derived(d)
        by[outcome].append(feat)
        per_symbol.setdefault(sym, {"win": 0, "loss": 0})[outcome] += 1
        if outcome == "win" and mfe and mfe > 0 and expts is not None:
            capture.append(min(max(expts / mfe, 0.0), 1.5))

    # ── FAKEOUT SEPARATION: winners vs losers at ENTRY ──
    rec("\n--- ENTRY-SIGNAL STRENGTH: winners vs losers (ATR-normalised) ---")
    keys = ["osma_atr", "osma_accel_atr", "bulls_atr", "bears_atr", "stretch_atr",
            "macd_hist", "rsi"]
    rec(f"{'feature':<14} {'WINNERS':<34} {'LOSERS':<34}")
    seps = {}
    for k in keys:
        w = [f.get(k) for f in by["win"]]
        l = [f.get(k) for f in by["loss"]]
        rec(f"{k:<14} {_summ(w):<34} {_summ(l):<34}")
        wv = [x for x in w if x is not None]; lv = [x for x in l if x is not None]
        if wv and lv:
            seps[k] = st.median(wv) - st.median(lv)

    # ── CAPTURE LEAK ──
    rec("\n--- PROFIT CAPTURE (winners: exit_points / MFE) ---")
    if capture:
        capture.sort()
        rec(f"median capture ratio = {st.median(capture)*100:.0f}%  "
            f"mean = {sum(capture)/len(capture)*100:.0f}%  (1.0 = kept the whole move)")
        low = sum(1 for x in capture if x < 0.5)
        rec(f"{low}/{len(capture)} winners kept <50% of their favourable move "
            f"-> exit-timing leak (giving profit back).")
    else:
        rec("no winner MFE data")

    # ── TAKEAWAYS ──
    rec("\n--- WHAT THIS SAYS (fakeouts + capture) ---")
    strong = sorted(seps.items(), key=lambda kv: -abs(kv[1]))
    for k, gap in strong[:4]:
        direction = "higher" if gap > 0 else "lower"
        rec(f"  * winners have {direction} {k} (median gap {gap:+.3f} ATR) "
            f"-> raising the {k} entry floor would filter more fakeouts")
    rec("  * If capture ratio is low, the leak is EXITS not entries -> wider "
        "trail / pyramiding into runners keeps more of the move.")
    rec(f"\nper-symbol win/loss: {per_symbol}")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))
    rec(f"\nwritten: {OUT}")


if __name__ == "__main__":
    main()
