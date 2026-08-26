"""Unit tests for the VectorBT-native indicator layer and metrics."""

import numpy as np
import pandas as pd
import pytest

from src.onboarding.backtest import BacktestResult, run_backtest
from src.onboarding.indicators import (
    all_indicators,
    enumerate_indicators,
    run_indicator,
    wrap,
)
from src.onboarding.metrics import composite_score, is_viable
from src.onboarding.signals import combine_signals, generate_signals


def _ohlcv(n=300):
    idx = pd.date_range("2026-01-01", periods=n, freq="1min")
    rng = np.random.default_rng(42)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 0.1, n)), index=idx)
    high = close + 0.5
    low = close - 0.5
    open_ = close
    volume = pd.Series(rng.integers(100, 1000, n), index=idx)
    return close, high, low, open_, volume


def test_enumerate_has_all_libraries():
    e = enumerate_indicators()
    assert "builtin" in e
    assert "pandas_ta" in e
    assert "talib" in e
    assert len(e["builtin"]) >= 8
    assert len(e["pandas_ta"]) >= 100
    assert len(e["talib"]) >= 50


def test_all_indicators_wrapped():
    inds = all_indicators()
    assert len(inds) >= 200


def test_run_rsi_produces_signals():
    close, high, low, open_, volume = _ohlcv()
    ind = wrap("RSI", "pandas_ta")
    run = run_indicator(ind, close, high, low, open_, volume, length=14)
    entries, exits = generate_signals(run, "pandas_ta", "RSI")
    assert len(entries) == len(close)
    assert entries.dtype == bool
    assert exits.dtype == bool


def test_run_bbands_band_signal():
    close, high, low, open_, volume = _ohlcv()
    ind = wrap("BBANDS", "pandas_ta")
    run = run_indicator(ind, close, high, low, open_, volume)
    entries, exits = generate_signals(run, "pandas_ta", "BBANDS")
    assert len(entries) == len(close)


def test_run_talib_rsi():
    close, high, low, open_, volume = _ohlcv()
    ind = wrap("RSI", "talib")
    run = run_indicator(ind, close, high, low, open_, volume, timeperiod=14)
    entries, exits = generate_signals(run, "talib", "RSI")
    assert len(entries) == len(close)


def test_combine_signals_and():
    a = np.array([True, True, False, False])
    b = np.array([True, False, True, False])
    entries, exits = combine_signals([a, b], [a, b], "and")
    assert entries.tolist() == [True, False, False, False]


def test_combine_signals_or():
    a = np.array([True, True, False, False])
    b = np.array([True, False, True, False])
    entries, exits = combine_signals([a, b], [a, b], "or")
    assert entries.tolist() == [True, True, True, False]


def test_composite_score_bounds():
    good = BacktestResult(
        trades=50, win_rate=0.6, profit_factor=2.0,
        total_return=0.3, max_drawdown=-0.1, sharpe=2.0, fill_mode="bar",
    )
    bad = BacktestResult(
        trades=5, win_rate=0.3, profit_factor=0.5,
        total_return=-0.2, max_drawdown=-0.5, sharpe=-1.0, fill_mode="bar",
    )
    assert composite_score(good) > composite_score(bad)
    assert 0.0 <= composite_score(good) <= 1.0


def test_is_viable():
    viable = BacktestResult(
        trades=20, win_rate=0.5, profit_factor=1.5,
        total_return=0.1, max_drawdown=-0.1, sharpe=1.0, fill_mode="bar",
    )
    not_viable = BacktestResult(
        trades=3, win_rate=0.5, profit_factor=1.5,
        total_return=0.1, max_drawdown=-0.1, sharpe=1.0, fill_mode="bar",
    )
    assert is_viable(viable)
    assert not is_viable(not_viable)


def test_run_backtest_no_trades_returns_none():
    close = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    entries = np.zeros(5, dtype=bool)
    exits = np.zeros(5, dtype=bool)
    assert run_backtest(close, entries, exits) is None
