"""
PatternOptimizer (#36/#40) — continually discover + LOCK IN the MACD-leads-OsMA
pattern AND its optimal exits, PER SYMBOL.

This turns the one-off scripts/backtest_macd_osma.py into a reusable engine the
continual researcher calls on a cadence. For a symbol it:
  1. finds MACD-leads-OsMA zero-cross triggers on real M1 history (MACD line
     crosses zero first, OsMA confirms same direction), with M5/M15 MACD alignment;
  2. sweeps exit variations (sl_atr x tp_rr) + MTF-alignment filters;
  3. picks the best config that GENERALIZES (PF>=min, enough trades, positive
     expectancy) — biased toward "let winners run / cut losers early" = WIDE stop,
     right-sized TP;
  4. returns the winning config so the caller writes it into the symbol's live
     tuned_params (sl_atr/tp_rr) — gated, then the #27 checkpointer verifies
     realised expectancy and reverts if worse.

Symbol-agnostic: the edge the trader discovered on gold works across symbols;
this finds each symbol's own best exit calibration (indicator scales differ).
Offline analysis (uses historical rates); places no orders.
"""

from __future__ import annotations

import logging
import pandas as pd

from src.strategies.confluence_signal import find_confluence_triggers

logger = logging.getLogger("pattern_optimizer")

SL_GRID = (1.0, 1.5, 2.0, 2.5)
TP_GRID = (0.7, 1.0, 1.5, 2.0)


def find_triggers(m1, m5, m15, cfg=None):
    """FULL 7-indicator confluence triggers (shared definition). m1/m5/m15 are
    lists of rate dicts; wrap as DataFrames for the shared module."""
    d1 = pd.DataFrame(m1); d5 = pd.DataFrame(m5); d15 = pd.DataFrame(m15)
    trg, _ = find_confluence_triggers(d1, d5, d15, cfg)
    return trg, d1


def _simulate(triggers, df1, sl_atr, tp_atr, require_m5, require_m15, max_hold=60):
    wins = losses = 0
    gw = gl = 0.0
    closes = df1["close"].values; highs = df1["high"].values; lows = df1["low"].values
    n = len(closes)
    for t in triggers:
        if require_m5 and not t.get("m5_ok"):
            continue
        if require_m15 and not t.get("m15_ok"):
            continue
        atr = t["atr"]
        if atr <= 0:
            continue
        i = t["i"]; entry = t["entry"]; buy = t["direction"] == "buy"
        sl = entry - sl_atr * atr if buy else entry + sl_atr * atr
        tp = entry + tp_atr * atr if buy else entry - tp_atr * atr
        outcome = None
        for k in range(i + 1, min(i + 1 + max_hold, n)):
            if buy:
                if lows[k] <= sl: outcome = -sl_atr * atr; break
                if highs[k] >= tp: outcome = tp_atr * atr; break
            else:
                if highs[k] >= sl: outcome = -sl_atr * atr; break
                if lows[k] <= tp: outcome = tp_atr * atr; break
        if outcome is None:
            outcome = (closes[min(i + max_hold, n - 1)] - entry) * (1 if buy else -1)
        if outcome > 0: wins += 1; gw += outcome
        else: losses += 1; gl += abs(outcome)
    n_tr = wins + losses
    if n_tr == 0:
        return None
    pf = gw / gl if gl > 0 else (gw or 0)
    return {"trades": n_tr, "win_rate": round(wins / n_tr * 100, 1),
            "profit_factor": round(pf, 2), "expectancy": round((gw - gl) / n_tr, 3),
            "sl_atr": sl_atr, "tp_rr": round(tp_atr / sl_atr, 2), "tp_atr": tp_atr}


class PatternOptimizer:
    def __init__(self, get_rates_fn, min_trades=20, min_pf=1.3):
        self.get_rates = get_rates_fn
        self.min_trades = min_trades
        self.min_pf = min_pf

    def discover(self, symbol: str, bars: int = 8000) -> dict:
        """Find the best-generalizing exit config for the MACD-leads-OsMA pattern
        on `symbol`. Returns {found, best:{sl_atr,tp_rr,...}, alt_filter, triggers}."""
        try:
            m1 = self.get_rates(symbol, timeframe="M1", count=bars)
            m5 = self.get_rates(symbol, timeframe="M5", count=max(bars // 5, 500))
            m15 = self.get_rates(symbol, timeframe="M15", count=max(bars // 15, 400))
        except Exception as e:
            logger.debug(f"pattern discover rates skip {symbol}: {e}")
            return {"found": False, "reason": f"rates: {e}"}
        if not m1 or not m5 or not m15 or len(m1) < 200:
            return {"found": False, "reason": "insufficient rates"}
        triggers, df1 = find_triggers(m1, m5, m15)
        if len(triggers) < self.min_trades:
            return {"found": False, "reason": f"only {len(triggers)} triggers", "triggers": len(triggers)}
        best = None
        best_filter = None
        for label, rm5, rm15 in (("all", False, False), ("m5", True, False), ("m5+m15", True, True)):
            for sl in SL_GRID:
                for tp in TP_GRID:
                    r = _simulate(triggers, df1, sl, tp, rm5, rm15)
                    if not r or r["trades"] < self.min_trades:
                        continue
                    if r["profit_factor"] >= self.min_pf and r["expectancy"] > 0:
                        if best is None or r["profit_factor"] > best["profit_factor"]:
                            best = r; best_filter = label
        if best is None:
            return {"found": False, "reason": "no config cleared the gate",
                    "triggers": len(triggers)}
        return {"found": True, "best": best, "alt_filter": best_filter,
                "triggers": len(triggers), "symbol": symbol.upper()}
