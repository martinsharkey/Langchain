"""
Live MT5 terminal connection check — runs at the end of the test cycle.

Pass `-m live` to exercise the real MT5 connection (requires the terminal to be
running and the demo account logged in).  Skipped by default so offline CI stays
fast.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.mark.skipif(not os.getenv("RUN_LIVE_RESTART") == "1",
                    reason="requires RUN_LIVE_RESTART=1 and live MT5 terminal")
def test_live_mt5_terminal_connection():
    """Verify the codebase can connect to the actual live MT5 terminal."""
    from src.mt5.connector import get_connector
    conn = get_connector()
    ok = conn.initialize()
    assert ok, "Live MT5 connection failed"

    info = conn.terminal_info()
    assert info is not None, "terminal_info returned None"
    assert info.get("connected") is True, "MT5 terminal not connected"
    assert info.get("trade_allowed") is True, "MT5 trade API disabled"

    account = conn.get_account_info()
    assert account is not None, "account_info returned None"
    assert account.get("login") is not None, "account login missing"

    print(f"[LIVE_MT5_CHECK] Connected to {info.get('name')} "
          f"account={account.get('login')} server={account.get('server')}")


@pytest.mark.skipif(not os.getenv("RUN_LIVE_RESTART") == "1",
                    reason="requires RUN_LIVE_RESTART=1 and live MT5 terminal")
def test_live_mt5_bot_restart_adopts_positions():
    """End-to-end: restart the bot and confirm it adopts live positions."""
    import time
    import json
    import urllib.request
    from tests.test_bot_restart import find_bot_processes, stop_bot, start_bot, wait_for_dashboard

    procs = find_bot_processes()
    if procs:
        alive = stop_bot(procs, timeout=15)
        assert not alive, f"could not terminate: {alive}"
        time.sleep(2)

    proc = start_bot("LIVE_MICRO")
    try:
        status = wait_for_dashboard(timeout=60)
        assert status.get("running") is True
        assert status.get("mode") == "LIVE_MICRO"

        from src import config
        positions = status.get("open_positions", [])
        for pos in positions:
            sym = pos.get("symbol", "")
            expected_magic = config.magic_for_symbol(sym)
            assert pos.get("magic") == expected_magic, (
                f"position {pos.get('ticket')} magic mismatch"
            )

        state_url = "http://127.0.0.1:5000/api/trading_state"
        with urllib.request.urlopen(state_url, timeout=5) as r:
            st = json.loads(r.read())
        assert st.get("state") == "TRADING"
        assert st.get("mode") == "LIVE_MICRO"
    finally:
        stop_bot([proc], timeout=10)
