"""
Big-candle driver analysis.

Question: what drove today's largest candles, and were our indicators configured to
enter that move? If the big winners (large candles in our favour) were NOT aligned
with our OsMA/Bulls/Bears entry conditions, our indicators are mis-configured for
catching the moves that matter.

Runs INSIDE the engine (uses its MT5 session — never open a second one). For each
symbol it finds the largest M1 candles over a window and reports, per candle: size,
direction, and the OsMA / Bulls / Bears / EMA-slope state at that bar — plus whether
our confluence would have been ALIGNED to trade that direction. Aggregates how many
big moves we were aligned for vs missed.
"""
from __future__ import annotations
import statistics
from typing import Optional, Callable

from src.utils.logger import get_logger

logger = get_logger("big_candle")


class BigCandleAnalyzer:
    def __init__(self, get_rates_fn: Callable, point_fn: Callable):
        """get_rates_fn(resolved, timeframe, count) -> list[bar dicts];
        point_fn(resolved) -> point size. Both injected from the engine."""
        self._rates = get_rates_fn
        self._point = point_fn

    def analyze(self, base: str, resolved: str, count: int = 500, top_n: int = 10) -> dict:
        from src.strategies.indicators import compute_indicator_series
        try:
            rates = self._rates(resolved, "M1", count)
        except Exception as e:
            return {"symbol": base, "error": str(e)}
        if not rates or len(rates) < 60:
            return {"symbol": base, "error": "insufficient rates"}
        pt = self._point(resolved) or 0.01
        series = compute_indicator_series(rates, {})

        cands = []
        for i in range(30, len(rates)):
            rng = (rates[i]["high"] - rates[i]["low"]) / pt
            direction = "up" if rates[i]["close"] >= rates[i]["open"] else "down"
            ind = series[i] if i < len(series) else {}
            osma = float(ind.get("osma") or 0)
            atr = float(ind.get("atr") or 1) or 1
            # was OsMA (and thus our confluence direction) aligned with this candle?
            aligned = (direction == "up" and osma > 0) or (direction == "down" and osma < 0)
            cands.append({
                "range_pts": round(rng, 0), "dir": direction, "bar": i,
                "osma": round(osma, 4), "osma_over_atr": round(abs(osma) / atr, 3),
                "bulls": round(float(ind.get("bulls_power") or 0), 3),
                "bears": round(float(ind.get("bears_power") or 0), 3),
                "ema_slope": round(float(ind.get("ema_fast") or 0) - float(ind.get("ema_prev") or 0), 4),
                "rsi": round(float(ind.get("rsi") or 50), 1),
                "aligned": aligned,
            })
        cands.sort(key=lambda c: -c["range_pts"])
        big = cands[:top_n]
        aligned_n = sum(1 for c in big if c["aligned"])
        med_rng = statistics.median([c["range_pts"] for c in cands]) if cands else 0
        return {
            "symbol": base, "n_bars": len(cands), "median_range_pts": round(med_rng, 0),
            "top": big, "aligned_of_top": aligned_n, "top_n": len(big),
            "aligned_pct": round(aligned_n / len(big) * 100, 0) if big else 0,
        }

    def report(self, symbols):  # symbols: list of (base, resolved)
        out = {}
        for base, resolved in symbols:
            a = self.analyze(base, resolved)
            out[base] = a
            if a.get("error"):
                logger.info(f"[BIG-CANDLE] {base}: {a['error']}"); continue
            logger.info(f"[BIG-CANDLE] {base}: our OsMA aligned with {a['aligned_of_top']}/{a['top_n']} "
                        f"biggest candles ({a['aligned_pct']}%); median M1 range {a['median_range_pts']}pts")
            for c in a["top"][:5]:
                logger.info(f"   {c['range_pts']:.0f}pts {c['dir']} | osma={c['osma']} "
                            f"(|osma|/atr={c['osma_over_atr']}) bulls={c['bulls']} bears={c['bears']} "
                            f"emaSlope={c['ema_slope']} rsi={c['rsi']} aligned={c['aligned']}")
        return out
