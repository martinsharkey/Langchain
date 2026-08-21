"""
Closed-loop integration test — verify the full self-learning pipeline works
end-to-end: mock trade data -> post-mortem -> directives -> param_optimizer
-> ChangeValidator -> apply_tuned -> tuned_params.json changes.
"""
from __future__ import annotations

import sys
import os
import json
import pytest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.learning.param_optimizer import ParameterOptimizer
from src.learning.change_validator import ChangeValidator
from src.learning.strategy_registry import StrategyRegistry


def test_closed_loop_cold_start_accepts_first_generalizing(tmp_path):
    """When the incumbent doesn't generalize, the first generalizing candidate
    should be accepted by optimize() and written via apply_tuned().
    """
    call_num = [0]
    original_persist = ParameterOptimizer._persist
    persist_calls = []
    
    def mock_persist(self):
        persist_calls.append(dict(self.tuned))
        # Actually persist to tmp_path for realism
        tmp_file = tmp_path / "tuned_params.json"
        import json
        with open(tmp_file, "w") as f:
            json.dump(dict(self.tuned), f)
    
    try:
        ParameterOptimizer._persist = mock_persist
        
        opt = ParameterOptimizer(registry=StrategyRegistry(), backtest_fn=None)
        
        def cold_start_bt(symbol, params, sl_atr=1.0, tp_rr=2.0):
            call_num[0] += 1
            if call_num[0] == 1:
                return {
                    "pfs": [0.9, 0.95, 0.92],
                    "wrs": [45.0, 47.0, 46.0],
                    "n_total": 100,
                    "generalizes": False,
                    "score": 0.9,
                    "session_scores": {},
                }
            else:
                return {
                    "pfs": [1.05, 1.08, 1.03],
                    "wrs": [52.0, 54.0, 51.0],
                    "n_total": 160,
                    "generalizes": True,
                    "score": 1.03,
                    "session_scores": {
                        "Asian": {"trades": 30, "wins": 10, "losses": 20, "gross_win_r": 15.0, "gross_loss_r": 20.0, "pf": 0.75, "wr": 33.3},
                        "London": {"trades": 80, "wins": 40, "losses": 40, "gross_win_r": 50.0, "gross_loss_r": 40.0, "pf": 1.25, "wr": 50.0},
                        "NewYork": {"trades": 50, "wins": 28, "losses": 22, "gross_win_r": 32.0, "gross_loss_r": 22.0, "pf": 1.45, "wr": 56.0},
                    },
                }
        
        opt.backtest_fn = cold_start_bt
        
        result = opt.optimize("XAUUSD", iterations=12, directives={"tp_rr": 3.0})
        
        assert result.get("improved") is True, f"Expected improved=True, got {result}"
        assert result.get("score") == 1.03, f"Score should be 1.03, got {result.get('score')}"
        assert len(persist_calls) > 0, "apply_tuned should have persisted params"
        
    finally:
        ParameterOptimizer._persist = original_persist


def test_closed_loop_second_run_beats_new_incumbent(tmp_path):
    """After cold-start establishes a new incumbent at 1.03, a second run
    with candidates scoring 1.06 should improve over that incumbent.
    """
    call_num = [0]
    original_persist = ParameterOptimizer._persist
    persist_calls = []
    
    def mock_persist(self):
        persist_calls.append(dict(self.tuned))
        tmp_file = tmp_path / "tuned_params.json"
        with open(tmp_file, "w") as f:
            json.dump(dict(self.tuned), f)
    
    try:
        ParameterOptimizer._persist = mock_persist
        
        opt = ParameterOptimizer(registry=StrategyRegistry(), backtest_fn=None)
        
        # First run: base doesn't generalize, guided candidate does (1.03)
        def bt_run1(symbol, params, sl_atr=1.0, tp_rr=2.0):
            call_num[0] += 1
            if call_num[0] == 1:
                return {
                    "pfs": [0.9, 0.95, 0.92],
                    "wrs": [45.0, 47.0, 46.0],
                    "n_total": 100,
                    "generalizes": False,
                    "score": 0.9,
                    "session_scores": {},
                }
            elif call_num[0] == 2:
                return {
                    "pfs": [1.05, 1.08, 1.03],
                    "wrs": [52.0, 54.0, 51.0],
                    "n_total": 160,
                    "generalizes": True,
                    "score": 1.03,
                    "session_scores": {},
                }
            else:
                return {
                    "pfs": [0.95, 0.98, 0.96],
                    "wrs": [48.0, 49.0, 48.0],
                    "n_total": 140,
                    "generalizes": False,
                    "score": 0.95,
                    "session_scores": {},
                }
        
        opt.backtest_fn = bt_run1
        result1 = opt.optimize("XAUUSD", iterations=12, directives={"tp_rr": 3.0})
        assert result1.get("improved") is True
        assert result1.get("score") == 1.03
        
        # Second run: base params (now tuned) score 1.03, candidates score 1.06
        call_num[0] = 0
        def bt_run2(symbol, params, sl_atr=1.0, tp_rr=2.0):
            call_num[0] += 1
            # Base params from tuned (written by first run) score 1.03
            if params.get("tp_rr") == 3.0 and params.get("osma_min_long") == 1.37:
                return {
                    "pfs": [1.05, 1.08, 1.03],
                    "wrs": [52.0, 54.0, 51.0],
                    "n_total": 160,
                    "generalizes": True,
                    "score": 1.03,
                    "session_scores": {},
                }
            return {
                "pfs": [1.08, 1.10, 1.06],
                "wrs": [53.0, 55.0, 52.0],
                "n_total": 170,
                "generalizes": True,
                "score": 1.06,
                "session_scores": {},
            }
        
        opt.backtest_fn = bt_run2
        result2 = opt.optimize("XAUUSD", iterations=12)
        assert result2.get("improved") is True, f"Second run should improve, got {result2}"
        assert result2.get("score") == 1.06, f"Should beat new incumbent 1.03, got {result2.get('score')}"
        
    finally:
        ParameterOptimizer._persist = original_persist


def test_closed_loop_rejects_below_new_incumbent(tmp_path):
    """After cold-start establishes a new incumbent at 1.03, a candidate
    scoring 1.01 must be rejected.
    """
    call_num = [0]
    original_persist = ParameterOptimizer._persist
    persist_calls = []
    
    def mock_persist(self):
        persist_calls.append(dict(self.tuned))
        tmp_file = tmp_path / "tuned_params.json"
        with open(tmp_file, "w") as f:
            json.dump(dict(self.tuned), f)
    
    try:
        ParameterOptimizer._persist = mock_persist
        
        opt = ParameterOptimizer(registry=StrategyRegistry(), backtest_fn=None)
        
        def bt_fn(symbol, params, sl_atr=1.0, tp_rr=2.0):
            if call_num[0] == 0:
                call_num[0] += 1
                return {
                    "pfs": [0.9, 0.95, 0.92],
                    "wrs": [45.0, 47.0, 46.0],
                    "n_total": 100,
                    "generalizes": False,
                    "score": 0.9,
                    "session_scores": {},
                }
            elif call_num[0] == 1:
                call_num[0] += 1
                return {
                    "pfs": [1.05, 1.08, 1.03],
                    "wrs": [52.0, 54.0, 51.0],
                    "n_total": 160,
                    "generalizes": True,
                    "score": 1.03,
                    "session_scores": {},
                }
            else:
                return {
                    "pfs": [1.01, 1.02, 1.00],
                    "wrs": [50.0, 51.0, 50.0],
                    "n_total": 150,
                    "generalizes": True,
                    "score": 1.01,
                    "session_scores": {},
                }
        
        opt.backtest_fn = bt_fn
        
        # First run: establish incumbent at 1.03
        result1 = opt.optimize("XAUUSD", iterations=12, directives={"tp_rr": 3.0})
        assert result1.get("improved") is True
        assert result1.get("score") == 1.03
        
        # Second run: all candidates score 1.01 (below new incumbent 1.03)
        result2 = opt.optimize("XAUUSD", iterations=12)
        assert result2.get("improved") is False, f"Weaker candidate should be rejected, got {result2}"
        
    finally:
        ParameterOptimizer._persist = original_persist


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
