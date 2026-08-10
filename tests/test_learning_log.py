"""Test LearningLog (#45.1) — rolling most-recent-first digest, non-fatal."""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.learning_log import LearningLog


def test_records_most_recent_first_with_header():
    d = tempfile.mkdtemp()
    try:
        lg = LearningLog(path=os.path.join(d, "L.md"))
        lg.exit_lock("BTCUSD", 2.0, 1.0, "excursion", metric="exp -0.03 (n=30)")
        lg.revert("XAUUSD", why="degraded", metric="restored sl_atr 0.8")
        txt = open(os.path.join(d, "L.md"), encoding="utf-8").read()
        assert txt.startswith("# Learning & Adjustments Log")
        lines = [l for l in txt.splitlines() if l.startswith("- ")]
        assert len(lines) == 2
        assert "REVERT" in lines[0] and "XAUUSD" in lines[0]   # most recent first
        assert "EXIT-LOCK" in lines[1]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_config_change_and_discovery():
    d = tempfile.mkdtemp()
    try:
        lg = LearningLog(path=os.path.join(d, "L.md"))
        lg.config_change("BTCUSD", {"osma_fast": (12, 18)}, why="optimizer", metric="PF 1.1->1.3")
        lg.discovery("BTCUSD", "whale edge marginal", metric="PF 0.70 vs 0.60")
        txt = open(os.path.join(d, "L.md"), encoding="utf-8").read()
        assert "osma_fast 12→18" in txt
        assert "DISCOVERY" in txt and "marginal" in txt
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_cap_and_nonfatal():
    d = tempfile.mkdtemp()
    try:
        lg = LearningLog(path=os.path.join(d, "L.md"), max_entries=5)
        for i in range(20):
            lg.record("CONFIG", "X", f"change {i}")
        lines = [l for l in open(os.path.join(d, "L.md"), encoding="utf-8").read().splitlines() if l.startswith("- ")]
        assert len(lines) == 5
        assert "change 19" in lines[0]  # newest kept
        # non-fatal on bad path
        LearningLog(path="/nonexistent/dir/x.md").record("X", "Y", "z")  # no raise
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    test_records_most_recent_first_with_header()
    test_config_change_and_discovery()
    test_cap_and_nonfatal()
    print("learning log tests passed")
