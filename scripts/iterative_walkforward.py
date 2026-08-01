"""
Iterative walk-forward tuner for the BTCUSD MACD-leads-OsMA strategy (#43).

Runs N rounds (default 10). Each round:
  1. BACKTEST the current config on the IN-SAMPLE window (older 60% of history).
  2. FORWARD-TEST it on the OUT-OF-SAMPLE window (newer 40%) — true generalization.
  3. Try small INCREMENTAL adjustments (sl_atr, tp_rr, macd_lead_bars, MTF filter);
     keep the one that best improves OUT-OF-SAMPLE profit factor (only if it also
     stays profitable in-sample — no overfitting to the OOS window).
  4. Log the round (config + IS/OOS metrics + what changed) to a results file.

Real in-sample -> real out-of-sample, so we build confidence that a change
generalizes, not just fits the past. Nothing is placed; analysis only.

Run:  python -m scripts.iterative_walkforward  [SYMBOL]  [ROUNDS]  [BARS]
Results appended to data/walkforward_results.json.
"""

from __future__ import annotations

import os
import sys
import json
import copy
from datetime import datetime, timezone

from src.mt5.data import get_rates
from scripts.backtest_macd_osma import find_triggers, simulate


def _metrics(triggers, df1, cfg):
    r = simulate(triggers, df1, cfg["sl_atr"], cfg["sl_atr"] * cfg["tp_rr"],
                 require_m5=cfg["require_m5"], require_m15=cfg["require_m15"])
    return r  # {trades, win_rate, profit_factor, expectancy} or None


def _score(m):
    if not m or m["trades"] < 15:
        return -1.0
    return m["profit_factor"]


def _candidates(cfg):
    """Small incremental neighbours of the current config (one knob at a time)."""
    out = []
    for d in (-0.5, +0.5):
        c = copy.deepcopy(cfg); c["sl_atr"] = round(max(0.5, min(3.0, c["sl_atr"] + d)), 2)
        out.append(("sl_atr", c))
    for d in (-0.3, +0.3):
        c = copy.deepcopy(cfg); c["tp_rr"] = round(max(0.4, min(2.5, c["tp_rr"] + d)), 2)
        out.append(("tp_rr", c))
    for d in (-2, +2):
        c = copy.deepcopy(cfg); c["macd_lead_bars"] = max(2, min(12, c["macd_lead_bars"] + d))
        out.append(("macd_lead_bars", c))
    # MTF filter toggles
    c = copy.deepcopy(cfg); c["require_m5"] = not c["require_m5"]; out.append(("require_m5", c))
    c = copy.deepcopy(cfg); c["require_m15"] = not c["require_m15"]; out.append(("require_m15", c))
    return out


def run(symbol="BTCUSD", rounds=10, bars=12000):
    from src.mt5.connector import get_connector
    try:
        get_connector().initialize()
    except Exception as e:
        print(f"MT5 init failed: {e}")

    m1 = get_rates(symbol, timeframe="M1", count=bars)
    m5 = get_rates(symbol, timeframe="M5", count=max(bars // 5, 800))
    m15 = get_rates(symbol, timeframe="M15", count=max(bars // 15, 500))
    if not m1 or len(m1) < 1000:
        print("Insufficient M1 history (MT5 not connected / market data). Stop the bot first.")
        return

    # chronological split: older 60% in-sample, newer 40% out-of-sample
    cut = int(len(m1) * 0.6)
    m1_is, m1_oos = m1[:cut], m1[cut:]
    # HTF windows aligned to each M1 span by time
    t_cut = m1[cut]["time"]
    m5_is = [b for b in m5 if b["time"] <= t_cut]; m5_oos = m5
    m15_is = [b for b in m15 if b["time"] <= t_cut]; m15_oos = m15

    trig_is, df_is = find_triggers(m1_is, m5_is or m5, m15_is or m15)
    trig_oos, df_oos = find_triggers(m1_oos, m5_oos, m15_oos)
    print(f"{symbol}: {len(m1)} M1 bars | IS triggers {len(trig_is)} | OOS triggers {len(trig_oos)}")

    # starting config (the backtest-proven wide-stop/tight-tp)
    cfg = {"sl_atr": 1.5, "tp_rr": 0.7, "macd_lead_bars": 5,
           "require_m5": False, "require_m15": False}

    results = []
    for rnd in range(1, rounds + 1):
        is_m = _metrics(trig_is, df_is, cfg)
        oos_m = _metrics(trig_oos, df_oos, cfg)
        base_oos = _score(oos_m)

        # try neighbours; keep the best OOS improvement that is also IS-profitable
        best = None
        for knob, cand in _candidates(cfg):
            cm_is = _metrics(trig_is, df_is, cand)
            cm_oos = _metrics(trig_oos, df_oos, cand)
            if cm_is and cm_is["profit_factor"] >= 1.0 and _score(cm_oos) > base_oos + 0.02:
                if best is None or _score(cm_oos) > best[3]:
                    best = (knob, cand, cm_oos, _score(cm_oos))

        change = "none (converged)"
        if best:
            knob, cand, cm_oos, sc = best
            change = f"{knob}: {cfg[knob]} -> {cand[knob]} (OOS PF {base_oos:.2f}->{sc:.2f})"
            cfg = cand

        rec = {
            "round": rnd, "config": copy.deepcopy(cfg),
            "in_sample": is_m, "out_of_sample": oos_m, "adjustment": change,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        results.append(rec)
        isf = f"IS PF {is_m['profit_factor'] if is_m else '-'} WR {is_m['win_rate'] if is_m else '-'}%"
        oosf = f"OOS PF {oos_m['profit_factor'] if oos_m else '-'} WR {oos_m['win_rate'] if oos_m else '-'}%"
        print(f"  round {rnd:2}: sl {cfg['sl_atr']} tp_rr {cfg['tp_rr']} lead {cfg['macd_lead_bars']} "
              f"m5 {int(cfg['require_m5'])} m15 {int(cfg['require_m15'])} | {isf} | {oosf} | {change}")
        if not best:
            print("  -> converged (no incremental change improves OOS)")
            break

    # persist
    try:
        from src import config
        p = os.path.join(config.DATA_DIR, "walkforward_results.json")
    except Exception:
        p = "walkforward_results.json"
    payload = {"symbol": symbol, "bars": len(m1), "rounds": results,
               "final_config": cfg, "run_at": datetime.now(timezone.utc).isoformat()}
    try:
        with open(p, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"\nResults written to {p}")
    except Exception as e:
        print(f"could not write results: {e}")

    if results:
        last = results[-1]
        print(f"\nFINAL: {last['config']}")
        print(f"  in-sample: {last['in_sample']}")
        print(f"  out-of-sample: {last['out_of_sample']}")
    return payload


if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSD"
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    bars = int(sys.argv[3]) if len(sys.argv) > 3 else 12000
    run(sym, rounds, bars)
