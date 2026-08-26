"""
Session Selection Module - UTC-based Trading Session Determination

Determines current trading session based on UTC timestamp.
Used by ScalpEngine to select strategy per session.

Status: IMPLEMENTATION (Day 3)
"""

from datetime import datetime, timezone
from typing import Optional


# Session definitions (UTC times)
SESSION_DEFINITIONS = {
    'overlap_london_ny': {'days': [0, 1, 2, 3, 4], 'start_hour': 13, 'end_hour': 16},  # Mon-Fri 13:00-16:00
    'london': {'days': [0, 1, 2, 3, 4], 'start_hour': 8, 'end_hour': 16},               # Mon-Fri 08:00-16:00
    'newyork': {'days': [0, 1, 2, 3, 4], 'start_hour': 13, 'end_hour': 21},             # Mon-Fri 13:00-21:00
    'friday_evening': {'days': [4], 'start_hour': 21, 'end_hour': 24},                  # Fri 21:00-00:00
    'weekend_saturday': {'days': [5], 'start_hour': 0, 'end_hour': 24},                 # Sat all day
    'sunday_trading': {'days': [6], 'start_hour': 0, 'end_hour': 21},                   # Sun 00:00-21:00
    'asian': {'days': [0, 1, 2, 3, 4], 'start_hour': 0, 'end_hour': 8},                 # Mon-Fri 00:00-08:00
}

# Session precedence (check in this order)
SESSION_PRECEDENCE = [
    'overlap_london_ny',   # Highest priority - highest volatility
    'london',
    'newyork',
    'friday_evening',
    'weekend_saturday',
    'sunday_trading',
    'asian',               # Lowest priority
]


def get_current_session_utc(timestamp_utc: datetime) -> str:
    """
    Determine trading session based on UTC timestamp.
    
    Precedence (highest to lowest):
    1. overlap_london_ny: Mon-Fri 13:00-16:00 UTC
    2. london: Mon-Fri 08:00-16:00 UTC
    3. newyork: Mon-Fri 13:00-21:00 UTC
    4. friday_evening: Fri 21:00-00:00 UTC (Friday only)
    5. weekend_saturday: Sat 00:00-24:00 UTC (Saturday only)
    6. sunday_trading: Sun 00:00-21:00 UTC (Sunday only)
    7. asian: Mon-Fri 00:00-08:00 UTC (weekdays only)
    
    Args:
        timestamp_utc: datetime object in UTC timezone
    
    Returns:
        session name (str): one of the 7 session names above
    
    Raises:
        ValueError: if no session found for the given timestamp
    
    Example:
        >>> ts = datetime(2026, 8, 25, 14, 0, 0, tzinfo=timezone.utc)  # Mon 14:00
        >>> get_current_session_utc(ts)
        'overlap_london_ny'
    """
    
    hour = timestamp_utc.hour              # 0-23
    weekday = timestamp_utc.weekday()      # Mon=0, Tue=1, ..., Sun=6
    
    # Check each session in precedence order
    for session_name in SESSION_PRECEDENCE:
        session_def = SESSION_DEFINITIONS[session_name]
        
        # Check if current weekday is in session's days
        if weekday not in session_def['days']:
            continue
        
        # Check if current hour is within session's time range
        start_hour = session_def['start_hour']
        end_hour = session_def['end_hour']
        
        if start_hour <= hour < end_hour:
            return session_name
    
    # No session found
    raise ValueError(
        f"No session defined for {timestamp_utc.isoformat()} "
        f"(weekday={weekday}, hour={hour})"
    )


def get_current_session_now() -> str:
    """
    Get current trading session (shorthand for current UTC time).
    
    Returns:
        session name (str)
    
    Raises:
        ValueError: if no session found
    """
    return get_current_session_utc(datetime.now(timezone.utc))


def is_trading_session(timestamp_utc: datetime) -> bool:
    """
    Check if timestamp falls within ANY trading session.
    
    Args:
        timestamp_utc: datetime object in UTC timezone
    
    Returns:
        True if trading session, False otherwise
    
    Example:
        >>> ts = datetime(2026, 8, 25, 21, 30, 0, tzinfo=timezone.utc)  # Mon 21:30 (gap)
        >>> is_trading_session(ts)
        False
    """
    try:
        get_current_session_utc(timestamp_utc)
        return True
    except ValueError:
        return False


def get_all_sessions() -> list:
    """Return list of all defined sessions."""
    return list(SESSION_DEFINITIONS.keys())


def get_sessions_for_weekday(weekday: int) -> list:
    """
    Get all sessions that occur on a given weekday.
    
    Args:
        weekday: 0=Monday, 1=Tuesday, ..., 6=Sunday
    
    Returns:
        List of session names occurring on that weekday
    
    Example:
        >>> get_sessions_for_weekday(4)  # Friday
        ['overlap_london_ny', 'london', 'newyork', 'friday_evening', 'asian']
    """
    sessions = []
    for session_name, session_def in SESSION_DEFINITIONS.items():
        if weekday in session_def['days']:
            sessions.append(session_name)
    return sessions


def get_session_times_utc(session_name: str) -> dict:
    """
    Get UTC time range for a session.
    
    Args:
        session_name: name of session
    
    Returns:
        dict with 'start_hour', 'end_hour', 'days', 'description'
    
    Example:
        >>> get_session_times_utc('london')
        {
            'start_hour': 8,
            'end_hour': 16,
            'days': [0, 1, 2, 3, 4],
            'description': 'Mon-Fri 08:00-16:00 UTC'
        }
    """
    if session_name not in SESSION_DEFINITIONS:
        raise ValueError(f"Unknown session: {session_name}")
    
    session_def = SESSION_DEFINITIONS[session_name]
    
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    day_str = ', '.join(day_names[d] for d in session_def['days'])
    
    start_hour = session_def['start_hour']
    end_hour = session_def['end_hour']
    
    if end_hour == 24:
        time_str = f"{start_hour:02d}:00-23:59"
    else:
        time_str = f"{start_hour:02d}:00-{end_hour:02d}:00"
    
    return {
        'start_hour': session_def['start_hour'],
        'end_hour': session_def['end_hour'],
        'days': session_def['days'],
        'description': f"{day_str} {time_str} UTC"
    }


# ============================================================================
# VALIDATION
# ============================================================================

def validate_session_coverage() -> dict:
    """
    Validate that session definitions cover all trading times correctly.
    
    Returns:
        dict with 'valid': bool, 'gaps': list, 'overlaps': list
    """
    gaps = []
    overlaps = []
    
    # Check coverage for Mon-Fri (weekdays)
    for weekday in range(5):  # Mon-Fri
        for hour in range(24):
            sessions = []
            for session_name in SESSION_DEFINITIONS.keys():
                session_def = SESSION_DEFINITIONS[session_name]
                if weekday in session_def['days']:
                    if session_def['start_hour'] <= hour < session_def['end_hour']:
                        sessions.append(session_name)
            
            if len(sessions) == 0:
                day_name = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'][weekday]
                gaps.append(f"{day_name} {hour:02d}:00")
            elif len(sessions) > 1:
                # Check precedence - only first session in precedence should match
                first_match = None
                for session_name in SESSION_PRECEDENCE:
                    if session_name in sessions:
                        first_match = session_name
                        break
                
                if len(sessions) > 1:
                    day_name = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'][weekday]
                    overlaps.append(f"{day_name} {hour:02d}:00: {sessions}")
    
    # Check coverage for Sat
    for hour in range(24):
        sessions = []
        for session_name in SESSION_DEFINITIONS.keys():
            session_def = SESSION_DEFINITIONS[session_name]
            if 5 in session_def['days']:  # Sat
                if session_def['start_hour'] <= hour < session_def['end_hour']:
                    sessions.append(session_name)
        
        if len(sessions) == 0:
            gaps.append(f"Sat {hour:02d}:00")
    
    # Check coverage for Sun
    for hour in range(24):
        sessions = []
        for session_name in SESSION_DEFINITIONS.keys():
            session_def = SESSION_DEFINITIONS[session_name]
            if 6 in session_def['days']:  # Sun
                if session_def['start_hour'] <= hour < session_def['end_hour']:
                    sessions.append(session_name)
        
        if len(sessions) == 0 and hour < 21:  # Sun trading until 21:00
            gaps.append(f"Sun {hour:02d}:00")
    
    return {
        'valid': len(gaps) == 0 and len(overlaps) == 0,
        'gaps': gaps,
        'overlaps': overlaps
    }


__all__ = [
    'get_current_session_utc',
    'get_current_session_now',
    'is_trading_session',
    'get_all_sessions',
    'get_sessions_for_weekday',
    'get_session_times_utc',
    'validate_session_coverage',
    'SESSION_DEFINITIONS',
    'SESSION_PRECEDENCE',
]
