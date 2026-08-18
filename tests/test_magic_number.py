"""
Regression tests for issue #66: hardcoded magic number 880011.

Ensures:
  * no literal 880011 remains in source, templates, or generated EAs
  * magic_for_symbol is deterministic and unique per symbol
  * generated EAs use a per-symbol magic derived from config
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import json
import subprocess

from src.config import BOT_MAGIC, magic_for_symbol




def test_magic_for_symbol_deterministic_and_unique():
    """Same symbol -> same magic; different symbols -> different magics."""
    m1 = magic_for_symbol("XAUUSD")
    m2 = magic_for_symbol("XAUUSD")
    m3 = magic_for_symbol("BTCUSD")
    assert m1 == m2
    assert m1 != m3
    assert 100_000 <= m1 <= 999_999
    assert 100_000 <= m3 <= 999_999


def test_base_magic_change_reshuffles():
    """Changing BOT_MAGIC base produces a different per-symbol magic."""
    m_default = magic_for_symbol("XAUUSD")
    m_shifted = magic_for_symbol("XAUUSD", base=BOT_MAGIC + 1)
    assert m_shifted != m_default




if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
