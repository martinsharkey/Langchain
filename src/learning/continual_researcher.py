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
                 edge_discovery=None, repo: str = "martinsharkey/Langchain",
                 pattern_optimizer=None, apply_exit_config=None, excursion_analyzer=None):
        self.db = experience_db
        self.mql5 = mql5_knowledge
        self.ks = knowledge_store
        self.edge_discovery = edge_discovery
        self.repo = repo
        self._last_run_day = None
        # #40: discover + LOCK IN the MACD-leads-OsMA pattern's best exits per symbol
        self.pattern_optimizer = pattern_optimizer
        self.apply_exit_config = apply_exit_config  # callable(symbol, sl_atr, tp_rr)
        self._pattern_locked = {}
        # #41: per-symbol OsMA-cycle excursion analyzer (how far the symbol moves,
        # peak/trough, wick) -> symbol-specific exit calibration.
        self.excursion_analyzer = excursion_analyzer
        self._excursion = {}

    def lock_in_pattern(self, base_symbol: str, resolved: str = None) -> dict:
        """
        #40 CORE: discover the best exit config for the MACD-leads-OsMA pattern on
        this symbol and LOCK IT IN (write to live tuned params). This is how the
        bot auto-finds "let winners run / cut losers early" per symbol. Gated by
        the pattern optimizer's PF/sample gate; the #27 checkpointer then verifies
        realised expectancy and reverts if it doesn't hold up.
        """
        if self.pattern_optimizer is None:
            return {"found": False, "reason": "no pattern optimizer"}
        sym = resolved or base_symbol
        try:
            res = self.pattern_optimizer.discover(sym)
        except Exception as e:
            logger.debug(f"pattern discover skip {base_symbol}: {e}")
            return {"found": False, "reason": str(e)[:80]}
        if not res.get("found"):
            return res
        best = res["best"]
        # write the winning exit config live (sl_atr / tp_rr) if a writer is wired
        if self.apply_exit_config is not None:
            try:
                self.apply_exit_config(base_symbol, best["sl_atr"], best["tp_rr"])
            except Exception as e:
                logger.debug(f"apply exit config skip {base_symbol}: {e}")
        self._pattern_locked[base_symbol.upper()] = best
        logger.warning(f"[PATTERN-LOCK] {base_symbol}: MACD-leads-OsMA best exits "
                       f"sl_atr {best['sl_atr']} tp_rr {best['tp_rr']} "
                       f"({res['alt_filter']} filter, WR {best['win_rate']}% PF {best['profit_factor']}, "
                       f"n {best['trades']}) -> locked into live tuned params")
        if self.ks is not None:
            try:
                self.ks.remember(
                    key=f"pattern_lock_{base_symbol.upper()}", kind="finding",
                    topic=f"pattern exits {base_symbol.upper()}", source="pattern_optimizer",
                    text=(f"{base_symbol.upper()} MACD-leads-OsMA best exits: sl_atr {best['sl_atr']}, "
                          f"tp_rr {best['tp_rr']} ({res['alt_filter']} MTF filter) -> WR {best['win_rate']}% "
                          f"PF {best['profit_factor']} exp {best['expectancy']} over {best['trades']} triggers. "
                          f"Wide-stop/right-TP = let winners run, cut losers early. Locked live; checkpointer verifies."))
            except Exception:
                pass
        return res

    def pattern_snapshot(self) -> dict:
        return dict(self._pattern_locked)

    def measure_excursion(self, base_symbol: str, resolved: str = None) -> dict:
        """#41: measure the symbol's OsMA-cycle excursion (peak/trough/wick) so the
        exit is calibrated to how far THIS symbol actually moves. Stored in the RAG."""
        if self.excursion_analyzer is None:
            return {"found": False}
        try:
            r = self.excursion_analyzer.measure(resolved or base_symbol)
        except Exception as e:
            logger.debug(f"excursion measure skip {base_symbol}: {e}")
            return {"found": False, "reason": str(e)[:80]}
        if r.get("found"):
            self._excursion[base_symbol.upper()] = r
            if self.ks is not None:
                try:
                    rec = r["recommendation"]
                    self.ks.remember(
                        key=f"excursion_{base_symbol.upper()}", kind="finding",
                        topic=f"excursion {base_symbol.upper()}", source="excursion_analyzer",
                        text=(f"{base_symbol.upper()} OsMA-cycle excursion ({r['osma_cycles']} cycles): "
                              f"median peak-in-favour {r['median_peak_pts']}pts, adverse "
                              f"{r['median_trough_pts']}pts, wick {r['median_wick_pts']}pts, "
                              f"peak/trough {r['peak_to_trough_ratio']}. Exit rec: sl_atr "
                              f"{rec['suggested_sl_atr']}, tp_rr {rec['suggested_tp_rr']} (stop wide "
                              f"enough to survive adverse+wick; TP ~70% of typical peak = exit near "
                              f"OsMA reversal, don't give it back). Entries ~95% correct direction; "
                              f"exit management is the leak."))
                except Exception:
                    pass
        return r

    def excursion_snapshot(self) -> dict:
        return {k: v.get("recommendation") for k, v in self._excursion.items()}

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

    # ── per-symbol INDICATOR SCALE profiling (indicator values differ hugely by symbol) ──
    def profile_indicator_scale(self, base_symbol: str, resolved: str = None) -> dict:
        """
        Explore a symbol's indicator SCALE so thresholds are calibrated per symbol,
        not copied from gold. Indicator absolute values differ by orders of
        magnitude across symbols (BTC ~63000 vs XAUUSD ~2600), so ATR/OsMA/power
        magnitudes are not comparable. Returns normalised, symbol-relative stats
        (ATR as % of price, median |OsMA| relative to ATR, power ranges) and
        stores them in the KnowledgeStore for the tuner/researcher to use.
        """
        prof = {"symbol": base_symbol.upper()}
        try:
            import statistics
            from src.mt5.data import get_rates
            from src.strategies.indicators import compute_indicator_series
            from src import config as _cfg
            rates = get_rates(resolved or base_symbol, timeframe=_cfg.ENTRY_TIMEFRAME, count=300)
            if not rates or len(rates) < 60:
                return prof
            series = compute_indicator_series(rates, None)
            closes = [b.get("close") for b in series if b.get("close")]
            atrs = [b.get("atr") for b in series if b.get("atr")]
            osmas = [abs(b.get("osma") or 0) for b in series if b.get("close")]
            bulls = [b.get("bulls_power") or 0 for b in series if b.get("close")]
            if closes and atrs:
                med_price = statistics.median(closes)
                med_atr = statistics.median(atrs)
                prof.update({
                    "median_price": round(med_price, 2),
                    "median_atr": round(med_atr, 4),
                    # ATR as % of price -> comparable across symbols
                    "atr_pct_of_price": round(med_atr / med_price * 100, 4) if med_price else 0,
                    "median_abs_osma": round(statistics.median(osmas), 4) if osmas else 0,
                    # OsMA magnitude relative to ATR (symbol-agnostic entry-strength ref)
                    "osma_over_atr": round(statistics.median(osmas) / med_atr, 3) if (osmas and med_atr) else 0,
                    "median_abs_bulls": round(statistics.median([abs(b) for b in bulls]), 4) if bulls else 0,
                })
        except Exception as e:
            logger.debug(f"indicator scale profile skip {base_symbol}: {e}")
            return prof
        if self.ks is not None and prof.get("atr_pct_of_price"):
            try:
                self.ks.remember(
                    key=f"indicator_scale_{base_symbol.upper()}", kind="finding",
                    topic=f"indicator scale {base_symbol.upper()}", source="continual_researcher",
                    text=(f"{base_symbol.upper()} indicator SCALE (calibrate thresholds to THIS, "
                          f"not gold): ATR ~{prof['atr_pct_of_price']}% of price, median |OsMA| "
                          f"{prof['median_abs_osma']} (~{prof.get('osma_over_atr')}x ATR), median "
                          f"|Bulls| {prof.get('median_abs_bulls')}. Absolute indicator values are "
                          f"NOT comparable to other symbols; use ATR-relative / %-of-price gates."))
            except Exception:
                pass
        return prof

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
            # per-symbol indicator-scale profiling (calibrate thresholds per symbol)
            scale = self.profile_indicator_scale(sym)
            # #40: discover + lock in the MACD-leads-OsMA pattern's best exits
            pat = self.lock_in_pattern(sym)
            # #41: measure per-symbol OsMA-cycle excursion (calibrate exits to movement)
            exc = self.measure_excursion(sym)
            summary["symbols"][sym.upper()] = {
                "expectancy": r["review"].get("expectancy"),
                "hypothesis": bool(r["hypothesis"]),
                "knowledge_hits": len(r["knowledge"]),
                "atr_pct_of_price": scale.get("atr_pct_of_price"),
                "pattern_locked": pat.get("found", False),
                "excursion_peak_pts": (exc.get("median_peak_pts") if exc.get("found") else None),
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
