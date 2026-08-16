"""
Broker time — the SINGLE, portable source of truth for time alignment.

Three independent clocks exist and MUST NOT be conflated:
  1. SYSTEM/VPS local time   — whatever tz the host (or VPS) is set to.
  2. BROKER/server time      — the tz MT5 stamps bar & tick epochs in (varies per
                               broker: commonly UTC+2/+3, but any offset is possible).
  3. UTC                     — the neutral reference we anchor everything to.

Everything that correlates MT5 bars/ticks with our own records (post-mortem,
reversal-signature, ML labels/MFE/MAE, forensics, backtest windows) goes through
this module so the offset is defined in exactly ONE place and is correct on ANY
host and ANY broker — independent of the VPS timezone.

Design guarantees:
  * VPS-timezone independent: we compare the broker epoch (interpreted as UTC via
    utcfromtimestamp) against real UTC (timezone-aware) — never against local time.
    So a VPS in London, New York, or UTC all yield the SAME broker offset.
  * Broker independent: the offset is MEASURED from a live tick, not hard-coded.
  * Stale-quote safe: offsets are snapped to the nearest whole-minute and sanity
    bounded to [-14h, +14h]; a stale weekend tick can't poison the cache once a
    fresh tick arrives (auto-refresh).
"""

from __future__ import annotations

import threading
import time as _time
from datetime import datetime, timezone, timedelta
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("broker_time")

_LOCK = threading.Lock()
_OFFSET_SECONDS: Optional[float] = None      # broker_time - utc_time (seconds)
_LAST_MEASURED: float = 0.0
_REFRESH_EVERY = 1800.0                        # re-measure at most every 30 min
_MAX_ABS_OFFSET = 14 * 3600                    # sanity bound (max real-world tz gap)

# Symbols tried (in order) to read a live server tick. Broker suffixes vary, so we
# try common variants; callers may extend via set_reference_symbols().
_REF_SYMBOLS = ["XAUUSD-ECN", "BTCUSD", "EURUSD-ECN", "XAUUSD", "EURUSD", "BTCUSD-ECN"]


def set_reference_symbols(symbols) -> None:
    """Let a deployment override which symbols are used to read the server tick
    (useful for brokers with unusual symbol naming)."""
    global _REF_SYMBOLS
    if symbols:
        _REF_SYMBOLS = list(symbols) + [s for s in _REF_SYMBOLS if s not in symbols]


def _utc_now() -> datetime:
    # timezone-aware UTC, naive for arithmetic. Avoids deprecated utcnow().
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _measure_offset() -> Optional[float]:
    """broker_now - utc_now in seconds, from a live tick. None if unavailable/unsafe.

    Uses utcfromtimestamp on the broker epoch (so the result is broker-vs-UTC and
    does NOT depend on the host/VPS timezone at all)."""
    try:
        import MetaTrader5 as mt5
    except Exception:
        return None
    try:
        tick = None
        for sym in _REF_SYMBOLS:
            try:
                t = mt5.symbol_info_tick(sym)
            except Exception:
                t = None
            if t and getattr(t, "time", 0):
                tick = t
                break
        if not tick:
            return None
        broker = datetime.utcfromtimestamp(tick.time)   # broker epoch interpreted as wall-clock
        raw = (broker - _utc_now()).total_seconds()
        # reject impossible offsets (e.g. a corrupt/stale epoch)
        if abs(raw) > _MAX_ABS_OFFSET:
            logger.warning(f"broker offset {raw/3600:.1f}h out of bounds — ignoring sample")
            return None
        # snap to the nearest minute: real broker offsets are whole (half-)hours;
        # tick latency of a few seconds should not wobble the offset.
        return round(raw / 60.0) * 60.0
    except Exception as e:
        logger.debug(f"broker offset measure failed: {e}")
        return None


def broker_offset_seconds(force: bool = False) -> float:
    """Cached broker-minus-UTC offset in seconds. 0.0 only if MT5 never available
    (in which case broker time == UTC is the safest assumption)."""
    global _OFFSET_SECONDS, _LAST_MEASURED
    with _LOCK:
        now = _time.time()
        if force or _OFFSET_SECONDS is None or (now - _LAST_MEASURED) > _REFRESH_EVERY:
            m = _measure_offset()
            if m is not None:
                if _OFFSET_SECONDS is None or abs(m - _OFFSET_SECONDS) > 1:
                    logger.info(f"broker time offset = {m/3600.0:+.2f}h vs UTC "
                                f"(broker clock is {'ahead of' if m>=0 else 'behind'} UTC)")
                _OFFSET_SECONDS = m
                _LAST_MEASURED = now
        return _OFFSET_SECONDS or 0.0


def broker_offset_hours() -> float:
    return broker_offset_seconds() / 3600.0


def system_utc_offset_hours() -> float:
    """The VPS/host local-vs-UTC offset (informational; NOT used in alignment math)."""
    return (datetime.now() - _utc_now()).total_seconds() / 3600.0


def utc_to_broker(dt: datetime) -> datetime:
    """UTC datetime -> broker server time (e.g. to build a copy_rates_range window)."""
    base = dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    return base + timedelta(seconds=broker_offset_seconds())


def broker_to_utc(dt: datetime) -> datetime:
    """Broker-server datetime (e.g. an MT5 bar time) -> real UTC."""
    base = dt.replace(tzinfo=None) if dt.tzinfo else dt
    return base - timedelta(seconds=broker_offset_seconds())


def bar_epoch_to_utc(epoch: float) -> datetime:
    """MT5 bar/tick epoch (broker server time) -> real UTC datetime."""
    return datetime.utcfromtimestamp(float(epoch)) - timedelta(seconds=broker_offset_seconds())


def utc_to_bar_epoch(dt: datetime) -> float:
    """UTC datetime -> the epoch value MT5 expects (broker server time)."""
    base = dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    broker = base + timedelta(seconds=broker_offset_seconds())
    return (broker - datetime(1970, 1, 1)).total_seconds()
