"""
DAY 6: UNIT TESTS - Session Selection (15 tests)

Comprehensive test coverage for UTC-based session determination.

Status: DAY 6 TESTING
"""

import pytest
from datetime import datetime, timezone
from src.session_selection import (
    get_current_session_utc,
    is_trading_session,
    get_sessions_for_weekday,
    get_session_times_utc,
    validate_session_coverage
)


class TestSessionSelection:
    """Test UTC-based session selection algorithm."""
    
    # ASIAN SESSION TESTS
    def test_asian_monday_0400_utc(self):
        """Mon 04:00 UTC should be Asian session."""
        ts = datetime(2026, 8, 25, 4, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'asian'
    
    def test_asian_tuesday_0700_utc(self):
        """Tue 07:00 UTC should be Asian session."""
        ts = datetime(2026, 8, 26, 7, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'asian'
    
    def test_asian_boundary_0759_utc(self):
        """Mon 07:59 UTC is last minute of Asian."""
        ts = datetime(2026, 8, 25, 7, 59, 59, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'asian'
    
    # LONDON SESSION TESTS
    def test_london_monday_0800_utc(self):
        """Mon 08:00 UTC should start London session."""
        ts = datetime(2026, 8, 25, 8, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'london'
    
    def test_london_wednesday_1200_utc(self):
        """Wed 12:00 UTC should be London session."""
        ts = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'london'
    
    def test_london_boundary_1559_utc(self):
        """Mon 15:59 UTC is last minute of London."""
        ts = datetime(2026, 8, 25, 15, 59, 59, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'london'
    
    # OVERLAP SESSION TESTS (HIGHEST PRIORITY)
    def test_overlap_london_ny_monday_1400_utc(self):
        """Mon 14:00 UTC is overlap (takes precedence over London)."""
        ts = datetime(2026, 8, 25, 14, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'overlap_london_ny'
    
    def test_overlap_boundary_1300_utc(self):
        """Mon 13:00 UTC starts overlap."""
        ts = datetime(2026, 8, 25, 13, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'overlap_london_ny'
    
    def test_overlap_boundary_1559_utc(self):
        """Mon 15:59 UTC is last minute of overlap."""
        ts = datetime(2026, 8, 25, 15, 59, 59, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'overlap_london_ny'
    
    # NEW YORK SESSION TESTS
    def test_newyork_monday_1800_utc(self):
        """Mon 18:00 UTC (after overlap) should be New York."""
        ts = datetime(2026, 8, 25, 18, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'newyork'
    
    def test_newyork_boundary_2059_utc(self):
        """Mon 20:59 UTC is last minute of New York."""
        ts = datetime(2026, 8, 25, 20, 59, 59, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'newyork'
    
    # FRIDAY EVENING TESTS
    def test_friday_evening_2100_utc(self):
        """Fri 21:00 UTC starts Friday evening."""
        ts = datetime(2026, 8, 29, 21, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'friday_evening'
    
    def test_friday_evening_boundary_2359_utc(self):
        """Fri 23:59 UTC is last minute of Friday evening."""
        ts = datetime(2026, 8, 29, 23, 59, 59, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'friday_evening'
    
    # WEEKEND TESTS
    def test_weekend_saturday_full_day(self):
        """Sat 12:00 UTC should be weekend_saturday."""
        ts = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'weekend_saturday'
    
    def test_sunday_trading_1400_utc(self):
        """Sun 14:00 UTC should be sunday_trading."""
        ts = datetime(2026, 8, 31, 14, 0, 0, tzinfo=timezone.utc)
        assert get_current_session_utc(ts) == 'sunday_trading'
    
    # ERROR CASES
    def test_no_session_monday_2100_utc(self):
        """Mon 21:00 UTC has no session (gap)."""
        ts = datetime(2026, 8, 25, 21, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError):
            get_current_session_utc(ts)
    
    def test_no_session_sunday_2100_utc(self):
        """Sun 21:00 UTC has no session (after trading)."""
        ts = datetime(2026, 8, 31, 21, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError):
            get_current_session_utc(ts)
    
    # UTILITY FUNCTIONS
    def test_is_trading_session_true(self):
        """is_trading_session should return True for valid sessions."""
        ts = datetime(2026, 8, 25, 14, 0, 0, tzinfo=timezone.utc)
        assert is_trading_session(ts) is True
    
    def test_is_trading_session_false(self):
        """is_trading_session should return False for gaps."""
        ts = datetime(2026, 8, 25, 21, 30, 0, tzinfo=timezone.utc)
        assert is_trading_session(ts) is False
    
    def test_get_sessions_for_weekday_friday(self):
        """Friday should include 6 sessions (including friday_evening)."""
        sessions = get_sessions_for_weekday(4)
        assert 'friday_evening' in sessions
        assert 'london' in sessions
        assert 'newyork' in sessions
    
    def test_get_session_times_utc(self):
        """Get session times should return dict with hours and days."""
        times = get_session_times_utc('london')
        assert times['start_hour'] == 8
        assert times['end_hour'] == 16
        assert 0 in times['days']  # Monday
    
    def test_validate_session_coverage(self):
        """Session coverage should be valid with no gaps/overlaps."""
        result = validate_session_coverage()
        assert result['valid'] is True
        assert len(result['gaps']) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
