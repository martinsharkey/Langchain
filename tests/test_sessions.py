"""Tests for canonical session boundary logic."""

import pytest

from src.strategies.sessions import all_sessions, session_of, trading_session


# Reference precedence from the live MQL5 EA CurSession():
# NewYork 12-20, London 7-15, Asian 0-8, Off 21-23.
_EXPECTED = {
    0: "Asian",
    1: "Asian",
    2: "Asian",
    3: "Asian",
    4: "Asian",
    5: "Asian",
    6: "Asian",
    7: "London",
    8: "London",       # overlaps Asian [0,9) and London [7,16) -> London wins
    9: "London",
    10: "London",
    11: "London",
    12: "NewYork",
    13: "NewYork",
    14: "NewYork",
    15: "NewYork",    # overlaps London [7,16) and NewYork [12,21) -> NewYork wins
    16: "NewYork",    # overlaps London [7,16) (exclusive end) and NewYork [12,21) -> NewYork wins
    17: "NewYork",
    18: "NewYork",
    19: "NewYork",
    20: "NewYork",
    21: "Off",
    22: "Off",
    23: "Off",
}


@pytest.mark.parametrize("hour,expected", list(_EXPECTED.items()))
def test_session_of_all_hours(hour, expected):
    assert session_of(hour) == expected


def test_session_of_non_int_fails():
    with pytest.raises(TypeError):
        session_of("12")


@pytest.mark.parametrize("bad_hour", [-1, 24, 100])
def test_session_of_out_of_range_fails(bad_hour):
    with pytest.raises(ValueError):
        session_of(bad_hour)


def test_trading_session_alias_matches_session_of():
    for h in range(24):
        assert trading_session(h) == session_of(h)


def test_all_sessions_order():
    assert all_sessions() == ("Asian", "London", "NewYork", "Off")


def test_overlap_windows_use_ea_precedence():
    """Hours that fall in multiple raw windows must resolve by EA precedence.

    Critical overlap cases:
    - 7:  Asian [0,9) and London [7,16) -> London (NewYork not involved)
    - 8:  Asian [0,9) and London [7,16) -> London
    - 12: London [7,16) and NewYork [12,21) -> NewYork
    - 15: London [7,16) and NewYork [12,21) -> NewYork
    - 16: London [7,16) exclusive end, NewYork [12,21) -> NewYork
    """
    assert session_of(7) == "London"
    assert session_of(8) == "London"
    assert session_of(12) == "NewYork"
    assert session_of(15) == "NewYork"
    assert session_of(16) == "NewYork"
    assert session_of(20) == "NewYork"
