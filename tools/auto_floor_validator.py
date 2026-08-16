"""
Auto-escalating floor validator (owner method 2026-08-13).

The principle the owner has taught: RAISING indicator floors increases entry
quality/success. So instead of a fixed min-trade gate on a 2.8-day window, this
validator:

  1. Backtests over a MULTI-WEEK period (>= 1 week; default ~5-7 weeks of M1).
  2. Starts at the per-symbol baseline floors (alignment_floors) and, if win rate is
     below the target (default 70%), AUTO-ESCALATES the floors — longs UP in +step,
     shorts DOWN in -step — re-testing each level until win rate >= target OR the
     entries dry up (fewer than a small floor of trades over the WHOLE period).
  3. Reports, per level: floors, trades, trades/week, win rate, PF, total R.

There is NO per-window minimum-trade requirement. A high-quality, low-frequency
strategy (e.g. 15 trades/week at >70%) is a VALID result — the whole point.

Uses the be_trail exit model (wide SL + BE + trail, no TP), matching live.

Usage:
  python tools/auto_floor_validator.py XAUUSD-ECN
  python tools/auto_floor_validator.py BTCUSD
"""
import os, sys
sys.path.insert(0, os.getcwd())
os.environ.setdefault("USE_SAFE_EMBEDDER", "1")
os.environ.setdefault("FORCE_LOCAL_VECTOR_STORE", "1")

from src.mt5.connector import get_connector
import MetaTrader5 as mt5
import pandas as pd
from src.strategies.confluence_signal import find_confluence_triggers
from src.learning.param_optimizer import DEFAULTS
from src.strategies.alignment_floors import baseline
from src.learning.golden_baseline import golden

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD-ECN"
TARGET_WR = float(os.getenv("TARGET_WR", "70"))
BARS = int(os.getenv("VALIDATE_BARS", "50000"))          # ~5-7 weeks of M1
MIN_TOTAL = int(os.getenv("MIN_TOTAL_TRADES", "8"))       # tiny floor: below this the sample is too small to trust
MAX_STEPS = int(os.getenv("MAX_ESCALATE_STEPS", "25"))

# escalation step per indicator (native units): fine for gold, coarser for BTC
STEP = {"XAUUSD-ECN": {"osma": 0.05, "bulls": 0.25, "bears": 0.10},
        "XAUUSD":     {"osma": 0.05, "bulls": 0.25, "bears": 0.10},
        "BTCUSD":     {"osma": 0.5,  "bulls": 2.5,  "bears": 0.5}}
# per-symbol exit geometry (points) — BTC scaled ~15x gold
EXIT = {"XAUUSD-ECN": (500, 150, 150), "XAUUSD": (500, 150, 150),
        "BTCUSD": (8000, 800, 1000)}


def simulate(trig, hi, lo, cl, pt, sl_pts, be_pts, tr_pts):
    SL, BE, TR = sl_pts*pt, be_pts*pt, tr_pts*pt
    N = len(cl); w = l = 0; netR = 0.0; gw = gl = 0.0
    for t in trig:
        i = t["i"]; d = t.get("direction") or t.get("dir"); e = t["entry"]
        sl = (e-SL) if d == "buy" else (e+SL); best = e; be = False; R = None
        for k in range(i+1, min(i+1000, N)):
            if d == "buy":
                if lo[k] <= sl: R = (sl-e)/SL; break
                best = max(best, hi[k])
                if not be and (best-e) >= BE: sl = max(sl, e+2*pt); be = True
                if be: sl = max(sl, best-TR)
            else:
                if hi[k] >= sl: R = (e-sl)/SL; break
                best = min(best, lo[k])
                if not be and (e-best) >= BE: sl = min(sl, e-2*pt); be = True
                if be: sl = min(sl, best+TR)
        if R is None:
            last = cl[min(i+1000, N-1)]
            R = ((last-e) if d == "buy" else (e-last))/SL
        netR += R
        if R > 0: w += 1; gw += R
        else: l += 1; gl += abs(R)
    n = w+l
    pf = (gw/gl) if gl > 0 else (gw if gw else 0)
    return n, (w/n*100 if n else 0), round(pf, 2), round(netR, 1)


def run():
    conn = get_connector(); conn.initialize()
    tf = {"M1": mt5.TIMEFRAME_M1}["M1"]
    df = pd.DataFrame(mt5.copy_rates_from_pos(SYMBOL, tf, 0, BARS)).rename(columns={"tick_volume": "volume"})
    m5 = pd.DataFrame(mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, BARS//5+50)).rename(columns={"tick_volume": "volume"})
    m15 = pd.DataFrame(mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, BARS//15+50)).rename(columns={"tick_volume": "volume"})
    weeks = (df["time"].iloc[-1]-df["time"].iloc[0])/86400.0/7
    hi = df["high"].values; lo = df["low"].values; cl = df["close"].values
    pt = mt5.symbol_info(SYMBOL).point or 0.01
    sl_pts, be_pts, tr_pts = EXIT.get(SYMBOL, (500, 150, 150))
    step = STEP.get(SYMBOL, STEP["XAUUSD-ECN"])

    b = baseline(SYMBOL)
    fl = {"osma_min_long": b["long"]["osma_min"], "bulls_min_long": b["long"]["bulls_min"],
          "bears_min_long": b["long"]["bears_min"], "osma_max_short": b["short"]["osma_max"],
          "bears_max_short": b["short"]["bears_max"], "bulls_max_short": b["short"]["bulls_max"]}

    print(f"=== AUTO-FLOOR VALIDATOR {SYMBOL} over {weeks:.1f} weeks, target WR>={TARGET_WR}% ===")
    print(f"exit: SL={sl_pts} BE={be_pts} trail={tr_pts} pts | escalate step {step}\n")
    print(f"{'lvl':>3}{'osmaL':>7}{'bullsL':>7}{'bearsL':>7}{'n':>5}{'t/wk':>6}{'WR%':>7}{'PF':>6}{'netR':>7}")
    best = None
    for lvl in range(MAX_STEPS):
        p = dict(DEFAULTS); p["symbol"] = SYMBOL; p["min_confluence"] = 3; p.update(fl)
        trig, _ = find_confluence_triggers(df, m5, m15, p)
        n, wr, pf, netR = simulate(trig, hi, lo, cl, pt, sl_pts, be_pts, tr_pts)
        twk = n/weeks if weeks else 0
        print(f"{lvl:>3}{fl['osma_min_long']:>7.2f}{fl['bulls_min_long']:>7.2f}{fl['bears_min_long']:>7.2f}"
              f"{n:>5}{twk:>6.1f}{wr:>7.1f}{pf:>6}{netR:>7}")
        if n < MIN_TOTAL:
            print(f"    -> entries dried up (<{MIN_TOTAL} over {weeks:.0f} wks); stop escalating.")
            break
        if wr >= TARGET_WR and pf >= 1.0:
            best = dict(fl); best.update({"n": n, "wr": wr, "pf": pf, "netR": netR, "twk": round(twk, 1)})
            print(f"    -> TARGET MET: WR {wr:.1f}% PF {pf} at {twk:.1f} trades/week")
            break
        # escalate: longs UP, shorts DOWN (stricter both sides)
        fl["osma_min_long"] = round(fl["osma_min_long"] + step["osma"], 2)
        fl["bulls_min_long"] = round(fl["bulls_min_long"] + step["bulls"], 2)
        fl["bears_min_long"] = round(fl["bears_min_long"] + step["bears"], 2)
        fl["osma_max_short"] = round(fl["osma_max_short"] - step["osma"], 2)
        fl["bears_max_short"] = round(fl["bears_max_short"] - step["bulls"], 2)
        fl["bulls_max_short"] = round(fl["bulls_max_short"] - step["bears"], 2)
    if best:
        print(f"\nHIGH-QUALITY FLOORS FOUND: osma_long={best['osma_min_long']} bulls_long={best['bulls_min_long']} "
              f"bears_long={best['bears_min_long']} | WR={best['wr']:.1f}% PF={best['pf']} {best['twk']}/wk")
    else:
        print(f"\nNo level reached {TARGET_WR}% before entries dried up — see table for best WR achieved.")
    conn.shutdown()


if __name__ == "__main__":
    run()
