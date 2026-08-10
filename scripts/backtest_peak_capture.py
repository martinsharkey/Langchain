"""
Peak-capture exit backtest (#43) on REAL GoldShark per-candle telemetry.

The telemetry proved: 100% of trades reached a positive peak but only ~33% of that
peak was captured. This replays each trade's candle-by-candle PeakProfit path under
different PEAK-CAPTURE TRAILING rules and measures the resulting capture ratio +
median realised points — so we can pick an exit rule that materially beats the
33% baseline, validated on real trades (not synthetic).

Trailing rule tested: once profit reaches `arm` points, exit if profit falls to
`give` fraction of the running peak (i.e. lock in `give` x peak). Also a hard wide
stop at `stop` points adverse. This mirrors what the live engine's giveback/trail
would do — so results transfer.

Run: python -m scripts.backtest_peak_capture
"""

from __future__ import annotations

import csv
import statistics
from collections import defaultdict

LOG = r"C:\Users\MartinSharkey\Documents\Langchain\MT5_OLD_EA's\Goldshark\BTCUSD_UnifiedLog.csv"


def _num(v):
    try:
        return float(v)
    except Exception:
        return None


def load_paths(path=LOG):
    """Return {trade_id: [profit_pts per candle, ORDERED by CandleNumber]}."""
    rows_by_trade = defaultdict(list)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            tid = row.get("TradeID")
            pr = _num(row.get("ProfitPts"))
            cn = _num(row.get("CandleNumber"))
            if tid and pr is not None:
                rows_by_trade[tid].append((cn if cn is not None else 0.0, pr))
    paths = {}
    for tid, seq in rows_by_trade.items():
        seq.sort(key=lambda x: x[0])   # NUMERIC candle order (was string -> scrambled)
        paths[tid] = [p for _, p in seq]
    return paths


def simulate_exit(path, arm, give, stop):
    """Replay one trade's profit path under a peak-capture trailing rule.
    Returns realised points."""
    peak = 0.0
    armed = False
    for p in path:
        # hard wide stop
        if p <= -abs(stop):
            return -abs(stop)
        peak = max(peak, p)
        if peak >= arm:
            armed = True
        if armed and peak > 0 and p <= give * peak:
            return p  # trailed out, locking in ~give*peak
    return path[-1] if path else 0.0


def main():
    try:
        paths = load_paths()
    except FileNotFoundError:
        print("GoldShark telemetry not found on this machine.")
        return
    peaks = [max(p) for p in paths.values() if p]
    actual_exit = [p[-1] for p in paths.values() if p]
    base_cap = statistics.median([e / mx for p in paths.values() if p and (mx := max(p)) > 50
                                  for e in [p[-1]]])
    print(f"trades: {len(paths)} | median peak {statistics.median(peaks):.0f} | "
          f"median ACTUAL exit {statistics.median(actual_exit):.0f} | baseline capture {base_cap*100:.0f}%")
    print(f"\n{'arm':>8} {'give':>5} {'stop':>8} {'med_realised':>13} {'capture%':>9} {'win%':>6}")
    best = None
    for arm in (2000, 5000, 10000):
        for give in (0.5, 0.6, 0.7):
            for stop in (5000, 8000, 12000):
                res = [simulate_exit(p, arm, give, stop) for p in paths.values() if p]
                med = statistics.median(res)
                caps = [r / mx for p in paths.values() if p and (mx := max(p)) > 50
                        for r in [simulate_exit(p, arm, give, stop)]]
                cap = statistics.median(caps) if caps else 0
                win = sum(1 for r in res if r > 0) / len(res) * 100
                print(f"{arm:>8} {give:>5} {stop:>8} {med:>13.0f} {cap*100:>8.0f}% {win:>5.0f}%")
                if best is None or med > best[1]:
                    best = ((arm, give, stop), med, cap, win)
    if best:
        (a, g, s), med, cap, win = best
        print(f"\nBEST: arm {a}, give {g}, stop {s} -> median realised {med:.0f} pts "
              f"(capture {cap*100:.0f}% vs {base_cap*100:.0f}% baseline), win {win:.0f}%")


if __name__ == "__main__":
    main()
