"""Test MFE/MAE/exit-points persistence + capture_stats (exit-capture study)."""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.experience_db import ExperienceDatabase


def _db(d):
    return ExperienceDatabase(db_path=os.path.join(d, "e.db"))


def test_migration_adds_excursion_columns():
    d = tempfile.mkdtemp()
    try:
        db = _db(d)
        import sqlite3
        cols = {r[1] for r in sqlite3.connect(db.db_path).execute("PRAGMA table_info(trades)").fetchall()}
        assert {"mfe_points", "mae_points", "exit_points"} <= cols
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_update_and_capture_stats():
    d = tempfile.mkdtemp()
    try:
        db = _db(d)
        # record + close 3 trades with excursion: exits capture ~60% of peak
        for i, (mfe, exitp) in enumerate([(100, 60), (80, 50), (120, 70)]):
            sig = {"symbol": "BTCUSD", "action": "buy", "price": 100.0, "confidence": 0.6,
                   "strategy_used": "OsMA_Confluence"}
            tid = db.record_trade(sig, {"trend": "up", "rsi": 55, "atr": 1.0}, mt5_ticket=100 + i)
            db.update_trade_outcome(tid, "win", profit_loss=exitp, exit_price=100 + exitp/100,
                                    mfe_points=mfe, mae_points=-20, exit_points=exitp)
        cs = db.capture_stats("BTCUSD")
        assert cs["n"] == 3
        assert cs["median_mfe"] == 100
        assert cs["median_mae"] == -20
        # median capture: exits were 60/100, 50/80, 70/120 -> ~0.6
        assert 0.5 <= cs["median_capture_ratio"] <= 0.7, cs
        assert cs["left_on_table_pct"] is not None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_capture_stats_empty_when_no_mfe():
    d = tempfile.mkdtemp()
    try:
        db = _db(d)
        assert db.capture_stats()["n"] == 0
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    test_migration_adds_excursion_columns()
    test_update_and_capture_stats()
    test_capture_stats_empty_when_no_mfe()
    print("mfe capture tests passed")
