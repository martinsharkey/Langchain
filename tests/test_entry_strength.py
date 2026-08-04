"""
Tests for the GoldShark-exact entry: OsMA acceleration gate + learned PRICE-STRETCH
gate (the winner-separating feature) + the entry-quality learner.

Evidence-based: strength magnitude does NOT separate winners (verified on full
telemetry), so there is NO strength-floor gate. PriceStretch does separate winners.
"""
import sys, os, tempfile, sqlite3, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.strategies.confluence_signal import evaluate_confluence_bar
from src.learning.experience_db import ExperienceDatabase
from src.learning.entry_strength import EntryStrengthLearner


def _bar(**kw):
    """A bar that passes the base confluence (buy, close near EMA) unless overridden."""
    d = {"close": 2000.0, "osma": 0.6, "osma_prev": -0.1, "macd_line": 0.5,
         "ema_fast": 1999.5, "ema_prev": 1999.0, "atr": 3.0, "atr_prev": 2.9,
         "bulls_power": 2.0, "bears_power": 1.0, "rsi": 55.0, "med_atr": 3.0}
    d.update(kw)
    return d


def test_accelerating_cross_enters():
    r = evaluate_confluence_bar(_bar())  # fresh up-cross, accelerating, near EMA
    assert r["action"] == "buy", r


def test_osma_not_accelerating_holds():
    # up-cross but osma_now <= osma_prev is impossible for a real cross; test decel sell
    r = evaluate_confluence_bar(_bar(osma=0.05, osma_prev=0.10))  # no cross + not accel
    assert r["action"] == "hold"


def test_strength_magnitude_is_NOT_gated():
    """A LOW-strength but valid cross near the EMA must still enter — we deliberately
    do NOT gate on OsMA/Bulls/Bears magnitude (it does not separate winners)."""
    r = evaluate_confluence_bar(_bar(osma=0.05, osma_prev=-0.02, bulls_power=0.3, bears_power=0.2))
    assert r["action"] == "buy", r


def test_price_stretch_gate_blocks_overextended_entry():
    """With a learned max_stretch_atr, an entry far from the EMA must hold."""
    # close 2000, ema 1990, atr 3 -> stretch = 10/3 = 3.33xATR; ceiling 1.0 -> blocked
    r = evaluate_confluence_bar(_bar(close=2000.0, ema_fast=1990.0, ema_prev=1989.5),
                                cfg={"max_stretch_atr": 1.0})
    assert r["action"] == "hold" and "over-extended" in r["reason"], r


def test_price_stretch_gate_allows_near_ema_entry():
    # close 2000, ema 1999.5, atr 3 -> stretch 0.17xATR <= ceiling 1.0 -> enters
    r = evaluate_confluence_bar(_bar(close=2000.0, ema_fast=1999.5),
                                cfg={"max_stretch_atr": 1.0})
    assert r["action"] == "buy", r


def test_accel_gate_blocks_stale_cross():
    """A cross with weak OsMA acceleration must hold when accel_min is set."""
    # osma 0.55 vs prev 0.5 -> accel 0.05/atr3 = 0.017 < 0.05 min -> hold
    r = evaluate_confluence_bar(_bar(osma=0.55, osma_prev=0.50), cfg={"accel_min": 0.05})
    # note: 0.50->0.55 is not a fresh up-cross; use a fresh cross with tiny accel
    r = evaluate_confluence_bar(_bar(osma=0.02, osma_prev=-0.01), cfg={"accel_min": 0.05})
    assert r["action"] == "hold", r


def test_dom_gate_blocks_weak_power():
    r = evaluate_confluence_bar(_bar(bulls_power=0.3), cfg={"dom_min": 1.0})  # 0.3/3=0.1 < 1.0
    assert r["action"] == "hold" and "dominant power" in r["reason"], r


def test_runway_gate_blocks_low_runway():
    # osma 0.6, recent avg 0.5 -> runway 1.2 < 2.0 -> hold
    r = evaluate_confluence_bar(_bar(osma_recent_avg=0.5), cfg={"runway_min": 2.0})
    assert r["action"] == "hold" and "runway" in r["reason"], r


def test_full_recipe_allows_quality_entry():
    r = evaluate_confluence_bar(_bar(osma=0.9, osma_prev=-0.05, bulls_power=4.0, osma_recent_avg=0.3),
                                cfg={"accel_min": 0.05, "dom_min": 1.0, "runway_min": 2.0, "max_stretch_atr": 1.0})
    assert r["action"] == "buy", r


def test_learner_derives_recipe_that_lifts_entry_success():
    with tempfile.TemporaryDirectory() as d:
        db = ExperienceDatabase(db_path=os.path.join(d, "t.db"))
        def add(green, accel_ok, atr=3.0):
            ema = 1999.0; close = ema + 0.2 * atr
            osma_prev = -0.02
            osma = osma_prev + (0.3 if accel_ok else 0.03) * atr   # accel high vs low
            snap = {"osma": osma, "osma_prev": osma_prev, "bulls_power": 4.0, "bears_power": 1.0,
                    "atr": atr, "close": close, "ema_fast": ema, "osma_recent": [0.1, 0.1, 0.1]}
            tid = db.record_trade(signal={"symbol": "XAUUSD", "action": "buy", "price": close,
                                          "strategy_used": "OsMA_Confluence"},
                                  indicators=snap, outcome="pending")
            db.update_trade_outcome(trade_id=tid, outcome="win" if green else "loss",
                                    profit_loss=1.0 if green else -1.0, exit_price=close,
                                    mfe_points=(2*atr) if green else 0.0, mae_points=-5, exit_points=10)
        # fresh-accel entries go green; stale ones don't
        for _ in range(25): add(True, True)
        for _ in range(25): add(False, False)
        learner = EntryStrengthLearner(db, min_sample=30)
        r = learner.learn_symbol("XAUUSD")
        assert r is not None and r["improves"] is True, r
        assert r["gated_success"] > r["base_success"], r
        assert "accel_min" in r["recipe"], r


if __name__ == "__main__":
    test_accelerating_cross_enters()
    test_osma_not_accelerating_holds()
    test_strength_magnitude_is_NOT_gated()
    test_price_stretch_gate_blocks_overextended_entry()
    test_price_stretch_gate_allows_near_ema_entry()
    test_accel_gate_blocks_stale_cross()
    test_dom_gate_blocks_weak_power()
    test_runway_gate_blocks_low_runway()
    test_full_recipe_allows_quality_entry()
    test_learner_derives_recipe_that_lifts_entry_success()
    print("entry quality tests passed")
