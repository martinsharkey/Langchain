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

Hot-reload (code watcher):
    Set HOTRELOAD=1 to enable file-watcher hot-reload. When src/ or scripts/
    change, the engine thread is restarted gracefully (state is preserved on
    disk). The dashboard stays up.
"""

import os
import sys
import time
import threading
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Allow mode override as first CLI arg
if len(sys.argv) > 1 and sys.argv[1].upper() in ("OBSERVE", "PAPER", "LIVE_MICRO", "LIVE"):
    os.environ["TRADING_MODE"] = sys.argv[1].upper()

from src import config
from src.utils.logger import get_logger, console
from dashboard.app import app as flask_app

logger = get_logger("app")

_ENGINE_THREAD = None
_ENGINE_INSTANCE = None
_RELOAD_DEBOUNCE_SECS = 2.0
_LAST_RELOAD_TRIGGER = 0.0
_RELOAD_LOCK = threading.Lock()


def start_dashboard():
    """Run the Flask dashboard in a daemon thread (never blocks trading)."""
    def _run():
        import logging as pylog
        pylog.getLogger("werkzeug").setLevel(pylog.ERROR)
        flask_app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    t = threading.Thread(target=_run, daemon=True, name="dashboard")
    t.start()
    return t


def _run_engine():
    global _ENGINE_INSTANCE
    try:
        from src.trading.scalp_engine import ScalpEngine
        engine = ScalpEngine()
        _ENGINE_INSTANCE = engine
        engine.run()
    except Exception as e:
        logger.error(f"Trading engine stopped: {e}", exc_info=True)
        _ENGINE_INSTANCE = None


def start_engine():
    """Run the trading engine in a daemon thread."""
    global _ENGINE_THREAD
    _ENGINE_THREAD = threading.Thread(target=_run_engine, daemon=True, name="engine")
    _ENGINE_THREAD.start()
    return _ENGINE_THREAD


def _purge_app_modules():
    """Drop cached `src.*` / `scripts.*` modules so a fresh import actually picks up
    the changed code. Without this, `from src.trading.scalp_engine import ScalpEngine`
    returns the STALE module from sys.modules and hot-reload silently no-ops."""
    import importlib
    purged = []
    for name in list(sys.modules.keys()):
        if name == "src" or name.startswith("src.") or name == "scripts" or name.startswith("scripts."):
            purged.append(name)
            del sys.modules[name]
    if purged:
        logger.info(f"[HOTRELOAD] purged {len(purged)} cached modules "
                    f"({purged[0]} … {purged[-1]})")
    return purged


def _restart_engine():
    """Gracefully stop the current engine and start a fresh one."""
    global _ENGINE_THREAD, _ENGINE_INSTANCE
    engine = _ENGINE_INSTANCE
    if engine is not None:
        try:
            logger.info("[HOTRELOAD] stopping current engine…")
            engine.stop()
        except Exception as e:
            logger.warning(f"[HOTRELOAD] engine stop failed: {e}")
    else:
        logger.info("[HOTRELOAD] no running engine instance to stop")
    if _ENGINE_THREAD is not None:
        try:
            _ENGINE_THREAD.join(timeout=30)
        except Exception:
            pass
    # Invalidate cached modules so the fresh engine thread imports the NEW code.
    _purge_app_modules()
    logger.info("[HOTRELOAD] starting fresh engine…")
    start_engine()


def _trigger_reload():
    """Debounced reload trigger."""
    global _LAST_RELOAD_TRIGGER
    now = time.time()
    with _RELOAD_LOCK:
        if now - _LAST_RELOAD_TRIGGER < _RELOAD_DEBOUNCE_SECS:
            return
        _LAST_RELOAD_TRIGGER = now
    logger.info(f"[HOTRELOAD] code change detected at {datetime.now(timezone.utc).isoformat()}Z")
    _restart_engine()


def start_hot_reload():
    """Start a file-watcher that restarts the engine when src/ or scripts/ change."""
    if os.environ.get("HOTRELOAD", "").lower() not in ("1", "true", "yes"):
        return None
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler, FileModifiedEvent, DirModifiedEvent
    except Exception as e:
        logger.warning(f"hot-reload unavailable (watchdog missing): {e}")
        return None

    class _Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if event.is_directory:
                return
            src = event.src_path
            if not (src.endswith(".py") or src.endswith(".json")):
                return
            # Only watch src/ and scripts/ (ignore data/, .git/, __pycache__)
            parts = src.replace("\\", "/").split("/")
            if len(parts) < 2:
                return
            if not any(p in ("src", "scripts") for p in parts):
                return
            if any(part in (".git", "__pycache__", "data", "chromadb_store") for part in parts):
                return
            _trigger_reload()

    watch_dirs = []
    root = os.path.dirname(os.path.abspath(__file__))
    for d in ("src", "scripts"):
        p = os.path.join(root, d)
        if os.path.isdir(p):
            watch_dirs.append(p)

    if not watch_dirs:
        return None

    obs = Observer()
    for d in watch_dirs:
        obs.schedule(_Handler(), path=d, recursive=True)
    obs.start()
    logger.info(f"[HOTRELOAD] watching {', '.join(watch_dirs)} for code changes")
    return obs


def start_research_best_effort():
    """Start the research scheduler if available; never fatal."""
    try:
        from src.orchestration import get_orchestrator
        orch = get_orchestrator()
        orch.start()
        console.print("  [green]Research scheduler started[/green]")
        return orch
    except Exception as e:
        console.print(f"  [yellow]Research scheduler unavailable (non-fatal): {e}[/yellow]")
        logger.warning(f"research start failed: {e}")
        return None


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

    # 2) research (best effort, non-fatal)
    start_research_best_effort()

    # 2b) CryptoRTI live whale-signal feed (best effort, non-fatal)
    start_cryptorti_best_effort()

    # 3) trading engine
    start_engine()
    console.print(f"  [green]Trading engine started[/green] (mode={mode})\n")

    # 4) hot-reload watcher (opt-in via HOTRELOAD=1)
    reload_observer = start_hot_reload()
    if reload_observer:
        console.print("  [green]Hot-reload:[/green] watching src/ + scripts/ for changes")

    if mode == "OBSERVE":
        console.print("  [yellow]OBSERVE mode:[/yellow] analyzing only — no orders will be placed.")
        console.print("  Run 'python app.py LIVE_MICRO' to trade the demo account.\n")

    console.print("  Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n  Shutting down…", style="yellow")
        if reload_observer:
            try:
                reload_observer.stop()
                reload_observer.join(timeout=5)
            except Exception:
                pass
        console.print("  Stopped.\n", style="green")


if __name__ == "__main__":
    main()
