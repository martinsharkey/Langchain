"""
Decision Alignment Tracker
==========================

Fast, self-validating feedback loop for the LLM trade supervisor's questions.

The trade supervisor (`langgraph_trade_supervisor.py`) asks the LLM a directional
question on every OPEN position and gets back ONE token: HOLD / TIGHTEN / EXIT /
CUT_ALL / ADD_LEG. This module answers the only question that matters:

    "Did the LLM's answer align with what the trade actually did?"

It does this WITHOUT any RAG, embeddings, or extra LLM calls — purely by
correlating each captured decision (with the profit/MFE/MAE context at the moment
it was made) against the trade's realised outcome at close. A rolling per-decision
hit-rate is persisted so the researcher can see whether a given question is
producing correct outcomes, and refine it when alignment drops.

Scoring rules (deliberately simple + testable):
  * HOLD      correct if the trade did NOT immediately reverse into a worse loss —
              i.e. final profit >= profit-at-decision OR the trade still ran
              favourably afterwards (final MFE > profit at decision).
  * TIGHTEN   correct if it locked in profit before a reversal — the trade was in
              profit at the call AND gave back a meaningful chunk afterwards
              (peak MFE well above final), so tightening protected gains.
  * EXIT /    correct if leaving was better than staying — the trade was closed at
  * CUT_ALL   >= the profit at the decision (didn't sacrifice a runner), OR it was
              a losing/near-zero trade where exiting avoided a deeper MAE.

This is READ-ONLY with respect to trading: it never blocks or alters orders.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("decision_alignment")

_VALID = ("HOLD", "TIGHTEN", "EXIT", "CUT_ALL", "ADD_LEG")


class DecisionAlignmentTracker:
    """Captures supervisor decisions and scores them against trade outcomes.

    Storage layout (data/llm_decision_scores.json):
    {
      "pending": { "<ticket>": [ {decision, profit_pts, ts, reason, symbol}, ... ] },
      "scores":  { "HOLD": {"n": int, "correct": int}, "EXIT": {...}, ... },
      "recent":  [ {ticket, decision, aligned, final_pnl, ...}, ... ]  # last 200
    }
    """

    def __init__(self, path: Optional[str] = None):
        if path is None:
            from src import config
            base = getattr(config, "DATA_DIR", None) or os.path.join(os.getcwd(), "data")
            path = os.path.join(base, "llm_decision_scores.json")
        self.path = path
        self._lock = threading.Lock()
        self._state = self._load()

    # ── persistence ──
    def _load(self) -> dict:
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    s = json.load(f)
                s.setdefault("pending", {})
                s.setdefault("scores", {})
                s.setdefault("recent", [])
                return s
        except Exception as e:
            logger.debug(f"load scores failed ({e}); starting fresh")
        return {"pending": {}, "scores": {}, "recent": []}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)
            os.replace(tmp, self.path)
        except Exception as e:
            logger.debug(f"save scores failed: {e}")

    # ── 1) CAPTURE — called at the moment the supervisor makes a decision ──
    def record_decision(self, ticket: int, decision: str, profit_pts: float,
                         symbol: str = "", reason: str = "", n_legs: int = 1) -> None:
        """Stash one supervisor decision with the profit context at that instant.
        Only decisions that came from the LLM (reason contains 'llm') are scored;
        rules-only/default fallbacks are recorded but flagged so they don't pollute
        the LLM's own hit-rate."""
        decision = (decision or "").upper()
        if decision not in _VALID:
            return
        try:
            with self._lock:
                key = str(ticket)
                self._state["pending"].setdefault(key, []).append({
                    "decision": decision,
                    "profit_pts": round(float(profit_pts), 1),
                    "ts": time.time(),
                    "symbol": symbol,
                    "reason": reason,
                    "n_legs": n_legs,
                    "from_llm": "llm" in (reason or "").lower(),
                })
                self._save()
        except Exception as e:
            logger.debug(f"record_decision skip: {e}")

    # ── 2) SCORE — called at trade close in _reconcile_closed ──
    def score_trade(self, ticket: int, final_pnl: float, final_profit_pts: Optional[float],
                    mfe_pts: Optional[float], mae_pts: Optional[float]) -> None:
        """Score every captured decision for this ticket against the realised
        outcome, update rolling per-decision hit-rates, and log the alignment."""
        try:
            with self._lock:
                key = str(ticket)
                decisions = self._state["pending"].pop(key, [])
                if not decisions:
                    self._save()
                    return

                fp = final_profit_pts if final_profit_pts is not None else 0.0
                peak = mfe_pts if mfe_pts is not None else fp
                worst = mae_pts if mae_pts is not None else min(fp, 0.0)

                for d in decisions:
                    aligned = self._judge(d["decision"], d["profit_pts"], fp, peak, worst)
                    # Only LLM-authored decisions count toward the LLM hit-rate.
                    if d.get("from_llm"):
                        sc = self._state["scores"].setdefault(
                            d["decision"], {"n": 0, "correct": 0})
                        sc["n"] += 1
                        if aligned:
                            sc["correct"] += 1
                    self._state["recent"].append({
                        "ticket": ticket, "symbol": d.get("symbol"),
                        "decision": d["decision"], "from_llm": d.get("from_llm"),
                        "profit_at_call_pts": d["profit_pts"],
                        "final_profit_pts": round(fp, 1), "final_pnl": round(final_pnl, 2),
                        "peak_pts": round(peak, 1), "worst_pts": round(worst, 1),
                        "aligned": aligned, "ts": time.time(),
                    })
                # keep the recent list bounded
                self._state["recent"] = self._state["recent"][-200:]
                self._save()

                # log a compact alignment summary for this trade
                llm_ds = [d for d in decisions if d.get("from_llm")]
                if llm_ds:
                    summary = ", ".join(
                        f"{d['decision']}@{d['profit_pts']:.0f}pts"
                        f"->{'OK' if self._judge(d['decision'], d['profit_pts'], fp, peak, worst) else 'MISS'}"
                        for d in llm_ds)
                    logger.info(
                        f"[ALIGN] #{ticket} {llm_ds[0].get('symbol')}: final {fp:.0f}pts "
                        f"(peak {peak:.0f}/worst {worst:.0f}) | LLM decisions: {summary}")
        except Exception as e:
            logger.debug(f"score_trade skip: {e}")

    def _judge(self, decision: str, at_call: float, final: float,
               peak: float, worst: float) -> bool:
        """Return True if the decision aligned with the realised outcome."""
        if decision == "HOLD":
            # Holding was right if the trade didn't reverse into a worse position:
            # it ended at least as profitable as when we held, OR it kept running up.
            return final >= at_call or peak > at_call + 1e-9
        if decision in ("EXIT", "CUT_ALL"):
            # Exiting was right if we didn't abandon a bigger runner (we left at
            # roughly the final level) OR it was a loser where leaving cut the loss.
            if at_call <= 0:
                return True  # cutting a losing/flat trade is defensively correct
            return final <= at_call + 1e-9
        if decision == "TIGHTEN":
            # Tightening was right if in profit AND price later gave back a chunk
            # from the peak (so protecting gains mattered).
            return at_call > 0 and peak > final + max(1.0, 0.2 * abs(peak))
        if decision == "ADD_LEG":
            # Adding was right if the trade continued in our favour after.
            return final >= at_call
        return True

    # ── 3) READ — for the researcher / prompt feedback ──
    def hit_rates(self) -> dict:
        """Return {decision: {n, correct, rate}} for LLM-authored decisions."""
        with self._lock:
            out = {}
            for k, v in self._state.get("scores", {}).items():
                n = v.get("n", 0)
                out[k] = {"n": n, "correct": v.get("correct", 0),
                          "rate": round(v.get("correct", 0) / n, 3) if n else None}
            return out

    def summary_text(self) -> str:
        """One-line human/LLM-readable summary of decision alignment."""
        hr = self.hit_rates()
        if not hr:
            return "no LLM decisions scored yet"
        parts = [f"{k} {v['correct']}/{v['n']} ({int(v['rate']*100)}%)"
                 for k, v in sorted(hr.items()) if v["rate"] is not None]
        return "; ".join(parts) if parts else "no scored decisions yet"
