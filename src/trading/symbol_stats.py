"""
Per-symbol market statistics.

Computes, for each traded symbol, how it actually behaves across timeframes:
typical bar range, ATR (typical move), median absolute % return, and current
spread. This is the foundation for:
  * sizing stop-losses relative to how far a symbol really moves,
  * scalp TP/SL targets that respect volatility,
  * multi-timeframe directional alignment before a 1m entry.

Stats are cached (in-memory + JSON on disk) and refreshed on an interval so the
trading loop stays fast. Later this cache layer is where Redis slots in for a
low-latency VPS deployment (same interface, different backend).
"""

from __future__ import annotations

import os
import json
import time
from dataclasses import dataclass, asdict, field
from typing import Optional

from src import config
from src.mt5.data import get_rates, get_last_price
from src.strategies.indicators import ohlcv_to_dataframe, atr as atr_fn
from src.utils.logger import get_logger

logger = get_logger("symbol_stats")

STATS_PATH = os.path.join(config.DATA_DIR, "symbol_stats.json")

# Timeframes we profile, with how many bars to sample and the MT5 code
TF_SAMPLE = {
    "M1": 300, "M5": 300, "M15": 200, "M30": 200,
    "H1": 200, "H4": 180, "D1": 120, "W1": 60,
}


@dataclass
class TimeframeStat:
    timeframe: str
    bars: int
    atr: float                 # average true range (price units) — typical move
    atr_pct: float             # ATR as % of price
    median_range: float        # median high-low per bar (price units)
    median_abs_ret_pct: float  # median |close-to-close| % move
    last_close: float
    direction: str             # bullish|bearish|neutral (EMA fast vs slow)


@dataclass
class SymbolStats:
    symbol: str
    point: float
    digits: int
    spread_points: float
    price: float
    computed_at: float
    timeframes: dict = field(default_factory=dict)  # tf -> TimeframeStat dict


class SymbolStatsEngine:
    def __init__(self, refresh_seconds: int = 900):
        self.refresh_seconds = refresh_seconds
        self._cache: dict[str, SymbolStats] = {}
        self._load()

    # ── persistence (Redis-swappable later) ──
    def _load(self):
        try:
            if os.path.exists(STATS_PATH):
                with open(STATS_PATH) as f:
                    raw = json.load(f)
                for sym, s in raw.get("symbols", {}).items():
                    self._cache[sym] = SymbolStats(**s)
        except Exception as e:
            logger.debug(f"stats load skip: {e}")

    def _persist(self):
        try:
            payload = {"updated_at": time.time(),
                       "symbols": {k: asdict(v) for k, v in self._cache.items()}}
            os.makedirs(config.DATA_DIR, exist_ok=True)
            tmp = STATS_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(payload, f, indent=2, default=str)
            os.replace(tmp, STATS_PATH)
        except Exception as e:
            logger.warning(f"stats persist failed: {e}")

    # ── compute ──
    def get(self, symbol: str, point: float, digits: float, force: bool = False) -> Optional[SymbolStats]:
        cached = self._cache.get(symbol)
        if cached and not force and (time.time() - cached.computed_at) < self.refresh_seconds:
            return cached
        return self.compute(symbol, point, digits)

    def compute(self, symbol: str, point: float, digits: float) -> Optional[SymbolStats]:
        import numpy as np
        tick = get_last_price(symbol)
        price = 0.0
        spread_pts = 0.0
        if isinstance(tick, dict):
            bid = tick.get("bid", 0) or 0
            ask = tick.get("ask", 0) or 0
            price = (bid + ask) / 2 if (bid and ask) else (bid or ask)
            spread_pts = ((ask - bid) / point) if (point and ask and bid) else 0.0

        tfs = {}
        for tf, n in TF_SAMPLE.items():
            rates = get_rates(symbol, timeframe=tf, count=n)
            if not rates or len(rates) < 20:
                continue
            df = ohlcv_to_dataframe(rates)
            highs = df["high"].astype(float)
            lows = df["low"].astype(float)
            closes = df["close"].astype(float)
            a = atr_fn(df, 14)
            atr_v = float(a.iloc[-1]) if a.notna().any() else float((highs - lows).tail(14).mean())
            last_close = float(closes.iloc[-1])
            rng = (highs - lows)
            median_range = float(rng.median())
            rets = closes.pct_change().abs().dropna()
            median_abs_ret = float(rets.median() * 100) if len(rets) else 0.0
            # simple direction via EMAs
            ema_fast = closes.ewm(span=9, adjust=False).mean().iloc[-1]
            ema_slow = closes.ewm(span=21, adjust=False).mean().iloc[-1]
            direction = ("bullish" if ema_fast > ema_slow * 1.0005
                         else "bearish" if ema_fast < ema_slow * 0.9995
                         else "neutral")
            tfs[tf] = asdict(TimeframeStat(
                timeframe=tf, bars=len(df),
                atr=round(atr_v, int(digits) if digits else 2),
                atr_pct=round(atr_v / last_close * 100, 4) if last_close else 0.0,
                median_range=round(median_range, int(digits) if digits else 2),
                median_abs_ret_pct=round(median_abs_ret, 4),
                last_close=round(last_close, int(digits) if digits else 2),
                direction=direction,
            ))

        stats = SymbolStats(
            symbol=symbol, point=point, digits=int(digits) if digits else 2,
            spread_points=round(spread_pts, 1), price=round(price, int(digits) if digits else 2),
            computed_at=time.time(), timeframes=tfs,
        )
        self._cache[symbol] = stats
        self._persist()
        logger.info(f"Stats computed for {symbol}: "
                    f"M1 atr={tfs.get('M1',{}).get('atr')} H1 atr={tfs.get('H1',{}).get('atr')} "
                    f"spread={spread_pts:.1f}pts")
        return stats

    # ── helpers for the trading loop ──
    def atr_points(self, symbol: str, timeframe: str) -> Optional[float]:
        s = self._cache.get(symbol)
        if not s or timeframe not in s.timeframes:
            return None
        tf = s.timeframes[timeframe]
        return tf["atr"] / s.point if s.point else None

    def direction(self, symbol: str, timeframe: str) -> Optional[str]:
        s = self._cache.get(symbol)
        if not s or timeframe not in s.timeframes:
            return None
        return s.timeframes[timeframe]["direction"]
