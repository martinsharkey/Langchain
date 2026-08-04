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


def test_learner_derives_stretch_ceiling_that_improves_wr():
    with tempfile.TemporaryDirectory() as d:
        db = ExperienceDatabase(db_path=os.path.join(d, "t.db"))
        def add(is_win, stretch_atr, atr=3.0):
            ema = 1999.0
            close = ema + stretch_atr * atr   # controlled stretch
            snap = {"osma": 0.6, "bulls_power": 2.0, "bears_power": 1.0, "atr": atr,
                    "close": close, "ema_fast": ema}
            tid = db.record_trade(signal={"symbol": "XAUUSD", "action": "buy", "price": close,
                                          "strategy_used": "OsMA_Confluence"},
                                  indicators=snap, outcome="pending")
            db.update_trade_outcome(trade_id=tid, outcome="win" if is_win else "loss",
                                    profit_loss=1.0 if is_win else -1.0,
                                    exit_price=close + (1 if is_win else -1),
                                    mfe_points=200 if is_win else 5, mae_points=-5,
                                    exit_points=100 if is_win else -50)
        # winners enter NEAR ema (low stretch); losers enter over-extended (high stretch)
        for _ in range(20): add(True, 0.2)
        for _ in range(20): add(False, 2.5)
        learner = EntryStrengthLearner(db, min_sample=20)
        r = learner.learn_symbol("XAUUSD")
        assert r is not None and r["n"] == 40, r
        assert r["improves"] is True, r
        assert 0 < r["max_stretch_atr"] < 2.5, r
        assert r["gated_win_rate"] > r["base_win_rate"], r


if __name__ == "__main__":
    test_accelerating_cross_enters()
    test_osma_not_accelerating_holds()
    test_strength_magnitude_is_NOT_gated()
    test_price_stretch_gate_blocks_overextended_entry()
    test_price_stretch_gate_allows_near_ema_entry()
    test_learner_derives_stretch_ceiling_that_improves_wr()
    print("entry quality tests passed")
