"""
Tests for validate_dukascopy_fidelity.py (#88).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scripts.validate_dukascopy_fidelity as vf


def test_compare_returns_dict_keys():
    res = vf.compare("XAUUSD", tf="H1", hours=1)
    assert isinstance(res, dict)
    assert "ok" in res
    assert "symbol" in res
    assert "shared_bars" in res
    assert "gap_frac" in res
    assert "price_divergence_p99" in res
    assert "spread_divergence_p99" in res


def test_compare_handles_missing_source(monkeypatch):
    monkeypatch.setattr(vf, "_fetch_dukascopy_bars", lambda *a, **k: [])
    monkeypatch.setattr(vf, "_fetch_mt5_bars", lambda *a, **k: [])
    res = vf.compare("XAUUSD", tf="H1", hours=1)
    assert res["ok"] is False
    assert "both sources empty" in res.get("error", "")


def test_thresholds_lookup():
    thresh = vf._THRESHOLDS.get("XAUUSD")
    assert thresh["max_bar_gap_frac"] == 0.05
    assert thresh["max_price_divergence"] == 2.0


def test_mt5_symbol_mapping():
    assert vf._MT5_SYMBOL_MAP["XAUUSD"] == "XAUUSD.crp"
    assert vf._MT5_SYMBOL_MAP["GER40"] == "GER40."


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-q"])
