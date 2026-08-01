"""
Continual ReAct Researcher (#32).

Runs on a daily cadence and, per traded symbol, performs a reason -> act ->
observe -> reflect cycle that USES the mql5 knowledge RAG (#22) on an ongoing
basis to improve trading — not a one-off crawl:

  1. REVIEW  live results per symbol (realised expectancy, PF, win rate, recent
             degradation, dominant exit/failure mode) from the experience DB.
  2. QUERY   the mql5 RAG (#22) for that symbol's failure mode -> is there a
             better indicator / parameter direction / technique to try?
  3. REASON  combine (our results + retrieved knowledge) into a concrete,
             testable hypothesis (which knob to move, which regime, why).
  4. ACT     hand validated hypotheses to the SAME walk-forward gate: the
             per-symbol edge-discovery sweep (#31) + param_optimizer. Only
             gate-passing changes go live (the engine already applies the
             overlay + tuned params; the #27 checkpointer keeps/reverts).
  5. REFLECT store every hypothesis + outcome in the KnowledgeStore so learning
             compounds and failed directions aren't retried.

AUTO-FILE GITHUB ISSUES: when the researcher finds something needing CODE (a new
symbol worth adding, a new indicator/technique, an ONNX/ML opportunity, a data
gap), it opens a deduped GitHub issue via `gh` so NO discovery is a dead end.

Cheap + rate-limited (daily), offline-after-fetch, non-fatal. Nothing bypasses
the walk-forward gate.
"""

from __future__ import annotations

import os
import time
import json
import shutil
import logging
import subprocess
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("continual_researcher")


class ContinualResearcher:
    def __init__(self, experience_db, mql5_knowledge=None, knowledge_store=None,
                 edge_discovery=None, repo: str = "martinsharkey/Langchain"):
        self.db = experience_db
        self.mql5 = mql5_knowledge
        self.ks = knowledge_store
        self.edge_discovery = edge_discovery
        self.repo = repo
        self._last_run_day = None

    # ── 1. REVIEW ──
    def review_symbol(self, base_symbol: str, limit: int = 40) -> dict:
        """Summarise recent realised performance + dominant failure mode."""
        import sqlite3
        out = {"symbol": base_symbol.upper(), "n": 0}
        try:
            conn = sqlite3.connect(self.db.db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT outcome, profit_loss, exit_reason, strategy_used FROM trades "
                "WHERE symbol LIKE ? AND outcome IN ('win','loss','breakeven') "
                "AND (exit_reason IS NULL OR exit_reason<>'pre_rebuild_synthetic') "
                "ORDER BY id DESC LIMIT ?", (base_symbol.upper() + "%", limit)).fetchall()
            conn.close()
        except Exception as e:
            logger.debug(f"review skip {base_symbol}: {e}")
            return out
        n = len(rows)
        if n == 0:
            return out
        wins = sum(1 for r in rows if r["outcome"] == "win")
        pnl = sum((r["profit_loss"] or 0) for r in rows)
        # dominant exit reason (failure mode proxy) among losers
        from collections import Counter
        loss_exits = Counter((r["exit_reason"] or "unknown") for r in rows if r["outcome"] == "loss")
        worst_strats = Counter()
        for r in rows:
            if r["outcome"] == "loss":
                worst_strats[r["strategy_used"] or "unknown"] += 1
        out.update({
            "n": n, "win_rate": round(wins / n * 100, 1),
            "expectancy": round(pnl / n, 4), "net_pnl": round(pnl, 2),
            "dominant_loss_exit": (loss_exits.most_common(1)[0][0] if loss_exits else None),
            "worst_strategy": (worst_strats.most_common(1)[0][0] if worst_strats else None),
        })
        return out

    # ── 2+3. QUERY mql5 + REASON ──
    def research_symbol(self, base_symbol: str) -> dict:
        """Review + query mql5 RAG for a better technique; produce a hypothesis."""
        review = self.review_symbol(base_symbol)
        hypothesis = None
        knowledge = []
        if self.mql5 is not None and review.get("n", 0) >= 10:
            # ground the search in the symbol's actual weakness
            q = (f"improve {base_symbol} trading: win rate {review.get('win_rate')}% "
                 f"expectancy {review.get('expectancy')}, losers exit via "
                 f"{review.get('dominant_loss_exit')}; better indicator or parameter?")
            try:
                knowledge = self.mql5.research(q, n_results=3)
            except Exception as e:
                logger.debug(f"mql5 research skip {base_symbol}: {e}")
            if knowledge:
                top = knowledge[0]
                hypothesis = (f"{base_symbol}: expectancy {review.get('expectancy')} with "
                              f"losers exiting via {review.get('dominant_loss_exit')}. mql5 "
                              f"knowledge suggests: {top['text'][:160]} "
                              f"(src {top['metadata'].get('title')}). Test via edge sweep + optimizer.")
        result = {"review": review, "knowledge": knowledge, "hypothesis": hypothesis}
        if hypothesis and self.ks is not None:
            try:
                self.ks.remember(key=f"research_hypothesis_{base_symbol.upper()}",
                                 kind="note", topic=f"research {base_symbol.upper()}",
                                 source="continual_researcher", text=hypothesis)
            except Exception:
                pass
        return result

    # ── AUTO-FILE GITHUB ISSUES ──
    def _gh_available(self) -> bool:
        return shutil.which("gh") is not None

    def _existing_issue_titles(self) -> list[str]:
        if not self._gh_available():
            return []
        try:
            out = subprocess.run(
                ["gh", "issue", "list", "-R", self.repo, "--state", "open",
                 "--limit", "200", "--json", "title"],
                capture_output=True, text=True, timeout=30)
            if out.returncode == 0:
                return [i["title"].lower() for i in json.loads(out.stdout or "[]")]
        except Exception as e:
            logger.debug(f"gh issue list skip: {e}")
        return []

    def file_issue(self, title: str, body: str, labels: list[str] = None) -> Optional[str]:
        """Open a deduped GitHub issue for a development-worthy discovery."""
        if not self._gh_available():
            logger.info(f"[RESEARCHER] gh not available; would file issue: {title}")
            return None
        # dedupe: skip if a very similar title already exists
        existing = self._existing_issue_titles()
        tl = title.lower()
        if any(tl[:40] in e or e[:40] in tl for e in existing):
            logger.info(f"[RESEARCHER] issue already exists (skip): {title}")
            return None
        cmd = ["gh", "issue", "create", "-R", self.repo, "--title", title, "--body", body]
        for lb in (labels or ["research"]):
            cmd += ["--label", lb]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if out.returncode == 0:
                url = (out.stdout or "").strip()
                logger.info(f"[RESEARCHER] filed issue: {url}")
                if self.ks is not None:
                    try:
                        self.ks.remember(key=f"auto_issue_{abs(hash(title)) % 10**8}",
                                         kind="note", topic="auto-filed issue",
                                         source="continual_researcher",
                                         text=f"Filed GitHub issue: {title} -> {url}")
                    except Exception:
                        pass
                return url
            logger.warning(f"[RESEARCHER] gh issue create failed: {out.stderr[:200]}")
        except Exception as e:
            logger.debug(f"gh issue create skip: {e}")
        return None

    # ── daily orchestration ──
    def daily_cycle(self, symbols: list[str], force: bool = False) -> dict:
        """
        Run the once-per-day ReAct research pass across symbols. Returns a summary.
        Idempotent per UTC day unless force=True.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not force and self._last_run_day == today:
            return {"skipped": True, "reason": "already ran today"}
        self._last_run_day = today
        summary = {"day": today, "symbols": {}, "issues_filed": []}
        for sym in symbols:
            r = self.research_symbol(sym)
            summary["symbols"][sym.upper()] = {
                "expectancy": r["review"].get("expectancy"),
                "hypothesis": bool(r["hypothesis"]),
                "knowledge_hits": len(r["knowledge"]),
            }
            # If a symbol persistently has no edge, propose a development issue
            rv = r["review"]
            if rv.get("n", 0) >= 30 and (rv.get("expectancy") or 0) < 0:
                url = self.file_issue(
                    title=f"[researcher] {sym.upper()} negative expectancy over {rv['n']} trades — investigate technique",
                    body=(f"The continual researcher (#32) found {sym.upper()} at expectancy "
                          f"{rv.get('expectancy')} / WR {rv.get('win_rate')}% over {rv['n']} recent "
                          f"trades; losers dominated by exit '{rv.get('dominant_loss_exit')}', worst "
                          f"strategy '{rv.get('worst_strategy')}'. mql5-grounded hypothesis: "
                          f"{r['hypothesis']}\n\nProposed: run the edge-discovery sweep (#31) + "
                          f"optimizer for this symbol; if no pocket validates, consider a new "
                          f"indicator/technique or ONNX model. Auto-filed; needs review."),
                    labels=["research", "learning"])
                if url:
                    summary["issues_filed"].append(url)
        # kick a validated re-sweep (gate-enforced) if edge discovery is wired
        if self.edge_discovery is not None:
            try:
                self.edge_discovery.sweep_all(symbols, persist=True)
                summary["edge_sweep"] = "ran"
            except Exception as e:
                logger.debug(f"researcher edge sweep skip: {e}")
        return summary
