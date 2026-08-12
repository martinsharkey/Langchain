"""
Market clock — session + hour-of-day context for LIQUIDITY-aware, conditional edge.

The trader's key insight: an indicator/gate (ATR, EMA, RSI overbought/oversold)
may ADD edge in one session/hour and DESTROY it in another (e.g. ATR helps in the
Asian session but hurts in New York). So every trade, feature row, and gate
decision must carry a SESSION + HOUR tag, and the combinatorial search / ML must be
able to find edge that only exists in specific sessions/hours.

This module is the single source of truth for that classification. It is pure and
dependency-free (just a UTC timestamp in), so it's reusable everywhere: entry
tagging, post-mortem, the optimiser's conditional search, and the ML feature set.

Sessions (UTC, overlap-aware; a bar can belong to more than one, we take the
DOMINANT liquidity session for a single label + expose the full set + overlap flag):
  - asian   : 23:00-08:00  (Tokyo/Sydney)
  - london  : 07:00-16:00
  - newyork : 12:00-21:00
  overlaps:  london+newyork 12:00-16:00 (highest liquidity), asian+london 07:00-08:00
"""
from datetime import datetime, timezone

# (start_hour, end_hour) in UTC; end exclusive, wrap handled for asian.
_SESSIONS = {
    "asian":   (23, 8),
    "london":  (7, 16),
    "newyork": (12, 21),
}
# dominant session priority when hours overlap (NY overlap = deepest liquidity)
_DOMINANCE = ["newyork", "london", "asian"]


def _in(hour: int, span) -> bool:
    lo, hi = span
    if lo <= hi:
        return lo <= hour < hi
    return hour >= lo or hour < hi   # wrap (asian)


def classify(ts) -> dict:
    """Classify a UTC timestamp (epoch seconds/ms, datetime, or ISO str) into
    session/hour context. Never raises; returns a stable dict."""
    dt = _to_utc(ts)
    if dt is None:
        return {"hour_utc": -1, "session": "unknown", "sessions": [],
                "overlap": False, "liquidity": "unknown"}
    h = dt.hour
    active = [s for s, span in _SESSIONS.items() if _in(h, span)]
    dominant = next((s for s in _DOMINANCE if s in active), "offhours")
    overlap = len(active) >= 2
    # liquidity bucket: NY+London overlap = peak; single major = high; asian = medium;
    # nothing = low (thin/off-hours).
    if overlap and "newyork" in active and "london" in active:
        liq = "peak"
    elif active:
        liq = "high" if dominant in ("london", "newyork") else "medium"
    else:
        liq = "low"
    return {"hour_utc": h, "session": dominant, "sessions": active,
            "overlap": overlap, "liquidity": liq}


def session_of(ts) -> str:
    return classify(ts)["session"]


def hour_of(ts) -> int:
    return classify(ts)["hour_utc"]


def _to_utc(ts):
    try:
        if ts is None:
            return None
        if isinstance(ts, datetime):
            return ts.astimezone(timezone.utc) if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        if isinstance(ts, str):
            return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc) \
                if "T" in ts or "-" in ts else None
        v = float(ts)
        # heuristics: ms (>1e12), us (>1e15), else seconds
        if v > 1e15:
            v /= 1e6
        elif v > 1e12:
            v /= 1e3
        return datetime.fromtimestamp(v, tz=timezone.utc)
    except Exception:
        return None
