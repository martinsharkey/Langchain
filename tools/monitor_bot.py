"""
One-hour bot health + trading monitor.

Samples every SAMPLE_SECONDS for DURATION_MIN minutes and records to
logs/monitor_report_<date>.log:
  - process alive (python app.py) + MT5 terminal alive
  - account balance/equity/free-margin (via MT5) and equity deltas
  - open-position count and per-symbol exposure
  - NEW log lines classified: OPENED / CLOSED / ERROR / TRACEBACK / MARKET-CLOSED
    / BASKET / PYRAMID / repeated identical ENTRY-HOLD (stall) / crash markers
  - a rolling summary + a final glitch report

Read-only: it never touches trades. Safe to run alongside the live bot.
"""

import os
import re
import time
import glob
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(REPO, "logs")
SAMPLE_SECONDS = 30
DURATION_MIN = 60

REPORT = os.path.join(LOG_DIR, f"monitor_report_{datetime.now():%Y%m%d_%H%M}.log")


def _today_bot_log():
    files = sorted(glob.glob(os.path.join(LOG_DIR, "trading_bot_*.log")))
    return files[-1] if files else None


def _rec(line):
    with open(REPORT, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    try:
        print(line, flush=True)
    except Exception:
        # never let a console encoding error kill the monitor
        print(line.encode("ascii", "replace").decode("ascii"), flush=True)


def _proc_alive(name_frag):
    try:
        import subprocess
        out = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=15).stdout.lower()
        return name_frag.lower() in out
    except Exception:
        return None


def _mt5_snapshot():
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize(login=1176166, password=os.getenv("MT5_PASSWORD", "PW4%Ce&l"),
                              server="VTMarkets-Demo"):
            return None
        ai = mt5.account_info()
        pos = mt5.positions_get() or []
        snap = {
            "balance": round(ai.balance, 2) if ai else None,
            "equity": round(ai.equity, 2) if ai else None,
            "free": round(ai.margin_free, 2) if ai else None,
            "positions": len(pos),
            "by_symbol": {},
        }
        for p in pos:
            snap["by_symbol"].setdefault(p.symbol, 0)
            snap["by_symbol"][p.symbol] += 1
        mt5.shutdown()
        return snap
    except Exception as e:
        return {"error": str(e)[:120]}


ERROR_PATTS = [
    ("TRACEBACK", re.compile(r"Traceback|Exception|access violation|fatal", re.I)),
    ("ERROR", re.compile(r"\|\s*ERROR\s*\|")),
    ("MARKET_CLOSED", re.compile(r"market closed", re.I)),
    ("ORDER_FAIL", re.compile(r"FAILED|retcode=(?!10009)", re.I)),
    ("OPENED", re.compile(r"OPENED (BUY|SELL)")),
    ("CLOSED", re.compile(r"CLOSED .*-> (win|loss|breakeven)", re.I)),
    ("BASKET", re.compile(r"\[BASKET|\[PYRAMID")),
]


def main():
    _rec(f"===== MONITOR START {datetime.now():%Y-%m-%d %H:%M:%S} (dur {DURATION_MIN}m) =====")
    botlog = _today_bot_log()
    _rec(f"Watching: {botlog}")
    pos = 0
    try:
        pos = os.path.getsize(botlog) if botlog else 0
    except Exception:
        pos = 0

    end = time.time() + DURATION_MIN * 60
    counts = {k: 0 for k, _ in ERROR_PATTS}
    last_equity = None
    hold_repeat = {}
    samples = 0

    while time.time() < end:
        samples += 1
        ts = datetime.now().strftime("%H:%M:%S")

        # 1) process + terminal liveness
        py_alive = _proc_alive("python.exe")
        term_alive = _proc_alive("terminal64.exe")
        if py_alive is False:
            _rec(f"[{ts}] !!! GLITCH: python process NOT found — bot may have crashed")
        if term_alive is False:
            _rec(f"[{ts}] !!! GLITCH: MT5 terminal64.exe NOT found")

        # 2) account snapshot
        snap = _mt5_snapshot()
        if snap and "error" not in snap:
            eq = snap["equity"]
            delta = ("" if last_equity is None else f" (d={round(eq-last_equity,2):+})")
            last_equity = eq
            _rec(f"[{ts}] eq={eq}{delta} bal={snap['balance']} free={snap['free']} "
                 f"pos={snap['positions']} {snap['by_symbol']}")
        elif snap:
            _rec(f"[{ts}] !!! MT5 snapshot error: {snap['error']}")

        # 3) scan new log lines
        botlog = botlog or _today_bot_log()
        if botlog and os.path.exists(botlog):
            try:
                with open(botlog, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(pos)
                    new = f.read()
                    pos = f.tell()
                for line in new.splitlines():
                    for name, patt in ERROR_PATTS:
                        if patt.search(line):
                            counts[name] += 1
                            if name in ("TRACEBACK", "ERROR", "ORDER_FAIL", "BASKET"):
                                _rec(f"[{ts}] {name}: {line.strip()[:180]}")
                    # stall detection: identical ENTRY-HOLD reason repeating a lot
                    m = re.search(r"\[ENTRY-HOLD\] (\w+): (.+?) \|", line)
                    if m:
                        key = f"{m.group(1)}:{m.group(2)[:40]}"
                        hold_repeat[key] = hold_repeat.get(key, 0) + 1
            except Exception as e:
                _rec(f"[{ts}] monitor read error: {e}")

        time.sleep(SAMPLE_SECONDS)

    # final report
    _rec("----- FINAL SUMMARY -----")
    _rec(f"samples={samples}  events={counts}")
    stalls = {k: v for k, v in hold_repeat.items() if v >= 20}
    if stalls:
        _rec(f"Persistent ENTRY-HOLD reasons (>=20x, possible over-tight gate): {stalls}")
    glitch = counts["TRACEBACK"] + counts["ERROR"]
    verdict = "CLEAN" if glitch == 0 else f"{glitch} error/traceback events — REVIEW"
    _rec(f"VERDICT: {verdict} | opened={counts['OPENED']} closed={counts['CLOSED']} "
         f"order_fails={counts['ORDER_FAIL']} market_closed={counts['MARKET_CLOSED']}")
    _rec(f"===== MONITOR END {datetime.now():%Y-%m-%d %H:%M:%S} =====")


if __name__ == "__main__":
    main()
