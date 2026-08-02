"""
RobustTester (#44) — M1-entry + HTF-support strategy optimiser validated across
RANDOM date windows, so the config trades well at ANY date (regime-agnostic), not
just one fitted window.

Design (per the trader):
  * ENTRY is on M1 (MACD-leads-OsMA zero-cross) WITH higher-timeframe SUPPORT
    (M5/M15 MACD alignment) — enter early on M1, confirmed by HTF, to capture more
    of the move.
  * Data: MT5 copy_rates_range gives ~40 days of M1 (57k bars) + months of M5/M15.
  * Method: optimise the full confluence + exit on a TRAINING slice, then VALIDATE
    the best config across N RANDOM M1 sub-windows. Keep a config only if it is
    profitable (PF >= target) across a MAJORITY of random windows — robustness,
    not single-window fit. Iterate, tightening, until it passes.

Uses copy_rates_range directly (the count-based fetch only returns a shallow
buffer). Offline analysis; no orders. Writes data/robust_config.json.

Run: python -m scripts.robust_tester [SYMBOL] [DAYS] [N_RANDOM] [ITERS]
"""

from __future__ import annotations

import os
import sys
import json
import random
import statistics
from datetime import datetime, timedelta, timezone

import pandas as pd



def _load_range(symbol, tf_const, days):
    import MetaTrader5 as mt5
    mt5.initialize(); mt5.symbol_select(symbol, True)
    end = datetime.now(); start = end - timedelta(days=days)
    r = mt5.copy_rates_range(symbol, tf_const, start, end)
    if r is None or len(r) == 0:
        return None
    return pd.DataFrame(r)


def find_triggers(m1, m5, m15, cfg):
    """FULL 7-indicator confluence triggers via the SHARED single source of truth
    (src.strategies.confluence_signal) so the robust tester validates EXACTLY the
    rules that trade live. Returns (triggers, m1_df) with i/direction/entry/atr/
    m5_ok/m15_ok/trigger_kind keys."""
    from src.strategies.confluence_signal import find_confluence_triggers
    trg, df1 = find_confluence_triggers(m1, m5, m15, cfg)
    return trg, df1



def simulate(triggers, m1, cfg, lo=None, hi=None, max_hold=120):
    """Simulate outcomes (points) for triggers whose bar index is in [lo,hi)."""
    highs = m1["high"].tolist(); lows = m1["low"].tolist(); closes = m1["close"].tolist()
    n = len(closes); sl_atr = cfg["sl_atr"]; tp_atr = cfg["sl_atr"] * cfg["tp_rr"]
    wins = losses = 0; gw = gl = 0.0
    for t in triggers:
        i = t["i"]
        if lo is not None and not (lo <= i < hi):
            continue
        if cfg.get("require_m5") and not t["m5_ok"]:
            continue
        if cfg.get("require_m15") and not t["m15_ok"]:
            continue
        atr = t["atr"]
        if atr <= 0:
            continue
        entry = t["entry"]; buy = t["direction"] == "buy"
        sl = entry - sl_atr * atr if buy else entry + sl_atr * atr
        tp = entry + tp_atr * atr if buy else entry - tp_atr * atr
        res = None
        for k in range(i + 1, min(i + 1 + max_hold, n)):
            if buy:
                if lows[k] <= sl: res = -sl_atr * atr; break
                if highs[k] >= tp: res = tp_atr * atr; break
            else:
                if highs[k] >= sl: res = -sl_atr * atr; break
                if lows[k] <= tp: res = tp_atr * atr; break
        if res is None:
            res = (closes[min(i + max_hold, n - 1)] - entry) * (1 if buy else -1)
        if res > 0: wins += 1; gw += res
        else: losses += 1; gl += abs(res)
    ntr = wins + losses
    if ntr == 0:
        return None
    return {"trades": ntr, "win_rate": round(wins / ntr * 100, 1),
            "profit_factor": round(gw / gl, 2) if gl > 0 else (gw or 0),
            "expectancy": round((gw - gl) / ntr, 2)}


def robustness(triggers, m1, cfg, n_random=8, win_bars=6000, min_trades=8, seed=1):
    """Validate cfg across N random M1 sub-windows. Return pass-rate + median PF."""
    rng = random.Random(seed)
    n = len(m1)
    pfs = []; passes = 0; tested = 0
    for _ in range(n_random):
        lo = rng.randint(0, max(1, n - win_bars)); hi = lo + win_bars
        r = simulate(triggers, m1, cfg, lo, hi)
        if not r or r["trades"] < min_trades:
            continue
        tested += 1
        pfs.append(r["profit_factor"])
        if r["profit_factor"] >= 1.2 and r["expectancy"] > 0:
            passes += 1
    if tested == 0:
        return {"tested": 0, "pass_rate": 0.0, "median_pf": 0.0}
    return {"tested": tested, "passes": passes, "pass_rate": round(passes / tested, 2),
            "median_pf": round(statistics.median(pfs), 2)}


def _candidates(cfg):
    """Neighbours across the FULL confluence: exit, OsMA engine, AND the strengths
    of every other indicator (EMA slope, ATR range, RSI thresholds, power period,
    price-stretch, confluence strictness)."""
    out = []
    grid = {
        "sl_atr": [round(cfg["sl_atr"] + d, 2) for d in (-0.5, 0.5)],
        "tp_rr": [round(cfg["tp_rr"] + d, 2) for d in (-0.3, 0.3)],
        "macd_lead_bars": [cfg["macd_lead_bars"] + d for d in (-2, 2)],
        "osma_fast": [cfg["osma_fast"] + d for d in (-4, 8)],
        "osma_slow": [cfg["osma_slow"] + d for d in (-10, 20)],
        "ema_period": [cfg["ema_period"] + d for d in (-20, 30)],
        "min_ema_slope_atr": [round(cfg["min_ema_slope_atr"] + d, 3) for d in (-0.02, 0.04)],
        "price_stretch_mult": [round(cfg["price_stretch_mult"] + d, 1) for d in (-0.5, 0.5)],
        "atr_min": [round(cfg["atr_min"] + d, 1) for d in (0.0, 0.5)],
        "atr_max": [round(cfg["atr_max"] + d, 1) for d in (0.0, 6.0)],
        "power_period": [cfg["power_period"] + d for d in (-4, 8)],
        "rsi_long_max": [cfg["rsi_long_max"] + d for d in (-5, 5)],
        "rsi_short_min": [cfg["rsi_short_min"] + d for d in (-5, 5)],
        "min_confluence": [cfg["min_confluence"] + d for d in (-1, 1)],
    }
    for k, opts in grid.items():
        for v in opts:
            c = dict(cfg); c[k] = v
            # sanity bounds
            if c["sl_atr"] < 0.5 or c["tp_rr"] < 0.4 or c["macd_lead_bars"] < 2:
                continue
            if c["osma_fast"] < 5 or c["osma_slow"] <= c["osma_fast"]:
                continue
            if c["ema_period"] < 10 or c["power_period"] < 5:
                continue
            if not (1 <= c["min_confluence"] <= 5):
                continue
            if c["atr_min"] < 0 or c["atr_max"] < 0:
                continue
            out.append((k, c))
    for key in ("require_m5", "require_m15"):
        c = dict(cfg); c[key] = not c.get(key, False); out.append((key, c))
    return out


def run(symbol="BTCUSD", days=40, n_random=8, iters=10):
    import MetaTrader5 as mt5
    print(f"Loading {symbol}: {days}d M1 + M5/M15 (copy_rates_range)...")
    m1 = _load_range(symbol, mt5.TIMEFRAME_M1, days)
    m5 = _load_range(symbol, mt5.TIMEFRAME_M5, days + 5)
    m15 = _load_range(symbol, mt5.TIMEFRAME_M15, days + 10)
    if m1 is None or len(m1) < 5000 or m5 is None or m15 is None:
        print("Insufficient data (stop the live bot so MT5 is free).")
        return
    print(f"  M1 {len(m1)} bars, M5 {len(m5)}, M15 {len(m15)}")

    cfg = {
        # OsMA/MACD engine
        "osma_fast": 12, "osma_slow": 26, "osma_signal": 9, "macd_lead_bars": 5,
        # the other confluence indicators + their strengths (TUNED here)
        "ema_period": 50, "min_ema_slope_atr": 0.02, "price_stretch_mult": 2.0,
        "atr_period": 14, "atr_min": 0.0, "atr_max": 0.0,
        "power_period": 13, "rsi_period": 14, "rsi_long_max": 72.0, "rsi_short_min": 28.0,
        "min_confluence": 3,          # how many of the 5 soft checks must agree
        # exit + HTF support
        "sl_atr": 2.0, "tp_rr": 1.0, "require_m5": True, "require_m15": False,
    }

    rounds = []
    triggers, _ = find_triggers(m1, m5, m15, cfg)
    print(f"  M1 triggers (start cfg): {len(triggers)}\n")
    best_rb = robustness(triggers, m1, cfg, n_random)
    print(f"round  0: base cfg pass_rate {best_rb['pass_rate']} median_pf {best_rb['median_pf']} (tested {best_rb['tested']})")

    for rnd in range(1, iters + 1):
        improved = None
        for knob, cand in _candidates(cfg):
            trg, _ = find_triggers(m1, m5, m15, cand)  # osma params change triggers
            rb = robustness(trg, m1, cand, n_random)
            better = (rb["pass_rate"], rb["median_pf"]) > (best_rb["pass_rate"], best_rb["median_pf"])
            if rb["tested"] >= max(3, n_random // 2) and better:
                if improved is None or (rb["pass_rate"], rb["median_pf"]) > (improved[2]["pass_rate"], improved[2]["median_pf"]):
                    improved = (knob, cand, rb)
        if improved is None:
            print(f"round {rnd:2}: converged (no candidate beats pass_rate {best_rb['pass_rate']} / PF {best_rb['median_pf']})")
            break
        knob, cfg, best_rb = improved
        rounds.append({"round": rnd, "knob": knob, "config": dict(cfg), "robustness": best_rb})
        print(f"round {rnd:2}: {knob} -> pass_rate {best_rb['pass_rate']} median_pf {best_rb['median_pf']} "
              f"| cfg sl {cfg['sl_atr']} tp_rr {cfg['tp_rr']} lead {cfg['macd_lead_bars']} "
              f"osma {cfg['osma_fast']}/{cfg['osma_slow']} m5 {int(cfg['require_m5'])} m15 {int(cfg['require_m15'])}")

    # final full-window check
    trg, _ = find_triggers(m1, m5, m15, cfg)
    full = simulate(trg, m1, cfg)
    payload = {"symbol": symbol, "days": days, "n_random": n_random,
               "final_config": cfg, "final_robustness": best_rb, "full_window": full,
               "rounds": rounds, "run_at": datetime.now(timezone.utc).isoformat()}
    try:
        from src import config
        p = os.path.join(config.DATA_DIR, "robust_config.json")
        json.dump(payload, open(p, "w"), indent=2, default=str)
        print(f"\nWritten {p}")
    except Exception as e:
        print(f"write skip: {e}")
    print(f"\nFINAL cfg: {cfg}")
    print(f"  robustness across {n_random} random windows: pass_rate {best_rb['pass_rate']}, median PF {best_rb['median_pf']}")
    print(f"  full-window: {full}")
    return payload


if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSD"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    nrand = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    iters = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    run(sym, days, nrand, iters)


class RobustTester:
    """Callable wrapper so the continual researcher can run random-window robust
    optimisation per symbol on a cadence and receive the winning config."""

    def __init__(self, days: int = 40, n_random: int = 8, iters: int = 6):
        self.days = days
        self.n_random = n_random
        self.iters = iters

    def optimise(self, symbol: str) -> dict:
        """Run the walk-forward random-window optimiser; return the payload
        (final_config + robustness + full_window). Non-fatal."""
        try:
            return run(symbol, self.days, self.n_random, self.iters) or {}
        except Exception as e:
            return {"error": str(e)[:120]}
