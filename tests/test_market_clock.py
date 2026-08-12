"""
Tests for market_clock — session + hour context that makes edge liquidity-aware.
Pure/deterministic, no MT5.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from src.trading import market_clock as mc


def _ts(h):
    return datetime(2026, 8, 12, h, 0, 0, tzinfo=timezone.utc).timestamp()


def test_new_york_london_overlap_is_peak_liquidity():
    c = mc.classify(_ts(14))   # 14:00 UTC = NY+London overlap
    assert c["session"] == "newyork"          # NY dominant in overlap
    assert "london" in c["sessions"] and "newyork" in c["sessions"]
    assert c["overlap"] is True
    assert c["liquidity"] == "peak"


def test_asian_session_wraps_midnight():
    assert mc.session_of(_ts(2)) == "asian"    # 02:00 UTC
    assert mc.session_of(_ts(23)) == "asian"   # 23:00 UTC (wrap)
    assert mc.classify(_ts(2))["liquidity"] == "medium"


def test_london_only_is_high():
    c = mc.classify(_ts(9))    # 09:00 UTC = london (asian ended 08:00)
    assert c["session"] == "london"
    assert c["liquidity"] == "high"


def test_hour_and_iso_and_micros():
    assert mc.hour_of(_ts(15)) == 15
    assert mc.session_of("2026-08-12T14:00:00") == "newyork"
    # microsecond epoch (Danny's timestamps are microseconds)
    assert mc.hour_of(_ts(14) * 1e6) == 14


def test_offhours_low_liquidity():
    # 22:00 UTC: london closed (16), NY closed (21), asian starts 23 -> gap
    c = mc.classify(_ts(22))
    assert c["session"] == "offhours"
    assert c["liquidity"] == "low"


def test_bad_input_is_safe():
    c = mc.classify(None)
    assert c["session"] == "unknown" and c["hour_utc"] == -1
