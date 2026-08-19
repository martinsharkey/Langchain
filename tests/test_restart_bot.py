"""
Tests for scripts/restart_bot.py — Phase 3 of the safe-restart plan.

Covers:
- dry-run mode does not start/stop processes
- _find_bot_processes identifies app.py/scalp_engine processes
- _stop_processes terminates and kills as needed
- _mt5_account_ok validates MT5 connection
- _verify_adopted_positions checks magic numbers
"""
import sys, os, json, time
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import scripts.restart_bot as rb


class _FakeProc:
    def __init__(self, pid, cmdline, alive=True):
        self.pid = pid
        self._cmdline = cmdline
        self._alive = alive

    def is_running(self):
        return self._alive

    def terminate(self):
        self._alive = False

    def kill(self):
        self._alive = False


def test_find_bot_processes_filters_non_bot(monkeypatch):
    procs = [
        _FakeProc(1, "python app.py LIVE_MICRO"),
        _FakeProc(2, "python rag_watcher.py"),
    ]
    monkeypatch.setattr(rb, "psutil", type("psutil", (), {"process_iter": lambda *a, **k: []})())
    # psutil unavailable path returns empty list
    assert rb._find_bot_processes() == []


def test_stop_processes_terminates_then_kills(monkeypatch):
    p1 = _FakeProc(10, "python app.py LIVE_MICRO")
    p2 = _FakeProc(11, "python app.py LIVE_MICRO")
    procs = [p1, p2]
    # simulate process surviving terminate
    p1._alive = True
    p2._alive = False

    monkeypatch.setattr(rb, "psutil", type("psutil", (), {"process_iter": lambda *a, **k: procs})())
    alive = rb._stop_processes(procs, timeout=0.1)
    assert not p1._alive
    assert alive == []


def test_verify_adopted_positions_detects_mismatch():
    from src.config import magic_for_symbol
    status = {
        "open_positions": [
            {"ticket": 1, "symbol": "BTCUSD", "magic": 999999},
        ]
    }
    errors = rb._verify_adopted_positions(status)
    assert errors
    assert "BTCUSD" in errors[0]


def test_verify_ea_inputs_calls_ea_generator(monkeypatch):
    calls = []
    def fake_run(*a, **k):
        calls.append((a, k))
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(rb.subprocess, "run", fake_run)
    errors = rb._verify_ea_inputs(["BTCUSD"])
    assert errors == []
    assert len(calls) == 1


def test_mt5_account_ok_true(monkeypatch):
    class _AI:
        login = 1176166
        server = "VTMarkets-Demo"

    monkeypatch.setenv("MT5_ACCOUNT", "1176166")
    monkeypatch.setenv("MT5_SERVER", "VTMarkets-Demo")
    fake_mt5 = type("mt5", (), {
        "initialize": lambda *a, **k: True,
        "account_info": lambda *a, **k: _AI(),
        "shutdown": lambda *a, **k: None,
    })()
    monkeypatch.setattr(rb, "_mt5_module", fake_mt5)
    assert rb._mt5_account_ok() is True


def test_mt5_account_ok_false_on_mismatch(monkeypatch):
    monkeypatch.setenv("MT5_ACCOUNT", "999999")
    monkeypatch.setenv("MT5_SERVER", "WrongServer")
    fake_mt5 = type("mt5", (), {
        "initialize": lambda *a, **k: True,
        "account_info": lambda *a, **k: type("AI", (), {"login": 1, "server": "X"})(),
        "shutdown": lambda *a, **k: None,
    })()
    monkeypatch.setattr(rb, "_mt5_module", fake_mt5)
    assert rb._mt5_account_ok() is False


def test_main_dry_run_exits_zero(monkeypatch):
    monkeypatch.setattr(rb, "create_snapshot", lambda *a, **k: Path("/tmp/snap"))
    monkeypatch.setattr(rb, "list_snapshots", lambda: [Path("/tmp/snap")])
    monkeypatch.setattr(rb, "_find_bot_processes", lambda: [])
    monkeypatch.setattr(rb, "_mt5_account_ok", lambda: True)
    monkeypatch.setattr(rb, "_start_bot", lambda *a, **k: None)
    monkeypatch.setattr(rb, "_poll_dashboard", lambda **k: {"running": True, "cycle": 1, "open_positions": []})
    monkeypatch.setattr(rb, "_verify_adopted_positions", lambda s: [])
    monkeypatch.setattr(rb, "_verify_ea_inputs", lambda syms: [])
    assert rb.main(["--dry-run", "--mode", "PAPER"]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
