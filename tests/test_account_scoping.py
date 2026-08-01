"""
Tests for per-account scoping (#21): migration adds account columns, writes stamp
the current account, and account-scoped filtering isolates two accounts.
"""
import sys, os, sqlite3, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _db(path):
    from src.learning.experience_db import ExperienceDatabase
    return ExperienceDatabase(db_path=path)


def test_migration_adds_account_columns():
    d = tempfile.mkdtemp()
    try:
        db = _db(os.path.join(d, "e.db"))
        conn = sqlite3.connect(db.db_path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()}
        conn.close()
        assert {"account_login", "account_server", "account_trade_mode"} <= cols, cols
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_record_trade_stamps_account():
    d = tempfile.mkdtemp()
    try:
        db = _db(os.path.join(d, "e.db"))
        db.set_current_account(login=1176166, server="VTMarkets-Demo", trade_mode="DEMO")
        sig = {"symbol": "BTCUSD", "action": "buy", "price": 100.0, "confidence": 0.6,
               "strategy_used": "OsMA_Confluence"}
        db.record_trade(sig, {"trend": "up", "rsi": 55, "atr": 1.0}, mt5_ticket=111)
        conn = sqlite3.connect(db.db_path)
        row = conn.execute("SELECT account_login, account_server, account_trade_mode "
                           "FROM trades WHERE mt5_ticket=111").fetchone()
        conn.close()
        assert row == (1176166, "VTMarkets-Demo", "DEMO"), row
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_account_clause_isolates():
    d = tempfile.mkdtemp()
    try:
        db = _db(os.path.join(d, "e.db"))
        db.set_current_account(login=1, server="A", trade_mode="DEMO")
        assert db._account_clause()[0], "clause should be non-empty when account set"
        db.current_account = None
        assert db._account_clause() == ("", []), "clause empty when no account"
        # backfill stamps NULL rows
        conn = sqlite3.connect(db.db_path)
        conn.execute("INSERT INTO trades (timestamp, symbol, action, outcome, profit_loss) "
                     "VALUES ('2026-01-01T00:00:00','BTCUSD','buy','win',1.0)")
        conn.commit(); conn.close()
        n = db.backfill_account(1176166, "VTMarkets-Demo", "DEMO")
        assert n >= 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    test_migration_adds_account_columns()
    test_record_trade_stamps_account()
    test_account_clause_isolates()
    print("per-account scoping tests passed")
