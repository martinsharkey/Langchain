"""
Post-trade forensic: for every LOSING trade since a cutoff, pull real MT5 ticks
for +/- 5 minutes around entry and exit and evaluate two counterfactuals:

  (A) STRONGER ENTRY — in the 5 min BEFORE entry, was price already extended /
      moving against us (late entry)? Would waiting for a pullback or a stronger
      OsMA/였 momentum reading have given a better fill?
  (B) BETTER EXIT — in the 5 min AFTER our exit, did price run back our way by
      >= the loss (i.e. we exited too early / SL too tight)? What exit (wider SL,
      giveback trail, time-stop) would have turned it green?

Read-only. Uses the same get_ticks real-tick source the backtester uses.
Writes tools/loser_forensic_<ts>.txt and prints a summary.
"""

import os
import sys
import json
import sqlite3
from datetime import datetime, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from src.mt5.connector import get_connector
from src.mt5.data import get_ticks

DB = os.path.join(REPO, "data", "trading_experience.db")
CUTOFF = os.getenv("LOSER_CUTOFF", "2026-08-11T10:00")   # since the entry-fix
WIN = 5 * 60  # +/- 5 minutes in seconds
OUT = os.path.join(REPO, "tools", f"loser_forensic_{datetime.now():%Y%m%d_%H%M}.txt")


def _epoch(ts_iso):
    try:
        return datetime.fromisoformat(ts_iso).timestamp()
    except Exception:
        return None


def _ticks_window(symbol, center_epoch):
    if center_epoch is None:
        return []
    tk = get_ticks(symbol, center_epoch - WIN, center_epoch + WIN)
    if not tk or not tk.get("time"):
        return []
    return list(zip(tk["time"], tk["bid"], tk["ask"]))


def _mid(t):
    return (t[1] + t[2]) / 2.0


def analyse():
    conn = get_connector()
    conn.initialize()
    c = sqlite3.connect(DB)
    q = ("SELECT id,timestamp,symbol,action,entry_price,exit_price,profit_loss,"
         "exit_reason,mfe_points,mae_points,atr_value,mt5_ticket "
         "FROM trades WHERE outcome='loss' AND timestamp>=? ORDER BY id DESC")
    rows = c.execute(q, (CUTOFF,)).fetchall()

    lines = []
    def rec(s):
        lines.append(s); print(s, flush=True)

    rec(f"===== LOSER FORENSIC since {CUTOFF} — {len(rows)} losing trades =====")

    could_wait = 0        # entry: price extended against us just before entry
    exit_too_early = 0    # exit: price ran back our way >= loss within 5 min after
    recoverable_pts = []
    n = 0

    for (tid, ts, sym, action, entry, exit_px, pnl, exreason, mfe, mae, atr, ticket) in rows:
        n += 1
        e_ep = _epoch(ts)
        pt = 0.01 if sym.startswith("XAU") or sym.startswith("BTC") else 0.0001
        # ── entry window (5 min before) ──
        entry_ticks = _ticks_window(sym, e_ep)
        pre = [t for t in entry_ticks if t[0] <= e_ep]
        entry_note = ""
        if pre and entry:
            pre_prices = [_mid(t) for t in pre]
            # how far had price already moved in our direction in the 5 min before?
            first = pre_prices[0]
            run_into_entry = (entry - first) if action == "buy" else (first - entry)
            run_pts = run_into_entry / pt
            if atr and run_pts > 1.2 * (atr / pt):
                could_wait += 1
                entry_note = f"LATE: price already ran {run_pts:.0f}pts our way pre-entry (>1.2 ATR)"
            else:
                entry_note = f"entry ok: {run_pts:.0f}pts pre-move"

        # ── exit window (5 min after exit) : use exit_price as the exit anchor ──
        # exit epoch unknown precisely; approximate exit ~ entry + typical hold via
        # the post-exit tick scan anchored at exit_price crossing. We instead scan
        # the whole window after entry for the best reachable price AFTER our exit
        # price was hit, to see if it recovered.
        exit_note = ""
        if entry_ticks and exit_px and entry:
            post = [t for t in entry_ticks if t[0] >= e_ep]
            if post:
                if action == "buy":
                    best_after = max(_mid(t) for t in post)
                    recover = (best_after - exit_px) / pt
                else:
                    best_after = min(_mid(t) for t in post)
                    recover = (exit_px - best_after) / pt
                loss_pts = abs((entry - exit_px) / pt)
                if recover >= loss_pts and recover > 0:
                    exit_too_early += 1
                    recoverable_pts.append(recover)
                    exit_note = (f"EARLY EXIT: after exit @ {exit_px}, price ran "
                                 f"{recover:.0f}pts back our way (loss was {loss_pts:.0f}pts) "
                                 f"-> a wider SL / trail would have saved it")
                else:
                    exit_note = f"exit reasonable: only {recover:.0f}pts recovery vs {loss_pts:.0f}pt loss"

        rec(f"#{tid} {sym} {action} entry={entry} exit={exit_px} pnl={pnl} "
            f"reason={exreason} mfe={mfe} mae={mae}")
        if entry_note: rec(f"    ENTRY: {entry_note}")
        if exit_note:  rec(f"    EXIT : {exit_note}")

    rec("----- SUMMARY -----")
    rec(f"losers analysed: {n}")
    rec(f"(A) LATE ENTRIES (could have waited / entered stronger): {could_wait}/{n}"
        f"  ({100*could_wait/max(n,1):.0f}%)")
    rec(f"(B) EARLY EXITS (price recovered >= loss within 5 min after): {exit_too_early}/{n}"
        f"  ({100*exit_too_early/max(n,1):.0f}%)")
    if recoverable_pts:
        rec(f"    avg recoverable move after early exits: "
            f"{sum(recoverable_pts)/len(recoverable_pts):.0f}pts")
    rec("INTERPRETATION:")
    rec("  High (A) => tighten/optimise entry timing (avoid extended moves).")
    rec("  High (B) => the pyramiding-into-runners + wider learned SL/giveback exit")
    rec("             (the new supervisor) directly addresses these losers.")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nwritten: {OUT}", flush=True)
    conn.shutdown()


if __name__ == "__main__":
    analyse()
