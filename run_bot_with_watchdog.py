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

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "LIVE_MICRO"
    repo = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(repo, "venv", "Scripts", "python.exe")
    cmd = [venv_python, "app.py", mode]

    print(f"[watchdog] starting bot in {mode} mode")
    print(f"[watchdog] cmd: {' '.join(cmd)}")

    while True:
        proc = subprocess.Popen(cmd, cwd=repo)
        rc = proc.wait()
        print(f"[watchdog] bot exited with code {rc} — restarting in 5s")
        time.sleep(5)


if __name__ == "__main__":
    main()
