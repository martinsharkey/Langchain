"""
PerformanceResearcher — proactive self-analysis of what's actually working.

The daily market researcher looks OUTWARD (news, macro). This looks INWARD: it
analyses the bot's own REAL trading outcomes and turns them into actionable,
recallable insights — which symbols/strategies/sessions/variants win, and where
the bot is bleeding. Runs on a cadence from the engine (cheap, DB-only, no LLM
required for the core stats; optional LLM summary).

Insights are written to the knowledge base so they persist and can be recalled by
the trading loop and future reflection.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from collections import defaultdict

from src import config
from src.utils.logger import get_logger

logger = get_logger("perf_researcher")


class PerformanceResearcher:
    def __init__(self, experience_db):
        self.experience_db = experience_db
        self.last_report: dict = {}

    def _closed(self):
        conn = sqlite3.connect(self.experience_db.db_path)
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(
            "SELECT symbol, action, strategy_used, strategy_combination, mgmt_variant, "
            "outcome, profit_loss, timestamp, market_regime "
            "FROM trades WHERE outcome IN ('win','loss','breakeven')"
        ).fetchall()]
        conn.close()
        return rows

    def analyze(self) -> dict:
        rows = self._closed()
        n = len(rows)
        report = {"generated_at": datetime.now(timezone.utc).isoformat(), "sample": n,
                  "findings": [], "best_symbol": None, "worst_symbol": None,
                  "best_variant": None, "recommendations": []}
        if n < 8:
            report["findings"].append(f"Insufficient sample ({n}) for reliable analysis.")
            self.last_report = report
            return report

        def agg(key):
            d = defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0})
            for r in rows:
                k = r.get(key) or "?"
                d[k]["n"] += 1
                d[k]["w"] += 1 if r["outcome"] == "win" else 0
                d[k]["pnl"] += r.get("profit_loss") or 0
            return {k: {"n": v["n"], "win_rate": round(v["w"]/v["n"]*100, 1),
                        "pnl": round(v["pnl"], 2)} for k, v in d.items()}

        by_symbol = agg("symbol")
        by_variant = agg("mgmt_variant")
        by_regime = agg("market_regime")
        by_action = agg("action")

        # rank symbols by pnl (min sample 4)
        ranked_sym = sorted([(k, v) for k, v in by_symbol.items() if v["n"] >= 4],
                            key=lambda x: x[1]["pnl"], reverse=True)
        if ranked_sym:
            report["best_symbol"] = {"symbol": ranked_sym[0][0], **ranked_sym[0][1]}
            report["worst_symbol"] = {"symbol": ranked_sym[-1][0], **ranked_sym[-1][1]}
        ranked_var = sorted([(k, v) for k, v in by_variant.items() if v["n"] >= 4],
                            key=lambda x: x[1]["pnl"], reverse=True)
        if ranked_var:
            report["best_variant"] = {"variant": ranked_var[0][0], **ranked_var[0][1]}

        report["by_symbol"] = by_symbol
        report["by_variant"] = by_variant
        report["by_regime"] = by_regime
        report["by_action"] = by_action

        # ── actionable recommendations ──
        recs = report["recommendations"]
        # direction imbalance
        buys = by_action.get("buy", {}).get("n", 0)
        sells = by_action.get("sell", {}).get("n", 0)
        if buys + sells >= 10 and (buys == 0 or sells == 0):
            recs.append(f"Direction one-sided ({buys} buys / {sells} sells) — check ensemble balance.")
        # worst symbol bleeding
        if report["worst_symbol"] and report["worst_symbol"]["pnl"] < -5:
            recs.append(f"{report['worst_symbol']['symbol']} is bleeding "
                        f"({report['worst_symbol']['pnl']}); consider reducing size or pausing.")
        # best variant should get more weight
        if report["best_variant"]:
            recs.append(f"Management variant '{report['best_variant']['variant']}' is best "
                        f"(pnl {report['best_variant']['pnl']}, WR {report['best_variant']['win_rate']}%).")
        # regime insight
        good_regimes = [k for k, v in by_regime.items() if v["n"] >= 4 and v["win_rate"] >= 50]
        bad_regimes = [k for k, v in by_regime.items() if v["n"] >= 4 and v["win_rate"] < 35]
        if good_regimes:
            recs.append(f"Best regimes: {good_regimes}. Favour trading these.")
        if bad_regimes:
            recs.append(f"Weak regimes: {bad_regimes}. Consider filtering these out.")

        report["findings"] = recs or ["No strong signal yet; keep gathering data."]
        self.last_report = report
        self._persist_to_knowledge(report)
        logger.info(f"Performance research: {len(recs)} recommendations from {n} trades. "
                    f"Best symbol: {report.get('best_symbol')}")
        return report

    def _persist_to_knowledge(self, report: dict):
        """Write insights to the knowledge base for recall (best-effort)."""
        try:
            from src.learning.knowledge_base import KnowledgeBase
            kb = KnowledgeBase()
            answer = " | ".join(report.get("findings", []))
            kb.store_knowledge(
                question="What is working in our live trading right now?",
                answer=answer[:2000],
                topic="self_performance", subtopic="live_analysis",
                priority=8, confidence=0.7,
                tags=["performance", "self_analysis"],
            )
        except Exception as e:
            logger.debug(f"perf knowledge persist skip: {e}")

    def status(self) -> dict:
        return self.last_report
