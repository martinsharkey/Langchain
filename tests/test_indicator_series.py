"""Tests for compute_indicator_series() point/spread passthrough."""
import sys, os
import pandas as pd
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.strategies.indicators import compute_indicator_series


def _make_data(n=100, point=0.01, spread=0):
    import numpy as np
    t = pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC")
    close = 1000.0 + np.cumsum(np.random.randn(n) * 0.5)
    return [
        {
            "time": str(t[i]),
            "timestamp": int(t[i].timestamp()),
            "open": float(close[i] - 0.1),
            "high": float(close[i] + 0.3),
            "low": float(close[i] - 0.3),
            "close": float(close[i]),
            "volume": 1000,
            "point": point,
            "spread": spread,
        }
        for i in range(n)
    ]


def test_compute_indicator_series_passes_through_point():
    data = _make_data(point=0.00001, spread=4)
    series = compute_indicator_series(data)
    assert len(series) > 0
    for bar in series:
        assert bar["point"] == 0.00001
        assert bar["spread_points"] == 4


def test_compute_indicator_series_defaults_point_when_missing():
    data = _make_data()
    for bar in data:
        del bar["point"]
        del bar["spread"]
    series = compute_indicator_series(data)
    assert len(series) > 0
    for bar in series:
        assert bar["point"] == 0.01
        assert bar["spread_points"] == 0


def test_compute_indicator_series_has_all_expected_keys():
    data = _make_data(point=0.01, spread=10)
    series = compute_indicator_series(data)
    assert len(series) > 0
    bar = series[-1]
    expected_keys = {
        "close", "open", "high", "low", "volume",
        "ema_fast", "ema_slow", "atr", "osma",
        "bulls_power", "bears_power", "rsi",
        "point", "spread_points",
        "trend",
    }
    missing = expected_keys - set(bar.keys())
    assert not missing, f"Missing keys: {missing}"


if __name__ == "__main__":
    test_compute_indicator_series_passes_through_point()
    test_compute_indicator_series_defaults_point_when_missing()
    test_compute_indicator_series_has_all_expected_keys()
    print("indicator series tests passed")
