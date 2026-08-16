"""
Exit sweep — DATA-DRIVEN discovery of the wide-SL / break-even / trailing-stop
values that let runners run while avoiding stop-outs (owner exit design, NO TP).

Models the EXACT live exit rules (unlike the giveback backtester):
  * WIDE broker-side SL (points), no take-profit.
  * Move to BREAK-EVEN once profit >= be_trigger_pts (clear of wick noise).
  * Once past BE, TRAIL the stop trail_pts behind the best price (runner room).
  * Tick-accurate intrabar sequencing when ticks are available.

Sweeps sl_pts x be_trigger_pts x trail_pts per symbol on the confluence entries
(so the strict alignment gate is honoured) and reports, per combo: net R, win%,
avg win R vs avg loss R, trades, and the max single-run R captured (runner proof).
Objective = net EXPECTANCY (R), because a runner strategy wins on R-multiple, not
hit-rate. Read-only research tool; winning combos are printed for review.

Usage: python tools/exit_sweep.py XAUUSD-ECN   [BTCUSD]
"""
import os, sys, itertools
sys.path.insert(0, os.getcwd())
os.environ.setdefault("USE_SAFE_EMBEDDER", "1")
os.environ.setdefault("FORCE_LOCAL_VECTOR_STORE", "1")

from src.mt5.connector import get_connector
import MetaTrader5 as mt5
from src.strategies.confluence_signal import find_confluence_triggers
from src.mt5.data import get_ticks
from src.learning.param_optimizer import DEFAULTS
import pandas as pd

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD-ECN"
TF = os.getenv("EXIT_TF", "M1")
BARS = int(os.getenv("EXIT_BARS", "8000"))

# per-symbol sweep grids in POINTS (gold ~0.01/pt; BTC pt=0.01 too but moves are huge)
GRIDS = {
    "XAUUSD-ECN": {"sl": [300, 400, 500], "be": [80, 120, 160, 220], "trail": [150, 200, 250, 300, 400]},
    "XAUUSD":     {"sl": [300, 400, 500], "be": [80, 120, 160, 220], "trail": [150, 200, 250, 300, 400]},
    "BTCUSD":     {"sl": [3000, 5000, 8000], "be": [1000, 2000, 3500], "trail": [1500, 2500, 4000, 6000]},
}


def simulate(triggers, bars_df, ticks_by_i, pt, sl_pts, be_pts, trail_pts):
    """Run the wide-SL/BE/trail exit model over the confluence entries.
    Returns (n, wins, net_R, avg_win_R, avg_loss_R, max_run_R)."""
    n = wins = 0
    net_R = 0.0; win_Rs = []; loss_Rs = []; max_run = 0.0
    highs = bars_df["high"].values; lows = bars_df["low"].values; closes = bars_df["close"].values
    N = len(closes)
    for t in triggers:
        i = t["i"]; d = t["dir"]; entry = t["entry"]
        risk = sl_pts * pt
        if d == "buy":
            sl = entry - risk; best = entry; be_done = False
        else:
            sl = entry + risk; best = entry; be_done = False
        realised = None
        for k in range(i + 1, min(i + 600, N)):     # ride up to 600 bars
            hi = highs[k]; lo = lows[k]
            if d == "buy":
                # stop check first (intrabar low)
                if lo <= sl:
                    realised = (sl - entry) / risk; break
                best = max(best, hi)
                prof_pts = (best - entry) / pt
                if not be_done and prof_pts >= be_pts:
                    sl = max(sl, entry + 2 * pt); be_done = True     # BE+ tiny buffer
                if be_done:
                    sl = max(sl, best - trail_pts * pt)              # trail behind runner
            else:
                if hi >= sl:
                    realised = (entry - sl) / risk; break
                best = min(best, lo)
                prof_pts = (entry - best) / pt
                if not be_done and prof_pts >= be_pts:
                    sl = min(sl, entry - 2 * pt); be_done = True
                if be_done:
                    sl = min(sl, best + trail_pts * pt)
        if realised is None:
            # close at last bar
            last = closes[min(i + 600, N - 1)]
            realised = ((last - entry) if d == "buy" else (entry - last)) / risk
        n += 1; net_R += realised
        run_R = ((best - entry) if d == "buy" else (entry - best)) / risk
        max_run = max(max_run, run_R)
        if realised > 0: wins += 1; win_Rs.append(realised)
        else: loss_Rs.append(realised)
    avg_w = sum(win_Rs) / len(win_Rs) if win_Rs else 0
    avg_l = sum(loss_Rs) / len(loss_Rs) if loss_Rs else 0
    return n, wins, net_R, avg_w, avg_l, max_run


def run():
    conn = get_connector(); conn.initialize()
    tfmap = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15}
    bars = mt5.copy_rates_from_pos(SYMBOL, tfmap[TF], 0, BARS)
    df = pd.DataFrame(bars).rename(columns={"tick_volume": "volume"})
    pt = mt5.symbol_info(SYMBOL).point or 0.01
    cfg = dict(DEFAULTS); cfg["symbol"] = SYMBOL
    # need m5/m15 for HTF context in find_confluence_triggers
    m5 = pd.DataFrame(mt5.copy_rates_from_pos(SYMBOL, tfmap["M5"], 0, BARS//5+50)).rename(columns={"tick_volume":"volume"})
    m15 = pd.DataFrame(mt5.copy_rates_from_pos(SYMBOL, tfmap["M15"], 0, BARS//15+50)).rename(columns={"tick_volume":"volume"})
    triggers, _ = find_confluence_triggers(df, m5, m15, cfg)
    print(f"=== EXIT SWEEP {SYMBOL} {TF} bars={BARS} — {len(triggers)} confluence entries (strict-aligned) ===")
    if not triggers:
        print("No entries under the strict alignment gate — floors may be too high for this window.")
        conn.shutdown(); return
    g = GRIDS.get(SYMBOL, GRIDS["XAUUSD-ECN"])
    results = []
    for sl_pts, be_pts, trail_pts in itertools.product(g["sl"], g["be"], g["trail"]):
        n, wins, net_R, aw, al, mx = simulate(triggers, df, None, pt, sl_pts, be_pts, trail_pts)
        if n < 20: continue
        exp = net_R / n
        results.append({"sl": sl_pts, "be": be_pts, "trail": trail_pts, "n": n,
                        "wr": round(wins/n*100,1), "exp_R": round(exp,3), "net_R": round(net_R,1),
                        "avgW": round(aw,2), "avgL": round(al,2), "maxRun": round(mx,1)})
    results.sort(key=lambda x: -x["exp_R"])
    print(f"{'sl':>5}{'be':>5}{'trail':>7}{'n':>5}{'WR%':>7}{'expR':>7}{'netR':>7}{'avgW':>6}{'avgL':>6}{'maxRun':>7}")
    for r in results[:12]:
        print(f"{r['sl']:>5}{r['be']:>5}{r['trail']:>7}{r['n']:>5}{r['wr']:>7}{r['exp_R']:>7}{r['net_R']:>7}{r['avgW']:>6}{r['avgL']:>6}{r['maxRun']:>7}")
    if results:
        b = results[0]
        print(f"\nBEST expectancy: SL={b['sl']} BE={b['be']} TRAIL={b['trail']} -> "
              f"expR={b['exp_R']} WR={b['wr']}% avgWin={b['avgW']}R maxRunner={b['maxRun']}R over {b['n']} trades")
    conn.shutdown()


if __name__ == "__main__":
    run()
