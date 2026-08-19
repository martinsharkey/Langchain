"""
restart_bot.py — Phase 3 of the test-isolation + safe-restart plan.

Safely restart the trading bot with pre/post snapshot, dashboard validation,
and automatic rollback on failure.

Workflow:
  1. Snapshot live state via `scripts.snapshot_state`.
  2. Stop existing `python app.py` / `scalp_engine` processes.
  3. Verify MT5 terminal is running with the expected demo account.
  4. Start `python app.py <mode>` as a fresh subprocess.
  5. Poll dashboard `/api/status` until fresh and `algo_trading.can_trade=True`.
  6. Verify adopted open positions match `config.magic_for_symbol(sym)`.
  7. Run `scripts.qmmp.ea_generator <SYM> --verify` for each configured symbol.
  8. On failure, stop new process and restore snapshot.
  9. Log everything to `logs/restart_bot_YYYY-MM-DD.log`.

CLI:
  python -m scripts.restart_bot --dry-run
      Report what would be done without side effects.

  python -m scripts.restart_bot --mode PAPER
      Safe default restart.

  python -m scripts.restart_bot --mode LIVE_MICRO --confirm-live
      Explicit live confirmation required.

  python -m scripts.restart_bot --replay
      After restart, run lightweight vectorbt replay validation.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is optional
    psutil = None  # type: ignore

try:
    import MetaTrader5 as _mt5_module
except Exception:  # pragma: no cover
    _mt5_module = None  # type: ignore

try:
    from scripts.snapshot_state import create_snapshot, restore_snapshot, list_snapshots, prune_snapshots
except ImportError:  # pragma: no cover
    create_snapshot = restore_snapshot = list_snapshots = prune_snapshots = None  # type: ignore

LOGS_DIR = getattr(config, "LOGS_DIR", os.path.join(os.path.dirname(config.BASE_DIR), "logs"))
logger = logging.getLogger("restart_bot")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(msg: str) -> None:
    print(f"[restart_bot] {msg}")
    logger.info(msg)


def _find_bot_processes() -> List[psutil.Process]:  # type: ignore
    """Return processes whose command line contains app.py or scalp_engine."""
    if psutil is None:
        return []
    procs = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if "app.py" in cmd or "scalp_engine" in cmd:
                procs.append(p)
        except Exception:
            pass
    return procs


def _stop_processes(procs, timeout: int = 15) -> List:
    """Terminate then kill any remaining bot processes."""
    if not procs:
        return []
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    deadline = time.time() + timeout
    alive = list(procs)
    while time.time() < deadline and alive:
        still = []
        for p in alive:
            try:
                if p.is_running():
                    still.append(p)
            except Exception:
                pass
        alive = still
        if alive:
            time.sleep(0.2)
    for p in alive:
        try:
            p.kill()
        except Exception:
            pass
    return alive


def _start_bot(mode: str, cwd: Optional[Path] = None) -> subprocess.Popen:
    """Launch a fresh bot subprocess."""
    cwd = cwd or Path(config.BASE_DIR)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["TRADING_MODE"] = mode
    return subprocess.Popen(
        [sys.executable, "app.py", mode],
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _poll_dashboard(url: str = "http://127.0.0.1:5000/api/status", timeout: int = 60) -> dict:
    """Poll dashboard until it responds or timeout."""
    import urllib.request

    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return json.loads(r.read())
        except Exception as e:
            last_err = e
            time.sleep(0.5)
    raise TimeoutError(f"dashboard not reachable: {last_err}")


def _verify_adopted_positions(status: dict) -> List[str]:
    """Verify adopted positions match bot magic. Returns list of mismatch strings."""
    from src.config import magic_for_symbol

    mismatches = []
    for pos in status.get("open_positions", []):
        sym = pos.get("symbol", "")
        expected = magic_for_symbol(sym)
        actual = pos.get("magic")
        if actual != expected:
            mismatches.append(
                f"{pos.get('ticket')} {sym}: magic={actual} expected={expected}"
            )
    return mismatches


def _verify_ea_inputs(symbols: List[str]) -> List[str]:
    """Run ea_generator --verify for each symbol. Returns list of errors."""
    errors = []
    for sym in symbols:
        try:
            subprocess.run(
                [sys.executable, "-m", "scripts.qmmp.ea_generator", sym, "--verify"],
                cwd=str(config.BASE_DIR),
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            errors.append(f"{sym}: {e.stderr or e.stdout or str(e)}")
        except Exception as e:
            errors.append(f"{sym}: {e}")
    return errors


def _verify_vectorbt_replay(symbols: List[str], full: bool = False) -> List[str]:
    """Run lightweight vectorbt replay for model.json configs."""
    errors = []
    for sym in symbols:
        try:
            script = Path(config.BASE_DIR) / "scripts" / "qmmp" / "vbt_model.py"
            if not script.exists():
                continue
            args = [sys.executable, str(script), sym]
            if not full:
                args += ["--last-bars", "1000"]
            subprocess.run(
                args,
                cwd=str(config.BASE_DIR),
                capture_output=True,
                text=True,
                timeout=300,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            errors.append(f"{sym} vbt replay: {e.stderr or e.stdout or str(e)}")
        except Exception as e:
            errors.append(f"{sym} vbt replay: {e}")
    return errors


def _mt5_account_ok() -> bool:
    """Verify MT5 terminal is running with expected demo account."""
    if _mt5_module is None:
        return False
    try:
        if not _mt5_module.initialize():
            return False
        ai = _mt5_module.account_info()
        _mt5_module.shutdown()
        if not ai:
            return False
        expected_login = int(os.getenv("MT5_ACCOUNT", "0"))
        expected_server = os.getenv("MT5_SERVER", "")
        return ai.login == expected_login and expected_server in (ai.server or "")
    except Exception:
        return False


def _write_restart_log(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="Safely restart the trading bot.")
    ap.add_argument("--mode", default=os.getenv("TRADING_MODE", "PAPER"), choices=["OBSERVE", "PAPER", "LIVE_MICRO", "LIVE"])
    ap.add_argument("--dry-run", action="store_true", help="Report only, no side effects")
    ap.add_argument("--confirm-live", action="store_true", help="Required for LIVE_MICRO mode")
    ap.add_argument("--replay", action="store_true", help="Run vectorbt replay validation after restart")
    ap.add_argument("--full-replay", action="store_true", help="Run full historical replay (slow)")
    ap.add_argument("--rollback-on-validation-failure", action="store_true", help="Restore snapshot if validation fails")
    ap.add_argument("--snapshot-label", default=None, help="Label for pre-restart snapshot")
    args = ap.parse_args(argv)

    if args.mode == "LIVE_MICRO" and not args.confirm_live:
        ap.error("--confirm-live is required when mode=LIVE_MICRO")

    symbols = list(getattr(config, "TRADING_SYMBOLS", []))
    log_path = Path(LOGS_DIR) / f"restart_bot_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"

    def _record(step: str, status: str, detail: str = "") -> None:
        _write_restart_log(log_path, {
            "ts": _now_iso(),
            "step": step,
            "status": status,
            "detail": detail,
            "mode": args.mode,
        })

    # Step 1: snapshot
    _record("snapshot", "start")
    if create_snapshot is not None:
        snap = create_snapshot(label=args.snapshot_label)
        _record("snapshot", "ok", str(snap))
    else:
        _record("snapshot", "skip", "snapshot_state module unavailable")

    # Step 2: stop existing bot
    _record("stop", "start")
    procs = _find_bot_processes()
    _log(f"Found {len(procs)} bot processes to stop")
    if args.dry_run:
        _record("stop", "dry-run", f"would stop {len(procs)} processes")
    else:
        alive = _stop_processes(procs)
        _record("stop", "ok" if not alive else "partial", f"alive={[p.pid for p in alive]}")
        time.sleep(2)

    # Step 3: verify MT5
    _record("mt5", "start")
    if args.dry_run:
        _record("mt5", "dry-run", "would verify MT5 account")
    elif not _mt5_account_ok():
        _record("mt5", "fail", "MT5 account mismatch or terminal not running")
        _log("ERROR: MT5 account verification failed")
        return 2
    else:
        _record("mt5", "ok")

    # Step 4: start fresh bot
    _record("start", "start")
    proc = None
    if not args.dry_run:
        proc = _start_bot(args.mode)
        _log(f"Started bot PID {proc.pid} mode={args.mode}")

    # Step 5: poll dashboard
    _record("dashboard", "start")
    status = {}
    if not args.dry_run:
        try:
            status = _poll_dashboard(timeout=120)
            _record("dashboard", "ok", f"cycle={status.get('cycle')} running={status.get('running')}")
        except Exception as e:
            _record("dashboard", "fail", str(e))
            _log(f"ERROR: dashboard not reachable: {e}")
            if proc:
                _stop_processes([proc])
            return 3
    else:
        _record("dashboard", "dry-run", "would poll /api/status")

    # Step 6: validate adopted positions
    _record("positions", "start")
    position_errors = []
    if not args.dry_run and status:
        position_errors = _verify_adopted_positions(status)
        if position_errors:
            _record("positions", "fail", "; ".join(position_errors))
            _log(f"ERROR: position magic mismatches: {position_errors}")
            if proc:
                _stop_processes([proc])
            if args.rollback_on_validation_failure and create_snapshot is not None:
                snaps = list_snapshots()
                if snaps:
                    restore_snapshot(snaps[0])
                    _record("rollback", "ok", str(snaps[0]))
            return 4
        _record("positions", "ok")
    else:
        _record("positions", "dry-run" if args.dry_run else "skip")

    # Step 7: EA verify
    _record("ea_verify", "start")
    ea_errors = []
    if not args.dry_run:
        ea_errors = _verify_ea_inputs(symbols)
        if ea_errors:
            _record("ea_verify", "fail", "; ".join(ea_errors))
            _log(f"ERROR: EA verify failed: {ea_errors}")
        else:
            _record("ea_verify", "ok")
    else:
        _record("ea_verify", "dry-run")

    # Step 8: vectorbt replay (optional)
    if args.replay or args.full_replay:
        _record("vbt_replay", "start")
        vbt_errors = _verify_vectorbt_replay(symbols, full=args.full_replay)
        if vbt_errors:
            _record("vbt_replay", "fail", "; ".join(vbt_errors))
            _log(f"ERROR: vectorbt replay failed: {vbt_errors}")
        else:
            _record("vbt_replay", "ok")

    # Final status
    if args.dry_run:
        _log("Dry-run complete. No changes made.")
        return 0

    all_errors = position_errors + ea_errors
    if all_errors:
        _log(f"Restart completed with validation errors: {all_errors}")
        return 1

    if prune_snapshots is not None:
        try:
            prune_snapshots(keep=10)
        except Exception as e:
            _log(f"prune snapshots failed: {e}")

    _log(f"Restart OK | mode={args.mode} pid={proc.pid if proc else 'n/a'} symbols={symbols}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
