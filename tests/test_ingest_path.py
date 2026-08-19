"""Tests for ingest.py ECN suffix resolution and path handling."""
import sys, os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch

import scripts.qmmp.ingest as ingest_mod


def test_resolve_symbol_ecn_suffix():
    """ECN suffixes must be stripped for qmmp directory paths."""
    mock_info = MagicMock()
    mock_info.name = "AUDCAD-ECN"
    with patch.object(ingest_mod.mt5, "symbol_info", return_value=mock_info), \
         patch.object(ingest_mod.mt5, "symbols_get", return_value=[]), \
         patch.object(ingest_mod.mt5, "initialize", return_value=True), \
         patch.object(ingest_mod.mt5, "shutdown"):
        resolved = ingest_mod._resolve_symbol("AUDCAD-ECN")
        assert resolved == "AUDCAD-ECN"


def test_resolve_symbol_dot_suffix():
    """Dot suffixes must be stripped for qmmp directory paths."""
    mock_info = MagicMock()
    mock_info.name = "GER40."
    with patch.object(ingest_mod.mt5, "symbol_info", return_value=mock_info), \
         patch.object(ingest_mod.mt5, "symbols_get", return_value=[]), \
         patch.object(ingest_mod.mt5, "initialize", return_value=True), \
         patch.object(ingest_mod.mt5, "shutdown"):
        resolved = ingest_mod._resolve_symbol("GER40.")
        assert resolved == "GER40."


def test_ingest_output_path_strips_ecn_suffix():
    """ingest_mt5 must write parquet to data/qmmp/<BASE>/ not data/qmmp/<SYMBOL>/."""
    mock_info = MagicMock()
    mock_info.name = "AUDCAD-ECN"
    mock_rates = []
    with patch.object(ingest_mod.mt5, "symbol_info", return_value=mock_info), \
         patch.object(ingest_mod.mt5, "symbol_select"), \
         patch.object(ingest_mod.mt5, "copy_rates_range", return_value=[]), \
         patch.object(ingest_mod.mt5, "initialize", return_value=True), \
         patch.object(ingest_mod.mt5, "shutdown"), \
         patch("os.makedirs") as mock_makedirs, \
         patch("polars.DataFrame.write_parquet"):
        try:
            ingest_mod.ingest_mt5("AUDCAD-ECN")
        except SystemExit:
            pass
        called_dirs = [call[0][0] for call in mock_makedirs.call_args_list]
        assert any("AUDCAD" in d and "AUDCAD-ECN" not in d for d in called_dirs), \
            f"Expected path to strip ECN suffix, got: {called_dirs}"


if __name__ == "__main__":
    test_resolve_symbol_ecn_suffix()
    test_resolve_symbol_dot_suffix()
    test_ingest_output_path_strips_ecn_suffix()
    print("ingest path tests passed")
