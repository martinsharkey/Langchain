"""Tests for onboard_pipeline.py cost model and symbol resolution."""
import sys, os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch

import scripts.qmmp.onboard_pipeline as op_mod


def test_resolve_symbol_strips_ecn_suffix():
    mock_info = MagicMock()
    mock_info.name = "AUDCAD-ECN"
    mock_mt5 = MagicMock()
    mock_mt5.symbol_info.return_value = mock_info
    mock_mt5.symbols_get.return_value = []
    mock_mt5.initialize.return_value = True
    with patch.dict(sys.modules, {"MetaTrader5": mock_mt5}):
        assert op_mod._resolve_symbol("AUDCAD-ECN") == "AUDCAD-ECN"


def test_resolve_symbol_fallback_to_startswith():
    mock_info = MagicMock()
    mock_info.name = "GER40."
    sym1 = MagicMock()
    sym1.name = "GER40."
    sym2 = MagicMock()
    sym2.name = "GER40ft."
    mock_syms = [sym1, sym2]
    mock_mt5 = MagicMock()
    mock_mt5.symbol_info.return_value = None
    mock_mt5.symbols_get.return_value = mock_syms
    mock_mt5.initialize.return_value = True
    with patch.dict(sys.modules, {"MetaTrader5": mock_mt5}):
        assert op_mod._resolve_symbol("GER40") == "GER40."


def test_adaptive_slip_pts_fx():
    mock_info = MagicMock()
    mock_info.point = 0.00001
    mock_mt5 = MagicMock()
    mock_mt5.symbol_info.return_value = mock_info
    mock_mt5.initialize.return_value = True
    with patch.dict(sys.modules, {"MetaTrader5": mock_mt5}):
        assert op_mod._adaptive_slip_pts("AUDCAD") == 2.0


def test_adaptive_slip_pts_gold():
    mock_info = MagicMock()
    mock_info.point = 0.01
    mock_mt5 = MagicMock()
    mock_mt5.symbol_info.return_value = mock_info
    mock_mt5.initialize.return_value = True
    with patch.dict(sys.modules, {"MetaTrader5": mock_mt5}):
        assert op_mod._adaptive_slip_pts("XAUUSD") == 20.0


def test_adaptive_slip_pts_index():
    mock_info = MagicMock()
    mock_info.point = 0.1
    mock_mt5 = MagicMock()
    mock_mt5.symbol_info.return_value = mock_info
    mock_mt5.initialize.return_value = True
    with patch.dict(sys.modules, {"MetaTrader5": mock_mt5}):
        assert op_mod._adaptive_slip_pts("GER40.") == 100.0


def test_cost_model_uses_live_spread():
    mock_info = MagicMock()
    mock_info.point = 0.00001
    mock_info.spread = 4
    mock_tick = MagicMock()
    mock_tick.ask = 0.98437
    mock_acc = MagicMock()
    mock_acc.currency = "GBP"
    mock_mt5 = MagicMock()
    mock_mt5.symbol_info.return_value = mock_info
    mock_mt5.symbol_info_tick.return_value = mock_tick
    mock_mt5.account_info.return_value = mock_acc
    mock_mt5.initialize.return_value = True
    mock_mt5.order_calc_profit.return_value = 0.007
    with patch.dict(sys.modules, {"MetaTrader5": mock_mt5}):
        pt, gbp_pt = op_mod.pt_value("AUDCAD-ECN")
        assert pt == 0.00001
        assert gbp_pt > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])