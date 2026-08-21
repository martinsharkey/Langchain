"""
SessionManager — per-symbol trading-hours awareness.

MT5's session API isn't reliably queryable on this broker build, so schedules
are RESEARCHER-MAINTAINED here (overridable via data/session_schedule.json,
which the research agent can update). Defaults encode the well-known cases:

  * Gold (XAUUSD): trades ~24/5 with a DAILY BREAK around 21:00–22:00 UTC
    (broker maintenance) and the weekend close (Fri ~21:00 → Sun ~22:00 UTC).
  * Crypto (BTCUSD): 24/7 — no session close.

The engine uses this to answer two questions per open trade:
  1. Is the symbol about to close within the pre-close window (15–30 min)?
  2. Is the symbol currently open at all (don't try to enter when closed)?

All times are UTC. This is intentionally simple and explicit — a schedule you
can see and the researcher can correct — rather than a hidden broker guess.
"""

from __future__ import annotations

import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from src import config
from src.utils.logger import get_logger

logger = get_logger("session_manager")

SCHEDULE_PATH = os.path.join(config.DATA_DIR, "session_schedule.json")

# Default researcher-maintained schedules. Times are UTC "HH:MM".
# "daily_break": [start, end] closed each trading day.
# "weekend": {"close": [dow, "HH:MM"], "open": [dow, "HH:MM"]}  dow: 0=Mon..6=Sun
# "always_open": true for 24/7 symbols.
DEFAULT_SCHEDULES = {
    "XAUUSD": {
        "always_open": False,
        "weekend": {"close": [4, "21:00"], "open": [6, "22:00"]},
        "note": "Gold: 24/5 with weekend close. Daily break removed — broker trades through 21-22 UTC.",
    },
    "XAGUSD": {
        "always_open": False,
        "weekend": {"close": [4, "21:00"], "open": [6, "22:00"]},
        "note": "Silver: same as gold. Daily break removed.",
    },
    "EURUSD": {"always_open": False,
               "weekend": {"close": [4, "21:00"], "open": [6, "22:00"]},
               "note": "FX: weekend only on this broker."},
    "AUDUSD": {"always_open": False,
               "weekend": {"close": [4, "21:00"], "open": [6, "22:00"]},
               "note": "FX: weekend only on this broker."},
    "USDCAD": {"always_open": False,
               "weekend": {"close": [4, "21:00"], "open": [6, "22:00"]},
               "note": "FX: weekend only on this broker."},
    "GBPUSD": {"always_open": False,
               "weekend": {"close": [4, "21:00"], "open": [6, "22:00"]},
               "note": "FX: weekend only on this broker."},
    "USDJPY": {"always_open": False,
               "weekend": {"close": [4, "21:00"], "open": [6, "22:00"]},
               "note": "FX: weekend only on this broker."},
    "GER40": {"always_open": False,
              "weekend": {"close": [4, "21:00"], "open": [6, "22:00"]},
              "note": "Index CFD: weekend only on this broker. Daily break removed."},
    "BTCUSD": {"always_open": True, "note": "Crypto trades 24/7."},
    "ETHUSD": {"always_open": True, "note": "Crypto trades 24/7."},
}

# Default schedule for UNKNOWN symbols. SAFER to assume weekend-only closure
# (so pre-close protection fires) than to assume 24/7 and leave winners exposed
# over a gap. Crypto-like names (BTC/ETH/XBT/crypto) default to 24/7.
DEFAULT_NON_CRYPTO = {
    "always_open": False,
    "weekend": {"close": [4, "21:00"], "open": [6, "22:00"]},
    "note": "Unknown symbol — assumed weekend closure for safety.",
}
_CRYPTO_HINTS = ("BTC", "ETH", "XBT", "CRYPTO", "LTC", "XRP", "SOL", "DOGE")


def _hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


class SessionManager:
    def __init__(self):
        self.schedules = dict(DEFAULT_SCHEDULES)
        self._load_overrides()

    def _load_overrides(self):
        try:
            if os.path.exists(SCHEDULE_PATH):
                with open(SCHEDULE_PATH) as f:
                    override = json.load(f)
                for sym, sched in override.get("symbols", {}).items():
                    self.schedules[sym.upper()] = sched
                logger.info(f"Loaded session overrides for {list(override.get('symbols', {}))}")
        except Exception as e:
            logger.debug(f"session override load skip: {e}")

    def _sched_for(self, base_symbol: str) -> dict:
        s = base_symbol.upper()
        # match by prefix (XAUUSD-ECN -> XAUUSD)
        for key, sched in self.schedules.items():
            if s.startswith(key):
                return sched
        # unknown symbol: crypto-like -> 24/7; everything else -> safe FX/CFD
        # session (daily break + weekend) so pre-close protection still fires.
        if any(h in s for h in _CRYPTO_HINTS):
            logger.debug(f"No schedule for {base_symbol}; assuming 24/7 (crypto-like)")
            return {"always_open": True}
        logger.info(f"No schedule for {base_symbol}; assuming standard FX/CFD session (safe default)")
        return dict(DEFAULT_NON_CRYPTO)

    def _in_daily_break(self, now: datetime, db: list) -> bool:
        sh, sm = _hhmm(db[0]); eh, em = _hhmm(db[1])
        start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
        end = now.replace(hour=eh, minute=em, second=0, microsecond=0)
        if end <= start:   # break spans midnight
            end += timedelta(days=1)
        return start <= now < end

    def _in_weekend_closure(self, now: datetime, wk: dict) -> bool:
        close_dow, close_t = wk["close"]
        open_dow, open_t = wk["open"]
        ch, cm = _hhmm(close_t); oh, om = _hhmm(open_t)
        # find the most recent close boundary at/of this week
        days_since_close = (now.weekday() - close_dow) % 7
        close_dt = (now - timedelta(days=days_since_close)).replace(hour=ch, minute=cm, second=0, microsecond=0)
        if close_dt > now:
            close_dt -= timedelta(days=7)
        # corresponding open boundary after that close
        days_to_open = (open_dow - close_dow) % 7
        open_dt = close_dt + timedelta(days=days_to_open)
        open_dt = open_dt.replace(hour=oh, minute=om, second=0, microsecond=0)
        # advance past any intermediate opens so we land in the closure cycle
        # that actually contains `now` (fixes false weekend detection mid-week)
        while now >= open_dt:
            close_dt += timedelta(days=7)
            open_dt += timedelta(days=7)
        return close_dt <= now < open_dt

    def is_open(self, base_symbol: str, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        sched = self._sched_for(base_symbol)
        if sched.get("always_open"):
            return True
        wk = sched.get("weekend")
        if wk and self._in_weekend_closure(now, wk):
            return False
        db = sched.get("daily_break")
        if db and self._in_daily_break(now, db):
            return False
        return True

    def minutes_to_close(self, base_symbol: str, now: Optional[datetime] = None) -> Optional[int]:
        """
        Minutes until the NEXT close for this symbol, or None if 24/7 / no close soon.
        Only looks ahead within the next 24h (enough for the pre-close window).
        """
        now = now or datetime.now(timezone.utc)
        sched = self._sched_for(base_symbol)
        if sched.get("always_open"):
            return None
        candidates = []

        db = sched.get("daily_break")
        if db:
            start_h, start_m = _hhmm(db[0])
            close_today = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
            if close_today <= now:
                close_today += timedelta(days=1)
            candidates.append(close_today)

        wk = sched.get("weekend")
        if wk:
            dow, t = wk["close"]
            ch, cm = _hhmm(t)
            # find next occurrence of that weekday/time
            days_ahead = (dow - now.weekday()) % 7
            wclose = (now + timedelta(days=days_ahead)).replace(hour=ch, minute=cm, second=0, microsecond=0)
            if wclose <= now:
                wclose += timedelta(days=7)
            candidates.append(wclose)

        if not candidates:
            return None
        nxt = min(candidates)
        return int((nxt - now).total_seconds() // 60)

    def in_preclose_window(self, base_symbol: str, lo: int = 15, hi: int = 30,
                           now: Optional[datetime] = None) -> bool:
        """True if we're within the [lo, hi] minute window before a close."""
        m = self.minutes_to_close(base_symbol, now)
        if m is None:
            return False
        return lo <= m <= hi

    def status(self, base_symbol: str) -> dict:
        return {
            "symbol": base_symbol,
            "open": self.is_open(base_symbol),
            "minutes_to_close": self.minutes_to_close(base_symbol),
        }
