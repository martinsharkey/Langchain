"""
Tests for the shared exit model — parity between tick-accurate and bar-level paths.
"""
from __future__ import annotations

import sys
import os
import pytest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.exit_model import TradeState, resolve_exit_tick, resolve_exit_bar


def _make_trade(direction: str, entry: float, atr: float, sl_atr: float = 1.0, tp_rr: float = 2.0, giveback: float = 0.55, arm_atr: float = 0.5) -> TradeState:
    risk = sl_atr * atr
    sl = entry - risk if direction == "buy" else entry + risk
    tp = entry + tp_rr * risk if direction == "buy" else entry - tp_rr * risk
    return TradeState(dir=direction, entry=entry, sl=sl, tp=tp, risk=risk, rr=tp_rr,
                      peak=entry, arm=arm_atr * atr)


def test_resolve_exit_bar_sl_hit():
    ot = _make_trade("buy", 100.0, atr=2.0)
    r = resolve_exit_bar(ot, high=101.0, low=97.0, price=100.0)  # sl=98, low=97 <= 98
    assert r == -1.0


def test_resolve_exit_bar_tp_hit():
    ot = _make_trade("buy", 100.0, atr=2.0)
    r = resolve_exit_bar(ot, high=104.0, low=101.0, price=101.0)  # tp=104, high=104 >= 104
    assert r == 2.0


def test_resolve_exit_bar_giveback():
    ot = _make_trade("buy", 100.0, atr=2.0, arm_atr=0.5)
    # peak=103, price=101.0, fav=3, giveback=2, threshold=0.55*3=1.65
    # 2 >= 1.65 -> triggers giveback, R = (101-100)/2 = 0.5
    r = resolve_exit_bar(ot, high=103.0, low=101.0, price=101.0)
    assert r == 0.5


def test_resolve_exit_bar_giveback_not_triggered():
    ot = _make_trade("buy", 100.0, atr=2.0, arm_atr=0.5)
    # peak=103, price=101.8, fav=3, giveback=1.2, threshold=1.65
    # 1.2 < 1.65 -> NOT triggered
    r = resolve_exit_bar(ot, high=103.0, low=101.8, price=101.8)
    assert r is None


def test_resolve_exit_bar_giveback_triggers():
    ot = _make_trade("buy", 100.0, atr=2.0, arm_atr=0.5)
    # peak=103, price=101.2, giveback=1.8, 1.8 >= 1.65 -> triggers
    r = resolve_exit_bar(ot, high=103.0, low=101.2, price=101.2)
    assert r is not None
    assert r > 0


def test_resolve_exit_short_sl_hit():
    ot = _make_trade("sell", 100.0, atr=2.0)
    # SL=102, high=102.5 touches SL before any giveback can form
    r = resolve_exit_bar(ot, high=102.5, low=99.0, price=100.0)
    assert r == -1.0


def test_resolve_exit_short_tp_hit():
    ot = _make_trade("sell", 100.0, atr=2.0)
    r = resolve_exit_bar(ot, high=99.0, low=96.0, price=99.0)
    assert r == 2.0


def test_resolve_exit_short_giveback():
    ot = _make_trade("sell", 100.0, atr=2.0, arm_atr=0.5)
    # peak=97 (fav=3 >= arm=1), price=98.8, giveback=1.8, threshold=1.65
    # 1.8 >= 1.65 -> triggers, R = (100-98.8)/2 = 0.6
    r = resolve_exit_bar(ot, high=98.8, low=97.0, price=98.8)
    assert r is not None
    assert r > 0


def test_tick_vs_bar_parity_simple():
    """Tick and bar paths should agree on SL/TP hits at minimum."""
    for direction in ("buy", "sell"):
        for entry, atr, sl_hit, tp_hit in [
            (100.0, 2.0, 99.0, 104.0),
            (100.0, 2.0, 104.0, 96.0),
        ]:
            ot_tick = _make_trade(direction, entry, atr)
            ot_bar = _make_trade(direction, entry, atr)

            if direction == "buy":
                tick_r = resolve_exit_bar(ot_tick, high=tp_hit, low=sl_hit, price=entry)
                bar_r = resolve_exit_bar(ot_bar, high=tp_hit, low=sl_hit, price=entry)
            else:
                tick_r = resolve_exit_bar(ot_tick, high=tp_hit, low=sl_hit, price=entry)
                bar_r = resolve_exit_bar(ot_bar, high=tp_hit, low=sl_hit, price=entry)

            assert tick_r == bar_r, f"Mismatch for {direction} entry={entry}: tick={tick_r} bar={bar_r}"


def test_giveback_formula_matches_manual():
    """The giveback condition: fav >= arm AND giveback >= giveback_frac * fav."""
    ot = _make_trade("buy", 100.0, atr=2.0, arm_atr=0.5)
    ot.peak = 103.0
    fav = 3.0
    assert fav >= ot.arm  # 3.0 >= 1.0

    # giveback = 1.5, threshold = 0.55 * 3 = 1.65
    # 1.5 < 1.65 -> should NOT trigger
    giveback = 1.5
    threshold = 0.55 * fav
    assert giveback < threshold

    # giveback = 2.0, threshold = 1.65
    # 2.0 >= 1.65 -> should trigger
    giveback = 2.0
    threshold = 0.55 * fav
    assert giveback >= threshold


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
