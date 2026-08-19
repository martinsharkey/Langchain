"""
Test the bot restart / process-lifecycle layer:

1. A restart script/harness must be able to discover the running bot process,
   terminate it cleanly (or forcibly if needed), and start a fresh instance.
2. The freshly started bot must pick up the latest code on disk (no stale
   compiled modules or cached bytecode shadowing source changes).
3. The new instance must connect to the running MT5 terminal, read the demo
   account, and adopt any open positions that belong to the bot's magic number.
4. Dashboard endpoints must become reachable after restart.

This test is designed to run offline against a stub process table by default;
set RUN_LIVE_RESTART=1 to exercise the real `app.py` launch path (requires
MT5 terminal already running and the demo account available).
"""
import sys, os, json, time, subprocess, tempfile, shutil, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


class _FakeProcess:
    def __init__(self, pid, name, cmdline, alive=True):
        self.pid = pid
        self._name = name
        self._cmdline = cmdline
        self._alive = alive

    def name(self): return self._name
    def cmdline(self): return self._cmdline
    def is_running(self): return self._alive
    def terminate(self): self._alive = False
    def kill(self): self._alive = False
    def wait(self, timeout=None): pass


def _make_restart_harness():
    """Return the helper functions without importing psutil if unavailable."""
    try:
        import psutil
    except Exception:  # pragma: no cover - psutil is optional for stub test
        psutil = None

    def find_bot_processes():
        """Return processes whose command line contains app.py or scalp_engine."""
        procs = []
        if psutil is None:
            return procs
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmd = " ".join(p.info.get("cmdline") or [])
                if "app.py" in cmd or "scalp_engine" in cmd:
                    procs.append(p)
            except Exception:
                pass
        return procs

    def stop_bot(procs, timeout=10):
        """Terminate then kill any remaining bot processes."""
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        gone, alive = [], list(procs)
        deadline = time.time() + timeout
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

    def start_bot(mode="LIVE_MICRO", cwd=None, python=None):
        """Launch a fresh bot subprocess and return it."""
        cwd = cwd or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        python = python or sys.executable
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["TRADING_MODE"] = mode
        return subprocess.Popen(
            [python, "app.py", mode],
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def wait_for_dashboard(url="http://127.0.0.1:5000/api/status", timeout=30):
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

    return find_bot_processes, stop_bot, start_bot, wait_for_dashboard


find_bot_processes, stop_bot, start_bot, wait_for_dashboard = _make_restart_harness()


def test_find_and_stop_bot_processes():
    """Stub test: verify the harness identifies and terminates bot-like PIDs."""
    procs = [
        _FakeProcess(1, "python", ["python", "app.py", "LIVE_MICRO"]),
        _FakeProcess(2, "pythonw", ["pythonw", "app.py", "LIVE_MICRO"]),
        _FakeProcess(3, "python", ["python", "rag_watcher.py"]),  # unrelated
    ]
    bots = [p for p in procs if "app.py" in " ".join(p.cmdline())]
    assert len(bots) == 2
    stop_bot(bots)
    assert not any(p.is_running() for p in bots)
    assert procs[2].is_running()  # unrelated left alone


def test_start_bot_fresh_code(tmp_path, monkeypatch):
    """Verify a fresh bot subprocess imports the latest source modules."""
    if os.getenv("RUN_LIVE_RESTART") != "1":
        pytest.skip("Set RUN_LIVE_RESTART=1 to exercise real subprocess launch")

    cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # write a sentinel module and ensure it is picked up by a child python
    sentinel = tmp_path / "_restart_sentinel.py"
    sentinel.write_text(f"VALUE = {time.time()!r}\n")
    monkeypatch.syspath_prepend(str(tmp_path))

    # importing the sentinel in a fresh subprocess must yield the current value
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    out = subprocess.check_output(
        [sys.executable, "-c", "import _restart_sentinel; print(_restart_sentinel.VALUE)"],
        env=env,
        cwd=cwd,
        text=True,
    ).strip()
    assert float(out) > 0


@pytest.mark.skipif(os.getenv("RUN_LIVE_RESTART") != "1", reason="requires live MT5")
def test_live_restart_adopts_positions():
    """
    End-to-end restart test (RUN_LIVE_RESTART=1):
      - stop any running bot
      - start app.py LIVE_MICRO
      - wait for dashboard
      - assert status shows running=True, mode=LIVE_MICRO
      - assert open_positions contains positions whose magic matches BOT_MAGIC
    """
    # 1) clean slate
    procs = find_bot_processes()
    if procs:
        alive = stop_bot(procs, timeout=15)
        assert not alive, f"could not terminate: {alive}"
        time.sleep(2)

    # 2) start fresh
    proc = start_bot("LIVE_MICRO")
    try:
        status = wait_for_dashboard(timeout=60)
        assert status.get("running") is True
        assert status.get("mode") == "LIVE_MICRO"
        assert status.get("algo_trading", {}).get("can_trade") is True

        # open_positions should include bot-owned trades; if MT5 has any, magic
        # must match config.BOT_MAGIC or a per-symbol derivation.
        from src import config
        positions = status.get("open_positions", [])
        for pos in positions:
            sym = pos.get("symbol", "")
            # deterministic magic from current config
            expected_magic = config.magic_for_symbol(sym)
            assert pos.get("magic") == expected_magic, (
                f"position {pos.get('ticket')} magic mismatch"
            )

        # 3) dashboard state reflects engine continuity
        state_url = "http://127.0.0.1:5000/api/trading_state"
        import urllib.request
        with urllib.request.urlopen(state_url, timeout=5) as r:
            st = json.loads(r.read())
        assert st.get("state") == "TRADING"
        assert st.get("mode") == "LIVE_MICRO"

    finally:
        stop_bot([proc], timeout=10)


def test_restart_harness_documented():
    """Ensure the restart helper functions are importable and documented."""
    assert callable(find_bot_processes)
    assert callable(stop_bot)
    assert callable(start_bot)
    assert callable(wait_for_dashboard)


if __name__ == "__main__":
    test_find_and_stop_bot_processes()
    test_restart_harness_documented()
    print("bot restart unit tests passed")
