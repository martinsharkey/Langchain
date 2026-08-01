"""
Tests for per-symbol graduation (#24). Mock EdgeCalculator; temp state file.
"""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Edge:
    def __init__(self, **k):
        self.closed_trades = k.get("n", 0)
        self.profit_factor = k.get("pf", 1.0)
        self.expectancy = k.get("exp", 0.0)
        self.expectancy_r = k.get("exp_r", 0.0)
        self.win_rate = k.get("wr", 0.0)
        self.max_drawdown_pct = k.get("dd", 0.0)
        self.longest_loss_streak = k.get("streak", 0)


class _Calc:
    def __init__(self, edge): self._e = edge
    def compute(self, symbol=None): return self._e


def _grad(tmp, edge):
    import src.learning.graduation as g
    g._path = lambda: os.path.join(tmp, "graduation.json")
    return g.Graduation(_Calc(edge))


def test_strong_edge_graduates():
    d = tempfile.mkdtemp()
    try:
        e = _Edge(n=200, pf=1.5, exp=0.8, exp_r=0.2, wr=52, dd=10, streak=4)
        gr = _grad(d, e)
        r = gr.evaluate("XAUUSD")
        assert r["state"] == "GRADUATED", r
        assert gr.is_graduated("XAUUSD-ECN")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_weak_edge_stays_proving():
    d = tempfile.mkdtemp()
    try:
        e = _Edge(n=50, pf=0.9, exp=-0.2, exp_r=-0.1, wr=30, dd=25, streak=10)
        gr = _grad(d, e)
        r = gr.evaluate("BTCUSD")
        assert r["state"] == "PROVING", r
        assert r["blocker"] is not None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_graduated_then_degrades_to_probation():
    d = tempfile.mkdtemp()
    try:
        import src.learning.graduation as g
        g._path = lambda: os.path.join(d, "graduation.json")
        # first graduate
        gr = g.Graduation(_Calc(_Edge(n=200, pf=1.5, exp=0.8, exp_r=0.2, wr=52, dd=10, streak=4)))
        gr.evaluate("GER40")
        assert gr.is_graduated("GER40")
        # now degrade (PF between DEMOTE floor and grad min -> PROBATION)
        gr.edge = _Calc(_Edge(n=210, pf=1.2, exp=0.1, exp_r=0.05, wr=42, dd=12, streak=6))
        r = gr.evaluate("GER40")
        assert r["state"] == "PROBATION", r
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_force_probation_only_lowers():
    d = tempfile.mkdtemp()
    try:
        gr = _grad(d, _Edge(n=200, pf=1.5, exp=0.8, exp_r=0.2, wr=52, dd=10, streak=4))
        gr.evaluate("XAUUSD")
        gr.force_probation("XAUUSD", "governor pause")
        assert gr.state("XAUUSD") == "PROBATION"
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    test_strong_edge_graduates()
    test_weak_edge_stays_proving()
    test_graduated_then_degrades_to_probation()
    test_force_probation_only_lowers()
    print("graduation tests passed")
