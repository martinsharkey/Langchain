"""
Floor sweep — find the OsMA/Bulls/Bears strength floors that reach a target win-rate
per symbol while STILL trading enough (for runners + compounding).

Design to owner spec (2026-08-13):
  * Sweep OsMA, Bulls, Bears floors INDEPENDENTLY and ASYMMETRICALLY (long floors are
    NOT the mirror of short floors — GoldShark gold showed long osma~1.8/bulls>2/
    bears>1 but short osma~-1.0/bears~-1.8/bulls~-0.5).
  * Fine increments (default 0.01 in the symbol's native units for BTC-scale is coarse,
    so increments are configurable per symbol).
  * Honours the LIVE alignment gate (osma_confluence_signal) so results == live rule.
  * Reports win-rate, trades/day, PF and flags the combos that reach >= target WR
    while keeping trades/day above a frequency floor (so we can still compound).

This is a RESEARCH tool (read-only) — it does not change live config. Winning combos
are printed for review; applying them is a separate, deliberate step.

Usage:
  python tools/floor_sweep.py XAUUSD-ECN long
  python tools/floor_sweep.py BTCUSD short
"""
import os, sys, itertools
sys.path.insert(0, os.getcwd())
os.environ.setdefault("USE_SAFE_EMBEDDER", "1")
os.environ.setdefault("FORCE_LOCAL_VECTOR_STORE", "1")

from src.mt5.connector import get_connector
from src.learning.strategy_registry import StrategyRegistry
from src.learning.backtester import Backtester
from src.learning.param_optimizer import DEFAULTS

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD-ECN"
SIDE = sys.argv[2] if len(sys.argv) > 2 else "long"
TARGET_WR = float(os.getenv("TARGET_WR", "70"))
TIMEFRAME = os.getenv("SWEEP_TF", "M1")
BARS = int(os.getenv("SWEEP_BARS", "12000"))
MIN_TRADES_PER_DAY = float(os.getenv("MIN_TPD", "3"))   # frequency floor for compounding

# Per-symbol sweep grids (native units). Long floors positive, short floors negative.
# Fine 0.01-scale for gold; BTC needs coarser steps over a wider range (magnitudes ~15x).
GRIDS = {
    "XAUUSD-ECN": {
        "long":  {"osma": [round(x*0.1,2) for x in range(0, 30)],      # 0.0..2.9
                  "bulls":[round(x*0.5,2) for x in range(0, 12)],      # 0.0..5.5
                  "bears":[round(x*0.5,2) for x in range(0, 8)]},      # 0.0..3.5
        "short": {"osma": [round(-x*0.1,2) for x in range(0, 30)],
                  "bulls":[round(-x*0.5,2) for x in range(0, 12)],
                  "bears":[round(-x*0.5,2) for x in range(0, 8)]},
    },
    "BTCUSD": {
        "long":  {"osma": [round(x*1.0,1) for x in range(0, 20)],      # 0..19
                  "bulls":[round(x*5.0,1) for x in range(0, 16)],      # 0..75
                  "bears":[round(x*5.0,1) for x in range(0, 12)]},     # 0..55
        "short": {"osma": [round(-x*1.0,1) for x in range(0, 20)],
                  "bulls":[round(-x*5.0,1) for x in range(0, 16)],
                  "bears":[round(-x*5.0,1) for x in range(0, 12)]},
    },
}


def run():
    conn = get_connector(); conn.initialize()
    bt = Backtester(StrategyRegistry())
    grid = GRIDS.get(SYMBOL, GRIDS["XAUUSD-ECN"])[SIDE]
    okey = "osma_min_long" if SIDE == "long" else "osma_max_short"
    bkey = "bulls_min_long" if SIDE == "long" else "bulls_max_short"
    rkey = "bears_min_long" if SIDE == "long" else "bears_max_short"

    print(f"=== FLOOR SWEEP {SYMBOL} {SIDE.upper()} tf={TIMEFRAME} bars={BARS} "
          f"target_WR>={TARGET_WR}% min_trades/day>={MIN_TRADES_PER_DAY} ===")
    print(f"grid sizes: osma={len(grid['osma'])} bulls={len(grid['bulls'])} bears={len(grid['bears'])} "
          f"= {len(grid['osma'])*len(grid['bulls'])*len(grid['bears'])} combos\n")

    winners = []
    best_any = None
    combos = list(itertools.product(grid["osma"], grid["bulls"], grid["bears"]))
    for n_done, (o, b, r) in enumerate(combos):
        p = dict(DEFAULTS)
        p.update({"symbol": SYMBOL, okey: o, bkey: b, rkey: r,
                  "min_confluence": 3, "sl_atr": 1.0, "tp_rr": 2.0})
        try:
            res = bt.walkforward_focused(SYMBOL, p, sl_atr=1.0, tp_rr=2.0,
                                         timeframe=TIMEFRAME, bars=BARS)
        except Exception:
            continue
        if not res or not res.get("n_total"):
            continue
        wrs = res.get("wrs") or []
        wr = sum(wrs) / len(wrs) if wrs else 0
        tpd = res.get("trades_per_day", 0) or 0
        pf = res.get("score", 0)
        gen = res.get("generalizes")
        rec = {"osma": o, "bulls": b, "bears": r, "wr": round(wr, 1),
               "tpd": tpd, "pf": pf, "n": res["n_total"], "gen": gen}
        if best_any is None or wr > best_any["wr"]:
            best_any = rec
        if wr >= TARGET_WR and tpd >= MIN_TRADES_PER_DAY:
            winners.append(rec)
            print(f"  HIT osma={o} bulls={b} bears={r} -> WR={wr:.1f}% "
                  f"trades/day={tpd} PF={pf} n={res['n_total']} gen={gen}")

    print(f"\n--- swept {len(combos)} combos ---")
    if winners:
        # prefer highest WR, then highest trades/day (compounding), then PF
        winners.sort(key=lambda x: (-x["wr"], -x["tpd"], -(x["pf"] or 0)))
        print(f"TOP combos reaching >={TARGET_WR}% WR with trades/day>={MIN_TRADES_PER_DAY}:")
        for w in winners[:10]:
            print(f"  osma={w['osma']} bulls={w['bulls']} bears={w['bears']} | "
                  f"WR={w['wr']}% trades/day={w['tpd']} PF={w['pf']} n={w['n']} gen={w['gen']}")
    else:
        print(f"No combo reached {TARGET_WR}% WR at >={MIN_TRADES_PER_DAY} trades/day.")
        if best_any:
            print(f"Best WR seen: osma={best_any['osma']} bulls={best_any['bulls']} "
                  f"bears={best_any['bears']} -> WR={best_any['wr']}% trades/day={best_any['tpd']} "
                  f"PF={best_any['pf']} (raise target reachable? or frequency too low)")
    conn.shutdown()


if __name__ == "__main__":
    run()
