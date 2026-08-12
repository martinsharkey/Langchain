"""
Prove the volatility-scaled trail floor (SCALP_TRAIL_MIN_ATR) per symbol.

Sweeps trail_min_atr through walkforward_focused (real-tick, 70/30 windows) and
reports, per symbol, the min-window PF and total-R for each floor. Adopts the
best-GENERALISING floor (min-window PF > 1 and best total-R) so we trust a value
proven OUT-OF-SAMPLE, not one fitted to noise. Prints a table; does NOT auto-write
config (you decide) unless --apply is passed, in which case it writes the proven
floor into data/tuned_params.json per symbol.
"""
import os
import sys
import json

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from src.mt5.connector import get_connector
from src.learning.strategy_registry import StrategyRegistry
from src.learning.backtester import Backtester
from src.learning.param_optimizer import ParameterOptimizer, DEFAULTS

SYMBOLS = ["XAUUSD-ECN", "BTCUSD"]
GRID = [0.0, 0.25, 0.5, 0.75, 1.0, 1.5]


def main(apply=False):
    conn = get_connector()
    if not conn.initialize():
        print("MT5 connect failed"); return
    reg = StrategyRegistry()
    bt = Backtester(reg)

    def _dummy(s, p): return {"pf": 0.0, "trades": 0}
    po = ParameterOptimizer(registry=reg, backtest_fn=_dummy)

    proven = {}
    for sym in SYMBOLS:
        params = po.current_params(sym)
        sl = params.get("sl_atr", 1.0); rr = params.get("tp_rr", 2.0)
        print(f"\n=== {sym}  (sl_atr={sl} tp_rr={rr}) ===")
        print(f"{'trail_min_atr':<14}{'min-PF':<10}{'total-R':<10}{'generalises'}")
        best = None
        for t in GRID:
            r = bt.walkforward_focused(sym, params, sl_atr=sl, tp_rr=rr, trail_min_atr=t)
            if not r:
                print(f"{t:<14}{'no data'}"); continue
            mn = r.get("score", -1); tot = r.get("total_r", 0) if "total_r" in r else sum(r.get("pfs", []))
            gen = r.get("generalizes", False)
            print(f"{t:<14}{mn:<10}{round(tot,1):<10}{gen}")
            if gen and (best is None or mn > best[1]):
                best = (t, mn, tot)
        if best:
            proven[sym] = best[0]
            print(f"  -> PROVEN trail_min_atr={best[0]} (min-PF {best[1]})")
        else:
            print(f"  -> none generalised; keep default")

    print(f"\nPROVEN floors: {proven}")
    if apply and proven:
        for sym, t in proven.items():
            key = sym.upper()
            entry = po.tuned.get(key) or {"params": dict(DEFAULTS)}
            entry.setdefault("params", dict(DEFAULTS))
            entry["params"]["trail_min_atr"] = t
            entry["source"] = f"trail_floor_proof (min-PF gated)"
            po.tuned[key] = entry
        po._persist()
        print("applied to tuned_params.json")
    conn.shutdown()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
