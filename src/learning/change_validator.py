"""
ChangeValidator — the SINGLE enforced gate every live parameter change must pass.

Principle (no open loops): before ANY parameter change goes live it must PROVE, via a
walk-forward backtest + forward test on real data, that it beats ALL past results for that
symbol (a persisted best-ever high-water mark). If it doesn't beat the best, it is REJECTED
and the bot keeps the incumbent / tries something different. EVERY outcome — pass or fail —
is written to the RAG so the researcher knows what worked and what produced a bad backtest/
forward test, and won't blindly re-try it.

Score = walk-forward min-PF across windows; the LAST window is the forward (out-of-sample)
leg. A change must (a) generalize (all windows PF>=1), (b) forward PF>=1, and (c) beat the
symbol's best-ever validated score by a margin.
"""
from __future__ import annotations
import os, json, time
from datetime import datetime, timezone
from typing import Callable, Optional

from src.utils.logger import get_logger

logger = get_logger("change_validator")


class ChangeValidator:
    def __init__(self, backtest_fn: Callable, knowledge_store=None, margin: float = 0.05):
        """backtest_fn(symbol, params, sl_atr, tp_rr) -> {score, generalizes, pfs, wrs, n_total}
        (the real walk-forward backtester). knowledge_store: RAG for outcome memory."""
        self.backtest_fn = backtest_fn
        self.ks = knowledge_store
        self.margin = margin
        try:
            from src import config
            self._path = os.path.join(config.DATA_DIR, "best_ever_scores.json")
        except Exception:
            self._path = os.path.join("data", "best_ever_scores.json")
        self._best = self._load()

    def _load(self) -> dict:
        try:
            if os.path.exists(self._path):
                return json.load(open(self._path))
        except Exception:
            pass
        return {}

    def _save(self):
        try:
            tmp = self._path + ".tmp"
            json.dump(self._best, open(tmp, "w"), indent=1)
            os.replace(tmp, self._path)
        except Exception:
            pass

    def best_score(self, symbol: str) -> float:
        return float(self._best.get(symbol.upper().split("-")[0], {}).get("score", -1.0))

    def validate(self, symbol: str, params: dict, source: str = "?") -> dict:
        """Backtest+forward test `params`. Return {passed, score, forward_pf, best, reason}.
        A pass REQUIRES: generalizes, forward-window PF>=1, and score beats best-ever+margin.
        Records the outcome (pass OR fail) to the RAG. Never applies anything itself."""
        sym = symbol.upper().split("-")[0]
        res = self.backtest_fn(symbol, params, params.get("sl_atr", 1.0), params.get("tp_rr", 2.0))
        if not res:
            out = {"passed": False, "score": None, "reason": "no backtest data (thin cache)"}
            self._remember(sym, params, out, source)
            return out
        score = res.get("score", -1.0)
        pfs = res.get("pfs") or []
        forward_pf = pfs[-1] if pfs else 0.0   # last chronological window = forward/OOS
        generalizes = bool(res.get("generalizes"))
        best = self.best_score(sym)
        passed = generalizes and forward_pf >= 1.0 and score > best + self.margin
        reason = ("beats best-ever" if passed else
                  "does not generalize" if not generalizes else
                  f"forward PF {forward_pf:.2f} < 1" if forward_pf < 1.0 else
                  f"score {score:.2f} <= best-ever {best:.2f}+{self.margin}")
        out = {"passed": passed, "score": round(score, 3), "forward_pf": round(forward_pf, 2),
               "generalizes": generalizes, "best_ever": round(best, 3),
               "n_total": res.get("n_total"), "reason": reason}
        if passed:
            self._best[sym] = {"score": round(score, 3), "source": source,
                               "at": datetime.now(timezone.utc).isoformat(),
                               "params": {k: v for k, v in params.items() if not k.startswith("_")}}
            self._save()
        self._remember(sym, params, out, source)
        logger.warning(f"[VALIDATE] {sym} ({source}): {'PASS' if passed else 'REJECT'} "
                       f"score {out.get('score')} fwdPF {out.get('forward_pf')} vs best {out['best_ever']} — {reason}")
        return out

    def _remember(self, sym, params, out, source):
        """Feed EVERY validation outcome (good AND bad) to the RAG so the researcher learns
        what worked / what produced a bad backtest+forward, and won't blindly re-try it."""
        if self.ks is None:
            return
        try:
            key_bits = {k: params.get(k) for k in ("osma_min_long", "bulls_min_long", "dom_min",
                                                   "runway_min", "atr_min", "sl_atr", "tp_rr")
                        if k in params}
            verdict = "PASSED (new best)" if out.get("passed") else "REJECTED"
            self.ks.remember(
                key=f"validation_{sym}", kind="finding", topic=f"param validation {sym}",
                source="change_validator", accumulate=True,
                text=(f"{verdict} [{source}] {sym}: score {out.get('score')} forwardPF "
                      f"{out.get('forward_pf')} vs best-ever {out.get('best_ever')} — {out.get('reason')}. "
                      f"params {key_bits}. {'Adopt.' if out.get('passed') else 'Do not re-try this direction; try something different.'}"))
        except Exception as e:
            logger.debug(f"validation remember skip: {e}")
