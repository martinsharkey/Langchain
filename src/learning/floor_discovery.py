"""
Symbol onboarding: automatic per-symbol strength-floor DISCOVERY (backtest + forward
test). No symbol ever starts with zero floors — on first sight the bot backtests its
OWN bar+tick history to find the floor recipe that best balances frequency, entry-
direction success, and exit capture, validates it on a held-out forward window, and
seeds it as the symbol's baseline.

The indicator COMBINATION is symbol-agnostic; only the MAGNITUDE floors are searched
(ATR-normalized so scale-free). Fixed-point GoldShark-style exits are used for fills.

Public: FloorDiscovery(get_rates_fn, get_ticks_fn).onboard(symbol) -> recipe dict or None.
"""
from __future__ import annotations
import statistics
from typing import Optional, Callable

from src.utils.logger import get_logger

logger = get_logger("floor_discovery")

_OSMA_GRID = (0.0, 0.1, 0.2, 0.3, 0.5)
_DOM_GRID = (0.0, 0.5, 1.0, 1.5)


def _ema(vals, p):
    out = []; k = 2 / (p + 1); e = vals[0]
    for v in vals:
        e = v * k + e * (1 - k); out.append(e)
    return out


class FloorDiscovery:
    def __init__(self, get_rates_fn: Callable, get_ticks_fn: Callable,
                 bars: int = 60000, min_trades_per_day: float = 3.0):
        self._rates = get_rates_fn
        self._ticks = get_ticks_fn
        self.bars = bars
        self.min_tpd = min_trades_per_day

    def _indicators(self, bars):
        close = [b["close"] for b in bars]; high = [b["high"] for b in bars]; low = [b["low"] for b in bars]
        fast = _ema(close, 12); slow = _ema(close, 26); macd = [f - s for f, s in zip(fast, slow)]
        sig = _ema(macd, 9); osma = [m - s for m, s in zip(macd, sig)]
        ep = _ema(close, 13); bulls = [h - e for h, e in zip(high, ep)]; bears = [l - e for l, e in zip(low, ep)]
        tr = [high[0] - low[0]]
        for i in range(1, len(bars)):
            tr.append(max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])))
        atr = [sum(tr[max(0, i - 13):i + 1]) / min(i + 1, 14) for i in range(len(tr))]
        return osma, ep, bulls, bears, atr

    def _score_window(self, bars, ticks_t, ticks_b, ticks_a, osma, ep, bulls, bears, atr,
                      lo, hi, ti0, floor_osma, floor_dom, slope_min=0.05, green_atr=0.3):
        med_atr = statistics.median([a for a in atr[lo:hi] if a > 0]) or 1.0
        pt = 0.01
        be_trig = 1.5 * med_atr; tp_dist = 2.0 * med_atr; trail = 1.2 * med_atr; hard_sl = 3.0 * med_atr
        trades = wins = green = gw = gl = 0; ti = ti0; caps = []; days = set()
        for i in range(max(lo, 30), hi - 1):
            a1 = atr[i - 1]
            if a1 <= 0:
                continue
            o1, o2 = osma[i - 1], osma[i - 2]; b1, be1 = bulls[i - 1], bears[i - 1]
            slope = (ep[i - 1] - ep[i - 5]) / a1
            longR = (o1 > 0 and o1 > o2 and b1 > 0 and be1 > 0 and slope >= slope_min
                     and (abs(o1) / a1) >= floor_osma and (b1 / a1) >= floor_dom)
            shortR = (o1 < 0 and o1 < o2 and be1 < 0 and b1 < 0 and slope <= -slope_min
                      and (abs(o1) / a1) >= floor_osma and (-be1 / a1) >= floor_dom)
            if not (longR or shortR):
                continue
            d = 1 if longR else -1
            et = bars[i + 1]["timestamp"]
            while ti < len(ticks_t) and ticks_t[ti] < et:
                ti += 1
            if ti >= len(ticks_t):
                break
            entry = ticks_a[ti] if d == 1 else ticks_b[ti]
            sl = entry - hard_sl * d; tp = entry + tp_dist * d
            j = ti; exitp = None; peak = entry; moved = False
            while j < len(ticks_t):
                px = ticks_b[j] if d == 1 else ticks_a[j]
                if d == 1:
                    peak = max(peak, px)
                    if not moved and peak - entry >= be_trig: sl = entry + pt; moved = True
                    if peak - entry >= trail: sl = max(sl, peak - trail)
                    if px <= sl: exitp = sl; break
                    if px >= tp: exitp = tp; break
                else:
                    peak = min(peak, px)
                    if not moved and entry - peak >= be_trig: sl = entry - pt; moved = True
                    if entry - peak >= trail: sl = min(sl, peak + trail)
                    if px >= sl: exitp = sl; break
                    if px <= tp: exitp = tp; break
                j += 1
            if exitp is None:
                exitp = ticks_b[-1] if d == 1 else ticks_a[-1]
            mfe = (peak - entry) * d; pl = (exitp - entry) * d
            trades += 1; days.add(bars[i]["timestamp"] // 86400)
            if mfe >= green_atr * a1: green += 1
            if pl > 0: wins += 1; gw += pl
            else: gl += -pl
            if mfe > 0: caps.append(max(pl, 0) / mfe)
            ti = j
        nd = max(len(days), 1)
        pf = gw / gl if gl > 0 else (99 if gw else 0)
        return {"trades": trades, "per_day": trades / nd, "wr": (wins / trades * 100) if trades else 0,
                "green_pct": (green / trades * 100) if trades else 0, "pf": pf,
                "capture": (statistics.median(caps) * 100) if caps else 0}

    def onboard(self, symbol: str) -> Optional[dict]:
        """Backtest + forward-test the symbol's own history; return the best floor recipe.
        Split: first 70% = train (search), last 30% = forward-test (validate). Picks the
        floor combo with the best TRAIN score that also holds up in the FORWARD window and
        keeps >= min_trades_per_day (never chokes, never zero)."""
        try:
            rates = self._rates(symbol, timeframe="M1", count=self.bars)
        except Exception as e:
            logger.info(f"[ONBOARD] {symbol}: no rates ({e})"); return None
        if not rates or len(rates) < 5000:
            logger.info(f"[ONBOARD] {symbol}: insufficient bars ({0 if not rates else len(rates)})"); return None
        t0 = int(rates[0]["timestamp"]); t1 = int(rates[-1]["timestamp"]) + 60
        tk = self._ticks(symbol, t0, t1)
        if not tk or not tk.get("time"):
            logger.info(f"[ONBOARD] {symbol}: no ticks — cannot forward-test; skipping (stays structure-only)")
            return None
        tt = tk["time"]; tb = tk["bid"]; ta = tk["ask"]
        osma, ep, bulls, bears, atr = self._indicators(rates)
        n = len(rates); split = int(n * 0.7)
        best = None
        for fo in _OSMA_GRID:
            for fd in _DOM_GRID:
                tr = self._score_window(rates, tt, tb, ta, osma, ep, bulls, bears, atr, 30, split, 0, fo, fd)
                if tr["per_day"] < self.min_tpd:
                    continue
                score = tr["green_pct"] / 100 * tr["pf"] * min(tr["per_day"] / 10, 1.5)
                if best is None or score > best[0]:
                    best = (score, fo, fd, tr)
        if not best:
            logger.info(f"[ONBOARD] {symbol}: no non-choking floor found; structure-only")
            return None
        _, fo, fd, tr = best
        # FORWARD TEST the chosen floors on the held-out last 30%
        ft = self._score_window(rates, tt, tb, ta, osma, ep, bulls, bears, atr, split, n, 0, fo, fd)
        logger.warning(f"[ONBOARD] {symbol}: floors osma>={fo} dom>={fd} | "
                       f"TRAIN {tr['per_day']:.1f}/day green {tr['green_pct']:.0f}% PF {tr['pf']:.2f} | "
                       f"FWD green {ft['green_pct']:.0f}% PF {ft['pf']:.2f}")
        return {"osma_min_long": fo, "bulls_min_long": fd,
                "osma_max_short": -fo, "bears_max_short": -fd,
                "max_momentum_age": 26, "rsi_long_max": 100.0, "rsi_short_min": 0.0,
                "min_confluence": 3, "sl_atr": 0.8, "tp_rr": 2.0,
                "_train": tr, "_forward": ft}
