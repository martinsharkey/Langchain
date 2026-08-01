"""
Tests for ContinualResearcher (#32) — review + mql5-grounded hypothesis + daily
idempotency. No network, no gh, no MT5 (gh calls are guarded by _gh_available).
"""
import sys, os, sqlite3, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _DB:
    def __init__(self, path): self.db_path = path


class _MQL5:
    def research(self, q, n_results=3):
        return [{"text": "Lower OsMA fast period to react faster and catch the cross earlier.",
                 "metadata": {"title": "iOsMA"}, "similarity": 0.8}]


def _make_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE trades (id INTEGER PRIMARY KEY, symbol TEXT, outcome TEXT,
                    profit_loss REAL, exit_reason TEXT, strategy_used TEXT)""")
    for i, (sym, oc, pl, ex, st) in enumerate(rows):
        conn.execute("INSERT INTO trades (symbol,outcome,profit_loss,exit_reason,strategy_used) "
                     "VALUES (?,?,?,?,?)", (sym, oc, pl, ex, st))
    conn.commit(); conn.close()


def test_review_and_hypothesis():
    d = tempfile.mkdtemp()
    try:
        dbp = os.path.join(d, "exp.db")
        rows = [("BTCUSD", "loss", -1.0, "sl", "EMA_TrendFollow")] * 12 + \
               [("BTCUSD", "win", 0.6, "tp", "EMA_TrendFollow")] * 3
        _make_db(dbp, rows)
        from src.learning.continual_researcher import ContinualResearcher
        r = ContinualResearcher(_DB(dbp), mql5_knowledge=_MQL5(), knowledge_store=None)
        res = r.research_symbol("BTCUSD")
        assert res["review"]["n"] == 15
        assert res["review"]["expectancy"] < 0
        assert res["hypothesis"] and "osma" in res["hypothesis"].lower()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_daily_cycle_idempotent():
    d = tempfile.mkdtemp()
    try:
        dbp = os.path.join(d, "exp.db")
        _make_db(dbp, [("BTCUSD", "win", 0.5, "tp", "X")] * 12)
        from src.learning.continual_researcher import ContinualResearcher
        r = ContinualResearcher(_DB(dbp), mql5_knowledge=_MQL5(), knowledge_store=None)
        # force gh unavailable path by ensuring no issues filed for positive expectancy
        s1 = r.daily_cycle(["BTCUSD"])
        assert not s1.get("skipped")
        s2 = r.daily_cycle(["BTCUSD"])  # same day -> skipped
        assert s2.get("skipped") is True
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    test_review_and_hypothesis()
    test_daily_cycle_idempotent()
    print("continual researcher tests passed")
