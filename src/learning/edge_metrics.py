"""
EdgeMetrics — objective, measurable proof-of-edge from REAL closed trades.

Computes the KPIs that define success (per STRATEGY_OBJECTIVE.md): profit factor,
expectancy in R, win rate, max drawdown, longest losing streak — and evaluates
which PHASE gate the system currently satisfies. This is the honest scoreboard
for "is there a real edge yet?" and it GATES position sizing / compounding so the
system can never escalate risk past what the proven edge justifies.
"""

from __future__ import annotations

import os
import sqlite3
import statistics
from dataclasses import dataclass, asdict

from src import config
from src.utils.logger import get_logger

logger = get_logger("edge_metrics")


@dataclass
class Edge:
    closed_trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    gross_win: float
    gross_loss: float
    profit_factor: float
    net_pnl: float
    avg_win: float
    avg_loss: float
    expectancy: float          # avg P&L per trade (currency)
    expectancy_r: float        # avg P&L / avg risk (R units)
    max_drawdown_pct: float
    longest_loss_streak: int
    phase: int
    phase_name: str
    gate_progress: dict        # each Phase-1 gate condition -> (value, target, ok)


# Phase-1 gate thresholds (the definition of a proven edge)
GATE_MIN_TRADES = int(os.getenv("EDGE_MIN_TRADES", "200"))
GATE_MIN_PF = float(os.getenv("EDGE_MIN_PF", "1.3"))
GATE_MAX_DD = float(os.getenv("EDGE_MAX_DD_PCT", "20"))


class EdgeCalculator:
    def __init__(self, experience_db):
        self.experience_db = experience_db

    def compute(self) -> Edge:
        conn = sqlite3.connect(self.experience_db.db_path)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            "SELECT outcome, profit_loss FROM trades "
            "WHERE outcome IN ('win','loss','breakeven') ORDER BY id ASC"
        ).fetchall()]
        conn.close()

        n = len(rows)
        wins = [r["profit_loss"] for r in rows if r["outcome"] == "win"]
        losses = [r["profit_loss"] for r in rows if r["outcome"] == "loss"]
        be = sum(1 for r in rows if r["outcome"] == "breakeven")
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        net = gross_win - gross_loss
        win_rate = round(len(wins) / n * 100, 1) if n else 0.0
        avg_win = round(statistics.mean(wins), 4) if wins else 0.0
        avg_loss = round(abs(statistics.mean(losses)), 4) if losses else 0.0
        pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else (gross_win or 0.0)
        expectancy = round(net / n, 4) if n else 0.0
        # expectancy in R: avg P&L / avg risk (use avg_loss as the risk unit proxy)
        risk_unit = avg_loss if avg_loss > 0 else 1.0
        expectancy_r = round(expectancy / risk_unit, 3)

        # equity curve + max drawdown (as % of peak) on cumulative P&L
        cum = 0.0; peak = 0.0; max_dd = 0.0
        streak = 0; longest_streak = 0
        for r in rows:
            cum += r["profit_loss"] or 0
            peak = max(peak, cum)
            # Only measure drawdown once equity has a meaningful positive peak,
            # otherwise a near-zero early peak produces absurd % values.
            if peak >= 1.0:
                dd = (peak - cum) / peak * 100
                max_dd = min(max(max_dd, dd), 100.0)
            if r["outcome"] == "loss":
                streak += 1; longest_streak = max(longest_streak, streak)
            elif r["outcome"] == "win":
                streak = 0

        # phase determination
        gate = {
            "trades": {"value": n, "target": GATE_MIN_TRADES, "ok": n >= GATE_MIN_TRADES},
            "profit_factor": {"value": pf, "target": GATE_MIN_PF, "ok": pf >= GATE_MIN_PF},
            "expectancy_positive": {"value": expectancy, "target": 0, "ok": expectancy > 0},
            "max_drawdown": {"value": round(max_dd, 1), "target": GATE_MAX_DD, "ok": max_dd < GATE_MAX_DD},
        }
        phase1_pass = all(g["ok"] for g in gate.values())
        if n < 20:
            phase, name = 0, "Phase 0/1 — gathering sample"
        elif phase1_pass:
            phase, name = 2, "Phase 2 — edge proven, stabilising"
        else:
            phase, name = 1, "Phase 1 — proving edge"

        return Edge(
            closed_trades=n, wins=len(wins), losses=len(losses), breakeven=be,
            win_rate=win_rate, gross_win=round(gross_win, 2), gross_loss=round(gross_loss, 2),
            profit_factor=pf, net_pnl=round(net, 2), avg_win=avg_win, avg_loss=avg_loss,
            expectancy=expectancy, expectancy_r=expectancy_r,
            max_drawdown_pct=round(max_dd, 1), longest_loss_streak=longest_streak,
            phase=phase, phase_name=name, gate_progress=gate,
        )

    def status(self) -> dict:
        try:
            return asdict(self.compute())
        except Exception as e:
            logger.warning(f"edge compute failed: {e}")
            return {}
