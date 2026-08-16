#!/usr/bin/env python3
"""
Bot watchdog — runs the trading bot and auto-restarts it if it exits.

Usage:
    python run_bot_with_watchdog.py [LIVE_MICRO|OBSERVE|PAPER|LIVE]

Logs are written to logs/watchdog.log and logs/trading_bot_YYYYMMDD.log
via the bot's own logging. This script only logs restarts/fatal errors.
"""

import subprocess
import sys
import time
import os
from datetime import datetime


def _log(repo, msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {msg}"
    print(line)
    try:
        os.makedirs(os.path.join(repo, "logs"), exist_ok=True)
        with open(os.path.join(repo, "logs", "watchdog.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "LIVE_MICRO"
    repo = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(repo, "venv", "Scripts", "python.exe")
    cmd = [venv_python, "app.py", mode]

    # Safety env for every child: force the pure-Python vector store + safe hash
    # embedder so the native ChromaDB/torch layer (which segfaults on this Windows
    # host — repeated 0xC0000005 crashes overnight) is never invoked in-process.
    child_env = dict(os.environ)
    child_env.setdefault("FORCE_LOCAL_VECTOR_STORE", "1")
    child_env.setdefault("USE_SAFE_EMBEDDER", "1")
    child_env.setdefault("BACKTEST_MAX_TICKS", "750000")

    _log(repo, f"[watchdog] starting bot in {mode} mode")
    _log(repo, f"[watchdog] cmd: {' '.join(cmd)}")

    restarts = 0
    while True:
        started = time.time()
        proc = subprocess.Popen(cmd, cwd=repo, env=child_env)
        rc = proc.wait()
        ran_for = int(time.time() - started)
        restarts += 1
        _log(repo, f"[watchdog] bot exited with code {rc} after {ran_for}s "
                   f"(restart #{restarts}) — restarting in 5s")
        # If it dies almost immediately, back off to avoid a hot crash loop.
        if ran_for < 10:
            _log(repo, "[watchdog] bot died in <10s — backing off 30s (check logs/trading_bot_*.log)")
            time.sleep(30)
        else:
            time.sleep(5)


if __name__ == "__main__":
    main()
