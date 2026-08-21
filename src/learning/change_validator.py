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
    def __init__(self, backtest_fn: Callable, knowledge_store=None, margin: float = 0.05,
                 learning_log=None):
        """backtest_fn(symbol, params, sl_atr, tp_rr) -> {score, generalizes, pfs, wrs, n_total}
        (the real walk-forward backtester). knowledge_store: RAG for outcome memory.
        learning_log: optional LearningLog to record validation outcomes."""
        self.backtest_fn = backtest_fn
        self.ks = knowledge_store
        self.margin = margin
        self.learning_log = learning_log
        try:
            from src import config
            self._path = os.path.join(config.DATA_DIR, "best_ever_scores.json")
        except Exception:
            self._path = os.path.join("data", "best_ever_scores.json")
        self._best = self._load()
        self._memo = {}   # per-run memo: (symbol, params-hash) -> result (avoid re-backtesting the same config)

    def _memo_key(self, symbol, params):
        import hashlib, json as _j
        from src.utils.symbols import symbol_base
        h = hashlib.md5(_j.dumps({k: params.get(k) for k in sorted(params)}, default=str).encode()).hexdigest()[:12]
        return f"{symbol_base(symbol)}:{h}"

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
        """Best-ever validated score, with TIME DECAY so an unbeaten high-water mark relaxes
        over time (prevents a fluke peak permanently freezing tuning). Decays toward 1.0 at
        ~0.02 PF/day unbeaten, floored at 1.0 (still must be profitable to pass)."""
        from src.utils.symbols import symbol_base
        sym = symbol_base(symbol)
        rec = self._best.get(sym, {})
        raw = float(rec.get("score", -1.0))
        if raw <= 1.0:
            return raw
        try:
            at = rec.get("at")
            if at:
                age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(at)).total_seconds() / 86400.0
                decayed = raw - 0.02 * max(0.0, age_days)
                return max(1.0, round(decayed, 3))
        except Exception:
            pass
        return raw

    def validate(self, symbol: str, params: dict, source: str = "?", min_trades: int = 40) -> dict:
        """Backtest+forward test `params`. Return {passed, score, forward_pf, best, reason}.
        A pass REQUIRES: generalizes, forward-window PF>=1, enough trades (min_trades so a
        thin fluke can't set the bar), and score beats the (time-decayed) best-ever+margin.
        
        Generalizes gate: all walk-forward windows must have PF >= 1.0. If the current
        best-known config fails this gate its score is treated as -1.0 (invalid) and
        the cold-start rule accepts the first generalizing candidate instead.
        
        Cold-start: if no valid best-ever exists for this symbol, the first generalizing
        candidate is accepted (its score becomes the new bar).
        
        Session-scoped proposals (params containing `session_*` keys) are judged on the
        relevant session's sub-score from `session_scores`, not the aggregate across all
        sessions.
        Records the outcome (pass OR fail) to the RAG. Never applies anything itself."""
        from src.utils.symbols import symbol_base
        sym = symbol_base(symbol)
        mk = self._memo_key(symbol, params)
        if mk in self._memo:
            return self._memo[mk]
        res = self.backtest_fn(symbol, params, params.get("sl_atr", 1.0), params.get("tp_rr", 2.0))
        if not res:
            out = {"passed": False, "score": None, "reason": "no backtest data (thin cache)"}
            self._remember(sym, params, out, source)
            self._memo[mk] = out
            return out
        score = res.get("score", -1.0)
        pfs = res.get("pfs") or []
        forward_pf = pfs[-1] if pfs else 0.0   # last chronological window = forward/OOS
        generalizes = bool(res.get("generalizes"))
        n_total = res.get("n_total") or 0
        best = self.best_score(sym)
        enough = n_total >= min_trades
        session_scores = res.get("session_scores") or {}

        # ── Session-scored proposal: judge on the affected session's sub-score ──
        session_overrides = {k: v for k, v in params.items() if k.startswith("session_")}
        if session_overrides:
            sess_names = []
            for k, v in session_overrides.items():
                sess_name = k[len("session_"):].lower()
                for s in session_scores:
                    if s.lower() == sess_name:
                        sess_names.append(s)
                        break
            if sess_names:
                # Use the FIRST matched session's PF as the session-specific score.
                # If multiple sessions are overridden, each would need its own validate()
                # call in a future loop; here we gate on the primary session.
                primary_sess = sess_names[0]
                sess_data = session_scores[primary_sess]
                sess_pf = sess_data.get("pf", 0.0)
                sess_wr = sess_data.get("wr", 0.0)
                sess_trades = sess_data.get("trades", 0)
                # For session-scoped proposals, the session's overall PF replaces
                # the aggregate forward_pf and score for the gate decision.
                forward_pf = sess_pf
                score = sess_pf
                enough = sess_trades >= min_trades
                if not generalizes:
                    reason = f"session {primary_sess} PF {sess_pf:.2f} < 1 (does not generalize)"
                elif sess_pf < 1.0:
                    reason = f"session {primary_sess} PF {sess_pf:.2f} < 1"
                elif sess_trades < min_trades:
                    reason = f"session {primary_sess} only {sess_trades} trades (<{min_trades})"
                else:
                    reason = ""
                if reason:
                    out = {"passed": False, "score": round(score, 3), "forward_pf": round(forward_pf, 2),
                           "generalizes": generalizes, "best_ever": round(best, 3),
                           "n_total": sess_trades, "reason": reason,
                           "session_scores": session_scores,
                           "session_primary": primary_sess}
                    self._remember(sym, params, out, source)
                    self._memo[mk] = out
                    logger.warning(f"[VALIDATE] {sym} ({source}, session={primary_sess}): REJECT "
                                   f"score {out.get('score')} sessPF {sess_pf:.2f} vs best {best:.2f} — {reason}")
                    if self.learning_log:
                        self.learning_log.validate(sym, source, False, out.get("score", -1.0),
                                                   out.get("forward_pf", 0.0), reason, out.get("n_total", 0))
                    return out

        # ── Cold-start: no valid best-ever → accept first generalizing candidate ──
        cold_start = best <= 0.0
        if cold_start and generalizes and enough and forward_pf >= 1.0:
            out = {"passed": True, "score": round(score, 3), "forward_pf": round(forward_pf, 2),
                   "generalizes": generalizes, "best_ever": round(best, 3),
                   "n_total": n_total, "reason": "cold-start accept (no valid incumbent)",
                   "session_scores": session_scores}
            if session_overrides and sess_names:
                out["session_primary"] = sess_names[0]
            self._best[sym] = {"score": round(score, 3), "source": source,
                               "at": datetime.now(timezone.utc).isoformat(),
                               "params": {k: v for k, v in params.items() if not k.startswith("_")}}
            self._save()
            self._remember(sym, params, out, source)
            self._memo[mk] = out
            logger.warning(f"[VALIDATE] {sym} ({source}): PASS (cold-start) "
                           f"score {out.get('score')} fwdPF {out.get('forward_pf')} — {out['reason']}")
            if self.learning_log:
                self.learning_log.validate(sym, source, True, out.get("score", -1.0),
                                           out.get("forward_pf", 0.0), out["reason"], out.get("n_total", 0))
            return out

        best = self.best_score(sym)
        passed = generalizes and forward_pf >= 1.0 and enough and score > best + self.margin
        reason = ("beats best-ever" if passed else
                  "does not generalize" if not generalizes else
                  f"forward PF {forward_pf:.2f} < 1" if forward_pf < 1.0 else
                  f"only {n_total} trades (<{min_trades})" if not enough else
                  f"score {score:.2f} <= best-ever {best:.2f}+{self.margin}")
        out = {"passed": passed, "score": round(score, 3), "forward_pf": round(forward_pf, 2),
               "generalizes": generalizes, "best_ever": round(best, 3),
               "n_total": res.get("n_total"), "reason": reason,
               "session_scores": session_scores}
        if session_overrides and sess_names:
            out["session_primary"] = sess_names[0]
        if passed:
            self._best[sym] = {"score": round(score, 3), "source": source,
                               "at": datetime.now(timezone.utc).isoformat(),
                               "params": {k: v for k, v in params.items() if not k.startswith("_")}}
            self._save()
        self._remember(sym, params, out, source)
        self._memo[mk] = out
        logger.warning(f"[VALIDATE] {sym} ({source}): {'PASS' if passed else 'REJECT'} "
                       f"score {out.get('score')} fwdPF {out.get('forward_pf')} vs best {out['best_ever']} — {reason}")
        sess_scores = out.get("session_scores")
        if sess_scores:
            logger.info(f"[VALIDATE] {sym} ({source}): session_scores={sess_scores}")
        if self.learning_log:
            self.learning_log.validate(sym, source, passed, out.get("score", -1.0),
                                       out.get("forward_pf", 0.0), reason, out.get("n_total", 0))
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
