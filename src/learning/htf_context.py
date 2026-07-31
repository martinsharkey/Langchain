"""
HTFContext — multi-timeframe trend + momentum alignment, used at ENTRY and during
TRADE MANAGEMENT.

The intelligence the trader asked for: gold (and every symbol) should "see" the
higher timeframes (M5/M15/M30/H1). On entry, HTF agreement raises confidence and
disagreement lowers it. DURING a trade, we re-check the HTF — if the higher
timeframes STILL align with our position, a sudden adverse tick is likely a BLIP
and we should give the trade room (a wider stop) rather than get wicked out; if
the HTF momentum has genuinely FLIPPED against us, that's a real REVERSAL and we
should cut.

Pure-ish: reads bars via an injected `get_rates` (real MT5 in prod, fake in
tests), computes EMA-trend + MACD-momentum per timeframe, and returns an
alignment score in [-1, +1] (signed toward the position direction) plus a
blip-vs-reversal classification. Cached briefly so it never slows the loop.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Callable

from src.utils.logger import get_logger

logger = get_logger("htf_context")

# Timeframes to consider, weighted (higher TF = more weight for the trend read).
DEFAULT_TFS = [("M5", 1.0), ("M15", 1.5), ("M30", 2.0), ("H1", 2.5)]


@dataclass
class HTFRead:
    symbol: str
    action: str                 # 'buy' | 'sell' the score is oriented toward
    alignment: float            # [-1..+1]  +1 = all HTFs agree with action
    per_tf: dict                # {tf: {"trend": .., "momentum": .., "agree": bool}}
    aligned: bool               # net agreement toward action
    momentum_flipped: bool      # HTF momentum has turned AGAINST the action (reversal)
    reason: str = ""


def _ema(vals, period):
    if len(vals) < 2:
        return vals[-1] if vals else 0.0
    k = 2 / (period + 1)
    e = vals[0]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
    return e


def _macd_hist(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal:
        return 0.0
    macd_series = []
    # build MACD line over a trailing window, then signal EMA of it
    for i in range(slow, len(closes) + 1):
        seg = closes[:i]
        macd_series.append(_ema(seg, fast) - _ema(seg, slow))
    if len(macd_series) < signal:
        return macd_series[-1] if macd_series else 0.0
    sig = _ema(macd_series, signal)
    return macd_series[-1] - sig


class HTFContext:
    def __init__(self, get_rates: Callable, tfs=None, cache_seconds: int = 20):
        """
        get_rates(symbol, timeframe=str, count=int) -> list[dict bars] (same shape
        as src.mt5.data.get_rates). Injected so this is testable.
        """
        self.get_rates = get_rates
        self.tfs = tfs or DEFAULT_TFS
        self.cache_seconds = cache_seconds
        self._cache = {}   # (symbol) -> (ts, {tf: read})

    def _tf_read(self, symbol: str, tf: str) -> Optional[dict]:
        bars = self.get_rates(symbol, timeframe=tf, count=120)
        if not bars or len(bars) < 35:
            return None
        closes = [b["close"] for b in bars]
        ema_fast = _ema(closes[-40:], 9)
        ema_slow = _ema(closes[-40:], 21)
        trend = 1 if ema_fast > ema_slow * 1.0003 else -1 if ema_fast < ema_slow * 0.9997 else 0
        hist = _macd_hist(closes[-80:])
        momentum = 1 if hist > 0 else -1 if hist < 0 else 0
        return {"trend": trend, "momentum": momentum, "macd_hist": hist}

    def read(self, symbol: str, action: str) -> HTFRead:
        now = time.time()
        cached = self._cache.get(symbol)
        if not cached or (now - cached[0]) >= self.cache_seconds:
            per = {}
            for tf, _w in self.tfs:
                r = self._tf_read(symbol, tf)
                if r:
                    per[tf] = r
            self._cache[symbol] = (now, per)
        per = self._cache[symbol][1]

        want = 1 if action == "buy" else -1
        num = den = 0.0
        agree_count = flip_count = 0
        per_out = {}
        for tf, w in self.tfs:
            r = per.get(tf)
            if not r:
                continue
            # combined tf signal: trend + momentum, both toward `want`
            tf_dir = r["trend"] + r["momentum"]      # -2..+2
            score = (1 if tf_dir > 0 else -1 if tf_dir < 0 else 0)
            agree = (score == want)
            num += w * (1 if agree else (-1 if score == -want else 0))
            den += w
            if score == want:
                agree_count += 1
            # momentum flipped AGAINST us on this TF?
            if r["momentum"] == -want:
                flip_count += 1
            per_out[tf] = {"trend": r["trend"], "momentum": r["momentum"], "agree": agree}

        alignment = round(num / den, 3) if den else 0.0
        aligned = alignment > 0
        # genuine reversal: momentum flipped against us on the MAJORITY of HTFs
        momentum_flipped = flip_count >= max(2, (len(per_out) // 2) + 1) if per_out else False
        reason = (f"HTF align {alignment:+.2f} ({agree_count}/{len(per_out)} agree, "
                  f"{flip_count} momo-flipped)")
        return HTFRead(symbol=symbol, action=action, alignment=alignment, per_tf=per_out,
                       aligned=aligned, momentum_flipped=momentum_flipped, reason=reason)

    def blip_or_reversal(self, symbol: str, action: str) -> str:
        """
        Classify a sudden adverse move for an OPEN trade:
          'blip'     -> HTF still aligned with us; adverse tick likely noise -> give room
          'reversal' -> HTF momentum flipped against us -> cut
          'neutral'  -> unclear
        """
        r = self.read(symbol, action)
        if r.momentum_flipped and not r.aligned:
            return "reversal"
        if r.aligned and not r.momentum_flipped:
            return "blip"
        return "neutral"
