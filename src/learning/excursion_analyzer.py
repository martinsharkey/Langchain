"""
ExcursionAnalyzer (#41) — measure a symbol's typical movement DURING an OsMA cycle,
so the EXIT model can be calibrated per symbol.

The GoldShark intracandle telemetry proved entries are ~92-98% correct-direction;
the leak is EXIT management (trades peaked deeply green then were given back into a
loss). To fix exits per symbol we must know, for THAT symbol:
  - how far price typically travels (peak & trough, in points) between OsMA zero
    reversals (an "OsMA cycle") — i.e. the profit that is realistically available;
  - the typical candle WICK size (how much a bar spikes against you intrabar) — so
    the stop is wide enough to survive normal noise;
  - the MACD-cycle range for context.

From these we derive a symbol-specific exit recommendation:
  - suggested stop = a multiple of typical adverse excursion / wick (survive noise);
  - suggested take-profit / trail-arm = a fraction of typical favourable excursion
    (capture the move, exit near the OsMA reversal instead of giving it all back).

Symbol-agnostic: it measures each symbol's own points movement from live rates,
then the overarching "let winners run / cut losers early" logic is applied on top.
Offline analysis; no orders.
"""

from __future__ import annotations

import logging
import statistics
import pandas as pd

from src.strategies.indicators import macd as macd_fn, osma as osma_fn, atr as atr_fn

logger = logging.getLogger("excursion_analyzer")


class ExcursionAnalyzer:
    def __init__(self, get_rates_fn):
        self.get_rates = get_rates_fn

    def measure(self, symbol: str, point: float = None, bars: int = 6000,
                fast: int = 12, slow: int = 26, sig: int = 9) -> dict:
        """
        Measure OsMA-cycle excursion for `symbol`. Returns points-based stats +
        a symbol-specific exit recommendation. `point` converts price to points
        (defaults to trying the broker spec; falls back to raw price deltas).
        """
        try:
            rates = self.get_rates(symbol, timeframe="M1", count=bars)
        except Exception as e:
            return {"found": False, "reason": f"rates: {e}"}
        if not rates or len(rates) < 200:
            return {"found": False, "reason": "insufficient rates"}

        df = pd.DataFrame(rates)
        close = df["close"]
        osma = osma_fn(close, fast, slow, sig).reset_index(drop=True)
        macd_line = macd_fn(close, fast, slow, sig)[0].reset_index(drop=True)
        atr = atr_fn(df, 14).reset_index(drop=True)
        highs = df["high"].values; lows = df["low"].values; closes = close.values
        opens = df["open"].values if "open" in df else closes
        pt = point or self._infer_point(symbol, closes)

        # segment into OsMA cycles = spans between sign changes of OsMA
        cycles = []
        start = 0
        for i in range(1, len(osma)):
            if (osma[i] > 0) != (osma[i - 1] > 0):  # OsMA crossed zero
                if i - start >= 2:
                    cycles.append((start, i))
                start = i
        if len(cycles) < 5:
            return {"found": False, "reason": f"only {len(cycles)} OsMA cycles"}

        peak_pts, trough_pts, cycle_lens = [], [], []
        for a, b in cycles:
            seg_hi = max(highs[a:b]); seg_lo = min(lows[a:b]); entry = closes[a]
            up = osma[a + 1] > 0 if a + 1 < len(osma) else True
            if up:  # long cycle: favourable = high above entry, adverse = low below
                peak_pts.append((seg_hi - entry) / pt)
                trough_pts.append((entry - seg_lo) / pt)
            else:
                peak_pts.append((entry - seg_lo) / pt)
                trough_pts.append((seg_hi - entry) / pt)
            cycle_lens.append(b - a)

        # per-candle wick (spike against the close) in points
        wicks = []
        for i in range(len(closes)):
            body_hi = max(opens[i], closes[i]); body_lo = min(opens[i], closes[i])
            wicks.append(((highs[i] - body_hi) + (body_lo - lows[i])) / pt)

        med_peak = statistics.median([p for p in peak_pts if p >= 0] or [0])
        med_trough = statistics.median([t for t in trough_pts if t >= 0] or [0])
        med_wick = statistics.median(wicks) if wicks else 0
        med_atr_pts = (statistics.median([a for a in atr if a and a > 0]) / pt) if pt else 0

        # symbol-specific exit recommendation (points + ATR-relative)
        # stop: survive the typical adverse excursion + a wick buffer
        stop_pts = round(med_trough + 1.0 * med_wick, 1)
        # take/arm: capture ~70% of the typical favourable excursion (exit near OsMA reversal)
        tp_pts = round(0.7 * med_peak, 1)
        rec = {
            "suggested_stop_pts": round(float(stop_pts), 1),
            "suggested_tp_pts": round(float(tp_pts), 1),
            "suggested_sl_atr": round(float(stop_pts) / float(med_atr_pts), 2) if med_atr_pts else None,
            "suggested_tp_rr": round(float(tp_pts) / float(stop_pts), 2) if stop_pts else None,
        }
        result = {
            "found": True, "symbol": symbol.upper(), "point": pt,
            "osma_cycles": len(cycles),
            "median_peak_pts": round(med_peak, 1),      # profit typically AVAILABLE
            "median_trough_pts": round(med_trough, 1),  # adverse excursion to survive
            "median_wick_pts": round(med_wick, 1),
            "median_atr_pts": round(med_atr_pts, 1),
            "median_cycle_bars": int(statistics.median(cycle_lens)) if cycle_lens else 0,
            "peak_to_trough_ratio": round(med_peak / med_trough, 2) if med_trough else None,
            "recommendation": rec,
        }
        return result

    @staticmethod
    def _infer_point(symbol: str, closes) -> float:
        """Rough point size when the broker spec isn't passed (price scale heuristic)."""
        px = float(closes[-1]) if len(closes) else 1.0
        s = symbol.upper()
        if "JPY" in s:
            return 0.001
        if "XAU" in s or "GER" in s or "US30" in s or "NAS" in s:
            return 0.01
        if "BTC" in s or "ETH" in s or px > 1000:
            return 0.01
        return 0.0001  # FX default
