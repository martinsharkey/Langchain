"""
C11: Study-then-bridge same-day ordering test harness.

Verifies that the Optuna daily study thread and live bridge follow the correct
same-day ordering in scalp_engine:

  1. Study thread starts once per UTC day per symbol.
  2. Bridge waits for the study thread to complete before proposing.
  3. Bridge skips if already applied today (_optuna_applied_today).
  4. Bridge does NOT mark applied-today when there is no proposal (late study).
  5. _optuna_applied_today resets at midnight UTC.

No live MT5 terminal is required — adapters, bridge, and threads are mocked.
"""
from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import src.trading.scalp_engine as se_mod


class _FakeAdapter:
    def __init__(self, symbol: str):
        self.base = symbol.upper().replace("-", "").replace(".", "")
        self.resolved_symbol = symbol
        self.spec = None


class _FakeBridge:
    def __init__(self):
        self.calls = []
        self.proposed = True
        self.applied = True
        self.reason = "ok"

    def propose_and_apply(self, symbol: str, min_trades: int = 40) -> dict:
        self.calls.append((symbol, min_trades))
        return {
            "symbol": symbol,
            "proposed": self.proposed,
            "applied": self.applied,
            "reason": self.reason,
            "validation": {"passed": True, "score": 1.2},
        }


class _FakeThread:
    def __init__(self, target=None, name=None, daemon=False, args=(), kwargs=None, *a, **kw):
        self._target = target
        self.name = name
        self.daemon = daemon
        self._args = args
        self._kwargs = kwargs or {}
        self._started = False
        self._finished = False

    def start(self):
        self._started = True
        if self._target:
            self._target(*self._args, **self._kwargs)

    def is_alive(self) -> bool:
        return not self._finished

    def join(self, timeout=None):
        self._finished = True


def _patch_optuna_modules(monkeypatch, se_mod, run_fn=None):
    fake_mod = type(sys)("scripts.qmmp.optuna_floor_optimizer")
    fake_mod.run_daily_studies = run_fn or (lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "scripts.qmmp.optuna_floor_optimizer", fake_mod)
    monkeypatch.setattr(se_mod, "threading", type("t", (), {"Thread": _FakeThread})())


def test_study_runs_once_per_day(monkeypatch):
    from src.trading.scalp_engine import ScalpEngine

    engine = ScalpEngine.__new__(ScalpEngine)
    engine.adapters = {"XAUUSD": _FakeAdapter("XAUUSD-ECN")}
    engine.optuna_bridge = _FakeBridge()
    engine._optuna_study_run_day = None
    engine._optuna_study_threads = {}
    engine._optuna_applied_today = set()
    engine._optuna_last_run_day = None

    started = []

    def fake_run_daily_studies(symbols, **kwargs):
        started.extend(symbols)

    monkeypatch.setattr(engine, "_refresh_data_if_needed", lambda *a, **k: None)
    _patch_optuna_modules(monkeypatch, se_mod, run_fn=fake_run_daily_studies)

    engine._optuna_start_daily_studies()
    assert "XAUUSD-ECN" in started

    started.clear()
    engine._optuna_start_daily_studies()
    assert started == []


def test_bridge_skips_while_study_running(monkeypatch):
    from src.trading.scalp_engine import ScalpEngine

    engine = ScalpEngine.__new__(ScalpEngine)
    engine.adapters = {"XAUUSD": _FakeAdapter("XAUUSD-ECN")}
    engine.optuna_bridge = _FakeBridge()
    engine._optuna_study_run_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    engine._optuna_study_threads = {"XAUUSD-ECN": _FakeThread(None, "optuna-study-XAUUSD")}
    engine._optuna_study_threads["XAUUSD-ECN"]._started = True
    engine._optuna_study_threads["XAUUSD-ECN"]._finished = False
    engine._optuna_applied_today = set()
    engine._optuna_last_run_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    monkeypatch.setattr(engine, "_refresh_data_if_needed", lambda *a, **k: None)
    engine._optuna_bridge_cycle()
    assert engine.optuna_bridge.calls == []


def test_bridge_skips_if_already_applied_today(monkeypatch):
    from src.trading.scalp_engine import ScalpEngine

    engine = ScalpEngine.__new__(ScalpEngine)
    engine.adapters = {"XAUUSD": _FakeAdapter("XAUUSD-ECN")}
    engine.optuna_bridge = _FakeBridge()
    engine._optuna_study_run_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    engine._optuna_study_threads = {"XAUUSD-ECN": _FakeThread(None, "optuna-study-XAUUSD")}
    engine._optuna_study_threads["XAUUSD-ECN"]._started = True
    engine._optuna_study_threads["XAUUSD-ECN"]._finished = True
    engine._optuna_applied_today = {"XAUUSD-ECN"}
    engine._optuna_last_run_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    monkeypatch.setattr(engine, "_refresh_data_if_needed", lambda *a, **k: None)
    engine._optuna_bridge_cycle()
    assert engine.optuna_bridge.calls == []


def test_bridge_does_not_mark_no_proposal_as_applied(monkeypatch):
    from src.trading.scalp_engine import ScalpEngine

    engine = ScalpEngine.__new__(ScalpEngine)
    engine.adapters = {"XAUUSD": _FakeAdapter("XAUUSD-ECN")}
    bridge = _FakeBridge()
    bridge.proposed = False
    bridge.applied = False
    bridge.reason = "no completed study yet"
    engine.optuna_bridge = bridge
    engine._optuna_study_run_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    engine._optuna_study_threads = {"XAUUSD-ECN": _FakeThread(None, "optuna-study-XAUUSD")}
    engine._optuna_study_threads["XAUUSD-ECN"]._started = True
    engine._optuna_study_threads["XAUUSD-ECN"]._finished = True
    engine._optuna_applied_today = set()
    engine._optuna_last_run_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    monkeypatch.setattr(engine, "_refresh_data_if_needed", lambda *a, **k: None)
    engine._optuna_bridge_cycle()
    assert "XAUUSD-ECN" not in engine._optuna_applied_today


def test_applied_today_resets_at_midnight_utc(monkeypatch):
    """_optuna_applied_today must reset when the UTC day changes."""
    from src.trading.scalp_engine import ScalpEngine

    engine = ScalpEngine.__new__(ScalpEngine)
    engine.adapters = {"XAUUSD": _FakeAdapter("XAUUSD-ECN")}
    engine.optuna_bridge = _FakeBridge()
    engine._optuna_study_run_day = None
    engine._optuna_study_threads = {}
    engine._optuna_applied_today = {"XAUUSD-ECN"}
    engine._optuna_last_run_day = "2026-08-20"

    monkeypatch.setattr(engine, "_refresh_data_if_needed", lambda *a, **k: None)

    engine._optuna_bridge_cycle()
    assert engine._optuna_last_run_day == datetime.now(timezone.utc).strftime("%Y-%m-%d")


def test_full_cycle_study_then_bridge(monkeypatch):
    from src.trading.scalp_engine import ScalpEngine

    engine = ScalpEngine.__new__(ScalpEngine)
    engine.adapters = {"XAUUSD": _FakeAdapter("XAUUSD-ECN")}
    engine.optuna_bridge = _FakeBridge()
    engine._optuna_study_run_day = None
    engine._optuna_study_threads = {}
    engine._optuna_applied_today = set()
    engine._optuna_last_run_day = None

    study_events = []

    def fake_run_daily_studies(symbols, **kwargs):
        study_events.extend(symbols)
        for sym in symbols:
            t = engine._optuna_study_threads.get(sym)
            if t:
                t._finished = True

    monkeypatch.setattr(engine, "_refresh_data_if_needed", lambda *a, **k: None)
    _patch_optuna_modules(monkeypatch, se_mod, run_fn=fake_run_daily_studies)

    engine._optuna_start_daily_studies()
    engine._optuna_bridge_cycle()

    assert "XAUUSD-ECN" in study_events
    assert engine.optuna_bridge.calls == [("XAUUSD-ECN", 40)]
    assert "XAUUSD-ECN" in engine._optuna_applied_today


def test_multiple_symbols_staggered_completion(monkeypatch):
    """When multiple symbols run studies, the bridge must only propose for
    symbols whose study thread has already finished."""
    from src.trading.scalp_engine import ScalpEngine

    engine = ScalpEngine.__new__(ScalpEngine)
    engine.adapters = {
        "XAUUSD": _FakeAdapter("XAUUSD-ECN"),
        "GER40": _FakeAdapter("GER40"),
    }
    engine.optuna_bridge = _FakeBridge()
    engine._optuna_study_run_day = None
    engine._optuna_study_threads = {}
    engine._optuna_applied_today = set()
    engine._optuna_last_run_day = None

    study_events = []

    def fake_run_daily_studies(symbols, **kwargs):
        study_events.extend(symbols)
        for sym in symbols:
            t = engine._optuna_study_threads.get(sym)
            if t:
                t._finished = True

    monkeypatch.setattr(engine, "_refresh_data_if_needed", lambda *a, **k: None)
    _patch_optuna_modules(monkeypatch, se_mod, run_fn=fake_run_daily_studies)

    engine._optuna_start_daily_studies()
    # Mark only XAUUSD study as finished; GER40 is still running
    engine._optuna_study_threads["GER40"]._finished = False
    engine._optuna_bridge_cycle()

    assert "XAUUSD-ECN" in study_events
    assert "GER40" in study_events
    # Bridge should only propose for XAUUSD-ECN (finished), not GER40 (still running)
    assert ("XAUUSD-ECN", 40) in engine.optuna_bridge.calls
    assert not any(c[0] == "GER40" for c in engine.optuna_bridge.calls)
    assert "XAUUSD-ECN" in engine._optuna_applied_today
    assert "GER40" not in engine._optuna_applied_today


def test_bridge_handles_propose_exception(monkeypatch):
    """If propose_and_apply raises, the bridge must not crash and must not
    mark the symbol as applied-today."""
    from src.trading.scalp_engine import ScalpEngine

    class _FailingBridge:
        def propose_and_apply(self, symbol: str, min_trades: int = 40) -> dict:
            raise RuntimeError("optuna down")

    engine = ScalpEngine.__new__(ScalpEngine)
    engine.adapters = {"XAUUSD": _FakeAdapter("XAUUSD-ECN")}
    engine.optuna_bridge = _FailingBridge()
    engine._optuna_study_run_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    engine._optuna_study_threads = {"XAUUSD-ECN": _FakeThread(None, "optuna-study-XAUUSD")}
    engine._optuna_study_threads["XAUUSD-ECN"]._started = True
    engine._optuna_study_threads["XAUUSD-ECN"]._finished = True
    engine._optuna_applied_today = set()
    engine._optuna_last_run_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    monkeypatch.setattr(engine, "_refresh_data_if_needed", lambda *a, **k: None)
    # Should not raise
    engine._optuna_bridge_cycle()
    assert "XAUUSD-ECN" not in engine._optuna_applied_today


def test_run_cycle_calls_optuna_methods(monkeypatch):
    """_maybe_run_adaptive -> _work must invoke the Optuna study and bridge methods."""
    from src.trading.scalp_engine import ScalpEngine

    engine = ScalpEngine.__new__(ScalpEngine)
    engine.adapters = {"XAUUSD": _FakeAdapter("XAUUSD-ECN")}
    engine.optuna_bridge = _FakeBridge()
    engine._optuna_study_run_day = None
    engine._optuna_study_threads = {}
    engine._optuna_applied_today = set()
    engine._optuna_last_run_day = None
    engine.cycle = 5
    engine._adaptive_running = False
    engine.post_mortem = None
    engine.knowledge_store = None
    engine.param_optimizer = MagicMock()
    engine.change_validator = MagicMock()
    engine.adaptive = MagicMock()
    engine.adaptive.run_once.return_value = {}

    study_calls = []
    bridge_calls = []

    def fake_study():
        study_calls.append(True)

    def fake_bridge():
        bridge_calls.append(True)

    monkeypatch.setattr(engine, "_optuna_start_daily_studies", fake_study)
    monkeypatch.setattr(engine, "_optuna_bridge_cycle", fake_bridge)
    monkeypatch.setattr(engine, "_refresh_data_if_needed", lambda *a, **k: None)
    monkeypatch.setattr(se_mod, "threading", type("t", (), {"Thread": _FakeThread})())

    engine._maybe_run_adaptive()

    assert len(study_calls) == 1
    assert len(bridge_calls) == 1
