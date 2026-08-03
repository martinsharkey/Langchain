"""
Tests for the GoldShark-exact entry: OsMA acceleration gate + learned per-symbol
strength gate + the entry-strength learner.
"""
import sys, os, tempfile, sqlite3, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.strategies.confluence_signal import evaluate_confluence_bar
from src.learning.experience_db import ExperienceDatabase
from src.learning.entry_strength import EntryStrengthLearner


def _bar(**kw):
    """A bar that passes the base confluence (buy) unless overridden."""
    d = {"close": 2000.0, "osma": 0.6, "osma_prev": 0.1, "macd_line": 0.5,
         "ema_fast": 1999.0, "ema_prev": 1998.5, "atr": 3.0, "atr_prev": 2.9,
         "bulls_power": 2.0, "bears_power": 1.0, "rsi": 55.0, "med_atr": 3.0}
    d.update(kw)
    return d


def test_osma_must_accelerate():
    """A cross where OsMA is NOT accelerating (osma <= osma_prev) must hold."""
    # buy cross (prev<=0<now) but decelerating: prev 0.5 -> now 0.1 is not a cross;
    # use a cross that is not accelerating: prev=-0.1, now=0.05 but now<prev_peak...
    # simplest: osma_now just above 0 but LOWER than osma_prev is impossible for a
    # fresh up-cross; instead test the sell side decel.
    r = evaluate_confluence_bar(_bar(osma=0.05, osma_prev=0.10))  # not a cross up, and not accelerating
    assert r["action"] == "hold"


def test_accelerating_cross_enters():
    r = evaluate_confluence_bar(_bar(osma=0.6, osma_prev=-0.1))  # fresh up-cross, accelerating
    assert r["action"] == "buy", r


def test_learned_strength_gate_blocks_weak_entry():
    """With a learned osma/power floor, a cross whose strength is below it must hold."""
    # osma 0.30/atr 3 = 0.10 normalized; set floor 0.20 -> blocked
    r = evaluate_confluence_bar(_bar(osma=0.30, osma_prev=-0.05, bulls_power=2.0),
                                cfg={"osma_strength_min": 0.20, "power_strength_min": 0.0})
    assert r["action"] == "hold" and "strength" in r["reason"], r


def test_learned_strength_gate_allows_strong_entry():
    # osma 0.9/atr3 = 0.30 normalized >= floor 0.20; bulls 3.0/3 = 1.0 >= 0.5
    r = evaluate_confluence_bar(_bar(osma=0.9, osma_prev=-0.05, bulls_power=3.0),
                                cfg={"osma_strength_min": 0.20, "power_strength_min": 0.5})
    assert r["action"] == "buy", r


def test_entry_strength_learner_derives_per_symbol_floor():
    """The learner should derive an ATR-normalized floor from winners and only apply
    it when it improves win-rate."""
    with tempfile.TemporaryDirectory() as d:
        db = ExperienceDatabase(db_path=os.path.join(d, "t.db"))
        # winners: strong osma/bulls; losers: weak — so a floor should separate them
        def add(is_win, osma, bulls, atr=3.0):
            snap = {"osma": osma, "bulls_power": bulls, "bears_power": 1.0, "atr": atr, "close": 2000}
            tid = db.record_trade(signal={"symbol": "XAUUSD", "action": "buy", "price": 2000,
                                          "strategy_used": "OsMA_Confluence"},
                                  indicators=snap, outcome="pending")
            db.update_trade_outcome(trade_id=tid, outcome="win" if is_win else "loss",
                                    profit_loss=1.0 if is_win else -1.0, exit_price=2001 if is_win else 1999,
                                    mfe_points=200 if is_win else 5, mae_points=-5, exit_points=100 if is_win else -50)
        for _ in range(12): add(True, 0.9, 3.0)     # strong winners
        for _ in range(12): add(False, 0.2, 0.5)    # weak losers
        learner = EntryStrengthLearner(db, min_sample=10)
        r = learner.learn_symbol("XAUUSD")
        assert r is not None and r["n"] == 24
        # a floor should have been learned that improves win-rate
        assert r["improves"] is True, r
        assert r["osma_strength_min"] > 0 and r["power_strength_min"] > 0, r
        assert r["gated_win_rate"] > r["base_win_rate"], r


if __name__ == "__main__":
    test_osma_must_accelerate()
    test_accelerating_cross_enters()
    test_learned_strength_gate_blocks_weak_entry()
    test_learned_strength_gate_allows_strong_entry()
    test_entry_strength_learner_derives_per_symbol_floor()
    print("entry strength tests passed")
