"""Tests for QMMP floor name -> live tuned_params schema mapping."""

import pytest

from src.learning.param_optimizer import qmmp_floors_to_live_params


class TestQMMPFloorsToLiveParams:
    """Pure mapping: model.json QMMP names -> live confluence names."""

    def test_osma_mag_single_session(self):
        floors = {"osma_mag": {"Asian": 2.0}}
        out = qmmp_floors_to_live_params(floors)
        assert out["osma_min_long"] == 2.0
        assert out["osma_max_short"] == -2.0
        assert out["session_Asian"]["osma_min_long"] == 2.0
        assert out["session_Asian"]["osma_max_short"] == -2.0

    def test_osma_mag_multiple_sessions(self):
        floors = {"osma_mag": {"Asian": 2.0, "London": 3.0}}
        out = qmmp_floors_to_live_params(floors)
        assert out["osma_min_long"] == 2.0
        assert out["osma_max_short"] == -2.0
        assert out["session_Asian"]["osma_min_long"] == 2.0
        assert out["session_London"]["osma_min_long"] == 3.0
        assert out["session_London"]["osma_max_short"] == -3.0

    def test_ema_align(self):
        floors = {"ema_align": {"London": 0.25}}
        out = qmmp_floors_to_live_params(floors)
        assert out["min_ema_slope"] == 0.25
        assert out["session_London"]["min_ema_slope"] == 0.25

    def test_bulls_long_short_per_session(self):
        floors = {
            "bulls": {
                "Asian_long": 0.7,
                "Asian_short": -1.5,
                "London_long": 0.8,
            }
        }
        out = qmmp_floors_to_live_params(floors)
        assert out["bulls_min_long"] == 0.7
        assert out["bulls_max_short"] == -1.5
        assert out["session_Asian"]["bulls_min_long"] == 0.7
        assert out["session_Asian"]["bulls_max_short"] == -1.5
        assert out["session_London"]["bulls_min_long"] == 0.8

    def test_bears_long_short_per_session(self):
        floors = {
            "bears": {
                "Asian_long": -1.8,
                "Asian_short": -0.1,
                "London_short": -0.2,
            }
        }
        out = qmmp_floors_to_live_params(floors)
        assert out["bears_min_long"] == -1.8
        assert out["bears_max_short"] == -0.1
        assert out["session_Asian"]["bears_min_long"] == -1.8
        assert out["session_Asian"]["bears_max_short"] == -0.1
        assert out["session_London"]["bears_max_short"] == -0.2

    def test_atr_per_session(self):
        floors = {"atr": {"Asian": 1.4, "London": 1.2}}
        out = qmmp_floors_to_live_params(floors)
        assert out["atr_min"] == 1.4
        assert out["session_Asian"]["atr_min"] == 1.4
        assert out["session_London"]["atr_min"] == 1.2

    def test_full_xauusd_model(self):
        floors = {
            "osma_mag": {"Asian": 2.0, "London": 2.0, "NewYork": 2.0},
            "ema_align": {"Asian": 0.205, "London": 0.205, "NewYork": 0.205},
            "bulls": {
                "Asian_long": 0.7,
                "Asian_short": -1.5,
                "London_long": 0.7,
                "London_short": -1.5,
                "NewYork_long": 0.7,
                "NewYork_short": -1.5,
            },
            "bears": {
                "Asian_long": -1.8,
                "Asian_short": -0.1,
                "London_long": -1.8,
                "London_short": -0.1,
                "NewYork_long": -1.8,
                "NewYork_short": -0.1,
            },
            "atr": {"Asian": 1.4, "London": 1.4, "NewYork": 1.4},
        }
        out = qmmp_floors_to_live_params(floors)
        assert out["osma_min_long"] == 2.0
        assert out["osma_max_short"] == -2.0
        assert out["min_ema_slope"] == 0.205
        assert out["bulls_min_long"] == 0.7
        assert out["bulls_max_short"] == -1.5
        assert out["bears_min_long"] == -1.8
        assert out["bears_max_short"] == -0.1
        assert out["atr_min"] == 1.4
        assert out["session_Asian"]["osma_min_long"] == 2.0
        assert out["session_Asian"]["bulls_min_long"] == 0.7
        assert out["session_Asian"]["bears_max_short"] == -0.1

    def test_zeros_ignored(self):
        floors = {"osma_mag": {"Asian": 0.0}, "bulls": {"Asian_long": 0.0}}
        out = qmmp_floors_to_live_params(floors)
        assert "osma_min_long" not in out
        assert "bulls_min_long" not in out

    def test_empty_floors(self):
        out = qmmp_floors_to_live_params({})
        assert out == {}

    def test_scalar_atr(self):
        floors = {"atr": 1.5}
        out = qmmp_floors_to_live_params(floors)
        assert out["atr_min"] == 1.5

    def test_scalar_osma_mag(self):
        floors = {"osma_mag": 2.5}
        out = qmmp_floors_to_live_params(floors)
        assert out["osma_min_long"] == 2.5
        assert out["osma_max_short"] == -2.5
