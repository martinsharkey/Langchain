"""
Dashboard integration tests — verify all API endpoints are reachable, return
valid JSON, and expose the expected keys for the self-learning pipeline.
"""
from __future__ import annotations

import sys
import os
import json
import sqlite3
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock

from dashboard.app import app


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def mock_mt5_algo_status(monkeypatch):
    """Ensure MT5 algo status is always tradeable in tests."""
    fake_algo = MagicMock()
    fake_algo.terminal_trade_allowed = True
    fake_algo.account_trade_allowed = True
    fake_algo.connected = True
    fake_algo.can_trade = True
    fake_algo.reason = "OK"

    fake_acct = MagicMock()
    fake_acct.login = 123456
    fake_acct.server = "TestServer"
    fake_acct.balance = 10000.0
    fake_acct.equity = 10000.0

    monkeypatch.setattr("src.mt5.broker_adapter.get_algo_status", lambda: fake_algo)
    monkeypatch.setattr("src.mt5.account.get_account_info", lambda: fake_acct)
    monkeypatch.setattr("dashboard.app._read_status", lambda: {
        "running": True,
        "mode": "LIVE_MICRO",
        "algo_trading": {
            "can_trade": True,
            "terminal_trade_allowed": True,
            "account_trade_allowed": True,
            "connected": True,
            "reason": "OK",
        },
        "open_positions": [],
        "symbols": ["XAUUSD", "BTCUSD", "GER40"],
    })


def test_status_endpoint(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "engine_running" in data
    assert "mode" in data
    assert "algo_trading" in data


def test_pipeline_status_endpoint(client):
    resp = client.get("/api/pipeline/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "engine_running" in data
    assert "optuna" in data
    assert "recent_learning" in data
    assert "symbols" in data


def test_pipeline_optimizer_endpoint(client):
    resp = client.get("/api/pipeline/optimizer")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "tuned" in data
    assert "count" in data


def test_pipeline_bridge_endpoint(client):
    resp = client.get("/api/pipeline/bridge")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "recent" in data
    assert "count" in data


def test_pipeline_baseline_endpoint(client):
    resp = client.get("/api/pipeline/baseline")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "baseline_symbol" in data
    assert "baseline_pass_rate" in data
    assert "baseline_median_pf" in data
    assert "symbols" in data
    for sym, entry in data["symbols"].items():
        assert "status" in entry
        assert "current" in entry or entry["status"] == "no_baseline"


def test_dashboard_self_learning_flow(client):
    """Verify the self-learning pipeline is wired end-to-end through the dashboard.

    Checks:
    1. /api/status shows engine running and Algo Trading enabled
    2. /api/pipeline/status shows recent learning entries
    3. /api/pipeline/optimizer shows tuned params
    4. /api/pipeline/bridge shows Optuna apply history
    5. /api/pipeline/baseline shows baseline comparison
    """
    status = client.get("/api/status").get_json()
    assert status["engine_running"] is True
    assert status["algo_trading"]["can_trade"] is True

    pipeline = client.get("/api/pipeline/status").get_json()
    assert isinstance(pipeline["recent_learning"], list)
    assert isinstance(pipeline["symbols"], list)
    assert len(pipeline["symbols"]) > 0

    optimizer = client.get("/api/pipeline/optimizer").get_json()
    assert isinstance(optimizer["tuned"], dict)

    bridge = client.get("/api/pipeline/bridge").get_json()
    assert isinstance(bridge["recent"], list)

    baseline = client.get("/api/pipeline/baseline").get_json()
    assert baseline["baseline_symbol"] == "BTC-USD"
    assert baseline["baseline_pass_rate"] == 0.3
    assert baseline["baseline_median_pf"] == 0.9


def test_learning_log_records_optuna_events():
    """Verify LEARNING_LOG.md contains Optuna events when the bridge runs."""
    log_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "LEARNING_LOG.md",
    )
    if not os.path.exists(log_path):
        pytest.skip("LEARNING_LOG.md not found")
    with open(log_path, encoding="utf-8") as f:
        content = f.read()
    assert "[OPTIMIZER]" in content or "[OPTUNA]" in content or "[REVERT]" in content


def test_experience_db_records_trades():
    """Verify the experience DB has real trade data for the learning pipeline."""
    from src import config
    db_path = os.path.join(config.DATA_DIR, "trading_experience.db")
    if not os.path.exists(db_path):
        pytest.skip("experience DB not found")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT COUNT(*) as n FROM trades WHERE outcome IN ('win','loss','breakeven')"
    ).fetchone()
    conn.close()
    assert rows["n"] > 0, "experience DB has no closed trades"


def test_optuna_studies_have_completed_trials():
    """Verify Optuna studies exist and have completed trials."""
    import optuna
    from src import config

    for sym in ("BTCUSD", "GER40", "XAUUSD"):
        db_path = os.path.join(config.DATA_DIR, "qmmp", sym, "optuna", "study.db")
        if not os.path.exists(db_path):
            pytest.skip(f"Optuna study DB not found for {sym}")
        study = optuna.load_study(
            study_name=f"floors_{sym}",
            storage=f"sqlite:///{db_path}",
        )
        completed = sum(1 for t in study.trials if t.state.name == "COMPLETE")
        assert completed > 0, f"Optuna study for {sym} has no completed trials"
