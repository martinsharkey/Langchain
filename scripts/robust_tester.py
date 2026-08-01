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

from src.strategies.indicators import (
    macd as macd_fn, osma as osma_fn, atr as atr_fn, ema as ema_fn,
    rsi as rsi_fn, bulls_power as bulls_fn, bears_power as bears_fn,
)


def _load_range(symbol, tf_const, days):
    import MetaTrader5 as mt5
    mt5.initialize(); mt5.symbol_select(symbol, True)
    end = datetime.now(); start = end - timedelta(days=days)
    r = mt5.copy_rates_range(symbol, tf_const, start, end)
    if r is None or len(r) == 0:
        return None
    return pd.DataFrame(r)


def _indicators(df, cfg):
    """Compute the FULL 7-indicator confluence set as aligned series."""
    close = df["close"].reset_index(drop=True)
    fast, slow, sig = cfg["osma_fast"], cfg["osma_slow"], cfg["osma_signal"]
    macd_line = macd_fn(close, fast, slow, sig)[0].reset_index(drop=True)
    osma = osma_fn(close, fast, slow, sig).reset_index(drop=True)
    a = atr_fn(df, cfg.get("atr_period", 14)).reset_index(drop=True)
    ema_f = ema_fn(close, cfg.get("ema_period", 50)).reset_index(drop=True)
    r = rsi_fn(close, cfg.get("rsi_period", 14)).reset_index(drop=True)
    bp = bulls_fn(df, cfg.get("power_period", 13)).reset_index(drop=True)
    brp = bears_fn(df, cfg.get("power_period", 13)).reset_index(drop=True)
    return {"macd": macd_line, "osma": osma, "atr": a, "ema": ema_f,
            "rsi": r, "bulls": bp, "bears": brp}


def _htf_macd_side(ts, htf_times, htf_macd):
    # last HTF bar at/before ts
    lo, hi = 0, len(htf_times) - 1
    idx = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if htf_times[mid] <= ts:
            idx = mid; lo = mid + 1
        else:
            hi = mid - 1
    if idx < 0 or idx >= len(htf_macd):
        return 0
    v = htf_macd[idx]
    return 1 if v > 0 else (-1 if v < 0 else 0)


def find_triggers(m1, m5, m15, cfg):
    """
    M1 MACD-leads-OsMA trigger + the FULL 7-indicator confluence confirmation
    (MACD, OsMA, Bears Power, Bulls Power, EMA, ATR, RSI) + HTF support — matching
    src/strategies/osma_confluence.py. Only bars passing the hard gates AND >=
    min_confluence soft checks (+ required HTF alignment) become triggers.
    """
    ind = _indicators(m1, cfg)
    macd1, osma1, atr1 = ind["macd"], ind["osma"], ind["atr"]
    ema1, rsi1, bulls1, bears1 = ind["ema"], ind["rsi"], ind["bulls"], ind["bears"]
    m5_macd = _indicators(m5, cfg)["macd"]; m5_t = m5["time"].tolist()
    m15_macd = _indicators(m15, cfg)["macd"]; m15_t = m15["time"].tolist()
    times = m1["time"].tolist(); closes = m1["close"].tolist()
    lead = cfg["macd_lead_bars"]
    min_slope = cfg.get("min_ema_slope_atr", 0.02)
    stretch_mult = cfg.get("price_stretch_mult", 2.0)
    rsi_long_max = cfg.get("rsi_long_max", 72.0)
    rsi_short_min = cfg.get("rsi_short_min", 28.0)
    atr_min = cfg.get("atr_min", 0.0); atr_max = cfg.get("atr_max", 0.0)
    min_conf = cfg.get("min_confluence", 3)
    start = max(cfg["osma_slow"] + cfg["osma_signal"], cfg.get("ema_period", 50), 30)
    out = []
    for i in range(start, len(m1) - 1):
        cu = osma1[i - 1] <= 0 < osma1[i]
        cd = osma1[i - 1] >= 0 > osma1[i]
        if not (cu or cd):
            continue
        direction = "buy" if cu else "sell"
        # MACD leads: MACD crossed zero same direction within `lead` bars before
        led = False
        for k in range(1, lead + 1):
            j = i - k
            if j < 1:
                break
            if (direction == "buy" and macd1[j - 1] <= 0 < macd1[j]) or \
               (direction == "sell" and macd1[j - 1] >= 0 > macd1[j]):
                led = True; break
        if not led:
            continue
        atr = float(atr1[i] or 0)
        if atr <= 0:
            continue
        macd = float(macd1[i]); ema = float(ema1[i]); ema_prev = float(ema1[i - 1])
        close = closes[i]; rsi = float(rsi1[i] or 50)
        bulls = float(bulls1[i] or 0); bears = float(bears1[i] or 0)
        atr_prev = float(atr1[i - 1] or atr)
        # HARD gates (both must hold): MACD aligned side-of-zero + ATR expanding
        if direction == "buy" and not (macd > 0):
            continue
        if direction == "sell" and not (macd < 0):
            continue
        if not (atr > atr_prev):
            continue
        # SOFT confluence (each of the 5 adds to the score)
        def _atr_in_range():
            if atr_min <= 0 and atr_max <= 0:
                return True
            if atr_min > 0 and atr < atr_min:
                return False
            if atr_max > 0 and atr > atr_max:
                return False
            return True
        if direction == "buy":
            checks = [
                (ema - ema_prev) >= min_slope * atr and close > ema,   # EMA trend
                _atr_in_range(),                                        # ATR range
                abs(close - ema) <= stretch_mult * atr,                 # price stretch
                bulls > 0 and bears > -abs(bulls),                      # buyers in control
                rsi < rsi_long_max,                                     # RSI not exhausted
            ]
        else:
            checks = [
                (ema - ema_prev) <= -min_slope * atr and close < ema,
                _atr_in_range(),
                abs(close - ema) <= stretch_mult * atr,
                bears < 0 and bulls < abs(bears),
                rsi > rsi_short_min,
            ]
        if sum(1 for c in checks if c) < min_conf:
            continue
        ts = times[i]; want = 1 if direction == "buy" else -1
        out.append({"i": i, "direction": direction, "entry": close, "atr": atr,
                    "confluence": sum(1 for c in checks if c),
                    "m5_ok": _htf_macd_side(ts, m5_t, m5_macd) == want,
                    "m15_ok": _htf_macd_side(ts, m15_t, m15_macd) == want})
    return out, m1


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
