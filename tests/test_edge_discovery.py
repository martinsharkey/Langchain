"""
Tests for automated edge discovery (#31) — overlay merge + sweep orchestration.

Uses a mock registry + mock backtester (no MT5/rates). Verifies:
  * a validated pocket is written to the overlay and edge_weights accessors merge it;
  * a symbol with no generalizing pocket gets an empty focused entry (ensemble fallback);
  * the overlay wins over the static seed.
"""
import sys, os, json, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Strat:
    def __init__(self, name): self.name = name


class _Registry:
    def __init__(self, names): self._strategies = {n: _Strat(n) for n in names}
    def list_strategies(self): return list(self._strategies.values())


class _Backtester:
    """Returns a generalizing result only for (EMA_TrendFollow, trending)."""
    def walkforward_focused(self, symbol, params, timeframe="M15", **kw):
        import src.learning.edge_weights as ew
        rules = ew.focused_rules(symbol) or []
        for name, regimes in rules:
            if name == "EMA_TrendFollow" and "trending" in regimes:
                return {"pfs": [1.3, 1.25, 1.4], "wrs": [50, 48, 52],
                        "n_total": 120, "generalizes": True, "score": 1.25}
        return {"pfs": [0.8], "wrs": [30], "n_total": 40,
                "generalizes": False, "score": 0.8}


def test_sweep_writes_overlay_and_accessors_merge(monkeypatch=None):
    d = tempfile.mkdtemp()
    try:
        # point DATA_DIR at temp so overlay writes there
        from src import config
        orig_dir = config.DATA_DIR
        config.DATA_DIR = d
        import importlib
        import src.learning.edge_weights as ew
        importlib.reload(ew)  # pick up temp DATA_DIR for overlay path

        from src.learning.edge_discovery import EdgeDiscovery
        reg = _Registry(["EMA_TrendFollow", "RSI_Momentum"])
        disc = EdgeDiscovery(reg, _Backtester(), min_pf=1.15)
        overlay = disc.sweep_all(["XYZUSD"], timeframe="M15", persist=True)

        # overlay captured the validated pocket
        assert overlay["focused_edge"]["XYZUSD"] == [["EMA_TrendFollow", ["trending"]]], overlay
        assert "EMA_TrendFollow" in overlay["edge_weights"]["XYZUSD"]

        # file written
        p = os.path.join(d, "edge_weights.json")
        assert os.path.exists(p)
        with open(p) as f:
            assert "XYZUSD" in json.load(f)["focused_edge"]

        # accessors merge overlay over static seed
        ew.reload_overlay()
        assert ew.focused_rules("XYZUSD-ECN") == [("EMA_TrendFollow", {"trending"})]
        assert ew.edge_weight("XYZUSD", "EMA_TrendFollow") > 1.0
        assert ew.regime_edge_weight("XYZUSD", "EMA_TrendFollow", "trending") >= 1.15

        config.DATA_DIR = orig_dir
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_no_edge_symbol_gets_empty_focused():
    d = tempfile.mkdtemp()
    try:
        from src import config
        orig_dir = config.DATA_DIR
        config.DATA_DIR = d
        import importlib
        import src.learning.edge_weights as ew
        importlib.reload(ew)

        from src.learning.edge_discovery import EdgeDiscovery

        class _AllFail:
            def walkforward_focused(self, *a, **k):
                return {"pfs": [0.7], "wrs": [20], "n_total": 30,
                        "generalizes": False, "score": 0.7}

        reg = _Registry(["RSI_Momentum"])
        disc = EdgeDiscovery(reg, _AllFail(), min_pf=1.15)
        overlay = disc.sweep_all(["NOEDGE"], persist=True)
        assert overlay["focused_edge"]["NOEDGE"] == []       # empty -> ensemble fallback
        assert overlay["meta"]["symbols"]["NOEDGE"]["validated"] is False
        config.DATA_DIR = orig_dir
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    test_sweep_writes_overlay_and_accessors_merge()
    test_no_edge_symbol_gets_empty_focused()
    print("edge discovery tests passed")
