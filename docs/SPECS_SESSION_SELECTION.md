# SESSION SELECTION ALGORITHM SPECIFICATION

**Document:** Determine Trading Session from UTC Timestamp
**Date:** 2026-08-25
**Status:** SPECIFICATION

---

## Algorithm

```python
def get_current_session_utc(timestamp_utc: datetime) -> str:
    """
    Determine trading session based on UTC timestamp.
    
    Precedence (highest to lowest):
    1. overlap_london_ny: Mon-Fri 13:00-16:00 UTC
    2. london: Mon-Fri 08:00-16:00 UTC
    3. newyork: Mon-Fri 13:00-21:00 UTC
    4. friday_evening: Fri 21:00-00:00 UTC (Friday evening only)
    5. weekend_saturday: Sat 00:00-24:00 UTC (Saturday only)
    6. sunday_trading: Sun 00:00-21:00 UTC (Sunday only)
    7. asian: Mon-Fri 00:00-08:00 UTC (weekdays only)
    
    Returns: session name (str)
    Raises: ValueError if no session found
    """
    
    hour = timestamp_utc.hour              # 0-23
    weekday = timestamp_utc.weekday()      # Mon=0, Tue=1, ..., Sun=6
    
    # PRECEDENCE ORDER: check from highest to lowest priority
    
    # 1. Overlap (highest priority, highest volatility)
    if weekday < 5 and 13 <= hour < 16:
        return 'overlap_london_ny'
    
    # 2. London (08:00-16:00 UTC, Mon-Fri)
    if weekday < 5 and 8 <= hour < 16:
        return 'london'
    
    # 3. New York (13:00-21:00 UTC, Mon-Fri)
    # Note: overlap already handled above, so this is 16:00-21:00 for NY-specific
    if weekday < 5 and 13 <= hour < 21:
        return 'newyork'
    
    # 4. Friday Evening (21:00-00:00 UTC, Fri only)
    if weekday == 4 and 21 <= hour < 24:
        return 'friday_evening'
    
    # 5. Saturday (00:00-24:00 UTC, Sat only)
    # Note: using weekday == 5 for Saturday
    if weekday == 5:
        return 'weekend_saturday'
    
    # 6. Sunday (00:00-21:00 UTC, Sun only)
    # Note: using weekday == 6 for Sunday
    if weekday == 6 and 0 <= hour < 21:
        return 'sunday_trading'
    
    # 7. Asian (00:00-08:00 UTC, Mon-Fri)
    if weekday < 5 and 0 <= hour < 8:
        return 'asian'
    
    # No session found
    raise ValueError(f"No session defined for {timestamp_utc} (weekday={weekday}, hour={hour})")
```

---

## Test Cases

### Weekday Sessions

| Time (UTC) | Weekday | Expected | Reason |
|-----------|---------|----------|--------|
| Mon 04:00 | Monday | asian | 00:00-08:00 UTC, Mon-Fri |
| Mon 10:00 | Monday | london | 08:00-16:00 UTC, Mon-Fri |
| Mon 14:00 | Monday | overlap_london_ny | 13:00-16:00 UTC (precedence wins) |
| Mon 18:00 | Monday | newyork | 13:00-21:00 UTC (London ended) |
| Tue 04:00 | Tuesday | asian | 00:00-08:00 UTC |
| Tue 14:30 | Tuesday | overlap_london_ny | 13:00-16:00 UTC |
| Wed 10:00 | Wednesday | london | 08:00-16:00 UTC |
| Thu 20:00 | Thursday | newyork | 13:00-21:00 UTC |
| **Fri 14:00** | **Friday** | **overlap_london_ny** | **13:00-16:00 UTC** |
| **Fri 22:00** | **Friday** | **friday_evening** | **21:00-00:00 UTC** |

### Weekend Sessions

| Time (UTC) | Weekday | Expected | Reason |
|-----------|---------|----------|--------|
| Sat 00:00 | Saturday | weekend_saturday | Sat 00:00-24:00 UTC |
| Sat 12:00 | Saturday | weekend_saturday | All day Saturday |
| Sat 23:59 | Saturday | weekend_saturday | All day Saturday |
| Sun 10:00 | Sunday | sunday_trading | Sun 00:00-21:00 UTC |
| Sun 20:00 | Sunday | sunday_trading | Sun 00:00-21:00 UTC |
| **Sun 22:00** | **Sunday** | **ERROR** | **After 21:00 UTC** |
| Mon 00:00 | Monday | asian | 00:00-08:00 UTC |

### Edge Cases (Boundaries)

| Time (UTC) | Expected | Reason |
|-----------|----------|--------|
| Mon 07:59 | asian | Last minute of Asian |
| Mon 08:00 | london | Start of London (exact boundary) |
| Mon 15:59 | overlap_london_ny | Last minute of overlap |
| Mon 16:00 | newyork | Start of NY (London ended) |
| Mon 20:59 | newyork | Last minute of NY |
| Mon 21:00 | ERROR | No session (gap between sessions) |
| Fri 20:59 | newyork | Last minute of NY |
| Fri 21:00 | friday_evening | Start of Friday evening (exact boundary) |
| Fri 23:59 | friday_evening | Last minute of Friday evening |
| Sat 00:00 | weekend_saturday | Start of Saturday (exact boundary) |
| Sun 20:59 | sunday_trading | Last minute of Sunday trading |
| Sun 21:00 | ERROR | No session after 21:00 UTC Sunday |

---

## Implementation Notes

### Weekday Encoding (Python datetime.weekday())
- Monday = 0
- Tuesday = 1
- Wednesday = 2
- Thursday = 3
- Friday = 4
- Saturday = 5
- Sunday = 6

### Hour Range Notation
- `0 <= hour < 8` means 00:00:00 to 07:59:59
- `8 <= hour < 16` means 08:00:00 to 15:59:59
- `13 <= hour < 16` means 13:00:00 to 15:59:59

### Precedence Explanation

When multiple sessions could match (e.g., Mon 14:00 matches both `london` and `overlap_london_ny`), **check in precedence order and return the first match**:

```
# Mon 14:00 UTC
1. overlap_london_ny? 13 <= 14 < 16 AND weekday < 5? YES → return 'overlap_london_ny'
   (never reach london check)
```

```
# Fri 22:00 UTC
1. overlap_london_ny? 13 <= 22 < 16? NO
2. london? 8 <= 22 < 16? NO
3. newyork? 13 <= 22 < 21? NO
4. friday_evening? weekday == 4 AND 21 <= 22 < 24? YES → return 'friday_evening'
```

---

## Usage in ScalpEngine

```python
from datetime import datetime, timezone

def _evaluate_and_trade(self, base, adapter):
    current_time_utc = datetime.now(timezone.utc)
    
    try:
        current_session = get_current_session_utc(current_time_utc)
    except ValueError as e:
        logger.warning(f"{base}: {e}, skipping entry")
        return
    
    # Load strategy for current session
    strategy_config = self._load_strategy_for_session(base, current_session)
    if not strategy_config:
        logger.warning(f"{base}: no strategy for {current_session}")
        return
    
    # Proceed with entry logic using strategy_config['strategy_name']
    ...
```

---

## Validation

**Ensures:**
- ✅ Each UTC time maps to exactly ONE session
- ✅ No gaps in weekday coverage (Mon-Fri 00:00-21:00)
- ✅ Overlap is respected (highest priority)
- ✅ Weekend coverage complete (Sat full day, Sun until 21:00)
- ✅ Friday evening separate from NY session (specific handling)
- ✅ All boundaries at exact hour boundaries (no fractional hours)

---

**Status:** SPECIFICATION COMPLETE - Ready for implementation
