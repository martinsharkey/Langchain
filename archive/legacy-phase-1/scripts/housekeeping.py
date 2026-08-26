"""
Housekeeping — the DAILY_PROCESS.md checklist as an automated report.

Run manually, or on a schedule (Windows Task Scheduler). It does the safe automatic
cleanup, runs the data-flow / loop-closure integrity checks, and writes a concise
report to data/housekeeping/report_<ts>.txt (and stdout) that you can paste to the
assistant to decide if the checklist needs enhancing.

It does NOT stop/start the engine or trade — read-only + file cleanup only.

Usage:  python housekeeping.py            (report + safe cleanup)
        python housekeeping.py --report   (report only, no cleanup)
"""
from __future__ import annotations
import os, sys, glob, sqlite3, json, time
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "data", "trading_experience.db")
OUT = os.path.join(BASE, "data", "housekeeping")
LOGDIR = os.path.join(BASE, "logs")
MONDIR = os.path.join(BASE, "data", "monitor")
OVERLAY = os.path.join(BASE, "data", "edge_weights.json")


def _line(rep, s):
    rep.append(s); print(s)


def integrity_checks(rep):
    _line(rep, "\n== DATA-FLOW & LOOP INTEGRITY ==")
    if not os.path.exists(DB):
        _line(rep, "  ! no trades DB"); return
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    # entries today per symbol + green rate (clean-MFE)
    rows = [dict(r) for r in c.execute(
        "SELECT symbol, COUNT(*) n, SUM(CASE WHEN mfe_points>0 THEN 1 ELSE 0 END) green, "
        "SUM(CASE WHEN peak_indicators IS NOT NULL THEN 1 ELSE 0 END) peaksnap "
        "FROM trades WHERE (data_source IS NULL OR data_source='LIVE_MICRO') "
        "AND date(timestamp)=date('now') AND outcome IN ('win','loss','breakeven') "
        "GROUP BY symbol").fetchall()]
    if rows:
        for r in rows:
            n = r["n"] or 1
            _line(rep, f"  {r['symbol'][:8]:8} today: {r['n']} closed, "
                       f"green {r['green']}/{n} ({(r['green'] or 0)/n*100:.0f}%), "
                       f"peaksnap {r['peaksnap']}")
    else:
        _line(rep, "  ! NO closed trades today — check entry path (empty overlay? MT5 data?)")
    # loop-closure: pending stuck?
    pend = c.execute("SELECT COUNT(*) FROM trades WHERE outcome='pending'").fetchone()[0]
    _line(rep, f"  pending (unreconciled) trades: {pend}")
    # provenance breakdown
    prov = c.execute("SELECT data_source, COUNT(*) FROM trades GROUP BY data_source").fetchall()
    _line(rep, "  provenance: " + ", ".join(f"{p[0]}={p[1]}" for p in prov))
    c.close()


def overlay_check(rep):
    _line(rep, "\n== OVERLAY SANITY ==")
    if not os.path.exists(OVERLAY):
        _line(rep, "  no overlay (fine — uses static GoldShark rule)"); return
    try:
        o = json.load(open(OVERLAY))
        fe = o.get("focused_edge", {})
        empty = [k for k, v in fe.items() if not v]
        if empty:
            _line(rep, f"  ! EMPTY focused pockets present (ignored, but stale): {empty}")
        else:
            _line(rep, f"  focused_edge ok: {list(fe.keys()) or 'none'}")
    except Exception as e:
        _line(rep, f"  ! overlay unreadable: {e}")


def process_check(rep):
    _line(rep, "\n== PROCESSES ==")
    try:
        import subprocess
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
              "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
              "Where-Object { $_.CommandLine -like '*app.py*' } | Measure-Object).Count"],
              capture_output=True, text=True, timeout=20).stdout.strip()
        n = int(out or "0")
        flag = "  ! MULTIPLE engines (duplicate-engine bug)" if n > 2 else "  ok"
        _line(rep, f"  app.py engine processes: {n}{flag if n!=1 else ' (1)'}")
    except Exception as e:
        _line(rep, f"  (process check skipped: {e})")


def cleanup(rep, do_it):
    _line(rep, "\n== CLEANUP ==")
    cutoff = time.time() - 14 * 86400
    pruned = 0
    for pat in (os.path.join(LOGDIR, "trading_bot_*.log"),
                os.path.join(MONDIR, "live_monitor_*.jsonl")):
        for f in glob.glob(pat):
            if os.path.getmtime(f) < cutoff:
                if do_it:
                    try: os.remove(f); pruned += 1
                    except Exception: pass
                else:
                    pruned += 1
    _line(rep, f"  {'pruned' if do_it else 'would prune'} {pruned} files older than 14 days")


def main():
    report_only = "--report" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    rep = []
    _line(rep, f"HOUSEKEEPING REPORT {datetime.now().isoformat(timespec='seconds')}")
    _line(rep, "(review against DAILY_PROCESS.md; enhance the checklist if gaps found)")
    integrity_checks(rep)
    overlay_check(rep)
    process_check(rep)
    cleanup(rep, do_it=not report_only)
    _line(rep, "\nDONE. Paste this report to the assistant if anything is flagged (!).")
    path = os.path.join(OUT, f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    open(path, "w", encoding="utf-8").write("\n".join(rep))
    print(f"\nsaved: {path}")


if __name__ == "__main__":
    main()
