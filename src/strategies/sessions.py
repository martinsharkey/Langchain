"""Canonical trading session boundaries.

Used by the MQL5 EA generator, Optuna floor optimizer, and any live code that
needs to know which Asian/London/NewYork liquidity bucket a broker/server hour
belongs to. Precedence matches the live EA's CurSession(): NewYork > London >
Asian > Off.
"""


def session_of(hour: int) -> str:
    """Return the trading session for a broker/server hour (0-23).

    Precedence matches the live MQL5 EA CurSession():
        NewYork: 12-20 (inclusive start, exclusive end)
        London:  7-15
        Asian:   0-8
        Off:     21-23
    """
    if not isinstance(hour, int):
        raise TypeError(f"hour must be int, got {type(hour).__name__}")
    if hour < 0 or hour > 23:
        raise ValueError(f"hour must be in 0..23, got {hour}")
    if 12 <= hour < 21:
        return "NewYork"
    if 7 <= hour < 16:
        return "London"
    if 0 <= hour < 9:
        return "Asian"
    return "Off"


# Backwards-compatible aliases so existing scripts can import the same shape.
def trading_session(hour: int) -> str:
    """Alias for session_of(hour)."""
    return session_of(hour)


def all_sessions() -> tuple[str, ...]:
    """Canonical ordered session names."""
    return ("Asian", "London", "NewYork", "Off")
