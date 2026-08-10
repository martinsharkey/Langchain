#!/usr/bin/env python3
"""
app.py — Unified single-command launcher for the Agentic Trader.

Starts, in ONE process:
  1. The live dashboard (http://localhost:5000) — always available first.
  2. The trading engine (ScalpEngine) in a background thread, trading the
     configured symbols on the connected MT5 demo account.
  3. (Optional, best-effort) the research orchestrator/scheduler.

Trading mode is controlled by TRADING_MODE (.env or CLI arg):
    python app.py                 # uses TRADING_MODE from .env (default OBSERVE)
    python app.py LIVE_MICRO      # real 0.01-lot demo trading
    python app.py PAPER           # simulated fills at live prices
    python app.py OBSERVE         # analyze only, no orders

The dashboard shows ONLY real data (live MT5 + engine status + learning DBs).
"""

import os
import sys
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Allow mode override as first CLI arg
if len(sys.argv) > 1 and sys.argv[1].upper() in ("OBSERVE", "PAPER", "LIVE_MICRO", "LIVE"):
    os.environ["TRADING_MODE"] = sys.argv[1].upper()

from src import config
from src.utils.logger import get_logger, console
from dashboard.app import app as flask_app

logger = get_logger("app")


def start_dashboard():
    """Run the Flask dashboard in a daemon thread (never blocks trading)."""
    def _run():
        import logging as pylog
        pylog.getLogger("werkzeug").setLevel(pylog.ERROR)
        flask_app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    t = threading.Thread(target=_run, daemon=True, name="dashboard")
    t.start()
    return t


def start_engine():
    """Run the trading engine in a daemon thread."""
    from src.trading.scalp_engine import run_scalp_engine

    def _run():
        try:
            run_scalp_engine()
        except Exception as e:
            logger.error(f"Trading engine stopped: {e}", exc_info=True)
    t = threading.Thread(target=_run, daemon=True, name="engine")
    t.start()
    return t


def start_cryptorti_best_effort():
    """Start the CryptoRTI live signal client in a daemon thread (non-fatal)."""
    import os
    cert_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cryptorti", "certs")
    needed = [os.path.join(cert_dir, f) for f in ("ca.pem", "client.pem", "client-key.pem")]
    if not all(os.path.exists(p) for p in needed):
        console.print("  [yellow]CryptoRTI: certs not found — live signal feed disabled[/yellow]")
        return None
    try:
        from src.cryptorti.signal_client import run as run_cryptorti

        def _run():
            try:
                run_cryptorti()
            except Exception as e:
                logger.warning(f"CryptoRTI client stopped: {e}")
        t = threading.Thread(target=_run, daemon=True, name="cryptorti")
        t.start()
        console.print("  [green]CryptoRTI live signal feed started[/green]")
        return t
    except Exception as e:
        console.print(f"  [yellow]CryptoRTI feed unavailable (non-fatal): {e}[/yellow]")
        return None


def main():
    mode = os.environ.get("TRADING_MODE", config.TRADING_MODE)
    console.print("\n" + "=" * 66, style="bold cyan")
    console.print("  AGENTIC TRADER", style="bold cyan")
    console.print("=" * 66, style="bold cyan")
    console.print(f"  Mode:     [bold]{mode}[/bold]")
    console.print(f"  Symbols:  {', '.join(config.TRADING_SYMBOLS)}")
    console.print(f"  Target:   {config.SCALP_TARGET_TRADES} closed trades")
    console.print("=" * 66 + "\n", style="bold cyan")

    # 1) dashboard first — always available
    start_dashboard()
    console.print("  [green]Dashboard:[/green] http://localhost:5000")

    # 2) CryptoRTI live whale-signal feed (best effort, non-fatal)
    start_cryptorti_best_effort()

    # 3) trading engine
    start_engine()
    console.print(f"  [green]Trading engine started[/green] (mode={mode})\n")

    if mode == "OBSERVE":
        console.print("  [yellow]OBSERVE mode:[/yellow] analyzing only — no orders will be placed.")
        console.print("  Run 'python app.py LIVE_MICRO' to trade the demo account.\n")

    console.print("  Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n  Shutting down…", style="yellow")
        console.print("  Stopped.\n", style="green")


if __name__ == "__main__":
    main()
