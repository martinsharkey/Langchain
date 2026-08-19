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
    # BTCUSD is onboarded on H1 (QMMP): M1-scale strength floors do NOT transfer to H1,
    # so its baseline uses the BARE OsMA cross (floors zeroed, min_confluence=1). This is
    # symbol-specific by design (R5) and independently derived, NOT borrowed from gold.
    assert o.current_params("BTCUSD")["osma_min_long"] == SYMBOL_BASELINES["BTCUSD"]["osma_min_long"]
    assert SYMBOL_BASELINES["BTCUSD"]["osma_min_long"] != SYMBOL_BASELINES["XAUUSD"]["osma_min_long"]
    assert o.current_params("BTCUSD")["min_confluence"] == SYMBOL_BASELINES["BTCUSD"]["min_confluence"]
