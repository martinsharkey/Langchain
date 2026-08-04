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
        learner = EntryStrengthLearner(db, min_sample=30, min_trades_per_day=1.0)
        r = learner.learn_symbol("XAUUSD")
        assert r is not None and r["improves"] is True, r
        assert r["gated_success"] > r["base_success"], r
        # learner found SOME separating gate (via frequency analyzer or greedy path)
        assert r["recipe"], r


def test_frequency_analyzer_recommends_without_choking():
    """The frequency analyzer must recommend a strength level that lifts success but
    keeps >= min_trades_per_day (never chokes to zero)."""
    from src.learning.entry_frequency import EntryFrequencyAnalyzer
    import datetime as _dt
    with tempfile.TemporaryDirectory() as d:
        db = ExperienceDatabase(db_path=os.path.join(d, "t.db"))
        today = _dt.date.today().isoformat()
        def add(green, dom, atr=3.0):
            snap = {"osma": 0.6, "osma_prev": -0.1, "bulls_power": dom * atr, "bears_power": 1.0,
                    "atr": atr, "close": 2000.4, "ema_fast": 2000.0, "osma_recent": [0.2, 0.2]}
            tid = db.record_trade(signal={"symbol": "BTCUSD", "action": "buy", "price": 2000,
                                          "strategy_used": "OsMA_Confluence"},
                                  indicators=snap, outcome="pending")
            db.update_trade_outcome(trade_id=tid, outcome="win" if green else "loss",
                                    profit_loss=1.0 if green else -1.0, exit_price=2001,
                                    mfe_points=(2*atr) if green else 0.0, mae_points=-5, exit_points=10)
        # high-dom entries win; low-dom entries lose. plenty of volume (no choke risk).
        for _ in range(30): add(True, 1.5)
        for _ in range(30): add(False, 0.2)
        fa = EntryFrequencyAnalyzer(db, min_clean_date="2000-01-01")
        a = fa.analyze("BTCUSD", days=1, min_trades_per_day=3.0)
        assert a["recommended"] is not None, a
        assert a["recommended"]["success"] > a["base_success"], a
        assert a["recommended"]["per_day"] >= 3.0, a   # did not choke


def test_frequency_analyzer_wont_choke_when_all_levels_too_thin():
    """If every tightening drops below the floor, recommend nothing (keep base)."""
    from src.learning.entry_frequency import EntryFrequencyAnalyzer
    with tempfile.TemporaryDirectory() as d:
        db = ExperienceDatabase(db_path=os.path.join(d, "t.db"))
        def add(dom):
            snap = {"osma": 0.6, "osma_prev": -0.1, "bulls_power": dom * 3.0, "bears_power": 1.0,
                    "atr": 3.0, "close": 2000.4, "ema_fast": 2000.0, "osma_recent": [0.2]}
            tid = db.record_trade(signal={"symbol": "XAUUSD", "action": "buy", "price": 2000,
                                          "strategy_used": "OsMA_Confluence"},
                                  indicators=snap, outcome="pending")
            db.update_trade_outcome(trade_id=tid, outcome="loss", profit_loss=-1.0,
                                    exit_price=1999, mfe_points=0.0, mae_points=-5, exit_points=-10)
        for _ in range(25): add(0.1)   # only 25 trades total, tightening -> < floor
        fa = EntryFrequencyAnalyzer(db, min_clean_date="2000-01-01")
        a = fa.analyze("XAUUSD", days=1, min_trades_per_day=100.0)  # impossible floor
        assert a["recommended"] is None, a   # correctly refuses to choke


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
    test_frequency_analyzer_recommends_without_choking()
    test_frequency_analyzer_wont_choke_when_all_levels_too_thin()
    print("entry quality tests passed")


def test_signed_strength_floors_enforced_when_set():
    """Signed per-side strength floors (ATR-normalized) must gate when != 0, and be
    OFF at 0 (sign-only). This is the core buyer/seller-vigour signal."""
    from src.strategies.confluence_signal import evaluate_confluence_bar
    # fresh long, osma just above 0. atr=3. bulls=2.0 -> bulls/atr=0.67
    base = {"close": 2000.0, "osma": 0.6, "osma_prev": -0.1, "macd_line": 0.5,
            "ema_fast": 1999.5, "ema_prev": 1999.0, "atr": 3.0, "atr_prev": 2.9,
            "bulls_power": 2.0, "bears_power": 1.0, "rsi": 55.0, "med_atr": 3.0}
    # floor OFF (0) -> enters
    assert evaluate_confluence_bar(dict(base), {}).get("action") == "buy"
    # bulls_min_long 1.0 (ATR units) -> needs bulls >= 1.0*3 = 3.0; bulls=2.0 -> HOLD
    r = evaluate_confluence_bar(dict(base), {"bulls_min_long": 1.0})
    assert r["action"] == "hold" and "strength" in r["reason"], r
    # bulls_min_long 0.5 -> needs bulls >= 1.5; bulls=2.0 -> passes -> buy
    assert evaluate_confluence_bar(dict(base), {"bulls_min_long": 0.5}).get("action") == "buy"


def test_strength_floor_scales_per_symbol_by_atr():
    """The SAME ATR-normalized floor must translate to different raw levels per symbol
    (gold small ATR, BTC big ATR) — proving one PARAM_SPACE range fits all symbols."""
    from src.strategies.confluence_signal import evaluate_confluence_bar
    gold = {"close": 2000.0, "osma": 0.6, "osma_prev": -0.1, "macd_line": 0.5,
            "ema_fast": 1999.5, "ema_prev": 1999.0, "atr": 3.0, "atr_prev": 2.9,
            "bulls_power": 2.0, "bears_power": 1.0, "rsi": 55.0, "med_atr": 3.0}
    btc = dict(gold); btc.update({"atr": 100.0, "atr_prev": 99.0, "bulls_power": 60.0,
                                  "osma": 15.0, "osma_prev": -1.0, "macd_line": 10.0})
    # floor 0.5 ATR: gold needs bulls>=1.5 (has 2.0 -> buy), BTC needs bulls>=50 (has 60 -> buy)
    assert evaluate_confluence_bar(dict(gold), {"bulls_min_long": 0.5}).get("action") == "buy"
    assert evaluate_confluence_bar(dict(btc), {"bulls_min_long": 0.5}).get("action") == "buy"
    # floor 0.8 ATR: gold needs bulls>=2.4 (has 2.0 -> HOLD), BTC needs bulls>=80 (has 60 -> HOLD)
    assert evaluate_confluence_bar(dict(gold), {"bulls_min_long": 0.8}).get("action") == "hold"
    assert evaluate_confluence_bar(dict(btc), {"bulls_min_long": 0.8}).get("action") == "hold"


def test_strength_params_in_param_space_wide_and_signed():
    """All 8 signed floors must be in PARAM_SPACE with WIDE ranges (reach +-3+)."""
    from src.learning.param_optimizer import PARAM_SPACE
    for k in ("osma_min_long","osma_max_short","macd_min_long","macd_max_short",
              "bulls_min_long","bears_min_long","bears_max_short","bulls_max_short"):
        assert k in PARAM_SPACE, f"missing {k}"
    # long floors reach >=3, short floors reach <=-3 (ATR units -> raw far beyond +-3)
    assert PARAM_SPACE["osma_min_long"][1] >= 3.0
    assert PARAM_SPACE["osma_max_short"][0] <= -3.0
    assert PARAM_SPACE["bulls_min_long"][1] >= 3.0
