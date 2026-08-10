"""
SymbolGovernor — the learning-loop component that decides which symbols the bot
should keep trading, pause, or mark FAILED, and RECORDS WHY.

Design principle (trader's directive):
  * If a symbol never improves over a window of trades, pause it and REPORT the
    failure (which strategies failed, the stats) so we learn from it.
  * BUT never block everything — a symbol with an acceptable success rate keeps
    trading, so the bot always has something to learn from.

This is intentionally a PURE decision function over recent-trade stats so it can
be unit-tested deterministically (no DB/MT5 needed in tests). The engine feeds it
recent stats; it returns a decision + optional failure report which the learning
loop persists to the knowledge base.
"""

from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src import config
from src.utils.logger import get_logger

logger = get_logger("symbol_governor")

STATUS_PATH = os.path.join(config.DATA_DIR, "symbol_status.json")

ACTIVE = "active"
PAUSED = "paused"
FAILED = "failed"


@dataclass
class SymbolStats:
    symbol: str
    n: int                       # recent closed trades in window
    win_rate: float              # %
    pnl: float                   # recent net P&L
    per_strategy: dict = field(default_factory=dict)  # strategy -> {n,wins,pnl}


@dataclass
class Decision:
    symbol: str
    status: str                  # active | paused | failed
    reason: str
    report: Optional[dict] = None


def decide(stats: SymbolStats,
           window: int = None,
           min_trades: int = None,
           healthy_wr: float = None,
           catastrophic_wr: float = None,
           bleed_pnl: float = None) -> Decision:
    """
    Pure decision. Thresholds default to config but are overridable for testing.

      * Not enough sample            -> ACTIVE (keep gathering).
      * Healthy win rate (>=healthy) -> ACTIVE (never block a working symbol —
                                        this is what stops us blocking everything).
      * Catastrophic WR (<catastrophic) OR bleeding P&L (<=bleed) -> PAUSED/FAILED
        with a report of the worst strategies.
    """
    window = window if window is not None else config.SYMBOL_PAUSE_WINDOW
    min_trades = min_trades if min_trades is not None else config.SYMBOL_PAUSE_MIN_TRADES
    healthy_wr = healthy_wr if healthy_wr is not None else config.SYMBOL_PAUSE_HEALTHY_WR
    catastrophic_wr = catastrophic_wr if catastrophic_wr is not None else config.SYMBOL_PAUSE_WINRATE
    bleed_pnl = bleed_pnl if bleed_pnl is not None else config.SYMBOL_PAUSE_PNL

    if stats.n < min_trades:
        return Decision(stats.symbol, ACTIVE, f"insufficient sample ({stats.n}/{min_trades})")

    # Never block a symbol that is actually working — guarantees we keep learning.
    if stats.win_rate >= healthy_wr:
        return Decision(stats.symbol, ACTIVE,
                        f"healthy win rate {stats.win_rate:.0f}% (>= {healthy_wr})")

    catastrophic = stats.win_rate < catastrophic_wr
    bleeding = stats.pnl <= bleed_pnl
    if catastrophic or bleeding:
        # FAILED (harder) if BOTH bad; PAUSED if only one. Both stop new entries.
        status = FAILED if (catastrophic and bleeding) else PAUSED
        worst = sorted(
            [(k, v) for k, v in (stats.per_strategy or {}).items()],
            key=lambda kv: kv[1].get("pnl", 0))[:3]
        report = {
            "symbol": stats.symbol,
            "status": status,
            "recent_trades": stats.n,
            "win_rate": round(stats.win_rate, 1),
            "recent_pnl": round(stats.pnl, 2),
            "trigger": ("catastrophic_winrate+bleeding" if (catastrophic and bleeding)
                        else "catastrophic_winrate" if catastrophic else "bleeding_pnl"),
            "worst_strategies": [{"strategy": k, **v} for k, v in worst],
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        reason = (f"{status}: WR {stats.win_rate:.0f}% pnl {stats.pnl:.2f} "
                  f"({report['trigger']})")
        return Decision(stats.symbol, status, reason, report)

    return Decision(stats.symbol, ACTIVE, f"acceptable (WR {stats.win_rate:.0f}%, pnl {stats.pnl:.2f})")


class SymbolGovernor:
    """Stateful wrapper: persists status + failure reports; feeds knowledge base."""

    def __init__(self, knowledge_base=None):
        self.kb = knowledge_base
        self.status: dict = {}
        self._load()

    def _load(self):
        try:
            if os.path.exists(STATUS_PATH):
                with open(STATUS_PATH) as f:
                    self.status = json.load(f)
        except Exception:
            self.status = {}

    def _persist(self):
        try:
            os.makedirs(config.DATA_DIR, exist_ok=True)
            tmp = STATUS_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.status, f, indent=2, default=str)
            os.replace(tmp, STATUS_PATH)
        except Exception as e:
            logger.warning(f"symbol status persist failed: {e}")

    def evaluate(self, stats: SymbolStats) -> Decision:
        d = decide(stats)
        prev = (self.status.get(stats.symbol) or {}).get("status")
        self.status[stats.symbol] = {
            "status": d.status, "reason": d.reason,
            "win_rate": stats.win_rate, "pnl": round(stats.pnl, 2), "n": stats.n,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "report": d.report,
        }
        self._persist()
        # Report the failure to the knowledge base ONCE on transition into paused/failed
        if d.status in (PAUSED, FAILED) and prev != d.status and d.report and self.kb:
            try:
                self.kb.store_knowledge(
                    question=f"Why was {stats.symbol} {d.status}?",
                    answer=json.dumps(d.report)[:2000],
                    topic="symbol_governance", subtopic=d.status,
                    priority=7, confidence=0.8, tags=["symbol_pause", stats.symbol],
                )
            except Exception as e:
                logger.debug(f"kb store failed: {e}")
            logger.info(f"[GOVERNOR] {stats.symbol} -> {d.status.upper()}: {d.reason}; "
                        f"worst strategies: {[w['strategy'] for w in d.report.get('worst_strategies',[])]}")
        return d

    def is_blocked(self, symbol: str) -> bool:
        return (self.status.get(symbol) or {}).get("status") in (PAUSED, FAILED)

    def snapshot(self) -> dict:
        return dict(self.status)
