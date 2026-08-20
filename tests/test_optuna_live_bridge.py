"""Tests for Optuna → live tuning bridge."""

import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import optuna
import pytest

from scripts.qmmp.optuna_live_bridge import (
    OptunaLiveBridge,
    propose_live_params,
    _flat_params_to_floors,
    _load_best_trial_from_study,
)


class TestFlatParamsToFloors:
    """Inverse of optuna_floor_optimizer's flat->nested conversion."""

    def test_osma_per_session(self):
        flat = {"osma_Asian": 2.0, "osma_London": 3.0}
        floors = _flat_params_to_floors(flat)
        assert floors["osma_mag"] == {"Asian": 2.0, "London": 3.0}

    def test_ema_align_per_session(self):
        flat = {"ema_Asian": 0.25, "ema_London": 0.1}
        floors = _flat_params_to_floors(flat)
        assert floors["ema_align"] == {"Asian": 0.25, "London": 0.1}

    def test_bulls_long_short(self):
        flat = {"bulls_Asian_long": 0.7, "bulls_Asian_short": -1.5}
        floors = _flat_params_to_floors(flat)
        assert floors["bulls"]["Asian_long"] == 0.7
        assert floors["bulls"]["Asian_short"] == -1.5

    def test_bears_long_short(self):
        flat = {"bears_London_long": -1.8, "bears_London_short": -0.1}
        floors = _flat_params_to_floors(flat)
        assert floors["bears"]["London_long"] == -1.8
        assert floors["bears"]["London_short"] == -0.1

    def test_atr_per_session(self):
        flat = {"atr_Asian": 1.4, "atr_NewYork": 1.2}
        floors = _flat_params_to_floors(flat)
        assert floors["atr"] == {"Asian": 1.4, "NewYork": 1.2}

    def test_zeros_ignored(self):
        flat = {"osma_Asian": 0.0, "bulls_Asian_long": 0}
        floors = _flat_params_to_floors(flat)
        assert floors == {}

    def test_full_xauusd_like(self):
        flat = {
            "osma_Asian": 2.0, "osma_London": 2.0, "osma_NewYork": 2.0,
            "ema_Asian": 0.205, "ema_London": 0.205, "ema_NewYork": 0.205,
            "bulls_Asian_long": 0.7, "bulls_Asian_short": -1.5,
            "bulls_London_long": 0.7, "bulls_London_short": -1.5,
            "bulls_NewYork_long": 0.7, "bulls_NewYork_short": -1.5,
            "bears_Asian_long": -1.8, "bears_Asian_short": -0.1,
            "bears_London_long": -1.8, "bears_London_short": -0.1,
            "bears_NewYork_long": -1.8, "bears_NewYork_short": -0.1,
            "atr_Asian": 1.4, "atr_London": 1.4, "atr_NewYork": 1.4,
        }
        floors = _flat_params_to_floors(flat)
        assert floors["osma_mag"]["Asian"] == 2.0
        assert floors["bulls"]["Asian_long"] == 0.7
        assert floors["bears"]["London_short"] == -0.1
        assert floors["atr"]["NewYork"] == 1.4


class TestLoadBestTrialFromStudy:
    """Integration: create a temp Optuna study DB and read the best trial."""

    def test_loads_best_trial(self):
        tmp = tempfile.mkdtemp()
        try:
            optuna_dir = os.path.join(tmp, "XAUUSD", "optuna")
            os.makedirs(optuna_dir)
            storage = f"sqlite:///{os.path.join(optuna_dir, 'study.db')}"

            def objective(trial):
                trial.suggest_float("osma_Asian", 0.0, 5.0)
                trial.suggest_float("ema_Asian", 0.0, 1.0)
                trial.suggest_float("bulls_Asian_long", 0.0, 5.0)
                trial.suggest_float("bears_Asian_long", -5.0, 0.0)
                trial.suggest_float("atr_Asian", 0.0, 5.0)
                return trial.suggest_float("osma_Asian", 0.0, 5.0)  # maximize this

            study = optuna.create_study(
                study_name="floors_XAUUSD",
                storage=storage,
                sampler=optuna.samplers.TPESampler(seed=42),
                direction="maximize",
            )
            study.optimize(objective, n_trials=5, n_jobs=1)

            with patch("scripts.qmmp.optuna_live_bridge.D", tmp), \
                 patch("scripts.qmmp.optuna_live_bridge._resolve_symbol", return_value="XAUUSD"):
                flat = _load_best_trial_from_study("XAUUSD")
            assert flat is not None
            assert "osma_Asian" in flat
            assert flat["osma_Asian"] >= 0.0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_returns_none_when_no_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("scripts.qmmp.optuna_live_bridge._resolve_symbol", return_value="NOSYMBOL"):
                with patch("scripts.qmmp.optuna_live_bridge.D", tmp):
                    flat = _load_best_trial_from_study("NOSYMBOL")
                    assert flat is None


class TestProposeLiveParams:
    """End-to-end: study DB -> live params dict."""

    def test_propose_from_study(self):
        tmp = tempfile.mkdtemp()
        try:
            optuna_dir = os.path.join(tmp, "XAUUSD", "optuna")
            os.makedirs(optuna_dir)
            storage = f"sqlite:///{os.path.join(optuna_dir, 'study.db')}"

            def objective(trial):
                trial.suggest_float("osma_Asian", 1.0, 3.0)
                trial.suggest_float("ema_Asian", 0.1, 0.5)
                trial.suggest_float("bulls_Asian_long", 0.5, 1.5)
                trial.suggest_float("bears_Asian_long", -3.0, -0.5)
                trial.suggest_float("atr_Asian", 0.5, 2.0)
                return trial.suggest_float("osma_Asian", 1.0, 3.0)

            study = optuna.create_study(
                study_name="floors_XAUUSD",
                storage=storage,
                sampler=optuna.samplers.TPESampler(seed=42),
                direction="maximize",
            )
            study.optimize(objective, n_trials=5, n_jobs=1)

            with patch("scripts.qmmp.optuna_live_bridge.D", tmp), \
                 patch("scripts.qmmp.optuna_live_bridge._resolve_symbol", return_value="XAUUSD"):
                params = propose_live_params("XAUUSD")
                assert params is not None
                assert params["osma_min_long"] > 0
                assert params["osma_max_short"] < 0
                assert params["session_Asian"]["osma_min_long"] == params["osma_min_long"]
                assert params["session_Asian"]["bulls_min_long"] > 0
                assert params["session_Asian"]["bears_min_long"] < 0
                assert params["session_Asian"]["atr_min"] > 0
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_propose_returns_none_when_no_study(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("scripts.qmmp.optuna_live_bridge.D", tmp):
                params = propose_live_params("NOSYMBOL")
                assert params is None


class TestOptunaLiveBridge:
    """Bridge apply logic with mocked dependencies."""

    def _make_bridge(self, param_optimizer=None, change_validator=None, learning_log=None):
        return OptunaLiveBridge(
            param_optimizer=param_optimizer,
            change_validator=change_validator,
            learning_log=learning_log,
        )

    def test_no_proposed_when_no_study(self):
        bridge = self._make_bridge(
            change_validator=MagicMock(),
            param_optimizer=MagicMock(),
        )
        with patch("scripts.qmmp.optuna_live_bridge.propose_live_params", return_value=None):
            result = bridge.propose_and_apply("XAUUSD")
        assert result["proposed"] is False
        assert result["applied"] is False
        assert "no completed Optuna study" in result["reason"]

    def test_validation_failure_does_not_apply(self):
        cv = MagicMock()
        cv.validate.return_value = {"passed": False, "reason": "score too low"}
        bridge = self._make_bridge(
            change_validator=cv,
            param_optimizer=MagicMock(),
        )
        with patch("scripts.qmmp.optuna_live_bridge.propose_live_params", return_value={"osma_min_long": 2.0}):
            result = bridge.propose_and_apply("XAUUSD")
        assert result["proposed"] is True
        assert result["applied"] is False
        assert "validation failed" in result["reason"]

    def test_validation_pass_applies(self):
        cv = MagicMock()
        cv.validate.return_value = {"passed": True, "score": 1.5, "forward_pf": 1.2, "reason": "beats best-ever"}
        mock_po = MagicMock()
        mock_po._key.return_value = "XAUUSD"
        bridge = self._make_bridge(
            change_validator=cv,
            param_optimizer=mock_po,
        )
        proposed = {"osma_min_long": 2.0, "session_Asian": {"osma_min_long": 2.0}}
        with patch("scripts.qmmp.optuna_live_bridge.propose_live_params", return_value=proposed):
            result = bridge.propose_and_apply("XAUUSD")
        assert result["proposed"] is True
        assert result["applied"] is True
        assert mock_po.tuned.__setitem__.called
        assert mock_po._persist.called

    def test_no_validator_skips(self):
        bridge = self._make_bridge(
            change_validator=None,
            param_optimizer=MagicMock(),
        )
        with patch("scripts.qmmp.optuna_live_bridge.propose_live_params", return_value={"osma_min_long": 2.0}):
            result = bridge.propose_and_apply("XAUUSD")
        assert result["applied"] is False
        assert "no ChangeValidator" in result["reason"]

    def test_no_param_optimizer_skips_after_validation(self):
        cv = MagicMock()
        cv.validate.return_value = {"passed": True, "score": 1.5, "forward_pf": 1.2, "reason": "beats best-ever"}
        bridge = self._make_bridge(
            change_validator=cv,
            param_optimizer=None,
        )
        with patch("scripts.qmmp.optuna_live_bridge.propose_live_params", return_value={"osma_min_long": 2.0}):
            result = bridge.propose_and_apply("XAUUSD")
        assert result["applied"] is False
        assert "no ParameterOptimizer" in result["reason"]

    def test_learning_log_records_failure(self):
        cv = MagicMock()
        cv.validate.return_value = {"passed": False, "reason": "score too low"}
        mock_log = MagicMock()
        bridge = self._make_bridge(
            change_validator=cv,
            learning_log=mock_log,
        )
        with patch("scripts.qmmp.optuna_live_bridge.propose_live_params", return_value={"osma_min_long": 2.0}):
            bridge.propose_and_apply("XAUUSD")
        mock_log.record.assert_called_once()
        call = mock_log.record.call_args
        assert call.kwargs["kind"] == "OPTUNA"
        assert "rejected" in call.kwargs["what"]

    def test_learning_log_records_success(self):
        cv = MagicMock()
        cv.validate.return_value = {"passed": True, "score": 1.5, "forward_pf": 1.2, "reason": "beats best-ever"}
        mock_log = MagicMock()
        mock_po = MagicMock()
        mock_po._key.return_value = "XAUUSD"
        bridge = self._make_bridge(
            change_validator=cv,
            param_optimizer=mock_po,
            learning_log=mock_log,
        )
        with patch("scripts.qmmp.optuna_live_bridge.propose_live_params", return_value={"osma_min_long": 2.0}):
            bridge.propose_and_apply("XAUUSD")
        mock_log.record.assert_called_once()
        call = mock_log.record.call_args
        assert call.kwargs["kind"] == "OPTUNA"
        assert "applied" in call.kwargs["what"]
