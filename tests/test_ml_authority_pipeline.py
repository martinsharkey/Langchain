"""
Tests for the ML authority pipeline: adjustment ledger + ML pattern store +
AUTHORITY GATE. Pure DB logic on a temp database — no MT5, no live model needed
for the gate tests. Verifies the owner's rule: an ML pattern only becomes an
authoritative (usable-live) source once it proves enough support.
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.learning.experience_db import ExperienceDatabase


def _db():
    d = tempfile.mkdtemp()
    return ExperienceDatabase(db_path=os.path.join(d, "t.db"))


def test_adjustment_ledger_is_append_only():
    db = _db()
    db.record_adjustment("XAUUSD", "sl_atr", 1.0, 1.2, backtest_pf=1.3, fwd_pf=1.1,
                         exp_before=-0.02, exp_after=0.05, n_samples=120, adopted=True)
    db.record_adjustment("XAUUSD", "sl_atr", 1.2, 1.4, backtest_pf=1.4, fwd_pf=1.2,
                         exp_before=0.05, exp_after=0.08, n_samples=150, adopted=True)
    hist = db.adjustment_history(symbol="XAUUSD", param="sl_atr")
    assert len(hist) == 2, "ledger must RETAIN every adjustment, not overwrite"
    # newest first
    assert hist[0]["new_value"] == 1.4 and hist[1]["new_value"] == 1.2


def test_ledger_is_per_symbol():
    db = _db()
    db.record_adjustment("XAUUSD", "tp_rr", 2.0, 2.2, n_samples=100)
    db.record_adjustment("BTCUSD", "tp_rr", 1.5, 1.8, n_samples=100)
    assert len(db.adjustment_history(symbol="XAUUSD")) == 1
    assert len(db.adjustment_history(symbol="BTCUSD")) == 1


def test_ml_pattern_below_threshold_stays_provisional():
    db = _db()
    # weak support: few samples, no backtests
    db.record_ml_pattern("XAUUSD", "osma_importance", feature="osma_closed",
                         importance=0.4, support_samples=20, support_backtests=0, oos_score=0.6)
    promoted = db.promote_ml_patterns(min_samples=200, min_backtests=3, min_oos_score=0.55)
    assert promoted == 0, "under-supported pattern must NOT gain authority"
    assert db.authoritative_patterns("XAUUSD") == []


def test_ml_pattern_above_threshold_becomes_authoritative():
    db = _db()
    db.record_ml_pattern("XAUUSD", "osma_importance", feature="osma_closed",
                         importance=0.5, support_samples=300, support_backtests=5, oos_score=0.62)
    promoted = db.promote_ml_patterns(min_samples=200, min_backtests=3, min_oos_score=0.55)
    assert promoted == 1, "well-supported pattern must earn authority"
    auth = db.authoritative_patterns("XAUUSD")
    assert len(auth) == 1 and auth[0]["feature"] == "osma_closed"


def test_ml_authority_revoked_if_oos_too_low():
    db = _db()
    # plenty of samples/backtests but OOS score below the bar -> not authoritative
    db.record_ml_pattern("BTCUSD", "rsi_importance", feature="rsi",
                         importance=0.3, support_samples=500, support_backtests=10, oos_score=0.50)
    promoted = db.promote_ml_patterns(min_samples=200, min_backtests=3, min_oos_score=0.55)
    assert promoted == 0, "OOS below bar must block authority even with big sample"


def test_gate_is_reproducible_and_downgrades():
    """If thresholds tighten, a previously-authoritative pattern is downgraded."""
    db = _db()
    db.record_ml_pattern("XAUUSD", "macd_importance", feature="macd_line",
                         importance=0.4, support_samples=250, support_backtests=4, oos_score=0.58)
    assert db.promote_ml_patterns(200, 3, 0.55) == 1
    # tighten sample requirement above what the pattern has
    assert db.promote_ml_patterns(400, 3, 0.55) == 0
    assert db.authoritative_patterns("XAUUSD") == []
