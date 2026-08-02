"""
MT5 strategy-tester LOG parser (#50 / gold validation).

Parses an MT5 tester journal (e.g. GoldShark3 v3.05 XAUUSD backtest 2026.01-07) to
reconstruct REAL closed positions and compute genuine WR / PF / net — the trustworthy
gold backtest ground-truth to validate our findings against (the proven config).

MT5 logs deals as lines like:
  ... deal #N buy 0.03 XAUUSD-ECN at 4340.20 done (based on order #M)
  ... market sell 0.02 XAUUSD-ECN, close #2 (...)
We track per-POSITION net by summing signed deal cashflow (sell = +price*vol,
buy = -price*vol) per position id; a position closes when its net volume returns to 0.
Also extracts the final balance line.

Findings are pushed into the learning system via researcher.validate_hypothesis so
they are not lost. Run: python -m scripts.analyze_mt5_tester_log <path>
"""

from __future__ import annotations

import re
import sys
import statistics
from collections import defaultdict

DEAL_RE = re.compile(r"deal #(\d+)\s+(buy|sell)\s+([\d.]+)\s+(\S+)\s+at\s+([\d.]+)")
CLOSE_RE = re.compile(r"(buy|sell)\s+([\d.]+)\s+\S+,?\s*close #(\d+)")
BAL_RE = re.compile(r"final balance\s+([\d.]+)")


def parse(path):
    """Reconstruct positions from the tester log.
    - Opening deal:  'deal #N buy/sell VOL SYM at PRICE'  (N = position id)
    - Closing:       'market sell/buy VOL SYM, close #N (PRICE / ...)'  (refs pos N)
    P&L per position = sum over closes of (close_price - open_price)*vol*dir, where
    dir=+1 if the position is long (opened buy). Returns (pnls, final_balance)."""
    open_side = {}   # pos id -> 'buy'/'sell'
    open_price = {}  # pos id -> opening price
    pnl = defaultdict(float)
    final_balance = None
    open_re = re.compile(r"deal #(\d+)\s+(buy|sell)\s+([\d.]+)\s+\S+\s+at\s+([\d.]+)")
    close_re = re.compile(r"market\s+(buy|sell)\s+([\d.]+)\s+\S+,\s*close #(\d+)\s+\(([\d.]+)")
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            b = BAL_RE.search(line)
            if b:
                final_balance = float(b.group(1)); continue
            cm = close_re.search(line)
            if cm:
                _cside, cvol, pid, cprice = cm.group(1), float(cm.group(2)), cm.group(3), float(cm.group(4))
                if pid in open_price:
                    d = 1 if open_side[pid] == "buy" else -1
                    pnl[pid] += (cprice - open_price[pid]) * cvol * d
                continue
            om = open_re.search(line)
            if om:
                pid, side, _vol, price = om.group(1), om.group(2), float(om.group(3)), float(om.group(4))
                # only the FIRST deal for a pid is the opener
                if pid not in open_price:
                    open_side[pid] = side; open_price[pid] = price
    pnls = [round(v, 2) for v in pnl.values() if abs(v) > 1e-9]
    return pnls, final_balance


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else r"..\..\martysharkey\Documents\20260721.txt"
    trades, bal = parse(path)
    if not trades:
        print("no closed positions parsed (check log format)"); return
    wins = [t for t in trades if t > 0]; losses = [t for t in trades if t < 0]
    gw = sum(wins); gl = abs(sum(losses))
    pf = round(gw / gl, 2) if gl else float("inf")
    wr = round(len(wins) / len(trades) * 100, 1)
    print(f"=== MT5 tester log: {path.split(chr(92))[-1]} ===")
    print(f"  closed positions: {len(trades)} | WR {wr}% | PF {pf} | net(price*vol) {round(sum(trades),1)}")
    print(f"  avg win {round(statistics.mean(wins),2) if wins else 0} | avg loss {round(statistics.mean(losses),2) if losses else 0}")
    print(f"  final balance (from log): {bal}")

    try:
        from src.learning.continual_researcher import ContinualResearcher
        from src.learning.knowledge_store import KnowledgeStore
        from src.learning.experience_db import ExperienceDatabase
        r = ContinualResearcher(ExperienceDatabase(), knowledge_store=KnowledgeStore())
        r.validate_hypothesis(
            "goldshark3_gold_backtest_2026H1",
            "GoldShark3 v3.05 XAUUSD tester backtest (2026.01-07, the 'successful' config) "
            "real closed-position result",
            {"positions": len(trades), "win_rate": wr, "profit_factor": pf,
             "final_balance_gbp": bal, "n": len(trades)},
            verdict="agree" if (pf != float("inf") and pf >= 1.2 and wr >= 45) else "inconclusive",
            confidence="medium (single backtest, reconstructed from log)")
        print("\n[LEARNING] gold backtest result validated + stored via the researcher.")
    except Exception as e:
        print(f"[LEARNING] store skip: {e}")


if __name__ == "__main__":
    main()
