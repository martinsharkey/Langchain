"""The optimizer must SYSTEMATICALLY explore strength floors + periods (directed
coordinate search), not random-sample 2 of 24 params."""
import sys, os
import json
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.learning.param_optimizer import ParameterOptimizer, DEFAULTS, SYMBOL_BASELINES
from src import config


def test_directed_search_covers_strength_floors_and_periods():
    opt = ParameterOptimizer(registry=None, backtest_fn=lambda *a, **k: None)
    base = dict(DEFAULTS)
    touched = set()
    for pname, cand in opt._directed_candidates(base):
        touched.add(pname)
    # every signed strength floor must be explored
    for k in ("osma_min_long","osma_max_short","macd_min_long","macd_max_short",
              "bulls_min_long","bears_min_long","bears_max_short","bulls_max_short"):
        assert k in touched, f"directed search never explored {k}"
    # and the periods
    for k in ("osma_fast","osma_slow","osma_signal","ema_period","atr_period","power_period","rsi_period"):
        assert k in touched, f"directed search never explored period {k}"
    # and the newly-added tunables (RSI gate + MACD-lead window)
    for k in ("rsi_long_max","rsi_short_min","macd_lead_bars"):
        assert k in touched, f"directed search never explored {k}"


def test_directed_candidates_actually_change_the_value():
    opt = ParameterOptimizer(registry=None, backtest_fn=lambda *a, **k: None)
    base = dict(DEFAULTS)
    # a strength floor at 0 should get pushed to non-zero candidates
    osma_vals = {c["osma_min_long"] for p, c in opt._directed_candidates(base) if p == "osma_min_long"}
    assert any(v > 0 for v in osma_vals), osma_vals


def test_current_params_model_json_fallback(isolated_data_dir):
    """When no tuned entry exists, current_params() must fall back to model.json."""
    opt = ParameterOptimizer(registry=None, backtest_fn=lambda *a, **k: None)
    opt.tuned = {}

    sym = "TESTSYM"
    base = sym.upper()
    qmmp_dir = os.path.join(config.DATA_DIR, "qmmp", base)
    os.makedirs(qmmp_dir, exist_ok=True)

    model = {
        "entry": {"osma_params": {"fast": 12, "slow": 26, "signal": 9}},
        "floors": {"osma_mag": {"Asian": 5.0, "London": 3.0, "NewYork": 7.0}},
        "exit": {"early": 0.2, "max_legs": 3},
        "money_management": {"gbp_per_001": 75.0, "lot_cap_per_account": 50},
    }
    with open(os.path.join(qmmp_dir, "model.json"), "w", encoding="utf-8") as f:
        json.dump(model, f)

    p = opt.current_params(sym)
    assert p["osma_fast"] == 12
    assert p["osma_slow"] == 26
    assert p["osma_signal"] == 9
    assert p["tp_rr"] == 2.0
    assert p["early_frac"] == 0.2
    assert p["max_legs"] == 3
    assert p["gbp_per_001"] == 75.0
    assert p["lot_cap_per_account"] == 50


def test_current_params_model_json_malformed(isolated_data_dir):
    """Malformed model.json must fall back to baseline/defaults gracefully."""
    opt = ParameterOptimizer(registry=None, backtest_fn=lambda *a, **k: None)
    opt.tuned = {}

    sym = "BADJSON"
    base = sym.upper()
    qmmp_dir = os.path.join(config.DATA_DIR, "qmmp", base)
    os.makedirs(qmmp_dir, exist_ok=True)

    with open(os.path.join(qmmp_dir, "model.json"), "w", encoding="utf-8") as f:
        f.write("{not valid json")

    p = opt.current_params(sym)
    assert p["osma_fast"] == DEFAULTS["osma_fast"]


def test_current_params_model_json_partial_keys(isolated_data_dir):
    """model.json with only some keys must not wipe unspecified keys."""
    opt = ParameterOptimizer(registry=None, backtest_fn=lambda *a, **k: None)
    opt.tuned = {}

    sym = "PARTIAL"
    base = sym.upper()
    qmmp_dir = os.path.join(config.DATA_DIR, "qmmp", base)
    os.makedirs(qmmp_dir, exist_ok=True)

    model = {
        "entry": {"osma_params": {"fast": 12}},
    }
    with open(os.path.join(qmmp_dir, "model.json"), "w", encoding="utf-8") as f:
        json.dump(model, f)

    p = opt.current_params(sym)
    assert p["osma_fast"] == 12
    assert p["osma_slow"] == DEFAULTS["osma_slow"]
    assert p["min_confluence"] == DEFAULTS["min_confluence"]


if __name__ == "__main__":
    test_directed_search_covers_strength_floors_and_periods()
    test_directed_candidates_actually_change_the_value()
    print("directed search tests passed")


def test_gold_proven_edge_baseline_is_the_starting_point():
    """Gold must start from the mined GoldShark proven-edge baseline (non-zero strength
    floors + osma_slow 86), not generic zeros — so the directed optimizer refines a
    config that already had an edge."""
    assert "XAUUSD" in SYMBOL_BASELINES
    o = ParameterOptimizer(registry=None, backtest_fn=lambda *a, **k: None)
    o.tuned = {}   # fresh clone, no tuned file
    p = o.current_params("XAUUSD-ECN")
    assert p["osma_slow"] == 26, p            # pass5469 proven period
    assert p["osma_min_long"] > 0, p          # non-zero strength floor (edge, not sign-only)
    assert p["bulls_min_long"] > 0, p
    assert p["osma_max_short"] < 0, p         # short floor is negative
    # BTCUSD is onboarded on H1 (QMMP): when a model.json exists, its QMMP floors are
    # mapped to live confluence keys and override the zeroed baseline. This is correct:
    # the model.json was produced on H1, so its floors ARE H1-scale.
    btc = o.current_params("BTCUSD")
    assert btc["osma_min_long"] == pytest.approx(17.971, abs=0.01), btc
    # min_confluence is a structural default (not a per-symbol floor), so it comes
    # from DEFAULTS, not SYMBOL_BASELINES (which must never carry hardcoded floors).
    assert btc["min_confluence"] == DEFAULTS["min_confluence"]


def test_optimize_cold_start_accepts_first_generalizing_candidate():
    """When the incumbent does not generalize, optimize() must accept the first
    candidate that generalizes on its own merits (cold-start rule)."""
    call_count = [0]

    def mock_bt(symbol, params, sl_atr=1.0, tp_rr=2.0):
        call_count[0] += 1
        # SYMBOL_BASELINES['XAUUSD'] has osma_min_long=2.0; treat that as the
        # non-generalizing baseline. Any other value generalizes.
        if params.get("osma_min_long") == 2.0:
            return {"pfs": [0.85, 0.92, 0.88], "wrs": [45.0, 48.0, 46.0],
                    "n_total": 150, "generalizes": False, "score": -1.0,
                    "session_scores": {}}
        return {"pfs": [1.05, 1.08, 1.03], "wrs": [52.0, 54.0, 51.0],
                "n_total": 160, "generalizes": True, "score": 1.03,
                "session_scores": {}}

    opt = ParameterOptimizer(registry=None, backtest_fn=mock_bt)
    opt.tuned = {}   # isolate from disk state
    result = opt.optimize("XAUUSD", iterations=2)
    assert result["improved"] is True, f"expected cold-start accept, got {result}"
    assert result["score"] == 1.03, result
    assert result["tried"] >= 1
    assert call_count[0] >= 2  # baseline + at least one candidate


def test_optimize_does_not_regress_after_cold_start():
    """After the incumbent is set to a generalizing candidate, subsequent candidates
    must beat its score (normal competition resumes)."""
    def mock_bt(symbol, params, sl_atr=1.0, tp_rr=2.0):
        # Check the mutated param FIRST, because candidates preserve other base keys.
        if params.get("osma_fast") == 16:
            return {"pfs": [1.15, 1.12, 1.10], "wrs": [55.0, 56.0, 54.0],
                    "n_total": 170, "generalizes": True, "score": 1.10,
                    "session_scores": {}}
        oml = params.get("osma_min_long")
        if oml == 2.0:
            return {"pfs": [0.85, 0.92, 0.88], "wrs": [45.0, 48.0, 46.0],
                    "n_total": 150, "generalizes": False, "score": -1.0,
                    "session_scores": {}}
        if oml == 2.1:
            return {"pfs": [1.05, 1.08, 1.03], "wrs": [52.0, 54.0, 51.0],
                    "n_total": 160, "generalizes": True, "score": 1.03,
                    "session_scores": {}}
        return {"pfs": [0.85, 0.92, 0.88], "wrs": [45.0, 48.0, 46.0],
                "n_total": 150, "generalizes": False, "score": -1.0,
                "session_scores": {}}

    opt = ParameterOptimizer(registry=None, backtest_fn=mock_bt)
    # Simulate a tuned entry that already generalizes (post-cold-start state)
    opt.tuned = {"XAUUSD": {"params": {"osma_min_long": 2.1}, "score": 1.03}}
    r = opt.optimize("XAUUSD", iterations=60)
    assert r["improved"] is True, f"expected improvement over incumbent, got {r}"
    assert r["score"] == 1.10, r
    # SYMBOL_BASELINES must never carry hardcoded floors (R3/R5 automation rule):
    # neither BTCUSD nor XAUUSD may define osma_min_long in the baseline.
    assert "osma_min_long" not in SYMBOL_BASELINES["BTCUSD"]
    assert "osma_min_long" not in SYMBOL_BASELINES["XAUUSD"]
